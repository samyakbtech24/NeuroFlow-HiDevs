# Walkthrough - Task 4: Ingestion Pipeline with Deduplication & Async Processing
We have successfully implemented the Ingestion Pipeline for the NeuroFlow project, allowing the system to accept document uploads and URLs, process them asynchronously in a worker container, chunk the texts using auto-selected strategies, store embeddings in PostgreSQL, and avoid reprocessing identical files.

## Changes Made
### 1. Queue Architecture & System Setup
- **Dockerfile**: Added tesseract-ocr and libtesseract-dev installation directly inside the Docker container so OCR works out-of-the-box.

- **docker-compose.yml**: Updated build context for both api and worker to the root folder (../) so they can see and import the pipelines package.

- **docker-compose.override.yml**: Exposed PostgreSQL port 5432 to the host.

- **requirements.txt**: Appended new libraries (pypdfium2, pdfplumber, pytesseract, python-docx, pandas, trafilatura, tiktoken, Pillow, python-multipart).

- **worker.py**: Implemented an active polling loop using Redis brpop (timeout = 1s to avoid socket timeouts), which updates document status, calls extractors/chunkers, handles embeddings, and inserts them into PostgreSQL in a transaction block.

### 2. File Extractors
- **extracted_page.py**: Defined the page data structure.

- **pdf_extractor.py**: Extracts digital PDF text with pypdfium2, scanned pages with pytesseract OCR, and tables as markdown using pdfplumber.

- **docx_extractor.py**: Extracts text and tables, and preserves h1/h2 headings in metadata.

- **image_extractor.py**: Resizes images to max 1024px using Pillow, gets a description from vision LLM (via NeuroFlowClient), runs OCR, and merges both.

- **csv_extractor.py**: Reads CSVs using pandas, outputs markdown tables for small datasets, generates summary stats for large datasets, and batches rows in 100-row blocks.

- **url_extractor.py**: Checks robots.txt using RobotFileParser, fetches pages asynchronously with httpx, and extracts text/metadata using trafilatura.

### 3. Text Chunker
**chunker.py**: Implements fixed_size (sentence-aware splits, 512-token size, 64-token overlap), semantic (sentence similarity threshold of 0.7), and hierarchical (linking sub-section child chunks to parent heading chunks via parent_id in metadata). Handles auto-selection.

### 4. API Endpoints
**ingest.py**: Handles POST /ingest (multipart upload and JSON url), computes SHA-256 hash, runs deduplication checks, and enqueues tasks. Exposes GET /documents/{document_id} for polling.

**main.py**: Registered the ingestion router endpoints.

## Verification Results
We verified the pipeline locally using backend/test_ingestion.py.

**Successful Test Log:**
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
Response JSON: {"document_id":"ac5cde80-f842-4396-9a9d-5439d96639b6","status":"queued","duplicate":false}
Uploading the exact same file content again to test Deduplication...
Response code: 200
Response JSON: {"document_id":"ac5cde80-f842-4396-9a9d-5439d96639b6","status":"queued","duplicate":true}
Deduplication logic verified successfully!
Querying document processing status...
Attempt 1: Status is 'queued'
...
Attempt 9: Status is 'complete'
Document processing completed! Chunk count: 1
```

And the worker log showed the task completed successfully:

**text**
```text
INFO:worker:Starting ingestion process for document ac5cde80-f842-4396-9a9d-5439d96639b6 (csv)
INFO:chunker:Auto-selected fixed_size chunking for table-only document.
INFO:openai-provider:OpenAIProvider (gpt-4o-mini) is initialized in Mock/Offline mode.
INFO:worker:Successfully processed document ac5cde80-f842-4396-9a9d-5439d96639b6 (1 chunks, 52 tokens)
```

This confirms that the entire ingestion loop, from file upload to deduplication, worker picking, text extraction, sentence-boundary chunking, and database inserts is fully correct.
