# Changelog

## v3 — Accuracy Improvements (this submission)

### app/core/extractor.py
- `_normalize_text`: rejoins OCR-split hyphenated words ("dis-\ncharge" → "discharge")
- `extract_text_from_pdf`: now calls `page.extract_tables()` and converts table rows to
  "Label: Value" lines before the paragraph text — preserves structured demographic tables
- `_ocr_page`: added tesseract `--psm 6` flag and `preserve_interword_spaces=1` for better
  accuracy on medical forms with many short label fields
- `extract_text_from_ccda`: filters single-char XML tag noise from section blobs

### app/core/classifier.py
- Scans last 2000 chars in addition to first 6000 (some notes put type in footer)
- Multi-keyword scoring: 2+ strong hits → 0.95, 1 strong → 0.85, weak → max 0.79
- Filename substring hints (lab, rad, op, dc…) contribute +0.05 when aligned with text
- Added Emergency Department as a distinct document type with 5 patterns

### app/core/demographics_parser.py
- MRN validation: `_validate_mrn()` — only accepts 4-15 alphanumeric chars, rejects sentence fragments
- DOB two-digit year fix: if parsed year > current year, subtract 100
- Name: added middle-name support; strips suffixes (Jr., Sr., III, PhD, MD) before first/last split
- Phone: `_normalize_phone()` — normalises to (NNN) NNN-NNNN format
- Added `Pt ID` / `Patient ID` as MRN aliases; added `Policy Holder` as insurance alias
- Added table-format DOB pattern ("DOB  06/22/1985" — two spaces from table extraction)
- `_validate_demographics()`: cross-checks DOB/age consistency, rejects future DOBs, logs warnings
- **LLM fallback** (`_llm_extract_demographics`): calls Claude API only when patient_name, dob, or
  mrn are still None after all regex passes — keeps API cost minimal

### app/core/encounter_parser.py
- Date patterns: added "Service Date" and table-format "Service Date  MM/DD/YYYY"
- Date validation: rejects dates > 30 years ago or in the future
- Encounter type normalisation: ED → Emergency Department, ER → Emergency Department, SNF → Skilled Nursing Facility
- Facility patterns: added Health System, Medical Group, Clinic at anchor words
- `_extract_summary`: multi-paragraph capture up to 600 chars; added Hospital Course section
- Reason patterns: added "Presents with / Presenting with" trigger
- Block splitter: added "ENCOUNTER DATE / VISIT DATE" label as encounter boundary marker
- **LLM fallback** (`_llm_extract_encounter`): called when reason_for_visit, encounter_summary,
  encounter_date, or provider_name are all None after regex — recovers free-text narrative fields

### app/core/pipeline.py
- Post-extraction confidence gate: `requires_review = True` when `classification_confidence < 0.50`
- Low-confidence documents logged at WARNING level with filename

### app/models/schemas.py
- `DocumentMetadata`: added `requires_review: bool` field

---

## v2 (previous submission)
- OCR 200 → 300 dpi; CCDA section-labeled parsing; text normalisation
- Classifier: 3000 → 6000 char scan window; confidence tuple; 4 new doc types
- Demographics: all-caps + hyphenated name; expanded gender; tightened address
- Encounter: flexible block splitting; consulting provider; IMPRESSION/A/P summary
- Pipeline: classification_confidence in metadata
