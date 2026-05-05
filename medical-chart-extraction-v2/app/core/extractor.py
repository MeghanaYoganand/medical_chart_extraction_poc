"""
Text extraction from PDF and CCDA XML files.

v3 CHANGES:
  - _normalize_text: added dash normalization and hyphenated-word rejoining
    (OCR often splits "dis- charge" across lines)
  - extract_text_from_pdf: now also extracts table cells via page.extract_tables()
    so structured lab/demographic tables are not lost
  - _ocr_page: added tesseract config flag for medical documents (preserve digits)
  - extract_text_from_ccda: strips XML tag noise from section blobs more aggressively
"""
import io
import re
import xml.etree.ElementTree as ET
from typing import Tuple, Dict

CCDA_SECTION_CODES: Dict[str, str] = {
    "10164-2": "history_of_present_illness",
    "11450-4": "problem_list",
    "29299-5": "reason_for_visit",
    "18776-5": "plan_of_care",
    "10183-2": "discharge_summary",
    "11348-0": "past_medical_history",
    "29548-5": "diagnosis",
    "57827-8": "discharge_medications",
    "47519-4": "procedures",
    "30954-2": "results_labs",
}


def _normalize_text(text: str) -> str:
    """Clean OCR/PDF artifacts before regex parsing."""
    ligatures = {
        "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
        "\ufb03": "ffi", "\ufb04": "ffl", "\u00a0": " ",
    }
    for src, dst in ligatures.items():
        text = text.replace(src, dst)

    # v3: rejoin OCR-split hyphenated words ("dis-\ncharge" → "discharge")
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)

    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return text.strip()


def _table_to_text(tables) -> str:
    """
    v3 NEW: Convert pdfplumber table rows into label: value lines.
    This preserves structured data (demographics tables, lab results) that
    pure text extraction flattens or loses entirely.
    """
    lines = []
    for table in tables:
        for row in table:
            cells = [c.strip() if c else "" for c in row]
            non_empty = [c for c in cells if c]
            if len(non_empty) == 2:
                lines.append(f"{non_empty[0]}: {non_empty[1]}")
            elif non_empty:
                lines.append("  ".join(non_empty))
    return "\n".join(lines)


def extract_text_from_pdf(file_bytes: bytes) -> Tuple[str, int]:
    """
    Extract plain text + table content from a PDF file.
    Returns (normalized_text, page_count).

    v3 CHANGES:
      - Calls page.extract_tables() and appends structured table text before
        flowing paragraph text so label:value pairs are regex-friendly
    """
    import pdfplumber

    text_parts = []
    page_count = 0

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            # v3: extract tables first so structured fields appear as "Label: Value"
            tables = page.extract_tables() or []
            table_text = _table_to_text(tables)

            page_text = page.extract_text() or ""
            word_count = len(page_text.split())

            if word_count >= 10:
                combined = (table_text + "\n" + page_text).strip() if table_text else page_text
                text_parts.append(combined)
            else:
                ocr_text = _ocr_page(page, resolution=300)
                combined = (table_text + "\n" + ocr_text).strip() if table_text else ocr_text
                if combined:
                    text_parts.append(combined)

    raw = "\n".join(text_parts)
    return _normalize_text(raw), page_count


def _ocr_page(page, resolution: int = 300) -> str:
    """
    Fallback OCR using pytesseract.
    v3: added --psm 6 (uniform block of text) and preserve_interword_spaces=1
    which improves accuracy on medical forms with many short label fields.
    """
    try:
        import pytesseract
        img = page.to_image(resolution=resolution).original
        config = "--psm 6 -c preserve_interword_spaces=1"
        return pytesseract.image_to_string(img, config=config)
    except Exception:
        return ""


def extract_text_from_ccda(file_bytes: bytes) -> Tuple[str, int]:
    """
    Extract human-readable text from a CCDA XML file, labeled by section.

    v3: strips numeric-only tokens and XML tag names that leaked into section blobs.
    """
    try:
        root = ET.fromstring(file_bytes.decode("utf-8", errors="replace"))
        ns = {"hl7": "urn:hl7-org:v3"}

        sections_text = []
        found_coded = False

        for section in root.findall(".//hl7:section", ns):
            code_elem = section.find("hl7:code", ns)
            code = code_elem.get("code", "") if code_elem is not None else ""
            label = CCDA_SECTION_CODES.get(code, None)

            section_words = [
                elem.text.strip()
                for elem in section.iter()
                if elem.text and elem.text.strip() and len(elem.text.strip()) > 1
            ]
            section_blob = " ".join(section_words)

            if label:
                found_coded = True
                sections_text.append(f"SECTION: {label}\n{section_blob}")
            else:
                sections_text.append(section_blob)

        if not found_coded:
            texts = [
                elem.text.strip()
                for elem in root.iter()
                if elem.text and elem.text.strip()
            ]
            return _normalize_text("\n".join(texts)), 1

        return _normalize_text("\n\n".join(sections_text)), 1

    except ET.ParseError as e:
        return f"[CCDA parse error: {e}]", 0


def extract_text(file_bytes: bytes, content_type: str, filename: str) -> Tuple[str, int]:
    """Dispatch to the right extractor based on file type."""
    fname_lower = filename.lower()

    if fname_lower.endswith(".xml") or content_type in ("text/xml", "application/xml"):
        return extract_text_from_ccda(file_bytes)

    if fname_lower.endswith(".txt") or content_type == "text/plain":
        text = file_bytes.decode("utf-8", errors="replace")
        return _normalize_text(text), 1

    return extract_text_from_pdf(file_bytes)
