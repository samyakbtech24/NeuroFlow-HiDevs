# Task 9: Fine-Tuning Pipeline — Config & Implementation Plan

This implementation plan details the architecture for the automated Fine-Tuning Pipeline. It covers how we extract high-quality data, track the experiments via MLflow, and automatically route queries to the new models.

## User Review Required

Please review the extraction logic and MLflow integration plan below. If the architecture aligns with your expectations, approve it so we can begin coding!

## 1. Automated Data Extraction (`extractor.py`)

**The Goal:** Automatically gather the highest quality RAG outputs from the system to create a dataset for fine-tuning.

**The How:**
We will query the database joining three tables: `training_pairs`, `pipeline_runs`, and `evaluations`. 
We will strictly filter for:
*   `quality_score >= 0.82`
*   `user_rating >= 4` (or `NULL` if not rated)
*   `faithfulness > 0.8`

We will then run Python Regex to scrub the data for PII (Personally Identifiable Information) like emails or phone numbers, and ensure the generated text is between 50 and 2000 tokens and contains at least one citation (`[Source N]`).

**The Why:**
In enterprise AI, **"Garbage In, Garbage Out" (GIGO)** is the golden rule of fine-tuning. If you accidentally train your model on unfaithful hallucinations or answers containing sensitive user data (PII), the model will memorize and repeat those flaws. Strict SQL filtering guarantees we only train on "gold standard" examples, and PII regex scrubbing ensures compliance with privacy regulations (like GDPR). 

## 2. MLflow Experiment Tracking (`tracker.py`)

**The Goal:** Keep a historical, auditable record of every fine-tuning experiment we run.

**The How:**
We will use the `mlflow` Python SDK. When a job starts, we will create an MLflow run (`finetune-{job_id}`). We will log parameters like `training_pair_count`, `avg_quality_score`, and `base_model`. We will also upload the `.jsonl` training dataset directly to MLflow as an artifact.

**The Why:**
Data Science is an iterative science. If a new fine-tuned model performs worse than the previous one, you need to know exactly *why*. By logging the exact `.jsonl` dataset and average quality scores to MLflow, engineers can look back at the experiment 6 months from now, download the exact dataset used, and reproduce the training run. This is known as **Experiment Reproducibility**, a core tenet of MLOps.

## 3. Dynamic Model Registration (`job_manager.py`)

**The Goal:** Automatically deploy the fine-tuned model once OpenAI finishes training it.

**The How:**
Once the fine-tuning job succeeds, we will execute an `UPDATE` on the Redis `router:models` key. We will inject the newly minted model ID into our system, setting `is_fine_tuned = True` and `fine_tuned_for_task = "rag_generation"`. 

**The Why:**
Manual deployments cause bottlenecks. By dynamically updating Redis (our central caching layer), our `ModelRouter` from Task 3 will instantly detect the new model across all distributed worker nodes without requiring a server restart. If a request comes in with `prefer_fine_tuned=True`, the router will seamlessly shift traffic to the newly trained model in real-time.

## 4. Mock Mode Strategy

As per your instructions from Task 8, we will continue operating in **Mock Mode** (`GEMINI_API_KEY=mock`). 
*   We will mock the actual API request to OpenAI's `/v1/fine_tuning/jobs` endpoint so we don't accidentally spend real money submitting test jobs.
*   The architecture (Extraction, MLflow Tracking, Redis Registration, and the APIs) will function 100% authentically, proving the system works.
