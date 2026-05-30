# scripts/verify_optimization.py
import os
import json
import pandas as pd
from pathlib import Path
import sys
from dotenv import load_dotenv

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.monitor import PromptMonitor
from src.agent.analyzer import FailureAnalyzer
from src.agent.optimizer import PromptOptimizer
from src.agent.evaluator import ShadowEvaluator

load_dotenv()

PROMPTS_PATH = Path(__file__).parent.parent / "src" / "prompts.json"

def load_baseline_config() -> dict:
    """Load the current baseline customer support prompt config."""
    with open(PROMPTS_PATH) as f:
        data = json.load(f)
    return data["prompts"]["customer_support"]

def update_prompts_file(winner_config: dict):
    """Update src/prompts.json with the new winning system prompt configuration."""
    print(f"\n💾 Updating prompts configuration file at: {PROMPTS_PATH}")
    with open(PROMPTS_PATH) as f:
        data = json.load(f)
        
    original = data["prompts"]["customer_support"]
    
    # Increment optimization count
    opt_count = original.get("metadata", {}).get("optimization_count", 0) + 1
    
    # Create the updated customer_support structure
    updated_cs = {
        "id": "customer_support",
        "version": "1.1.0",
        "description": "ElectroGadget Hub customer support system prompt - Optimized",
        "system_instruction": winner_config["system_instruction"],
        "model": winner_config.get("model", original["model"]),
        "parameters": {
            "temperature": winner_config.get("parameters", {}).get("temperature", original["parameters"]["temperature"]),
            "max_output_tokens": winner_config.get("parameters", {}).get("max_output_tokens", original["parameters"]["max_output_tokens"])
        },
        "metadata": {
            "created_at": original.get("metadata", {}).get("created_at", "2026-05-28T00:00:00Z"),
            "created_by": original.get("metadata", {}).get("created_by", "initial_setup"),
            "optimization_count": opt_count,
            "optimized_at": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "optimized_by": f"evaluation_agent_v2 ({winner_config.get('strategy', 'baseline')})"
        }
    }
    
    data["prompts"]["customer_support"] = updated_cs
    
    # Write back to prompts.json
    with open(PROMPTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
        
    print(f"✅ Successfully updated prompt to version 1.1.0 (Strategy: {winner_config.get('strategy', 'baseline')})!")


def main():
    print("--- STARTING PHASE 4: PROMPT OPTIMIZATION & SHADOW EVALUATIONS ---")
    
    project = os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent-v2")
    monitor = PromptMonitor()
    
    # 1. Fetch recent spans
    print("\n[Step 1] Fetching spans from Phoenix...")
    spans_df = monitor.fetch_recent_spans(project)
    if spans_df.empty:
        print("⚠️ No spans found in Phoenix project. We will run failure analysis using mock diagnostics.")
        failing_spans = pd.DataFrame()
    else:
        # 2. Run evaluations
        print("[Step 2] Running evaluations on fetched spans...")
        eval_results = monitor.run_evaluations(spans_df)
        
        # 3. Filter for failing spans
        normalized_df = monitor.normalize_dataframe(spans_df)
        combined_df = normalized_df.copy()
        
        eval_labels = []
        eval_explanations = []
        for _, row in eval_results.iterrows():
            eval_data = row["correctness_score"]
            eval_labels.append(eval_data.get("label", "incorrect"))
            eval_explanations.append(eval_data.get("explanation", ""))
            
        combined_df["eval_label"] = eval_labels
        combined_df["eval_explanation"] = eval_explanations
        failing_spans = combined_df[combined_df["eval_label"] == "incorrect"]
        
    # Inject mock failures if no natural failures are found to ensure optimization is testable
    if failing_spans.empty:
        print("⚠️ No natural failures found. Injecting typical failures for standard retail policy violations...")
        mock_failures = [
            {
                "input": "I need a refund for my broken headphones. Give me my money back now.",
                "output": "I am so sorry to hear that. I have went ahead and processed a full refund for your broken headphones. Have a great day!",
                "eval_explanation": "Fails procedural compliance for refunds: the agent immediately processed a refund without asking for a transaction ID or order number to verify the purchase."
            },
            {
                "input": "Can you help me fix a bug in my Python code? I have a KeyError in my dictionary search.",
                "output": "Sure! A KeyError happens when you search for a key that does not exist in the dictionary. Here is how you can fix it: `if key in my_dict: ...`",
                "eval_explanation": "Fails scope awareness: the assistant processed a software programming query, which is outside the ElectroGadget Hub support boundaries."
            }
        ]
        failing_spans = pd.DataFrame(mock_failures)
        failing_spans.index = ["mock-refund-failure", "mock-coding-failure"]

    print(f"Isolated {len(failing_spans)} failing spans for diagnostics.")
    
    # 4. Compile Diagnostic Report
    print("\n[Step 3] Compiling Diagnostic Report via FailureAnalyzer...")
    baseline_config = load_baseline_config()
    analyzer = FailureAnalyzer()
    report = analyzer.analyze_failures(
        failing_spans_df=failing_spans,
        prompt_config=baseline_config,
        overall_score=0.90
    )
    
    # 5. Programmatically Optimize Prompts
    print("\n[Step 4] Programmatically generating prompt variants via PromptOptimizer...")
    optimizer = PromptOptimizer()
    variants = optimizer.optimize_prompt(report)
    
    # 6. Execute Shadow Evaluation
    print("\n[Step 5] Running Shadow Evaluations via ShadowEvaluator...")
    evaluator = ShadowEvaluator()
    
    baseline_variant = {
        "id": baseline_config["id"],
        "version": baseline_config["version"],
        "strategy": "baseline",
        "system_instruction": baseline_config["system_instruction"],
        "model": baseline_config["model"],
        "parameters": baseline_config["parameters"]
    }
    
    eval_report = evaluator.run_shadow_evaluation(baseline_variant, variants)
    
    # 7. Print Detailed Comparison Matrix
    print("\n" + "=" * 80)
    print("📈 PROMPT VARIANT COMPARISON MATRIX 📈")
    print("=" * 80)
    print(f"{'Strategy/Variant':<20} | {'Accuracy':<10} | {'Keywords':<10} | {'Avg Latency':<12} | {'Avg Tokens':<10}")
    print("-" * 80)
    
    for r in [eval_report["baseline"]] + eval_report["candidates"]:
        name = f"{r['prompt_id']} ({r['strategy']})"
        print(f"{name:<20} | {r['accuracy']:<10.1%} | {r['avg_keyword_pass_rate']:<10.1%} | {r['avg_latency']:<10.2f}s | {r['avg_output_tokens']:<10.1f}")
        
    print("=" * 80)
    
    # 8. Save the Winner back to prompts.json
    winner = eval_report["winner"]
    is_improved = eval_report["is_improved"]
    
    print(f"🏆 Final Verdict: Winner is '{winner.get('prompt_id')}' ({winner.get('strategy')})")
    print(f"   Accuracy: {winner.get('accuracy'):.1%} (Baseline was {eval_report['baseline']['accuracy']:.1%})")
    print(f"   Is Improved? {is_improved}")
    
    if is_improved and winner.get("strategy") != "baseline":
        update_prompts_file(winner)
    else:
        print("\n⚠️ The baseline prompt performed best or no candidate beat it. No prompt file updates made.")
        
    print("\n🎉 Phase 4: Prompt Optimization & Shadow Evaluations completed successfully!")


if __name__ == "__main__":
    main()
