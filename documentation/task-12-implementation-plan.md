# Task 12: Full Observability Stack Implementation Plan

This plan covers the implementation of a full-scale Observability Stack to monitor the NeuroFlow RAG Subsystem. This includes tracing via OpenTelemetry (Jaeger) and metrics collection via Prometheus and Grafana.

## Proposed Changes

### Setup & Infrastructure
- **Branch Strategy:** Checkout `task-11`, branch to `task-12`.
- **Dependencies:** Add Prometheus client libraries, OpenTelemetry SDKs, and exporter configurations.
- **Docker Compose:** Introduce `prometheus` and `grafana` containers into `infra/docker-compose.yml`.

---

### Distributed Tracing (OpenTelemetry)
- **[NEW]** Wrap the core RAG lifecycle inside OpenTelemetry spans.
- **[MODIFY]** `pipelines/retrieval/retriever.py`: Add tracing spans (`retrieval.dense`, `retrieval.sparse`, `retrieval.rerank`) to track precise latency of vector DB calls.
- **[MODIFY]** `pipelines/generation/generator.py`: Wrap LLM generation steps in spans (`generation.llm_call`) to capture the exact timing of API calls to AI providers.
- **[MODIFY]** `evaluation/judge.py`: Wrap parallel LLM evaluation checks in spans (`evaluation.faithfulness`, `evaluation.relevance`) to monitor automated grading latencies.

---

### Custom Prometheus Metrics
- **[NEW]** `backend/monitoring/metrics.py`: Initialize a central metrics registry.
- **[MODIFY]** Register and update the following custom metrics:
  - **Latency Histograms:** Track exact timing distributions of ingestion, retrieval, generation, and evaluation phases.
  - **Token & Cost Counters:** Accumulate token counts used during LLM generation.
  - **Gauge Monitoring:** Track queue depths and the state of any open circuit breakers to detect localized failures.
- **[MODIFY]** `backend/main.py`: Expose a raw `/metrics` endpoint to serve the Prometheus text-format scrape output.

---

### Alerting & Dashboards (Prometheus/Grafana)
- **[NEW]** `infra/prometheus/prometheus.yml`: Configure scraping intervals to pull `/metrics` from the FastAPI backend.
- **[NEW]** `infra/prometheus/alerts.yml`: Define alerting thresholds:
  - `HighEvaluationFailureRate`
  - `CircuitBreakerOpen`
  - `QueueDepthHigh`
- **[NEW]** `infra/grafana/provisioning/`: Set up auto-provisioning configs so Grafana initializes datasources automatically.
- **[NEW]** `infra/grafana/dashboards/`: Create raw JSON dashboard definitions for a "System Overview" and a "Quality Monitor".
