# ADR 001: Selection of pgvector as the Vector Store

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

The RAG system requires a vector database to store document embeddings and perform similarity search. The solution should support semantic retrieval, metadata filtering, and simple deployment while remaining suitable for a university project. The primary options considered were Pinecone, Weaviate, Qdrant, and PostgreSQL with the pgvector extension.

| Option | Advantages | Limitations |
|--------|------------|-------------|
| Pinecone | Fully managed, highly scalable | Paid service, vendor lock-in |
| Weaviate | Rich feature set, hybrid search | Higher operational complexity |
| Qdrant | Excellent vector performance | Requires separate infrastructure |
| PostgreSQL + pgvector | Unified relational and vector storage, free, SQL support | Less suitable for very large-scale deployments |

## Decision

The project will use **PostgreSQL with the pgvector extension** as the primary vector store.

This approach allows embeddings, document metadata, evaluation results, and application data to reside within a single database. It simplifies deployment, reduces operational overhead, and provides sufficient retrieval performance for the expected project scale.

The retrieval layer will use pgvector for dense similarity search alongside keyword search and metadata filtering to implement hybrid retrieval.

## Consequences

### Positive

- Single database for structured and vector data
- Simplified backup and deployment
- No vendor lock-in or licensing costs
- Native SQL support for filtering and analytics
- Well suited for small-to-medium RAG workloads

### Negative

- Lower scalability compared to dedicated vector databases
- Advanced vector indexing features are more limited
- May require migration to a specialized vector database as data volume grows

## Rationale

Given the project's educational scope and expected workload, pgvector provides the best balance between simplicity, maintainability, and functionality while still reflecting common production practices.