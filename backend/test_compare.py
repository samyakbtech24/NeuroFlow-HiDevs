import asyncio
import httpx
import json
import time

async def test_pipelines():
    print("Testing Pipeline Creation and Comparison...")
    
    # 1. Create Pipeline A (Legal Research)
    config_a = {
        "name": "legal-research-v1",
        "description": "Dense retrieval for legal docs",
        "ingestion": {
            "chunking_strategy": "hierarchical",
            "chunk_size_tokens": 400,
            "chunk_overlap_tokens": 80,
            "extractors_enabled": ["pdf"]
        },
        "retrieval": {
            "dense_k": 30,
            "sparse_k": 0,
            "reranker": None,
            "top_k_after_rerank": 5,
            "query_expansion": False,
            "metadata_filters_enabled": False
        },
        "generation": {
            "model_routing": {"task_type": "rag_generation", "max_cost_per_call": 0.05},
            "max_context_tokens": 6000,
            "temperature": 0.1,
            "system_prompt_variant": "precise"
        },
        "evaluation": {
            "auto_evaluate": True,
            "training_threshold": 0.82
        }
    }
    
    # 2. Create Pipeline B (Customer Support)
    config_b = {
        "name": "support-chat-v1",
        "description": "Fast keyword retrieval",
        "ingestion": {
            "chunking_strategy": "fixed",
            "chunk_size_tokens": 200,
            "chunk_overlap_tokens": 20,
            "extractors_enabled": ["text"]
        },
        "retrieval": {
            "dense_k": 5,
            "sparse_k": 15,
            "reranker": None,
            "top_k_after_rerank": 5,
            "query_expansion": False,
            "metadata_filters_enabled": False
        },
        "generation": {
            "model_routing": {"task_type": "rag_generation", "max_cost_per_call": 0.01},
            "max_context_tokens": 2000,
            "temperature": 0.7,
            "system_prompt_variant": "friendly"
        },
        "evaluation": {
            "auto_evaluate": False,
            "training_threshold": None
        }
    }

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Create A
        res_a = await client.post("/pipelines", json=config_a)
        assert res_a.status_code == 200, res_a.text
        id_a = res_a.json()["pipeline_id"]
        print(f"Created Pipeline A: {id_a}")
        
        # Create B
        res_b = await client.post("/pipelines", json=config_b)
        assert res_b.status_code == 200, res_b.text
        id_b = res_b.json()["pipeline_id"]
        print(f"Created Pipeline B: {id_b}")
        
        # Test Compare Endpoint
        print("\nExecuting POST /pipelines/compare...")
        start = time.time()
        res_cmp = await client.post("/pipelines/compare", json={
            "query": "What is the liability clause?",
            "pipeline_a_id": id_a,
            "pipeline_b_id": id_b
        }, timeout=30.0)
        duration = time.time() - start
        
        print(f"Compare Request Status: {res_cmp.status_code} (took {duration:.2f}s)")
        print(json.dumps(res_cmp.json(), indent=2))
        
        # Wait a second for background evals
        await asyncio.sleep(2)
        
        # Test Analytics endpoint
        print("\nExecuting GET /pipelines/{id_a}/analytics...")
        res_analytics = await client.get(f"/pipelines/{id_a}/analytics")
        print(json.dumps(res_analytics.json(), indent=2))
        
if __name__ == "__main__":
    asyncio.run(test_pipelines())
