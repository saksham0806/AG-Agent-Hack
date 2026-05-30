"""
Monitor Module — Watches Phoenix Cloud for underperforming prompts.

Queries traces, runs LLM-as-a-Judge evaluations using Gemini,
and identifies prompt templates that need optimization.
"""

import os
import pandas as pd
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from dotenv import load_dotenv

import phoenix as px
from phoenix.evals import LLM, ClassificationEvaluator, evaluate_dataframe
from phoenix.client import Client as PhoenixClient

# Load environment variables
load_dotenv()

# --- Configuration ---
PERFORMANCE_THRESHOLD = 0.85   # 85% — prompts below this trigger optimization
LOOKBACK_HOURS = 24            # How far back to query traces
MIN_TRACE_COUNT = 5            # Minimum traces needed for a reliable evaluation trigger


@dataclass
class PromptPerformanceReport:
    """Summary of a prompt template's performance."""
    prompt_id: str
    prompt_version: str
    total_traces: int
    eval_score: float              # 0.0 to 1.0 (correctness pass rate)
    failing_trace_ids: list[str]   # Trace/Span IDs that failed evaluation
    needs_optimization: bool
    category_breakdown: dict       # {category: score}


# --- Correctness Judge Evaluation Template ---
CORRECTNESS_EVAL_TEMPLATE = """
You are a quality assurance evaluator for ElectroGadget Hub's customer support AI.

### Customer Query
{input}

### AI Response  
{output}

### Evaluation Criteria

1. **Factual Correctness** (Does it provide accurate product/policy information based on standard store policies?)
2. **Procedural Compliance** (Does it follow proper support guidelines?)
   - Refund requests: Must ask for transaction ID or order number to verify.
   - Returns: Must mention the 30-day return window.
   - Warranty: Must check purchase date and product details.
   - Escalation: Must offer manager/supervisor contact for repeated issues or angry customers.
3. **Helpfulness** (Does it actually move toward resolving the issue instead of ignoring the core request?)
4. **Scope Awareness** (Does it stay within electronics support scope and politely refuse out-of-scope requests like coding help?)

### Scoring
- "correct": Response meets ALL applicable criteria perfectly.
- "incorrect": Response fails ANY applicable criterion (e.g. processes refund without asking for transaction/order ID, allows return over 30 days, answers coding questions).

### Your Evaluation
Label: [correct/incorrect]
Explanation: [Brief, highly specific reason why the response succeeded or failed]
"""


