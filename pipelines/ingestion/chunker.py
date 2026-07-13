import re
import uuid
import logging
from typing import List, Dict, Optional
import tiktoken

from pipelines.ingestion.extractors.extracted_page import ExtractedPage
from backend.providers.client import NeuroFlowClient

logger = logging.getLogger("chunker")

# Encoding for token counting
ENCODING = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(ENCODING.encode(text))

def split_into_sentences(text: str) -> List[str]:
    """
    Splits text into sentences based on punctuation, preserving sentence endings.
    """
    sentence_endings = re.compile(r'(?<=[.!?])\s+')
    return [s.strip() for s in sentence_endings.split(text) if s.strip()]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """
    Computes cosine similarity between two vector lists.
    """
    dot_product = sum(x * y for x, y in zip(v1, v2))
    magnitude1 = sum(x * x for x in v1) ** 0.5
    magnitude2 = sum(x * x for x in v2) ** 0.5
    if magnitude1 * magnitude2 == 0:
        return 0.0
    return dot_product / (magnitude1 * magnitude2)

def chunk_fixed_size(text: str, max_tokens: int = 512, overlap_tokens: int = 64) -> List[Dict]:
    """
    Splits text into chunks of max_tokens size, with sentence boundaries respected.
    Ensures sentence breaks occur within 10% of the target size, avoiding mid-sentence cuts.
    """
    sentences = split_into_sentences(text)
    chunks = []
    
    current_sentences = []
    current_tokens = 0
    
    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)
        if sentence_tokens > max_tokens:
            # If a single sentence exceeds the maximum, split it by words
            words = sentence.split()
            for i in range(0, len(words), 100):
                word_chunk = " ".join(words[i : i + 100])
                chunks.append({
                    "id": str(uuid.uuid4()),
                    "content": word_chunk,
                    "parent_id": None,
                    "metadata": {}
                })
            continue

        if current_tokens + sentence_tokens <= max_tokens:
            current_sentences.append(sentence)
            current_tokens += sentence_tokens
        else:
            # Save current chunk
            chunks.append({
                "id": str(uuid.uuid4()),
                "content": " ".join(current_sentences),
                "parent_id": None,
                "metadata": {}
            })
            
            # Form overlap: keep sentences from the end of current chunk
            overlap_sentences = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tokens = count_tokens(s)
                if overlap_count + s_tokens <= overlap_tokens:
                    overlap_sentences.insert(0, s)
                    overlap_count += s_tokens
                else:
                    break
            
            current_sentences = overlap_sentences + [sentence]
            current_tokens = overlap_count + sentence_tokens
            
    if current_sentences:
        chunks.append({
            "id": str(uuid.uuid4()),
            "content": " ".join(current_sentences),
            "parent_id": None,
            "metadata": {}
        })
        
    return chunks

async def chunk_semantic(text: str, similarity_threshold: float = 0.7, max_chunk_tokens: int = 512) -> List[Dict]:
    """
    Splits text by identifying topic shifts.
    Embeds each sentence and splits where adjacent sentence similarity drops below 0.7.
    """
    sentences = split_into_sentences(text)
    if not sentences:
        return []
        
    client = NeuroFlowClient()
    
    # Generate embeddings for all sentences
    try:
        embeddings = await client.embed(sentences)
    except Exception as e:
        logger.error(f"Failed to generate embeddings for semantic chunking: {e}. Falling back to fixed size.")
        return chunk_fixed_size(text)

    chunks = []
    current_sentences = [sentences[0]]
    current_tokens = count_tokens(sentences[0])
    
    for i in range(1, len(sentences)):
        sim = cosine_similarity(embeddings[i - 1], embeddings[i])
        sentence_tokens = count_tokens(sentences[i])
        
        # Split if similarity drops below threshold OR if chunk size exceeds limit
        if sim < similarity_threshold or (current_tokens + sentence_tokens > max_chunk_tokens):
            chunks.append({
                "id": str(uuid.uuid4()),
                "content": " ".join(current_sentences),
                "parent_id": None,
                "metadata": {"similarity_before_split": sim}
            })
            current_sentences = [sentences[i]]
            current_tokens = sentence_tokens
        else:
            current_sentences.append(sentences[i])
            current_tokens += sentence_tokens
            
    if current_sentences:
        chunks.append({
            "id": str(uuid.uuid4()),
            "content": " ".join(current_sentences),
            "parent_id": None,
            "metadata": {}
        })
        
    return chunks

def chunk_hierarchical(pages: List[ExtractedPage]) -> List[Dict]:
    """
    Creates chunks with parent-child section nesting.
    Top-level heading pages (e.g. h1 level) are treated as parent chunks,
    and subsequent sub-section pages are linked as child chunks.
    """
    chunks = []
    last_parent_id = None
    
    for page in pages:
        page_metadata = page.metadata or {}
        level = page_metadata.get("level", "")
        
        chunk_id = str(uuid.uuid4())
        
        # Treat h1 or h2 as parent sections
        is_parent = level in ("h1", "h2")
        
        parent_id = None
        if is_parent:
            last_parent_id = chunk_id
        else:
            # Normal text pages inherit the parent ID
            parent_id = last_parent_id
            
        chunks.append({
            "id": chunk_id,
            "content": page.content,
            "parent_id": parent_id,
            "metadata": {
                "page_number": page.page_number,
                "section": page_metadata.get("section", ""),
                "is_parent": is_parent
            }
        })
        
    return chunks

async def chunk_document(pages: List[ExtractedPage], document_metadata: Dict) -> List[Dict]:
    """
    Selects chunking strategy automatically:
    - If all pages are tables -> fixed_size.
    - If DOCX with headings metadata -> hierarchical.
    - If PDF and page count > 50 -> semantic.
    - Default -> fixed_size.
    """
    source_type = document_metadata.get("source_type", "")
    page_count = len(pages)
    
    # Rule 1: Table content type check
    all_tables = all(p.content_type == "table" for p in pages)
    if all_tables:
        logger.info("Auto-selected fixed_size chunking for table-only document.")
        combined_text = "\n\n".join(p.content for p in pages)
        return chunk_fixed_size(combined_text)
        
    # Rule 2: Heading structure check (DOCX with headings)
    has_headings = any("level" in (p.metadata or {}) for p in pages)
    if source_type == "docx" and has_headings:
        logger.info("Auto-selected hierarchical chunking for structured DOCX.")
        return chunk_hierarchical(pages)
        
    # Rule 3: PDF > 50 pages check
    if source_type == "pdf" and page_count > 50:
        logger.info("Auto-selected semantic chunking for long PDF.")
        combined_text = "\n\n".join(p.content for p in pages)
        return await chunk_semantic(combined_text)
        
    # Default: fixed_size
    logger.info("Auto-selected default fixed_size chunking.")
    combined_text = "\n\n".join(p.content for p in pages)
    return chunk_fixed_size(combined_text)
