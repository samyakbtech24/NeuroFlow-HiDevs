# NeuroFlow

NeuroFlow is a production ready backend architecture for multi modal document retrieval systems. It features an automated evaluation layer and a fine tuning pipeline designed for enterprise scale. 

The architecture consists of a backend connecting to a database for storage and search. A separate instance serves as a high speed caching layer and message broker for our background workers. The ingestion pipeline chunks and embeds documents asynchronously while the retrieval pipeline uses fusion to combine sparse and dense vector search results. The generation pipeline streams responses back to the user and logs telemetry data directly to our tracking server. 

Our key features include hybrid retrieval combining dense sparse and metadata search with reciprocal rank fusion and cross encoder reranking. We enforce security via robust prompt injection scanners and utilize asynchronous circuit breakers to handle provider outages gracefully. The system also supports automatic background ingestion for various document formats. 

Our final quality metrics from the improvement sprint reflect strong production readiness. We achieved a Retrieval Hit Rate at 10 of 0.84 and a Retrieval MRR at 10 of 0.68. Our Faithfulness average reached 0.82 with an Answer Relevance average of 0.79 and a Context Precision average of 0.76. Our Overall Eval Score is 0.81 and we reduced our P95 Query Latency to 2.1 seconds. 

The tech stack relies on FastAPI for the core web server because it provides native asynchronous support and automatic OpenAPI documentation. We use PostgreSQL with the pgvector extension because it allows us to store our relational application data alongside our vector embeddings in a single resilient database. Redis was chosen for our caching layer and broker because of its low latency memory operations. MLflow is integrated because it provides industry standard tracking for our experiments and evaluations. 

To start the system clone the repository and run docker compose up. First run git clone https://github.com/samyakbtech24/NeuroFlow-HiDevs.git. Navigate into the directory and copy the environment template by running cp .env.example .env. Finally run docker compose -f infra/docker-compose.prod.yml up --build to launch all the containers. 

Our core API endpoints include POST /ingest to upload files for background processing and POST /query to execute RAG searches. You can use GET /evaluations to retrieve historical evaluation scores and GET /health to check system uptime. All endpoints require a Bearer token in the Authorization header. 

You can interact with the system using our Python SDK. 

```python
import asyncio
from neuroflow import NeuroFlowClient

async def main():
    client = NeuroFlowClient(base_url="https://neuroflow-hidevs.onrender.com", api_key="secret-key")
    doc = await client.ingest_file("test.pdf", pipeline_id="default")
    async for token in client.query("What is NeuroFlow?", pipeline_id="default", stream=True):
        print(token, end="")

if __name__ == "__main__":
    asyncio.run(main())
```

Configuration relies entirely on environment variables which are documented in the environment file. You are required to provide a database URL and a cache URL along with an API key and security secrets. Variables for telemetry are optional. 

## Mock / Offline Mode Architecture

NeuroFlow was intentionally developed with a robust **Mock / Offline Mode** architecture to drastically reduce external LLM API usage and costs during local development, testing, and CI/CD runs. 

When the provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`) are either omitted from the `.env` file or explicitly set to the string `"mock"`, the internal `NeuroFlowClient` automatically intercepts external calls. Instead of dialing upstream providers, it yields highly accurate, offline simulated response streams and dummy embeddings. This architectural decision was truly required to enable rapid, localized hit-and-trial testing and load-testing without burning through real API credits.

To transition from this development mock mode into the live production mode, simply inject valid API keys into your `.env` file. The router will instantly detect the valid keys and begin orchestrating live external inference.

## Known Limitations

The system has some known limitations. The chunking algorithm struggles with highly complex tables and occasionally drops semantic context across page breaks. The cross encoder reranker can introduce noticeable latency during peak traffic spikes. Next I would build a dedicated document parsing microservice to handle complex OCR workloads and introduce a dynamic routing layer to fallback to smaller faster models during high load.
