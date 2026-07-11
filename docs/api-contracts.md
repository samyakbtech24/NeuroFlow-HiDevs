# REST API Contracts

## Authentication

Unless stated otherwise, all endpoints require:

```
Authorization: Bearer <JWT>
```

Default Rate Limit

- 100 requests/minute per user

---

# POST /ingest

### Purpose

Upload documents or URLs for indexing.

### Request

```json
{
  "source_type": "pdf",
  "source": "document.pdf",
  "metadata": {
    "department": "research"
  }
}
```

### Response

```json
{
  "ingestion_id": "ing_001",
  "status": "processing",
  "message": "Ingestion started."
}
```

Errors

| Code | Meaning |
|------|----------|
|400|Invalid request|
|401|Unauthorized|
|413|File too large|
|415|Unsupported file type|
|500|Internal error|

---

# POST /query

### Purpose

Execute a RAG query.

### Request

```json
{
  "query":"What is Retrieval-Augmented Generation?",
  "top_k":5,
  "pipeline":"default"
}
```

### Response

```json
{
  "query_id":"q123",
  "status":"streaming",
  "sources":5
}
```

Errors

400, 401, 404, 429, 500

---

# GET /query/{query_id}/stream

### Purpose

Stream generated tokens using Server-Sent Events.

### Response (SSE)

```
data: {"token":"Retrieval"}

data: {"token":"Augmented"}

data: {"done":true}
```

Errors

404, 500

---

# GET /evaluations

### Purpose

Retrieve evaluation history.

### Query Parameters

- page
- page_size

### Response

```json
{
  "total":120,
  "items":[
    {
      "query_id":"q123",
      "faithfulness":0.94,
      "relevance":0.91,
      "precision":0.88,
      "recall":0.90
    }
  ]
}
```

Errors

401, 500

---

# GET /evaluations/aggregate

### Purpose

Retrieve rolling evaluation metrics.

### Response

```json
{
  "avg_faithfulness":0.92,
  "avg_relevance":0.90,
  "avg_precision":0.88,
  "avg_recall":0.89
}
```

---

# POST /pipelines

### Purpose

Create a reusable pipeline configuration.

### Request

```json
{
  "name":"default",
  "embedding_model":"bge-small",
  "llm":"gemini",
  "top_k":5
}
```

### Response

```json
{
  "pipeline_id":"pipe001",
  "status":"created"
}
```

Errors

400, 401, 409

---

# GET /pipelines/{id}/runs

### Purpose

Retrieve execution history for a pipeline.

### Response

```json
{
  "pipeline":"default",
  "runs":[
    {
      "run_id":"run001",
      "status":"completed",
      "duration_ms":542
    }
  ]
}
```

Errors

401, 404

---

# POST /finetune/jobs

### Purpose

Submit a fine-tuning job.

### Request

```json
{
  "dataset":"high_quality_v1",
  "base_model":"gemini"
}
```

### Response

```json
{
  "job_id":"ft001",
  "status":"queued"
}
```

Errors

400, 401, 500

---

# GET /finetune/jobs/{id}

### Purpose

Retrieve job status.

### Response

```json
{
  "job_id":"ft001",
  "status":"running",
  "progress":72,
  "metrics":{
    "loss":0.18
  }
}
```

Errors

401, 404

---

# GET /health

### Purpose

Health check endpoint.

Authentication

Not required.

### Response

```json
{
  "status":"healthy"
}
```

---

# GET /metrics

### Purpose

Expose Prometheus-compatible metrics.

Authentication

Admin only.

### Response

```
requests_total 1532
rag_latency_ms 428
cpu_usage 31
memory_usage 62
```

---

# Common Error Format

```json
{
  "error": {
    "code": 400,
    "message": "Validation failed."
  }
}
```

---

# HTTP Status Codes

| Code | Description |
|------|-------------|
|200|Success|
|201|Created|
|202|Accepted|
|400|Bad Request|
|401|Unauthorized|
|403|Forbidden|
|404|Not Found|
|409|Conflict|
|413|Payload Too Large|
|415|Unsupported Media Type|
|429|Rate Limit Exceeded|
|500|Internal Server Error|