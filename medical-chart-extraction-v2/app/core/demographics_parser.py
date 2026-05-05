"""
Patient Demographics Parser
Uses regex + rule-based patterns + LLM fallback to extract structured demographics.

v3 CHANGES:
  - MRN validation: length constraint (4-15 chars) + alphanumeric-only check
  - DOB two-digit year fix: if parsed year > current year, subtract 100
  - Name: added middle-name support and suffix stripping (Jr., Sr., III, PhD)
  - Phone: normalize output to (NNN) NNN-NNNN format
  - LLM fallback (_llm_extract_demographics): called only for fields that remain
    None after all regex passes — keeps cost minimal
  - Validation layer (_validate_demographics): cross-checks DOB/age consistency,
    flags impossible values, returns warnings list alongside result
"""
import re
from datetime import datetime, date
from typing import Optional, Tuple, List, Dict, Any
from app.models.schemas import PatientDemographics

# ── Patterns ──────────────────────────────────────────────────────────────────

_PATTERNS = {
    "patient_name": [
        # Title Case with optional middle name and suffix
        r"(?:Patient\s*(?:Name)?|Name)[:\s]+([A-Z][a-z]+(?:[\s\-'][A-Za-z]+){1,4})"
        r"(?:\s*(?:Jr\.?|Sr\.?|II|III|IV|PhD|MD|DO|RN))?(?=\s*\n|\s*$|\s+\d)",
        # All-caps header
        r"(?:PATIENT\s*NAME|PATIENT)[:\s]+([A-Z][A-Z\s\-']{2,50})(?=\s*\n|\s*\d)",
        # Loose fallback
        r"(?:Patient)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    ],
    "dob": [
        r"(?:Date\s+of\s+Birth|DOB|Birth\s+Date)[:\s]+(\d{4}-\d{2}-\d{2})",
        r"(?:Date\s+of\s+Birth|DOB|Birth\s+Date)[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
        r"(?:Date\s+of\s+Birth|DOB|Birth\s+Date)[:\s]+([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})",
        # Table-extracted format: "DOB  06/22/1985" (two spaces from table join)
        r"\bDOB\s{1,4}([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
    ],
    "gender": [
        r"(?:Gender|Sex)[:\s]+(Male|Female|Non-?binary|Transgender|Unknown|Other|M\b|F\b|NB\b)",
        # Table style: "Sex  M" or "Gender  F"
        r"(?:Gender|Sex)\s{1,4}(M|F|Male|Female|Non-?binary|Unknown|Other)\b",
    ],
    "mrn": [
        r"(?:MRN|Medical\s+Record\s+(?:Number|No\.?|#?))[:\s#]*([\w\d\-]{4,15})",
        r"\bMRN[:\s]*([\w\d\-]{4,15})",
        r"(?:Patient\s+ID|Pt\s+ID)[:\s]*([\w\d\-]{4,15})",
    ],
    "insurance_id": [
        r"(?:Insurance\s+(?:ID|Number|Member\s+ID)|Member\s+ID|Policy\s+(?:ID|Number))[:\s]*([\w\d\-]+)",
        r"(?:Group\s+(?:Number|No\.?|ID))[:\s]*([\w\d\-]+)",
        r"(?:Payer\s+(?:ID|Name))[:\s]+([A-Za-z0-9][A-Za-z0-9\s]{1,40})",
        r"(?:Policy\s+Holder)[:\s]+([A-Za-z\s]+)",
    ],
    "phone": [
        r"(?:Phone|Tel|Contact|Cell|Mobile)[:\s]*([\d\-\(\)\s\.]{10,16})",
        r"\b(\d{3}[\-\.\s]\d{3}[\-\.\s]\d{4})\b",
        r"\((\d{3})\)\s*(\d{3})[\-\s](\d{4})",
    ],
    "address": [
        r"(?:Address)[:\s]+(\d+\s+[A-Za-z0-9\s]+(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Court|Ct|Place|Pl|Terrace|Ter|Circle|Cir)\.?[^\n]{0,80})",
        r"(?:Address)[:\s]+([A-Za-z0-9\s,\.]+\d{5}(?:-\d{4})?)",
    ],
}

_DATE_FORMATS = [
    "%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y",
    "%d/%m/%Y", "%d-%m-%Y",
    "%Y-%m-%d",
    "%B %d, %Y", "%b %d, %Y",
    "%m/%d/%y", "%m-%d-%y",
]

_NAME_SUFFIXES = re.compile(r"\s+(?:Jr\.?|Sr\.?|II|III|IV|PhD|MD|DO|RN|NP)\s*$", re.IGNORECASE)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_first(text: str, patterns: list) -> Tuple[Optional[str], float]:
    for i, pattern in enumerate(patterns):
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            # use last group if phone has 3 capture groups
            value = "".join(g for g in m.groups() if g) if len(m.groups()) > 1 else m.group(1)
            confidence = 0.85 if i == 0 else 0.60
            return value.strip(), confidence
    return None, 0.0


def _parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
            # v3: fix two-digit year ambiguity
            if parsed.year > date.today().year:
                parsed = parsed.replace(year=parsed.year - 100)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _derive_age(dob_str: str) -> Optional[int]:
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age if 0 <= age <= 130 else None
    except Exception:
        return None


def _split_name(full_name: str):
    # Strip suffixes before splitting
    clean = _NAME_SUFFIXES.sub("", full_name).strip()
    parts = clean.split()
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:])
    return clean, None


