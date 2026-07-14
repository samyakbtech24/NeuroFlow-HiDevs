import logging
import re
from typing import List, Dict
import tiktoken

from pipelines.retrieval.retriever import RetrievalResult

logger = logging.getLogger("context-assembler")

def assemble_context(
    chunks: List[RetrievalResult], 
    token_budget: int = 4000,
    model_name: str = "cl100k_base"
) -> Dict:
    """
    Assembles the top-K reranked chunks into a structured context string,
    respecting a maximum token budget without truncating sentences in the middle.
    
    Returns:
        Dict: {
            "context": str,           # The assembled text
            "chunks_used": List[str], # IDs of the chunks included
            "total_tokens": int,      # Exact token count
            "sources": List[str]      # Names of files and pages used
        }
    """
    try:
        encoding = tiktoken.get_encoding(model_name)
    except Exception:
        # Fallback if the encoder isn't found
        encoding = tiktoken.get_encoding("cl100k_base")

    assembled_blocks: List[str] = []
    chunks_used: List[str] = []
    sources: List[str] = []
    
    current_tokens = 0
    
    for idx, chunk in enumerate(chunks, start=1):
        # 1. Determine the source descriptor
        filename = chunk.metadata.get("filename", "Unknown Document")
        page_number = chunk.metadata.get("page_number")
        
        if page_number is not None:
            source_str = f"Source {idx} — {filename}, page {page_number}"
        else:
            source_str = f"Source {idx} — {filename}"
            
        header = f"[{source_str}]\n"
        
        # 2. Check if we can fit the whole chunk + header
        full_block = f"{header}{chunk.content}\n\n"
        full_block_tokens = len(encoding.encode(full_block))
        
        if current_tokens + full_block_tokens <= token_budget:
            # The entire chunk fits
            assembled_blocks.append(full_block)
            current_tokens += full_block_tokens
            chunks_used.append(chunk.chunk_id)
            sources.append(source_str)
        else:
            # The entire chunk doesn't fit. Let's add sentence-by-sentence to avoid mid-sentence truncation.
            sentences = re.split(r'(?<=[.!?])\s+', chunk.content)
            
            # Start forming the partial block
            partial_content = ""
            partial_header_added = False
            
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                    
                # Test adding this sentence
                test_block = f"{header}{partial_content} {sentence}\n\n" if not partial_header_added else f"{partial_content} {sentence}"
                test_tokens = len(encoding.encode(test_block))
                
                if current_tokens + test_tokens <= token_budget:
                    # It fits! Update partial content
                    if not partial_header_added:
                        partial_content = f"{header}{sentence}"
                        partial_header_added = True
                        chunks_used.append(chunk.chunk_id)
                        sources.append(source_str)
                    else:
                        partial_content += f" {sentence}"
                else:
                    # Sentence exceeds budget, stop adding sentences
                    break
            
            if partial_content:
                # Add final trailing newlines to the partial block
                assembled_blocks.append(f"{partial_content}\n\n")
                current_tokens = len(encoding.encode("".join(assembled_blocks)))
            
            # We reached the token budget, stop processing further chunks
            break

    # Assemble the final context string and strip trailing whitespace
    context_str = "".join(assembled_blocks).strip()
    final_token_count = len(encoding.encode(context_str))
    
    return {
        "context": context_str,
        "chunks_used": chunks_used,
        "total_tokens": final_token_count,
        "sources": list(set(sources))  # Remove duplicates if any
    }
