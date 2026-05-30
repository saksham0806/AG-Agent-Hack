# scripts/verify_analysis.py
import os
import json
from dotenv import load_dotenv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.monitor import PromptMonitor
from src.agent.analyzer import FailureAnalyzer

load_dotenv()

print("--- STANDALONE FAILURE ANALYSIS VERIFICATION ---")
project = os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent-v2")

monitor = PromptMonitor()

# 1. Retrieve recent spans
spans_df = monitor.fetch_recent_spans(project)
if spans_df.empty:
    print("❌ No spans found to evaluate.")
    exit(1)

# 2. Run judge evaluations
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

# If no natural failures are detected in this run, inject a mock policy-violation failure 
# to guarantee that the FailureAnalyzer is fully verified end-to-end!
if failing_spans.empty:
    print("⚠️ No natural failures detected in this run. Injecting a mock policy-violation failure to verify FailureAnalyzer...")
    mock_row = pd.DataFrame([{
        "input": "Can you help me fix a bug in my Python code? I have a KeyError in my dictionary search.",
        "output": "Sure! A KeyError happens when you search for a key that does not exist in the dictionary. Here is how you can fix it: `if key in my_dict: ...`",
        "eval_label": "incorrect",
        "eval_explanation": "Fails procedural compliance and scope awareness: the AI processed a software coding request, which is completely outside the ElectroGadget Hub support scope."
    }])
    mock_row.index = ["mock-failing-span-id"]
    failing_spans = mock_row

print(f"\nIsolated {len(failing_spans)} failing spans for analytical diagnosis.")

if not failing_spans.empty:
    # 4. Define baseline prompt config
    prompt_config = {
        "id": "customer_support",
        "version": "1.0.0",
        "system_instruction": "You are a customer support agent for ElectroGadget Hub, an online electronics store. Help customers with product questions, order status, returns, and recommendations. Be friendly and helpful."
    }
    
    # 5. Run the Failure Analyzer
    analyzer = FailureAnalyzer()
    report = analyzer.analyze_failures(
        failing_spans_df=failing_spans,
        prompt_config=prompt_config,
        overall_score=0.90
    )
    
    # 6. Print Structured Diagnostic Report
    print("\n" + "=" * 60)
    print("🔥 STRUCTURED DIAGNOSTIC REPORT GENERATED 🔥")
    print("=" * 60)
    print(f"Project Name:      {project}")
    print(f"Prompt Config ID:  {report.prompt_id} (v{report.prompt_version})")
    print(f"Overall Score:     {report.overall_score:.1%}")
    print(f"Total Failures:    {report.total_failures}")
    print("-" * 60)
    print("FAILURE CLUSTERS ISOLATED:")
    for i, cluster in enumerate(report.failure_clusters):
        print(f"\n[{i+1}] Category: {cluster.category.upper()}")
        print(f"    Root Cause Pattern: {cluster.failure_pattern}")
        print(f"    Example Query:      \"{cluster.example_queries[0]}\"")
        print(f"    Example AI Response: \"{cluster.example_responses[0][:150]}...\"")
        print(f"    Expected Behavior:   {cluster.expected_behavior}")
        print(f"    Occurrences:         {cluster.count}")
    print("-" * 60)
    print("RECOMMENDED PROMPT IMPROVEMENT INSTRUCTIONS:")
    for sug in report.improvement_suggestions:
        print(f"  💡 {sug}")
    print("=" * 60)
else:
    print("✅ No failing spans detected! The system is performing perfectly.")
