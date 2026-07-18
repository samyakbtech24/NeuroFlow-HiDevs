# Architecture Runbook

This runbook provides diagnostic checklists and immediate remediation steps for the most common production incidents in the NeuroFlow platform.

## Incident 1 — High Query Latency (P95 > 10s)

**Checklist:**
- [ ] Check Jaeger traces to identify which specific span is slow (e.g., embedding generation, LLM generation, or database retrieval).
- [ ] Check Redis memory usage and cache hit rate in the infrastructure dashboard.
- [ ] Check Postgres query performance using `pg_stat_statements` to identify slow vector searches.

**Remediation:**
- Flush the Redis cache if it is thrashing.
- Add missing HNSW indexes to the Postgres pgvector tables if they were dropped.
- Scale API replicas horizontally to distribute incoming request load.

## Incident 2 — Evaluation Scores Degrading

**Checklist:**
- [ ] Check which specific pipeline and which metric (e.g., Faithfulness vs. Context Precision) is degrading in MLflow.
- [ ] Check recent ingested documents; low-quality or malformed input data directly leads to low-quality retrieval.
- [ ] Check MLflow for any recent fine-tuning job changes that may have deployed an overfit model.

**Remediation:**
- Revert the last fine-tuned model via the admin dashboard.
- Inspect and cleanse the training data quality.

## Incident 3 — LLM Provider Circuit Breaker Open

**Checklist:**
- [ ] Check `GET /health` to confirm the exact status of the LLM provider circuit breaker.
- [ ] Check the official provider status page (e.g., OpenAI or Anthropic status pages) for global outages.

**Remediation:**
- Wait for the recovery timeout to gracefully expire and transition the breaker to half-open.
- Manually force a reset via `POST /admin/circuit-breaker/reset` if the upstream provider has fully recovered.

## Incident 4 — Ingestion Queue Depth > 100

**Checklist:**
- [ ] Check `GET /health` to monitor real-time queue depth.
- [ ] Check background worker process logs for unhandled exceptions or OOM (Out of Memory) kills.

**Remediation:**
- Restart the worker containers to clear zombie processes.
- Check for stuck or corrupted jobs in the Redis message broker and clear them manually if necessary.

## Incident 5 — Database Disk Usage > 80%

**Checklist:**
- [ ] Check which table is growing the fastest (typically `chunks` or `pipeline_runs`).
- [ ] Check whether the automated data retention jobs are running and cleaning up old evaluations.

**Remediation:**
- Run the data retention job manually to immediately prune expired records.
- If storage remains critical, provision additional block storage to the database instance.
