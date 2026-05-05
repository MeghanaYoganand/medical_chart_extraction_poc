"""
Document API Routes
- POST /upload       → ingest + auto-extract
- POST /{id}/extract → re-run extraction
- GET  /{id}         → fetch stored result
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db, DocumentDB, PatientDB, EncounterDB
from app.core.pipeline import run_pipeline
from app.models.schemas import ExtractionResult, UploadResponse

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf", "application/xml", "text/xml",
    "application/octet-stream",  # fallback for unknown
}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a PDF or CCDA XML file. Returns document_id."""
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File exceeds 5 MB limit")

    result, raw_text = run_pipeline(
        file_bytes=content,
        filename=file.filename,
        content_type=file.content_type or "application/octet-stream",
    )

    _persist(db, result, raw_text)

    return UploadResponse(
        document_id=result.document_metadata.document_id,
        message="Document uploaded and extracted successfully",
        file_name=file.filename,
    )


@router.post("/{document_id}/extract", response_model=ExtractionResult)
def extract_document(document_id: str, db: Session = Depends(get_db)):
    """Re-run extraction on an already-uploaded document."""
    doc = db.query(DocumentDB).filter(DocumentDB.document_id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    result, raw_text = run_pipeline(
        file_bytes=doc.raw_text.encode() if doc.raw_text else b"",
        filename=doc.file_name,
        content_type="application/pdf",
    )
    result.document_metadata.document_id = document_id
    _update(db, doc, result)
    return result


@router.get("/{document_id}", response_model=ExtractionResult)
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Retrieve previously extracted data for a document."""
    doc = db.query(DocumentDB).filter(DocumentDB.document_id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    return _to_schema(doc)


# ── DB helpers ────────────────────────────────────────────────────────────────

def _persist(db: Session, result: ExtractionResult, raw_text: str):
    meta = result.document_metadata
    doc = DocumentDB(
        document_id=meta.document_id,
        file_name=meta.file_name,
        document_type=meta.document_type,
        source=meta.source,
        ingestion_timestamp=meta.ingestion_timestamp,
        page_count=meta.page_count,
        raw_text=raw_text,
    )
    db.add(doc)

    p = result.patient
    patient = PatientDB(
        document_id=meta.document_id,
        **p.dict()
    )
    db.add(patient)

    for enc in result.encounters:
        db.add(EncounterDB(document_id=meta.document_id, **enc.dict()))

    db.commit()


def _update(db: Session, doc: DocumentDB, result: ExtractionResult):
    db.query(PatientDB).filter(PatientDB.document_id == doc.document_id).delete()
    db.query(EncounterDB).filter(EncounterDB.document_id == doc.document_id).delete()
    p = result.patient
    db.add(PatientDB(document_id=doc.document_id, **p.dict()))
    for enc in result.encounters:
        db.add(EncounterDB(document_id=doc.document_id, **enc.dict()))
    db.commit()


def _to_schema(doc: DocumentDB) -> ExtractionResult:
    from app.models.schemas import (
        DocumentMetadata, PatientDemographics, EncounterInfo
    )
    meta = DocumentMetadata(
        document_id=doc.document_id,
        file_name=doc.file_name,
        document_type=doc.document_type,
        source=doc.source,
        ingestion_timestamp=doc.ingestion_timestamp,
        page_count=doc.page_count,
    )
    p = doc.patient
    patient = PatientDemographics(**{
        c.name: getattr(p, c.name)
        for c in PatientDB.__table__.columns
        if c.name not in ("id", "document_id")
    }) if p else PatientDemographics()

    encounters = []
    for enc in doc.encounters:
        encounters.append(EncounterInfo(**{
            c.name: getattr(enc, c.name)
            for c in EncounterDB.__table__.columns
            if c.name not in ("id", "document_id")
        }))

    return ExtractionResult(document_metadata=meta, patient=patient, encounters=encounters)
