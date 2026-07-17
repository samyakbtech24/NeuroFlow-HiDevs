# NeuroFlow

NeuroFlow is an enterprise-grade Retrieval-Augmented Generation (RAG) platform designed for scalable document processing, dynamic model routing, and automated continuous improvement. 

## Technical Architecture

The system is built on a modular, asynchronous microservices architecture utilizing FastAPI, PostgreSQL, and Redis. It enforces strict production resilience patterns and supports zero-downtime A/B testing of generation pipelines.

### Core Systems

- **Asynchronous Ingestion Engine:** Supports multiprotocol document ingestion (PDF, DOCX, CSV, Images, URLs) with automated deduplication (SHA-256 hashing). Utilizes background workers for OCR, table extraction, and semantic chunking.
- **Dynamic Model Routing:** Features a fallback-capable routing system interfacing with OpenAI, Anthropic, and Gemini. Routes requests based on dynamic criteria including cost boundaries, latency budgets, and vision requirements.
- **Named Pipeline System:** Enables additive, backward-compatible iterations of RAG configurations. Each pipeline explicitly defines retrieval parameters (k-chunks, similarity thresholds) and generation parameters (temperature, model selection). Supports side-by-side A/B comparison for continuous tuning.
- **Automated Evaluation Framework:** Implements an LLM-as-Judge architecture utilizing RAGAS-inspired metrics (Faithfulness, Answer Relevance, Context Precision, and Context Recall). Calculates a weighted overall quality score to audit system performance autonomously.
- **Continuous Fine-Tuning Pipeline:** Automatically extracts high-quality (human-approved or highly-rated) context-response pairs, formats them into OpenAI-compliant JSONL schemas, and orchestrates simulated fine-tuning jobs. Lineage and loss metrics are tracked via a local MLflow container.

### Production Resilience

To maintain high availability under adverse conditions, the platform implements the following resilience layers:
- **Circuit Breakers:** Wraps all external LLM provider calls in a Redis-backed state machine. Circuits trip OPEN after 5 consecutive failures, failing fast to prevent cascading system hangs.
- **Token Bucket Rate Limiting:** Enforces strict LLM provider API quotas (e.g., 3000 requests/minute) globally across all concurrent workers using atomic Lua scripts.
- **Sliding Window API Limits:** Protects user-facing endpoints (`/ingest`, `/query`) from abuse using rolling timeframe limits.
- **Queue Backpressure:** Monitors the background ingestion queue (`queue:ingest`). Automatically returns 503 Service Unavailable when depth exceeds 100 items, pushing pressure back to the client.
- **Timeout Management:** Enforces explicit context-appropriate timeouts for all network operations (e.g., 10s for embeddings, 120s for evaluations) via `asyncio.wait_for`.

## Infrastructure

- **API:** FastAPI (Python 3.11)
- **Database:** PostgreSQL (pgvector for embeddings, asyncpg)
- **Cache & Queues:** Redis (aioredis)
- **Observability:** MLflow (Experiment tracking and Model Registry)

## Live Production Environment

The live API endpoint is accessible at: [PENDING_LIVE_URL]
