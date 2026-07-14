import asyncio
import json
import os
import sys
from scipy.stats import pearsonr

# Add parent directory to path to allow importing packages
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.metrics.faithfulness import evaluate_faithfulness

async def run_calibration():
    print("--- Running Judge Faithfulness Calibration Check ---")
    
    # 1. Load annotated set
    base_dir = os.path.dirname(os.path.abspath(__file__))
    set_path = os.path.join(base_dir, "calibration", "annotated_set.json")
    
    with open(set_path, "r", encoding="utf-8") as f:
        annotated_set = json.load(f)
        
    print(f"Loaded {len(annotated_set)} annotated calibration examples.")
    
    # 2. Run automated evaluator faithfulness metric
    human_scores = []
    automated_scores = []
    
    for idx, item in enumerate(annotated_set):
        query = item["query"]
        context = item["context"]
        answer = item["answer"]
        human_score = item["human_score"]
        
        # Calculate automated score
        auto_score = await evaluate_faithfulness(query, answer, context)
        
        human_scores.append(human_score)
        automated_scores.append(auto_score)
        
        print(f"Sample {idx+1:02d}: Human={human_score:.1f} | Automated={auto_score:.4f}")

    # 3. Calculate Pearson correlation using SciPy
    r_coefficient, p_value = pearsonr(automated_scores, human_scores)
    
    print("\n--- Calibration Results ---")
    print(f"Pearson Correlation Coefficient (r): {r_coefficient:.6f}")
    print(f"P-value:                              {p_value:.6e}")
    
    status = "passed" if r_coefficient > 0.85 else "failed"
    results_payload = {
        "pearson_correlation": round(r_coefficient, 6),
        "p_value": p_value,
        "samples_count": len(annotated_set),
        "status": status
    }
    
    # 4. Write results to calibration_results.json
    results_path = os.path.join(base_dir, "calibration_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)
        
    print(f"Saved calibration results to: {results_path}")
    
    # 5. Assert quality threshold gate
    assert r_coefficient > 0.85, f"Calibration failed: Pearson correlation {r_coefficient:.4f} is not > 0.85"
    print("Pearson correlation check PASSED successfully! (r > 0.85)")

if __name__ == "__main__":
    asyncio.run(run_calibration())
