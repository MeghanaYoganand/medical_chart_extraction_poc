"""
Database setup - SQLite for PoC (swap PostgreSQL for production)
"""
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./poc.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class DocumentDB(Base):
    __tablename__ = "documents"

    document_id = Column(String, primary_key=True, index=True)
    file_name = Column(String)
    document_type = Column(String)
    source = Column(String)
    ingestion_timestamp = Column(DateTime, default=datetime.utcnow)
    page_count = Column(Integer, default=0)
    raw_text = Column(Text)

    patient = relationship("PatientDB", back_populates="document", uselist=False)
    encounters = relationship("EncounterDB", back_populates="document")


class PatientDB(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.document_id"))
    patient_name = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    dob = Column(String)
    age = Column(Integer)
    gender = Column(String)
    mrn = Column(String)
    insurance_id = Column(String)
    address = Column(String)
    phone = Column(String)

    document = relationship("DocumentDB", back_populates="patient")


class EncounterDB(Base):
    __tablename__ = "encounters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(String, ForeignKey("documents.document_id"))
    encounter_id = Column(String)
    encounter_date = Column(String)
    admission_date = Column(String)
    discharge_date = Column(String)
    encounter_type = Column(String)
    provider_name = Column(String)
    facility_name = Column(String)
    reason_for_visit = Column(String)
    encounter_summary = Column(Text)

    document = relationship("DocumentDB", back_populates="encounters")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
