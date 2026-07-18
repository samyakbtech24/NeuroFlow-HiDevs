import asyncio
import os
from neuroflow.client import NeuroFlowClient

async def main():
    print("Initializing NeuroFlow SDK...")
    # Initialize client (uses dummy base URL for example)
    client = NeuroFlowClient(base_url="http://localhost:8000", api_key=os.getenv("JWT_SECRET_KEY", "dev-key"))
    
    print("Ingesting test file...")
    doc = await client.ingest_file("test_doc.pdf", pipeline_id="default")
    print(f"Document successfully ingested with ID: {doc.id}")
    
    print("Executing streaming query...")
    # Run a streaming query and print tokens as they arrive
    generator = await client.query("Summarize the document?", pipeline_id="default", stream=True)
    async for token in generator:
        print(token, end="", flush=True)
    print("\nQuery complete.")

if __name__ == "__main__":
    asyncio.run(main())
