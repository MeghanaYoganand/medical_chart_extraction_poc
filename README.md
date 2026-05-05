# Medical Chart Extraction System

## Overview

This project extracts structured medical information from unstructured clinical documents using regex and rule-based parsing.

## Features

* Extracts patient demographics (Name, DOB, MRN)
* Parses encounter details from clinical text
* Handles OCR-based medical documents
* Validation for incorrect/missing values
* Fallback logic for low-confidence extraction

## Architecture

1. Document Classification
2. Parsing (Regex + Rule-based)
3. Data Structuring (Schemas)
4. Validation & Fallback Handling

## Tech Stack

* Python
* FastAPI
* Regex-based parsing

## How to Run

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Sample Input

Clinical text / CCDA XML

## Output

Structured JSON with extracted fields

## Improvements Done

* Improved regex accuracy
* Added validation for MRN/DOB
* OCR handling improvements
* Low-confidence flagging
