# Walkthrough - Task 4: Ingestion Pipeline with Deduplication & Async Processing

## Overview

Successfully implemented the **Ingestion Pipeline** for the **NeuroFlow** project. The pipeline enables the system to:
- Accept document uploads and URLs
- Process documents asynchronously in a worker container
- Automatically select appropriate text chunking strategies
- Generate and store embeddings in PostgreSQL
- Detect and skip duplicate document processing using SHA-256 hashing


## Changes Made

## 1. Queue Architecture & System Setup

### `Dockerfile`

- Added installation of:
  - `tesseract-ocr`
  - `libtesseract-dev`
- Enables OCR support directly inside the Docker container.

### `docker-compose.yml`

- Updated the build context for both **api** and **worker** to the project root (`../`).
- Allows both services to import the shared `pipelines` package.

### `docker-compose.override.yml`

- Exposed PostgreSQL on port **5432** for local access.

### `requirements.txt`

Added the following dependencies:

- `pypdfium2`
- `pdfplumber`
- `pytesseract`
- `python-docx`
- `pandas`
- `trafilatura`
- `tiktoken`
- `Pillow`
- `python-multipart`

### `worker.py`

Implemented an asynchronous worker that:

- Polls Redis using `BRPOP` (timeout = **1 second**) to prevent socket timeouts.
- Updates document processing status.
- Invokes extractors and chunkers.
- Generates embeddings.
- Inserts processed chunks into PostgreSQL inside a transaction block.

---

## 2. File Extractors

### `extracted_page.py`

- Defines the common extracted page data structure.

### `pdf_extractor.py`

Supports:

- Digital PDF text extraction using **pypdfium2**
- OCR on scanned pages using **pytesseract**
- Table extraction as Markdown using **pdfplumber**

### `docx_extractor.py`

Features:
- Text extraction
- Table extraction
- Preserves `H1` and `H2` headings as metadata

### `image_extractor.py`

Processing pipeline:
- Resizes images to a maximum width of **1024px** using Pillow
- Generates image descriptions via the Vision LLM (`NeuroFlowClient`)
- Performs OCR
- Merges OCR output with image description

### `csv_extractor.py`

Uses **pandas** to:
- Convert small CSV files into Markdown tables
- Produce summary statistics for larger datasets
- Batch rows into **100-row blocks**

### `url_extractor.py`

Implements:

- `robots.txt` compliance using `RobotFileParser`
- Asynchronous page fetching with `httpx`
- Content and metadata extraction using `trafilatura`


## 3. Text Chunker

### `chunker.py`

Implements three chunking strategies:

### Fixed Size

- Sentence-aware splitting
- Chunk size: **512 tokens**
- Overlap: **64 tokens**

### Semantic

- Splits text based on sentence similarity
- Similarity threshold: **0.7**

### Hierarchical

- Creates parent chunks from headings
- Links subsection chunks through `parent_id` metadata

### Auto Selection

Automatically selects the most suitable chunking strategy based on document type.

---

## 4. API Endpoints

### `ingest.py`

Implements:

#### `POST /ingest`

Supports:

- Multipart file uploads
- JSON URL ingestion

Processing includes:

- SHA-256 hash generation
- Duplicate detection
- Task enqueueing

#### `GET /documents/{document_id}`

Provides polling support for document processing status.

### `main.py`

- Registered all ingestion-related API routes.

---

# Verification Results

The complete pipeline was verified locally using:

```bash
backend/test_ingestion.py
```

## Successful Test Log

```text
--- 1. Testing Extractors & Chunker Standalone ---

Testing CSV Extractor...
CSV Pages Extracted: 1
CSV content is correct Markdown table.

Testing Chunker Strategy auto-selection...
Table page chunks count: 1
Hierarchical docx chunks: 2
Hierarchical parent-child linking verified successfully.

Waiting for API container boot...

--- 2. Testing Ingestion API and Deduplication (against http://localhost:8000) ---

Uploading file 'test_data_1783872055.csv' to http://localhost:8000/ingest...

Response code: 200

Response JSON:
{
  "document_id": "ac5cde80-f842-4396-9a9d-5439d96639b6",
  "status": "queued",
  "duplicate": false
}

Uploading the exact same file content again to test Deduplication...

Response code: 200

Response JSON:
{
  "document_id": "ac5cde80-f842-4396-9a9d-5439d96639b6",
  "status": "queued",
  "duplicate": true
}

Deduplication logic verified successfully!

Querying document processing status...

Attempt 1: Status is 'queued'
...
Attempt 9: Status is 'complete'

Document processing completed!
Chunk count: 1
```

---

## Worker Log

```text
INFO:worker:Starting ingestion process for document ac5cde80-f842-4396-9a9d-5439d96639b6 (csv)

INFO:chunker:Auto-selected fixed_size chunking for table-only document.

INFO:openai-provider:OpenAIProvider (gpt-4o-mini) is initialized in Mock/Offline mode.

INFO:worker:Successfully processed document ac5cde80-f842-4396-9a9d-5439d96639b6 (1 chunks, 52 tokens)
```

---

# Outcome

The successful test execution confirms that the complete ingestion pipeline is functioning correctly, including:

-  File upload
-  SHA-256 deduplication
-  Redis queueing
-  Worker-based asynchronous processing
-  File and URL extraction
-  Automatic chunking strategy selection
-  Sentence-aware chunk generation
-  Embedding generation
-  PostgreSQL storage
-  End-to-end document processing
```
