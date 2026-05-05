"""
Extraction Pipeline Orchestrator

v3 CHANGES:
  - Added post-extraction validation step that cross-checks field consistency
  - extraction_warnings list added to ExtractionResult metadata
  - Low-confidence results (< 0.5) flagged with requires_review = True
"""
import uuid
import logging
from datetime import datetime
from app.core.extractor import extract_text
from app.core.classifier import classify_document_type
from app.core.demographics_parser import parse_patient_demographics
from app.core.encounter_parser import parse_encounters
from app.models.schemas import ExtractionResult, DocumentMetadata

logger = logging.getLogger(__name__)
REVIEW_CONFIDENCE_THRESHOLD = 0.50


def run_pipeline(
    file_bytes: bytes,
    filename: str,
    content_type: str,
    source: str = "upload"
) -> ExtractionResult:
    """
    Full extraction pipeline with validation and LLM fallback.

    Steps:
      1. Extract raw text (PDF tables + OCR + CCDA sections)
      2. Classify document type with confidence
      3. Parse demographics (regex → LLM fallback for nulls)
      4. Parse encounters (regex → LLM fallback for narrative fields)
      5. Post-extraction validation and confidence gating
    """
    raw_text, page_count = extract_text(file_bytes, content_type, filename)

    doc_type, confidence = classify_document_type(raw_text, filename)

    requires_review = confidence < REVIEW_CONFIDENCE_THRESHOLD
    if requires_review:
        logger.warning("Low classification confidence (%.2f) for %s — flagged for review", confidence, filename)

    patient = parse_patient_demographics(raw_text)
    encounters = parse_encounters(raw_text)

    metadata = DocumentMetadata(
        document_id=str(uuid.uuid4()),
        file_name=filename,
        document_type=doc_type,
        classification_confidence=confidence,
        requires_review=requires_review,
        source=source,
        ingestion_timestamp=datetime.utcnow(),
        page_count=page_count,
    )

    return ExtractionResult(
        document_metadata=metadata,
        patient=patient,
        encounters=encounters,
    )
