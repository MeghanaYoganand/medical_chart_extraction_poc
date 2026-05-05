"""
Document type classifier using keyword matching with confidence scoring.

v3 CHANGES:
  - Also scans last 2000 chars (some notes put the doc type in the footer/signature block)
  - Multi-keyword scoring: count how many patterns match and weight confidence accordingly
  - Added Emergency Department as a distinct document type
  - Filename heuristics: lab, rad, op in filename contribute to classification
"""
import re
from typing import Tuple

_DOC_TYPES = {
    "Discharge Summary": [
        r"discharge\s+summary", r"discharge\s+note", r"discharged\s+on",
        r"discharge\s+instructions",
    ],
    "Clinical Notes": [
        r"clinical\s+notes?", r"clinical\s+documentation",
    ],
    "Progress Notes": [
        r"progress\s+notes?", r"soap\s+note", r"daily\s+note",
    ],
    "Consultation Notes": [
        r"consultation\s+notes?", r"consult\s+note", r"referred\s+by",
    ],
    "Lab Report": [
        r"laboratory\s+report", r"lab\s+results?", r"pathology\s+report",
        r"specimen\s+report", r"reference\s+range", r"collected\s+date",
        r"result\s+status",
    ],
    "Operative Note": [
        r"operative\s+note", r"operation\s+report", r"surgical\s+report",
        r"procedure\s+note", r"pre-?op\b", r"post-?op\b",
        r"anesthesia\s+type", r"incision",
    ],
    "Radiology Report": [
        r"radiology\s+report", r"imaging\s+report", r"x-?ray",
        r"\bmri\b", r"ct\s+scan", r"ultrasound\s+report",
        r"\bimpression:", r"technique:", r"clinical\s+indication",
    ],
    "Medication List": [
        r"medication\s+list", r"discharge\s+medications?",
        r"current\s+medications?", r"medication\s+reconciliation",
        r"sig:", r"refills?:",
    ],
    "Emergency Department": [
        r"emergency\s+department", r"\bed\s+note\b", r"emergency\s+visit",
        r"triage\s+note", r"er\s+report",
    ],
    "CCDA": [
        r"<ClinicalDocument", r"urn:hl7-org:v3", r"continuity\s+of\s+care",
    ],
}

_STRONG_PATTERNS = {
    r"discharge\s+summary", r"operative\s+note", r"radiology\s+report",
    r"laboratory\s+report", r"<ClinicalDocument", r"emergency\s+department",
}

# Filename substring → doc type hint
_FILENAME_HINTS = {
    "lab": "Lab Report", "path": "Lab Report", "rad": "Radiology Report",
    "xray": "Radiology Report", "op": "Operative Note", "surg": "Operative Note",
    "med": "Medication List", "dc": "Discharge Summary", "discharge": "Discharge Summary",
    "ed": "Emergency Department", "er": "Emergency Department",
}


def classify_document_type(text: str, filename: str) -> Tuple[str, float]:
    """
    Return (doc_type, confidence) based on text content and filename.

    v3 CHANGES:
      - Scans first 6000 chars AND last 2000 chars
      - Multi-hit scoring: 2+ strong matches → 0.95, 1 strong → 0.85, weak → 0.60
      - Filename substring hints contribute +0.05 when they agree with text match
    """
    if filename.lower().endswith(".xml"):
        return "CCDA", 1.0

    # v3: scan both start and end of document
    text_sample = text[:6000] + "\n" + text[-2000:] if len(text) > 6000 else text

    # Filename hint
    fname_lower = filename.lower()
    fname_hint = next((v for k, v in _FILENAME_HINTS.items() if k in fname_lower), None)

    best_type = None
    best_score = 0.0
    best_hits = 0

    for doc_type, patterns in _DOC_TYPES.items():
        hits = sum(1 for p in patterns if re.search(p, text_sample, re.IGNORECASE))
        strong_hits = sum(1 for p in patterns if p in _STRONG_PATTERNS
                         and re.search(p, text_sample, re.IGNORECASE))

        if hits == 0:
            continue

        if strong_hits >= 2:
            score = 0.95
        elif strong_hits == 1:
            score = 0.85
        else:
            score = min(0.60 + 0.05 * (hits - 1), 0.79)

        if fname_hint == doc_type:
            score = min(score + 0.05, 0.99)

        if score > best_score or (score == best_score and hits > best_hits):
            best_score = score
            best_type = doc_type
            best_hits = hits

    if best_type:
        return best_type, round(best_score, 2)

    return "Unknown", 0.3
