# ADR 002: Document Chunking Strategy

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

Retrieval quality in a RAG system depends heavily on how source documents are divided into chunks before embedding. Chunks that are too small lose context, while chunks that are too large reduce retrieval precision.

Three strategies were evaluated.

| Strategy | Advantages | Limitations |
|----------|------------|-------------|
| Fixed-size | Fast, simple, predictable | May split sentences and concepts |
| Sentence-aware | Preserves readability | Can create uneven chunk sizes |
| Semantic | Groups related ideas together | Higher computational cost |

## Decision

The primary chunking strategy will be **semantic chunking**, with **fixed-size chunking as a fallback** when semantic segmentation is unavailable or processing speed is prioritized.

Semantic chunking groups content based on meaning rather than arbitrary token limits, producing more coherent embeddings and improving retrieval quality.

Typical chunks will target approximately **400–600 tokens** with a small overlap to preserve context across chunk boundaries.

## Consequences

### Positive

- Better semantic coherence
- Improved retrieval accuracy
- Reduced context fragmentation
- Higher answer quality during generation

### Negative

- Additional preprocessing time
- Increased implementation complexity
- Slightly higher ingestion cost

## Future Considerations

If the system must process very large document collections or support real-time ingestion, fixed-size chunking may be used to reduce preprocessing latency. The chunking component is designed to be configurable so strategies can be swapped without affecting downstream services.