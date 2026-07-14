import re
import uuid
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Since pipelines.retrieval.retriever is needed for annotations,
# we use string-forward references in our annotations to avoid circular imports.

@dataclass
class Citation:
    """
    Represents a verified document reference cited by the LLM.
    """
    reference: str            # e.g., "Source 1"
    chunk_id: uuid.UUID       # Database UUID of the chunk
    document_name: str        # Filename or URL
    page_number: Optional[int] # Page number (if PDF/Docx)
    content_preview: str      # First 100 characters of the cited chunk content

def parse_citations(generation_text: str, context_chunks: List[Any]) -> List[Dict[str, Any]]:
    """
    Parses all '[Source N]' citation patterns from the model's generated text,
    resolves them to metadata from the retrieved chunks, and flags invalid/hallucinated ones.
    
    Returns:
        List[Dict]: List of citation dictionaries. Invalid citations have 'invalid_citation': True.
    """
    # Find all occurrences of [Source N] where N is a digit
    matches = re.findall(r'\[Source (\d+)\]', generation_text)
    
    # De-duplicate indices while preserving the generation occurrence order
    seen = set()
    unique_source_indices = []
    for m in matches:
        val = int(m)
        if val not in seen:
            seen.add(val)
            unique_source_indices.append(val)
            
    resolved_citations = []
    for n in unique_source_indices:
        # 1-based Source number maps to 0-based list index
        chunk_idx = n - 1
        
        if 0 <= chunk_idx < len(context_chunks):
            chunk = context_chunks[chunk_idx]
            
            # Extract document identifiers from metadata
            source_type = chunk.metadata.get("source_type", "file")
            if source_type == "url":
                filename = chunk.metadata.get("url", "URL Source")
            else:
                filename = chunk.metadata.get("filename", "Unknown Document")
                
            page_number = chunk.metadata.get("page_number")
            
            resolved_citations.append({
                "source": f"Source {n}",
                "chunk_id": str(chunk.chunk_id),
                "document": filename,
                "page": page_number,
                "content_preview": chunk.content[:100],
                "invalid_citation": False
            })
        else:
            # Hallucinated citation: N is larger than the number of provided sources
            resolved_citations.append({
                "source": f"Source {n}",
                "invalid_citation": True
            })
            
    return resolved_citations
