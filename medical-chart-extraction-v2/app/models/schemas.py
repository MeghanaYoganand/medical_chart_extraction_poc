"""
Pydantic models for API request/response schema

v3 CHANGES:
  - DocumentMetadata: added requires_review (bool) flag
  - ExtractionResult: no structural changes
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class DocumentMetadata(BaseModel):
    document_id: str
    file_name: str
    document_type: Optional[str] = None
    classification_confidence: Optional[float] = None
    requires_review: bool = False           # v3: True when confidence < 0.50
    source: str
    ingestion_timestamp: Optional[datetime] = None
    page_count: int = 0


class PatientDemographics(BaseModel):
    patient_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    dob: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    mrn: Optional[str] = None
    insurance_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None


class EncounterInfo(BaseModel):
    encounter_id: Optional[str] = None
    encounter_date: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    encounter_type: Optional[str] = None
    provider_name: Optional[str] = None
    facility_name: Optional[str] = None
    reason_for_visit: Optional[str] = None
    encounter_summary: Optional[str] = None


class ExtractionResult(BaseModel):
    document_metadata: DocumentMetadata
    patient: PatientDemographics
    encounters: List[EncounterInfo] = []


class UploadResponse(BaseModel):
    document_id: str
    message: str
    file_name: str
