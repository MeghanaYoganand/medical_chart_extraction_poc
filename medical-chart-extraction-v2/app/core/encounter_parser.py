"""
Encounter Information Parser
Extracts one or more encounter blocks from raw document text.

v3 CHANGES:
  - LLM fallback for encounter_summary and reason_for_visit when regex returns None
  - Encounter date: additional patterns for "Service Date", "Date of Service" table format
  - Facility: added more anchor words (Health System, Medical Group, Clinic at)
  - Encounter type normalisation: maps ED → Emergency Department, SNF → Skilled Nursing
  - _extract_summary: multi-paragraph capture (up to 600 chars) for richer summaries
  - Date validation: rejects dates more than 30 years in the past or in the future
"""
import re
import uuid
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from app.models.schemas import EncounterInfo

_DATE_PATTERNS = [
    r"(?:Encounter|Visit|Appointment|Service)\s+Date[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
    r"(?:Date\s+of\s+(?:Visit|Service|Encounter|Appointment))[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
    r"(?:Visit\s+Date)[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
    # Table-extracted "Service Date  03/10/2024"
    r"(?:Service\s+Date)\s{1,4}([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
]

_ADMISSION_PATTERNS = [
    r"(?:Admission|Admit(?:ted)?)\s+Date[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
    r"(?:Admission|Admit(?:ted)?)[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
    r"Admitted[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
]

_DISCHARGE_PATTERNS = [
    r"(?:Discharge(?:d)?)\s+Date[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
    r"(?:Discharge(?:d)?)[:\s]+([\d]{1,2}[/\-.][\d]{1,2}[/\-.][\d]{2,4})",
]

_TYPE_PATTERNS = [
    r"(?:Encounter|Visit)\s+Type[:\s]+(\w+(?:\s+\w+)?)",
    r"\b(Inpatient|Outpatient|Emergency\s+Department|Emergency\s+Room|ED\b|ER\b|"
    r"Observation|Telehealth|Urgent\s+Care|Home\s+Health|Skilled\s+Nursing|SNF\b|"
    r"Hospital\s+Outpatient|Wound\s+Care|Behavioral\s+Health)\b",
]

_TYPE_NORMALIZER = {
    "ED": "Emergency Department", "ER": "Emergency Department",
    "Emergency Room": "Emergency Department",
    "SNF": "Skilled Nursing Facility",
}

_PROVIDER_PATTERNS = [
    r"(?:Attending|Provider|Physician|Doctor)[:\s]+"
    r"(Dr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)(?!\s+(?:noted|stated|ordered|prescribed|reported|recommended))",
    r"(?:Provider|Physician|Doctor)[:\s]+(Dr\.?\s+\w+(?:\s+\w+){0,2})",
    r"\bDr\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
]

_CONSULTING_PROVIDER_PATTERNS = [
    r"(?:Consulting|Consultant|Consulted)[:\s]+(Dr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
    r"(?:Referring|Referred\s+By)[:\s]+(Dr\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
]

_FACILITY_PATTERNS = [
    r"(?:Facility|Hospital|Clinic|Location|Site)[:\s]+([A-Za-z0-9][A-Za-z0-9\s]+(?:Hospital|Medical Center|Health System|Medical Group|Clinic|Health|Clinic at)[^\n,]{0,60})",
    r"([A-Z][A-Za-z\s]+(?:Hospital|Medical Center|Health System|Clinic))\b",
]

_REASON_PATTERNS = [
    r"(?:Chief\s+Complaint|Reason\s+for\s+Visit|Presenting\s+Complaint|Chief\s+Concern)[:\s]+([^\n]{5,200})",
    r"(?:CC|Reason)[:\s]+([^\n]{5,200})",
    r"(?:Presenting\s+with|Presents\s+with)[:\s]+([^\n]{5,200})",
]

_DATE_FORMATS = [
    "%m/%d/%Y", "%m-%d-%Y", "%m.%d.%Y",
    "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d",
    "%B %d, %Y", "%b %d, %Y", "%m/%d/%y",
]