def _normalize_gender(raw: str) -> str:
    r = raw.strip().upper()
    mapping = {
        "M": "Male", "MALE": "Male",
        "F": "Female", "FEMALE": "Female",
        "NB": "Non-binary", "NON-BINARY": "Non-binary", "NONBINARY": "Non-binary",
        "T": "Transgender", "TRANSGENDER": "Transgender",
        "UNKNOWN": "Unknown",
    }
    return mapping.get(r, "Other")


def _normalize_phone(raw: str) -> str:
    """v3 NEW: strip formatting, output (NNN) NNN-NNNN."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return raw.strip()


def _validate_mrn(mrn: Optional[str]) -> Optional[str]:
    """
    v3 NEW: Accept only 4-15 alphanumeric chars (with optional dashes).
    Rejects long sentence fragments that crept past the length constraint.
    """
    if not mrn:
        return None
    clean = mrn.strip()
    if re.fullmatch(r"[\w\d\-]{4,15}", clean):
        return clean
    return None


def _validate_demographics(patient: PatientDemographics) -> List[str]:
    """
    v3 NEW: Cross-field sanity checks.
    Returns a list of warning strings (empty = all clear).
    """
    warnings = []
    if patient.dob and patient.age is not None:
        expected = _derive_age(patient.dob)
        if expected is not None and abs(expected - patient.age) > 1:
            warnings.append(f"DOB/age mismatch: DOB={patient.dob} implies age≈{expected}, got {patient.age}")
    if patient.age is not None and not (0 <= patient.age <= 130):
        warnings.append(f"Age out of valid range: {patient.age}")
    if patient.dob:
        try:
            dob = datetime.strptime(patient.dob, "%Y-%m-%d").date()
            if dob > date.today():
                warnings.append(f"DOB is in the future: {patient.dob}")
        except ValueError:
            warnings.append(f"DOB could not be validated: {patient.dob}")
    return warnings


# ── LLM fallback ──────────────────────────────────────────────────────────────

def _llm_extract_demographics(text: str, missing_fields: List[str]) -> Dict[str, Any]:
    """
    v3 NEW: Call Claude API for fields that regex could not find.
    Only invoked when at least one critical field (name, dob, mrn) is None.
    Returns a dict of field_name → extracted_value.
    """
    import json, urllib.request

    fields_str = ", ".join(missing_fields)
    prompt = f"""You are extracting patient demographics from a medical document.
Extract ONLY the following fields: {fields_str}.

Rules:
- Return ONLY a JSON object, no explanation, no markdown fences.
- If a field cannot be found, use null.
- For patient_name: return full name as written.
- For dob: return in YYYY-MM-DD format if possible.
- For mrn: return only the alphanumeric ID (4-15 chars).
- For gender: return Male, Female, Non-binary, Transgender, Unknown, or Other.

Document (first 3000 chars):
{text[:3000]}"""

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            raw = data["content"][0]["text"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            return json.loads(raw)
    except Exception:
        return {}


# ── Main extractor ────────────────────────────────────────────────────────────

def parse_patient_demographics(text: str) -> PatientDemographics:
    """
    Extract patient demographics. Regex-first, LLM fallback for critical nulls.
    v3: MRN validation, phone normalisation, DOB century fix, validation warnings.
    """
    raw_name, _ = _find_first(text, _PATTERNS["patient_name"])
    first_name, last_name = _split_name(raw_name) if raw_name else (None, None)

    raw_dob, _ = _find_first(text, _PATTERNS["dob"])
    dob = _parse_date(raw_dob) if raw_dob else None
    age = _derive_age(dob) if dob else None

    raw_gender, _ = _find_first(text, _PATTERNS["gender"])
    gender = _normalize_gender(raw_gender) if raw_gender else None

    raw_mrn, _ = _find_first(text, _PATTERNS["mrn"])
    mrn = _validate_mrn(raw_mrn)

    insurance_id, _ = _find_first(text, _PATTERNS["insurance_id"])

    raw_phone, _ = _find_first(text, _PATTERNS["phone"])
    phone = _normalize_phone(raw_phone) if raw_phone else None

    address, _ = _find_first(text, _PATTERNS["address"])

    # v3: LLM fallback for critical fields still None
    critical_missing = [f for f, v in [("patient_name", raw_name), ("dob", dob), ("mrn", mrn)] if not v]
    if critical_missing:
        llm_data = _llm_extract_demographics(text, critical_missing)
        if not raw_name and llm_data.get("patient_name"):
            raw_name = llm_data["patient_name"]
            first_name, last_name = _split_name(raw_name)
        if not dob and llm_data.get("dob"):
            dob = _parse_date(llm_data["dob"])
            age = _derive_age(dob) if dob else None
        if not mrn and llm_data.get("mrn"):
            mrn = _validate_mrn(llm_data["mrn"])
        if not gender and llm_data.get("gender"):
            gender = _normalize_gender(llm_data["gender"])

    patient = PatientDemographics(
        patient_name=raw_name,
        first_name=first_name,
        last_name=last_name,
        dob=dob,
        age=age,
        gender=gender,
        mrn=mrn,
        insurance_id=insurance_id,
        phone=phone,
        address=address,
    )

    # v3: run cross-field validation (warnings logged, not raised)
    warnings = _validate_demographics(patient)
    if warnings:
        import logging
        for w in warnings:
            logging.getLogger(__name__).warning("Demographics validation: %s", w)

    return patient
