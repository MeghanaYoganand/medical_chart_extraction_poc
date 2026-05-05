"""
Unit tests for Medical Chart Extraction PoC
Run: pytest tests/ -v
"""
import pytest
from app.core.demographics_parser import parse_patient_demographics
from app.core.encounter_parser import parse_encounters
from app.core.classifier import classify_document_type


# ── Demographics Tests ─────────────────────────────────────────────────────────

SAMPLE_DEMOGRAPHICS_TEXT = """
Patient Name: John Smith
Date of Birth: 01/15/1979
Gender: Male
MRN: MRN12345
Insurance ID: BCBS123456
Phone: 987-654-3210
Address: 123 Main St, Springfield, IL
"""

def test_parse_full_demographics():
    result = parse_patient_demographics(SAMPLE_DEMOGRAPHICS_TEXT)
    assert result.patient_name == "John Smith"
    assert result.first_name == "John"
    assert result.last_name == "Smith"
    assert result.dob == "1979-01-15"
    assert result.gender == "Male"
    assert result.mrn == "MRN12345"


def test_derive_age_from_dob():
    result = parse_patient_demographics(SAMPLE_DEMOGRAPHICS_TEXT)
    assert result.age is not None
    assert 40 < result.age < 60  # John was born in 1979


def test_missing_fields_handled_gracefully():
    result = parse_patient_demographics("No structured data here.")
    assert result.patient_name is None
    assert result.dob is None
    assert result.mrn is None


def test_gender_normalization():
    text = "Gender: M\nDate of Birth: 01/01/1990"
    result = parse_patient_demographics(text)
    assert result.gender == "Male"

    text2 = "Sex: F"
    result2 = parse_patient_demographics(text2)
    assert result2.gender == "Female"


# ── Encounter Tests ────────────────────────────────────────────────────────────

SAMPLE_ENCOUNTER_TEXT = """
Encounter Date: 03/10/2024
Admission Date: 03/08/2024
Discharge Date: 03/12/2024
Encounter Type: Inpatient
Provider: Dr. Sarah Johnson
Facility: ABC Hospital
Chief Complaint: Chest pain and shortness of breath
"""

def test_parse_encounter_dates():
    encounters = parse_encounters(SAMPLE_ENCOUNTER_TEXT)
    assert len(encounters) >= 1
    enc = encounters[0]
    assert enc.encounter_date == "2024-03-10"
    assert enc.admission_date == "2024-03-08"
    assert enc.discharge_date == "2024-03-12"


def test_parse_encounter_provider():
    encounters = parse_encounters(SAMPLE_ENCOUNTER_TEXT)
    assert encounters[0].provider_name is not None
    assert "Johnson" in encounters[0].provider_name


def test_parse_encounter_facility():
    encounters = parse_encounters(SAMPLE_ENCOUNTER_TEXT)
    assert encounters[0].facility_name is not None
    assert "Hospital" in encounters[0].facility_name


def test_encounter_id_generated():
    encounters = parse_encounters(SAMPLE_ENCOUNTER_TEXT)
    assert encounters[0].encounter_id is not None
    assert len(encounters[0].encounter_id) == 36  # UUID length


def test_missing_encounter_data():
    """Should return an encounter even if most fields are missing."""
    encounters = parse_encounters("No encounter info here.")
    assert isinstance(encounters, list)


# ── Classifier Tests ───────────────────────────────────────────────────────────

def test_classify_discharge_summary():
    text = "DISCHARGE SUMMARY\nPatient admitted for chest pain."
    result = classify_document_type(text, "chart.pdf")
    assert result == "Discharge Summary"


def test_classify_ccda_by_filename():
    result = classify_document_type("", "patient_record.xml")
    assert result == "CCDA"


def test_classify_progress_note():
    text = "PROGRESS NOTE\nS: Patient complains of fatigue."
    result = classify_document_type(text, "note.pdf")
    assert result == "Progress Notes"


def test_classify_unknown():
    result = classify_document_type("Random unrelated text", "file.pdf")
    assert result == "Unknown"


# ── Date Format Tests ──────────────────────────────────────────────────────────

def test_date_formats_dob():
    texts = [
        "DOB: 01-15-1979",
        "DOB: 01.15.1979",
        "Date of Birth: January 15, 1979",
        "DOB: 1979-01-15",
    ]
    for text in texts:
        result = parse_patient_demographics(text)
        assert result.dob == "1979-01-15", f"Failed for: {text}"
