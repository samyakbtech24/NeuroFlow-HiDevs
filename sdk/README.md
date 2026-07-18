# NeuroFlow Python SDK

A minimal but complete asynchronous Python client for integrating with the NeuroFlow API.

## Installation
```bash
pip install ./sdk
```

## Quickstart

```python
import asyncio
from neuroflow import NeuroFlowClient

async def main():
    client = NeuroFlowClient(base_url="https://api.neuroflow.ai", api_key="your_jwt_secret")
    
    # Ingest a file
    doc = await client.ingest_file("test.pdf", pipeline_id="default")
    print(f"Ingested document: {doc.id}")
    
    # Run a streaming query
    async for token in client.query("What is NeuroFlow?", pipeline_id="default", stream=True):
        print(token, end="")

if __name__ == "__main__":
    asyncio.run(main())
```
