import pytest
from pipelines.ingestion.chunker import chunk_document
from pipelines.ingestion.extractors.extracted_page import ExtractedPage

@pytest.mark.asyncio
async def test_chunker_empty_document():
    chunks = await chunk_document([], {"source_type": "text", "filename": "test.txt"})
    assert len(chunks) == 0

@pytest.mark.asyncio
async def test_chunker_single_page():
    page = ExtractedPage(page_number=1, content="Hello world. " * 50, content_type="text", metadata={})
    chunks = await chunk_document([page], {"source_type": "text", "filename": "test.txt"})
    assert len(chunks) > 0

@pytest.mark.asyncio
async def test_chunker_maintains_metadata():
    page = ExtractedPage(page_number=1, content="Hello metadata. ", content_type="text", metadata={"test": 1})
    chunks = await chunk_document([page], {"source_type": "text", "filename": "test.txt"})
    assert "metadata" in chunks[0]

@pytest.mark.asyncio
async def test_chunker_handles_large_text():
    page = ExtractedPage(page_number=1, content="Large text. " * 1000, content_type="text", metadata={})
    chunks = await chunk_document([page], {"source_type": "text", "filename": "test.txt"})
    assert len(chunks) > 1

@pytest.mark.asyncio
async def test_chunker_chunk_size_limits():
    page = ExtractedPage(page_number=1, content="Limits text. " * 500, content_type="text", metadata={})
    chunks = await chunk_document([page], {"source_type": "text", "filename": "test.txt"})
    for chunk in chunks:
        assert len(chunk["content"]) > 0
