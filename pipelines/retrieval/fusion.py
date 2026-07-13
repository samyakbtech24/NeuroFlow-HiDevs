from typing import List, Dict

def reciprocal_rank_fusion(
    result_lists: List[List],
    k: int = 60
) -> List:
    """
    Applies Reciprocal Rank Fusion (RRF) to combine multiple ranked lists of chunks.
    Formula: score(d) = sum( 1 / (k + rank_m(d)) ) across all lists m where d appears.
    k: constant parameter (default 60).
    """
    from pipelines.retrieval.retriever import RetrievalResult
    
    rrf_scores: Dict[str, float] = {}  # Map of chunk_id -> RRF score
    chunk_data: Dict[str, RetrievalResult] = {}  # Map of chunk_id -> RetrievalResult template

    for r_list in result_lists:
        # Each list is sorted descending by its own search score,
        # so the index + 1 is the 1-based rank of the chunk.
        for rank_idx, result in enumerate(r_list):
            chunk_id = result.chunk_id
            rank = rank_idx + 1
            
            # Initialize chunk template if we haven't seen it yet
            if chunk_id not in chunk_data:
                chunk_data[chunk_id] = result
                
            # Add to reciprocal rank score
            score_contrib = 1.0 / (k + rank)
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + score_contrib

    # Reassemble results with their new RRF scores
    fused_results = []
    for chunk_id, score in rrf_scores.items():
        original_res = chunk_data[chunk_id]
        fused_results.append(RetrievalResult(
            chunk_id=chunk_id,
            document_id=original_res.document_id,
            content=original_res.content,
            score=score,
            metadata=original_res.metadata
        ))

    # Sort results by RRF score descending
    fused_results.sort(key=lambda x: x.score, reverse=True)
    return fused_results