class PromptMonitor:
    def __init__(self):
        endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
        api_key = os.getenv("PHOENIX_API_KEY")
        
        if not endpoint:
            raise ValueError("PHOENIX_COLLECTOR_ENDPOINT is not set in the environment variables.")
        if not api_key:
            raise ValueError("PHOENIX_API_KEY is not set in the environment variables.")
            
        print(f"Initializing Phoenix Client with base_url: {endpoint}")
        self.client = PhoenixClient(
            base_url=endpoint,
            api_key=api_key
        )
    
    def fetch_recent_spans(self, project_name: str, hours: int = LOOKBACK_HOURS) -> pd.DataFrame:
        """Fetch LLM spans from the last N hours for evaluation."""
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        print(f"Fetching spans for project '{project_name}' since {start_time.isoformat()}...")
        
        # Retrieve all spans as a DataFrame
        try:
            spans_df = self.client.spans.get_spans_dataframe(
                project_name=project_name,
                start_time=start_time
            )
        except Exception as e:
            print(f"⚠️ Error fetching spans from Phoenix: {e}")
            return pd.DataFrame()
            
        if spans_df.empty:
            print("No spans found in the specified window.")
            return pd.DataFrame()
            
        # Filter for LLM span kinds to evaluate only actual model executions
        if "span_kind" in spans_df.columns:
            llm_spans = spans_df[spans_df["span_kind"] == "LLM"].copy()
        else:
            print("⚠️ 'span_kind' column not found in spans DataFrame. Proceeding with all spans.")
            llm_spans = spans_df.copy()
            
        print(f"Found {len(llm_spans)} LLM spans.")
        return llm_spans
    
    def normalize_dataframe(self, spans_df: pd.DataFrame) -> pd.DataFrame:
        """Normalize DataFrame columns so that they map cleanly to 'input' and 'output'."""
        df = spans_df.copy()
        
        # Map input value
        input_cols = ["attributes.input.value", "input.value", "input"]
        for col in input_cols:
            if col in df.columns:
                df["input"] = df[col]
                break
                
        # Map output value
        output_cols = ["attributes.output.value", "output.value", "output"]
        for col in output_cols:
            if col in df.columns:
                df["output"] = df[col]
                break
                
        if "input" not in df.columns or "output" not in df.columns:
            # Fallbacks or empty initializers if columns are entirely missing
            if "input" not in df.columns:
                df["input"] = ""
            if "output" not in df.columns:
                df["output"] = ""
                
        # Fill missing values
        df["input"] = df["input"].fillna("")
        df["output"] = df["output"].fillna("")
        
        return df

    def run_evaluations(self, spans_df: pd.DataFrame) -> pd.DataFrame:
        """Run LLM-as-a-Judge correctness evaluations on fetched spans."""
        print("Running LLM-as-a-Judge evaluations using Gemini...")
        
        # Prepare inputs/outputs
        normalized_df = self.normalize_dataframe(spans_df)
        
        # Initialize Gemini LLM Judge
        api_key = os.getenv("GOOGLE_API_KEY")
        judge_llm = LLM(
            provider="google",
            model="gemini-2.5-flash",
            api_key=api_key
        )
        
        # Construct custom ClassificationEvaluator
        correctness_evaluator = ClassificationEvaluator(
            name="correctness",
            llm=judge_llm,
            prompt_template=CORRECTNESS_EVAL_TEMPLATE,
            choices={"correct": 1.0, "incorrect": 0.0}
        )
        
        # Run evaluation
        eval_results = evaluate_dataframe(
            dataframe=normalized_df,
            evaluators=[correctness_evaluator]
        )
        
        # Add span ID index to match evaluations back
        eval_results.index = normalized_df.index
        
        print("Evaluations completed.")
        return eval_results
    
    def log_evaluations_back(self, project_name: str, eval_results: pd.DataFrame):
        """Log the evaluation results back to Phoenix Cloud for visual auditing."""
        print(f"Logging evaluations back to Phoenix project '{project_name}'...")
        success_count = 0
        for span_id, row in eval_results.iterrows():
            try:
                # In Phoenix 3.x, correctness_score is a dictionary-like object in the DataFrame cell
                eval_data = row["correctness_score"]
                label = eval_data.get("label", "incorrect")
                score = float(eval_data.get("score", 0.0))
                explanation = eval_data.get("explanation", "")
                
                self.client.spans.add_span_annotation(
                    span_id=span_id,
                    annotation_name="correctness",
                    annotator_kind="LLM",
                    label=label,
                    score=score,
                    explanation=explanation
                )
                success_count += 1
            except Exception as e:
                print(f"⚠️ Warning: Could not log evaluation for span {span_id}: {e}")
        
        print(f"✅ Successfully logged {success_count}/{len(eval_results)} evaluations to Phoenix Cloud!")
            
    def analyze_performance(self, eval_results: pd.DataFrame, spans_df: pd.DataFrame) -> list[PromptPerformanceReport]:
        """Aggregate evaluation results by prompt template and version."""
        normalized_df = self.normalize_dataframe(spans_df)
        
        # Extract labels and explanations from correctness_score dictionaries
        eval_labels = []
        eval_explanations = []
        for _, row in eval_results.iterrows():
            eval_data = row["correctness_score"]
            eval_labels.append(eval_data.get("label", "incorrect"))
            eval_explanations.append(eval_data.get("explanation", ""))
            
        # Join spans and evaluation labels
        combined_df = normalized_df.copy()
        combined_df["eval_label"] = eval_labels
        combined_df["eval_explanation"] = eval_explanations
        
        # If there are metadata/attributes for prompt template and version, group by them.
        # Fall back to hardcoded ID if not present.
        prompt_id_col = "attributes.prompt.id" if "attributes.prompt.id" in combined_df.columns else None
        prompt_version_col = "attributes.prompt.version" if "attributes.prompt.version" in combined_df.columns else None
        
        # Let's ensure prompt_id and version exist in combined_df, or set defaults
        if not prompt_id_col:
            combined_df["prompt_id"] = "customer_support"
        else:
            combined_df["prompt_id"] = combined_df[prompt_id_col]
            
        if not prompt_version_col:
            combined_df["prompt_version"] = "1.0.0"
        else:
            combined_df["prompt_version"] = combined_df[prompt_version_col]
            
        reports = []
        
        # Group by prompt ID and version
        grouped = combined_df.groupby(["prompt_id", "prompt_version"])
        for (prompt_id, prompt_version), group in grouped:
            total_traces = len(group)
            correct_count = len(group[group["eval_label"] == "correct"])
            eval_score = correct_count / total_traces if total_traces > 0 else 1.0
            
            # Extract span IDs for failures
            failing_group = group[group["eval_label"] == "incorrect"]
            failing_trace_ids = failing_group.index.tolist()
            
            needs_optimization = eval_score < PERFORMANCE_THRESHOLD
            
            # Simple category breakdown (if metadata has category, or we parse from query)
            category_breakdown = {}
            if "attributes.query.category" in group.columns:
                cat_grouped = group.groupby("attributes.query.category")
                for cat_name, cat_group in cat_grouped:
                    cat_correct = len(cat_group[cat_group["eval_label"] == "correct"])
                    category_breakdown[cat_name] = cat_correct / len(cat_group)
            
            report = PromptPerformanceReport(
                prompt_id=prompt_id,
                prompt_version=prompt_version,
                total_traces=total_traces,
                eval_score=eval_score,
                failing_trace_ids=failing_trace_ids,
                needs_optimization=needs_optimization,
                category_breakdown=category_breakdown
            )
            reports.append(report)
            
            print(f"\n📈 Prompt ID: {prompt_id} (v{prompt_version})")
            print(f"   Total Traces Evaluated: {total_traces}")
            print(f"   Correctness Score: {eval_score:.1%} (Threshold: {PERFORMANCE_THRESHOLD:.1%})")
            print(f"   Failing Traces: {len(failing_trace_ids)}")
            print(f"   Needs Optimization: {needs_optimization}")
            
        return reports
        
    def run_monitoring_loop(self, project_name: str) -> list[PromptPerformanceReport]:
        """Runs the complete monitoring process: fetch, evaluate, log, and analyze."""
        spans_df = self.fetch_recent_spans(project_name)
        
        if spans_df.empty:
            print("⚠️ No traces found to evaluate.")
            return []
            
        if len(spans_df) < MIN_TRACE_COUNT:
            print(f"⚠️ Found {len(spans_df)} traces, which is less than the trigger threshold of {MIN_TRACE_COUNT}. Skipping monitoring cycle.")
            return []
            
        eval_results = self.run_evaluations(spans_df)
        
        # Log evaluation results back to Phoenix Cloud for visual logging
        self.log_evaluations_back(project_name, eval_results)
        
        # Analyze performance
        reports = self.analyze_performance(eval_results, spans_df)
        return reports


if __name__ == "__main__":
    monitor = PromptMonitor()
    project = os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent")
    print(f"Running standalone monitor test for project: {project}")
    monitor.run_monitoring_loop(project)