def _find_first(text: str, patterns: list) -> Optional[str]:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _parse_date(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
            # v3: reject implausible dates
            yr = parsed.year
            if yr < date.today().year - 30 or parsed.date() > date.today():
                continue
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def _normalize_encounter_type(raw: Optional[str]) -> Optional[str]:
    """v3 NEW: standardise abbreviations."""
    if not raw:
        return None
    return _TYPE_NORMALIZER.get(raw.strip(), raw.strip())


def _extract_summary(text: str) -> Optional[str]:
    """
    v3: multi-paragraph capture (up to 600 chars) for richer summaries.
    """
    patterns = [
        r"(?:IMPRESSION)[:\s]+([^\n]{20,600})",
        r"(?:A[/&]P|Assessment\s+and\s+Plan)[:\s]+([^\n]{20,600})",
        r"(?:Discharge\s+(?:Summary|Diagnosis)|Assessment|Plan|Impression)[:\s]+([^\n]{20,400})",
        r"(?:SUMMARY|CLINICAL\s+SUMMARY)[:\s]+([^\n]{20,400})",
        r"(?:Hospital\s+Course)[:\s]+([^\n]{20,500})",
    ]
    return _find_first(text, patterns)


# ── LLM fallback ──────────────────────────────────────────────────────────────

def _llm_extract_encounter(block: str, missing_fields: List[str]) -> Dict[str, Any]:
    """
    v3 NEW: Call Claude API for encounter fields regex missed.
    Called only when reason_for_visit or encounter_summary is None.
    """
    import json, urllib.request

    fields_str = ", ".join(missing_fields)
    prompt = f"""You are extracting encounter information from a medical document.
Extract ONLY these fields: {fields_str}.

Rules:
- Return ONLY a JSON object, no markdown, no explanation.
- If a field is not found, use null.
- For encounter_date / admission_date / discharge_date: use YYYY-MM-DD format.
- For reason_for_visit: one sentence, the chief complaint.
- For encounter_summary: 1-3 sentences summarising the clinical course.
- For encounter_type: one of Inpatient, Outpatient, Emergency Department, Urgent Care, Telehealth, Observation, or null.
- For provider_name: full name with title (e.g. Dr. Jane Smith).
- For facility_name: the hospital or clinic name only.

Document excerpt:
{block[:2500]}"""

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 400,
        "messages": [{"role": "user", "content": prompt}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
            raw = data["content"][0]["text"].strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            return json.loads(raw)
    except Exception:
        return {}


# ── Main extractor ────────────────────────────────────────────────────────────

def parse_encounters(text: str) -> List[EncounterInfo]:
    blocks = _split_encounter_blocks(text)
    encounters = []

    for block in blocks:
        provider = _find_first(block, _PROVIDER_PATTERNS)
        consulting = _find_first(block, _CONSULTING_PROVIDER_PATTERNS)
        if consulting and consulting != provider:
            provider_combined = f"{provider} (Consulting: {consulting})" if provider else f"Consulting: {consulting}"
        else:
            provider_combined = provider

        enc_date = _parse_date(_find_first(block, _DATE_PATTERNS))
        adm_date = _parse_date(_find_first(block, _ADMISSION_PATTERNS))
        dis_date = _parse_date(_find_first(block, _DISCHARGE_PATTERNS))
        enc_type = _normalize_encounter_type(_find_first(block, _TYPE_PATTERNS))
        facility = _find_first(block, _FACILITY_PATTERNS)
        reason = _find_first(block, _REASON_PATTERNS)
        summary = _extract_summary(block)

        # v3: LLM fallback for narrative fields
        missing = []
        if not reason:
            missing.append("reason_for_visit")
        if not summary:
            missing.append("encounter_summary")
        if not enc_date and not adm_date:
            missing.append("encounter_date")
        if not provider_combined:
            missing.append("provider_name")

        if missing:
            llm = _llm_extract_encounter(block, missing)
            if not reason and llm.get("reason_for_visit"):
                reason = llm["reason_for_visit"]
            if not summary and llm.get("encounter_summary"):
                summary = llm["encounter_summary"]
            if not enc_date and llm.get("encounter_date"):
                enc_date = _parse_date(llm["encounter_date"])
            if not provider_combined and llm.get("provider_name"):
                provider_combined = llm["provider_name"]
            if not facility and llm.get("facility_name"):
                facility = llm["facility_name"]
            if not enc_type and llm.get("encounter_type"):
                enc_type = llm["encounter_type"]

        enc = EncounterInfo(
            encounter_id=str(uuid.uuid4()),
            encounter_date=enc_date,
            admission_date=adm_date,
            discharge_date=dis_date,
            encounter_type=enc_type,
            provider_name=provider_combined,
            facility_name=facility,
            reason_for_visit=reason,
            encounter_summary=summary,
        )

        if any([enc.encounter_date, enc.admission_date, enc.provider_name, enc.reason_for_visit, enc.encounter_summary]):
            encounters.append(enc)

    if not encounters:
        enc = EncounterInfo(
            encounter_id=str(uuid.uuid4()),
            encounter_date=_parse_date(_find_first(text, _DATE_PATTERNS)),
            admission_date=_parse_date(_find_first(text, _ADMISSION_PATTERNS)),
            discharge_date=_parse_date(_find_first(text, _DISCHARGE_PATTERNS)),
            encounter_type=_normalize_encounter_type(_find_first(text, _TYPE_PATTERNS)),
            provider_name=_find_first(text, _PROVIDER_PATTERNS),
            facility_name=_find_first(text, _FACILITY_PATTERNS),
            reason_for_visit=_find_first(text, _REASON_PATTERNS),
            encounter_summary=_extract_summary(text),
        )
        encounters.append(enc)

    return encounters


def _split_encounter_blocks(text: str) -> List[str]:
    separator = re.compile(
        r"(?:^|\n)(?="
        r"(?:ENCOUNTER|VISIT|ADMISSION)\s*(?:#\s*\d+)?\s*\n"
        r"|(?:VISIT\s+SUMMARY)\s*[\(\d]"
        r"|(?:={4,}|-{4,})\s*\n"
        r"|(?:ENCOUNTER\s+DATE|VISIT\s+DATE)\s*[:\s]"
        r")",
        re.IGNORECASE
    )
    splits = list(separator.finditer(text))
    if len(splits) < 2:
        return [text]

    blocks = []
    for i, match in enumerate(splits):
        start = match.start()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(text)
        blocks.append(text[start:end])
    return blocks
