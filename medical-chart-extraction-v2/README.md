# Medical Chart Extraction – PoC

Extract structured data (metadata, patient demographics, encounter info) from unstructured medical charts (PDF / CCDA XML).

---

## Project Structure

```
medical-chart-extraction/
├── app/
│   ├── main.py                  # FastAPI entry point
│   ├── api/
│   │   └── documents.py         # Upload / Extract / Fetch routes
│   ├── core/
│   │   ├── pipeline.py          # Orchestrates the full extraction flow
│   │   ├── extractor.py         # PDF & CCDA text extraction (OCR fallback)
│   │   ├── classifier.py        # Document type classifier
│   │   ├── demographics_parser.py  # Patient demographics parser
│   │   └── encounter_parser.py  # Encounter information parser
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   └── db/
│       └── database.py          # SQLAlchemy models + DB init
├── tests/
│   └── test_extraction.py       # Unit tests
├── sample_data/
│   ├── sample_chart.txt         # Sample discharge summary (rename to .pdf for upload)
│   └── sample_ccda.xml          # Sample CCDA XML
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate       # Linux/macOS
venv\Scripts\activate          # Windows
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

> **Note:** For OCR support on scanned PDFs, also install Tesseract:
> - Ubuntu: `sudo apt install tesseract-ocr`
> - macOS: `brew install tesseract`
> - Windows: [tesseract installer](https://github.com/tesseract-ocr/tesseract)

---

## Run the API

```bash
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/documents/upload` | Upload PDF or CCDA XML (max 5 MB) |
| `POST` | `/api/v1/documents/{id}/extract` | Re-run extraction on stored document |
| `GET`  | `/api/v1/documents/{id}` | Fetch extracted structured data |
| `GET`  | `/health` | Health check |

### Upload Example (cURL)
```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -F "file=@sample_data/sample_chart.pdf"
```

### Fetch Result
```bash
curl "http://localhost:8000/api/v1/documents/{document_id}"
```

---

## Sample Output (JSON)

```json
{
  "document_metadata": {
    "document_id": "550e8400-e29b-41d4-a716-446655440000",
    "file_name": "discharge_01.pdf",
    "document_type": "Discharge Summary",
    "source": "upload",
    "ingestion_timestamp": "2024-03-10T09:00:00",
    "page_count": 5
  },
  "patient": {
    "patient_name": "Jane Doe",
    "first_name": "Jane",
    "last_name": "Doe",
    "dob": "1985-06-22",
    "age": 38,
    "gender": "Female",
    "mrn": "MRN98765",
    "insurance_id": "AETNA567890"
  },
  "encounters": [
    {
      "encounter_id": "uuid",
      "encounter_date": "2024-03-10",
      "admission_date": "2024-03-08",
      "discharge_date": "2024-03-12",
      "encounter_type": "Inpatient",
      "provider_name": "Dr. Michael Chen",
      "facility_name": "ABC Medical Center",
      "reason_for_visit": "Chest pain and shortness of breath",
      "encounter_summary": "Patient stabilized and discharged on aspirin therapy."
    }
  ]
}
```

---

## Run Tests

```bash
pytest tests/ -v
```

Expected: **14 tests passing**

---

## Processing Flow

```
File Upload → Text Extraction (PDF/OCR/CCDA)
           → Document Type Classification
           → Demographics Parser (regex + rules)
           → Encounter Parser (multi-encounter aware)
           → JSON Output + SQLite Storage
           → API Response
```

---

## Out of Scope (PoC Phase)

- Full clinical entity extraction (labs, meds, procedures)
- ICD/CPT coding normalization
- ML-based extraction tuning
- Real-time at-scale processing

---

## Future Enhancements

- Replace SQLite with PostgreSQL for production
- Add ML/NLP layer (spaCy or MedSpaCy) for improved accuracy
- Integrate with search/analytics layer
- Human-in-the-loop feedback for corrections
- ICD/CPT code mapping
