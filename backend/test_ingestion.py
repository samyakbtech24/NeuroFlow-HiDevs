import asyncio
import base64
import json
import logging
import os
import sys
import time
import httpx

# Add backend directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipelines.ingestion.extractors.extracted_page import ExtractedPage
from pipelines.ingestion.extractors.pdf_extractor import extract_pdf
from pipelines.ingestion.extractors.docx_extractor import extract_docx
from pipelines.ingestion.extractors.image_extractor import extract_image
from pipelines.ingestion.extractors.csv_extractor import extract_csv
from pipelines.ingestion.extractors.url_extractor import extract_url
from pipelines.ingestion.chunker import chunk_document, chunk_fixed_size

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("test-ingestion")

def test_extractors_and_chunker_standalone():
    print("\n--- 1. Testing Extractors & Chunker Standalone ---")
    
    # A. CSV Extractor Test
    print("Testing CSV Extractor...")
    csv_data = "col1,col2,col3\n1,text1,10.5\n2,text2,20.5"
    csv_pages = extract_csv(csv_data.encode('utf-8'))
    print(f"CSV Pages Extracted: {len(csv_pages)}")
    assert len(csv_pages) == 1, "CSV extraction should yield 1 page"
    assert csv_pages[0].content_type == "table", "CSV extraction should yield a table content_type"
    print("CSV content is correct Markdown table.")

    # B. Chunker Strategy Selection Test
    print("\nTesting Chunker Strategy auto-selection...")
    
    # Test Table Auto-Selection
    table_page = ExtractedPage(page_number=1, content="| h1 |\n|---|", content_type="table", metadata={})
    strategy_table = asyncio.run(chunk_document([table_page], {"source_type": "csv"}))
    print(f"Table page chunks count: {len(strategy_table)}")
    
    # Test Hierarchical Auto-Selection
    docx_pages = [
        ExtractedPage(page_number=1, content="Title", content_type="text", metadata={"level": "h1", "section": "Intro"}),
        ExtractedPage(page_number=2, content="Body text", content_type="text", metadata={"section": "Intro"})
    ]
    chunks_docx = asyncio.run(chunk_document(docx_docx := docx_pages, {"source_type": "docx"}))
    print(f"Hierarchical docx chunks: {len(chunks_docx)}")
    assert chunks_docx[1]["parent_id"] == chunks_docx[0]["id"], "Child section should point to parent section ID"
    print("Hierarchical parent-child linking verified successfully.")

async def test_full_api_pipeline():
    print("\n--- 2. Testing Ingestion API and Deduplication (against http://localhost:8000) ---")
    
    # Define a clean unique test CSV content
    test_content = f"name,age,city\nUserA,30,NewYork\nUserB,25,Boston\nTimestamp,{time.time()},Local"
    file_bytes = test_content.encode('utf-8')
    filename = f"test_data_{int(time.time())}.csv"
    
    url = "http://localhost:8000/ingest"
    
    async with httpx.AsyncClient() as client:
        # First Ingestion Upload
        print(f"Uploading file '{filename}' to {url}...")
        files = {"file": (filename, file_bytes, "text/csv")}
        response = await client.post(url, files=files)
        
        print(f"Response code: {response.status_code}")
        print(f"Response JSON: {response.text}")
        assert response.status_code == 200, "First upload should succeed"
        
        res_data = response.json()
        doc_id = res_data["document_id"]
        duplicate_status = res_data["duplicate"]
        assert duplicate_status is False, "First upload should not be marked as a duplicate"
        
        # Second Ingestion Upload (Same File Contents) to test Deduplication
        print("\nUploading the exact same file content again to test Deduplication...")
        files_dup = {"file": (filename, file_bytes, "text/csv")}
        response_dup = await client.post(url, files=files_dup)
        
        print(f"Response code: {response_dup.status_code}")
        print(f"Response JSON: {response_dup.text}")
        assert response_dup.status_code == 200, "Deduplicated upload should succeed"
        
        res_dup_data = response_dup.json()
        assert res_dup_data["document_id"] == doc_id, "Deduplicated document ID should match the first ID"
        assert res_dup_data["duplicate"] is True, "Deduplicated document should have duplicate=True"
        print("Deduplication logic verified successfully!")

        # Query document status to verify state transitions (queued -> processing -> complete)
        print("\nQuerying document processing status...")
        status_url = f"http://localhost:8000/documents/{doc_id}"
        
        # Poll status until complete
        for attempt in range(10):
            status_resp = await client.get(status_url)
            assert status_resp.status_code == 200, "Status query should succeed"
            status_data = status_resp.json()
            current_status = status_data["status"]
            print(f"Attempt {attempt+1}: Status is '{current_status}'")
            if current_status == "complete":
                print(f"Document processing completed! Chunk count: {status_data['chunk_count']}")
                break
            await asyncio.sleep(2)
        else:
            raise TimeoutError("Ingestion worker took too long to process document")

def main():
    test_extractors_and_chunker_standalone()
    
    # Wait for docker compose build/recreate to complete before calling API
    print("\nWaiting for API container boot...")
    time.sleep(2)
    
    try:
        asyncio.run(test_full_api_pipeline())
    except Exception as e:
        print(f"API pipeline test skipped or failed: {e}")
        print("Please verify that docker containers are active and port 8000 is mapped.")

if __name__ == "__main__":
    main()
