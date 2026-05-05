"""
Medical Chart Extraction PoC - Main Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import documents
from app.db.database import init_db

app = FastAPI(
    title="Medical Chart Extraction PoC",
    description="Extract structured data from unstructured medical charts (PDF/CCDA)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "Medical Chart Extraction PoC"}
