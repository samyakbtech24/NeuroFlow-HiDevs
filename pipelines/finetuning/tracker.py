import mlflow
import uuid

def log_fine_tuning_run(job_id: uuid.UUID, base_model: str, pair_count: int, jsonl_path: str) -> str:
    """
    Logs the fine-tuning experiment to MLflow for easy reproducibility.
    """
    # Connect to our local MLflow server
    mlflow.set_tracking_uri("http://mlflow:5000")
    mlflow.set_experiment("Fine-Tuning Jobs")
    
    with mlflow.start_run(run_name=f"finetune-{job_id}") as run:
        # Log the basic parameters
        mlflow.log_params({
            "base_model": base_model,
            "training_pair_count": pair_count
        })
        
        # Upload the JSONL dataset so we can download it later if needed
        mlflow.log_artifact(jsonl_path)
        
        return run.info.run_id

def update_fine_tuning_metrics(mlflow_run_id: str, training_loss: float, validation_loss: float):
    """
    Called after the job finishes to log final model metrics.
    """
    mlflow.set_tracking_uri("http://mlflow:5000")
    with mlflow.start_run(run_id=mlflow_run_id):
        mlflow.log_metrics({
            "training_loss": training_loss,
            "validation_loss": validation_loss
        })
