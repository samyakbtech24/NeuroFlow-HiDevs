import re
import json
import uuid
import os
from typing import List, Dict, Any
from backend.db.pool import get_pool

# Basic regex to catch emails and phone numbers
PII_REGEX = re.compile(r"[\w\.-]+@[\w\.-]+|\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")

async def extract_training_data(job_id: uuid.UUID) -> str:
    """
    Finds high-quality training pairs from the database and formats them for OpenAI fine-tuning.
    Returns the file path to the generated JSONL file.
    """
    pool = get_pool()
    valid_pairs = []
    
    async with pool.acquire() as conn:
        # 1. Fetch potential training pairs from the database
        rows = await conn.fetch("""
            SELECT 
                tp.id, tp.system_prompt, tp.user_message, tp.assistant_message, 
                tp.quality_score, e.user_rating, e.faithfulness
            FROM training_pairs tp
            JOIN evaluations e ON tp.run_id = e.run_id
            WHERE tp.quality_score >= 0.82 
            AND tp.included_in_job IS NULL
        """)
        
        # 2. Validate each pair
        for row in rows:
            # Check user rating (must be 4+ or unrated)
            if row['user_rating'] is not None and row['user_rating'] < 4:
                continue
                
            # Check faithfulness (must be > 0.8)
            if row['faithfulness'] is None or row['faithfulness'] <= 0.8:
                continue
                
            assistant_msg = row['assistant_message']
            user_msg = row['user_message']
            
            # Simple token estimation (approx 4 chars per token)
            token_count = len(assistant_msg) / 4
            if token_count < 50 or token_count > 2000:
                continue
                
            # Must contain a citation
            if "[Source " not in assistant_msg:
                continue
                
            # Must not contain PII
            if PII_REGEX.search(user_msg):
                continue
                
            # If all checks pass, format it for OpenAI
            valid_pairs.append({
                "db_id": row['id'],
                "quality_score": row['quality_score'],
                "messages": [
                    {"role": "system", "content": row['system_prompt'] or "You are a precise research assistant."},
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": assistant_msg}
                ]
            })

        if not valid_pairs:
            return ""

        # 3. Write to a JSONL file
        os.makedirs("training_data", exist_ok=True)
        file_path = f"training_data/{job_id}.jsonl"
        with open(file_path, "w", encoding="utf-8") as f:
            for pair in valid_pairs:
                f.write(json.dumps({"messages": pair["messages"]}) + "\n")
                
        # 4. Mark these pairs as included in this job
        pair_ids = [p["db_id"] for p in valid_pairs]
        await conn.execute(
            "UPDATE training_pairs SET included_in_job = $1 WHERE id = ANY($2)",
            job_id, pair_ids
        )
        
        return file_path
