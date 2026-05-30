"""
Shadow Evaluator Module — Evaluates prompt variants against the Golden Dataset.

Runs baseline and candidates through double-layered evaluation (Keyword containing check + LLM-as-a-Judge),
tracks performance metrics (accuracy, latency, tokens), programmatically selects a winner,
and instruments evaluations with OpenTelemetry to log traces to Phoenix Cloud under a shadow project.
"""

import os
import json
import time
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- OpenTelemetry Instrumentation Setup ---
from phoenix.otel import register
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

# Initialize shadow evaluation project
shadow_project = os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent-v2") + "-shadow-eval"
print(f"Registering OpenTelemetry tracer provider for shadow evaluations under project: '{shadow_project}'")
tracer_provider = register(
    project_name=shadow_project,
    auto_instrument=True
)
# Instrument the Google GenAI SDK
GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)


class ShadowJudgeSchema(BaseModel):
    correct: bool = Field(
        description="True if the response meets all correctness criteria and matches the expected retail support guidelines. False otherwise."
    )
    reason: str = Field(
        description="A highly specific, detailed explanation of why the response is correct or incorrect, referencing specific store policies or expectations."
    )


class ShadowEvaluator:
    def __init__(self, golden_dataset_path: str = "data/golden_dataset.json"):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key or api_key == "your-gemini-api-key":
            raise ValueError("GOOGLE_API_KEY is not set in the environment variables.")
        self.client = genai.Client(api_key=api_key)
        self.dataset_path = golden_dataset_path
        self.dataset = self._load_dataset()

    def _load_dataset(self) -> dict:
        """Load ground-truth Q&As from golden_dataset.json."""
        if not os.path.exists(self.dataset_path):
            raise FileNotFoundError(f"Golden dataset not found at {self.dataset_path}")
        with open(self.dataset_path) as f:
            return json.load(f)

    def _generate_content_with_retry(self, **kwargs) -> Any:
        """
        Wrapper to invoke models.generate_content with exponential backoff on transient errors.
        """
        max_retries = 4
        initial_delay = 2.0
        delay = initial_delay
        
        for attempt in range(max_retries):
            try:
                return self.client.models.generate_content(**kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"      ❌ Gemini API call failed after {max_retries} attempts: {e}")
                    raise e
                
                err_msg = str(e)
                # Print a clean, trimmed version of the error message to avoid cluttering logs
                trimmed_err = err_msg[:120] + "..." if len(err_msg) > 120 else err_msg
                print(f"      ⚠️ Gemini API transient error (attempt {attempt+1}/{max_retries}): {trimmed_err}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= 2.0

    def _judge_response(self, query: str, response_text: str, expected_contains: List[str]) -> Dict[str, Any]:
        """
        Run LLM-as-a-Judge correctness evaluation on a single query-response pair.
        """
        judge_prompt = f"""
You are a senior quality assurance auditor for ElectroGadget Hub's customer support system.
Evaluate the following interaction between a customer and our AI support agent.

### Customer Query
\"{query}\"

### Agent Response
\"{response_text}\"

### Golden Dataset Requirements:
- The response is expected to cover these elements: {expected_contains}

### Evaluation Standard Retail Policies:
1. **Factual Correctness**: Does it provide accurate retail support information based on common-sense policies?
2. **Procedural Compliance**:
   - **Refunds**: The agent MUST explicitly request a transaction ID or order number before initiating, processing, or promising a refund.
   - **Returns**: Returns are limited to a strict 30-day return window. If the purchase was 45 days ago, it MUST state returns are expired and cannot be processed.
   - **Warranty**: Products have a 12-month warranty. Check details before initiating claims.
   - **Escalation**: Repeat issues (e.g., calling 5 times) or extremely angry queries MUST be offered escalation to a support manager or supervisor.
3. **Scope Awareness**: The store ONLY supports electronics sales/questions. Out-of-scope requests (e.g., writing Python code, fixing software bugs) MUST be politely declined.
4. **Helpfulness**: Response must move toward resolving the issue rather than ignoring the core question.

Format your output as a structured JSON object matching the requested schema.
"""
        try:
            # We run the Judge call using Gemini 2.5 Flash with retry
            judge_res = self._generate_content_with_retry(
                model="gemini-2.5-flash",
                contents=judge_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ShadowJudgeSchema,
                    temperature=0.0  # Zero temperature for deterministic auditing
                )
            )
            data = json.loads(judge_res.text)
            return {
                "correct": data.get("correct", False),
                "reason": data.get("reason", "No reason provided.")
            }
        except Exception as e:
            print(f"⚠️ Error running LLM-as-a-Judge: {e}")
            return {
                "correct": False,
                "reason": f"Evaluation error: {str(e)}"
            }

    def _evaluate_candidate(self, variant: dict, sample_size: int = None) -> dict:
        """
        Evaluate a single prompt variant against the entire golden dataset.
        """
        print(f"\nEvaluating variant '{variant.get('id')}' (Strategy: {variant.get('strategy')})...")
        
        entries = self.dataset.get("entries", [])
        if sample_size and sample_size < len(entries):
            import random
            rng = random.Random(42)  # Fixed seed for consistent evaluations across all candidates
            entries = rng.sample(entries, sample_size)
            entries.sort(key=lambda x: x.get("id", ""))
            print(f"🔬 Sampled {sample_size} queries from golden dataset for consistent shadow evaluation.")
            
        total_entries = len(entries)
        if total_entries == 0:
            return {"accuracy": 0.0, "avg_keyword_pass_rate": 0.0, "avg_latency": 0.0, "avg_output_tokens": 0.0, "results": []}
            
        results = []
        correct_count = 0
        total_keyword_pass_rate = 0.0
        total_latency = 0.0
        total_output_tokens = 0
        total_tokens = 0
        
        for idx, entry in enumerate(entries):
            query = entry["query"]
            expected_contains = entry.get("expected_answer_contains", [])
            
            # 1. Run the target app's query with the candidate system instruction (with retry)
            start_time = time.perf_counter()
            try:
                response = self._generate_content_with_retry(
                    model=variant.get("model", "gemini-2.5-flash"),
                    contents=query,
                    config=types.GenerateContentConfig(
                        system_instruction=variant.get("system_instruction"),
                        temperature=variant.get("parameters", {}).get("temperature", 0.3),
                        max_output_tokens=variant.get("parameters", {}).get("max_output_tokens", 1024),
                    )
                )
                latency = time.perf_counter() - start_time
                response_text = response.text
                
                # Extract token usage details
                prompt_tokens = 0
                output_tokens = 0
                if response.usage_metadata:
                    prompt_tokens = response.usage_metadata.prompt_token_count
                    output_tokens = response.usage_metadata.candidates_token_count
            except Exception as e:
                print(f"   ❌ Error running query on model: {e}")
                response_text = ""
                latency = time.perf_counter() - start_time
                prompt_tokens = 0
                output_tokens = 0
                
            # 2. Layer 1: Keyword containing check
            keywords_found = 0
            for kw in expected_contains:
                if kw.lower() in response_text.lower():
                    keywords_found += 1
            keyword_pass_rate = keywords_found / len(expected_contains) if expected_contains else 1.0
            
            # 3. Layer 2: LLM-as-a-Judge correctness
            judge_res = self._judge_response(query, response_text, expected_contains)
            is_correct = judge_res["correct"]
            judge_explanation = judge_res["reason"]
            
            if is_correct:
                correct_count += 1
                
            total_keyword_pass_rate += keyword_pass_rate
            total_latency += latency
            total_output_tokens += output_tokens
            total_tokens += (prompt_tokens + output_tokens)
            
            results.append({
                "entry_id": entry["id"],
                "query": query,
                "response": response_text,
                "is_correct": is_correct,
                "explanation": judge_explanation,
                "keyword_pass_rate": keyword_pass_rate,
                "latency": latency,
                "tokens": {
                    "prompt": prompt_tokens,
                    "output": output_tokens,
                    "total": prompt_tokens + output_tokens
                }
            })
            
            status_char = "✅" if is_correct else "❌"
            print(f"   [{idx+1}/{total_entries}] Query '{entry['id']}': {status_char} (Keywords: {keyword_pass_rate:.0%}, Latency: {latency:.2f}s)")

        accuracy = correct_count / total_entries
        avg_keyword_pass_rate = total_keyword_pass_rate / total_entries
        avg_latency = total_latency / total_entries
        avg_output_tokens = total_output_tokens / total_entries
        
        print(f"📊 Summary for '{variant.get('id')}': Accuracy = {accuracy:.1%}, Keywords = {avg_keyword_pass_rate:.1%}, Avg Latency = {avg_latency:.2f}s, Avg Tokens = {avg_output_tokens:.1f}")
        
        return {
            "prompt_id": variant.get("id"),
            "prompt_version": variant.get("version"),
            "strategy": variant.get("strategy"),
            "system_instruction": variant.get("system_instruction"),
            "accuracy": accuracy,
            "avg_keyword_pass_rate": avg_keyword_pass_rate,
            "avg_latency": avg_latency,
            "avg_output_tokens": avg_output_tokens,
            "total_tokens": total_tokens,
            "results": results
        }

    def run_shadow_evaluation(self, baseline_variant: dict, candidate_variants: List[dict], sample_size: int = 15) -> dict:
        """
        Run shadow evaluations for baseline + 3 candidate variants and select a statistical winner.
        """
        print(f"Starting Shadow Evaluations on sample size: {sample_size}...")
        
        # 1. Evaluate baseline
        baseline_report = self._evaluate_candidate(baseline_variant, sample_size=sample_size)
        
        # 2. Evaluate candidates
        candidate_reports = []
        for cand in candidate_variants:
            report = self._evaluate_candidate(cand, sample_size=sample_size)
            candidate_reports.append(report)
            
        # 3. Combine reports and pick winner
        all_reports = [baseline_report] + candidate_reports
        
        # Winner Selection Logic:
        # 1. Primary: Highest Accuracy
        # 2. Tiebreaker 1: Highest Average Keyword Pass Rate
        # 3. Tiebreaker 2: Lowest Average Latency
        # 4. Tiebreaker 3: Lowest Average Output Tokens
        
        # Sort candidates (excluding baseline first, or including baseline to see if any beats baseline)
        # We want to select the best of the candidate variants.
        sorted_candidates = sorted(
            candidate_reports,
            key=lambda x: (
                x["accuracy"],
                x["avg_keyword_pass_rate"],
                -x["avg_latency"],
                -x["avg_output_tokens"]
            ),
            reverse=True
        )
        
        best_candidate = sorted_candidates[0]
        
        # Check if the best candidate beats or matches the baseline
        improved = best_candidate["accuracy"] >= baseline_report["accuracy"]
        winner = best_candidate if improved else baseline_report
        
        evaluation_report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "project": shadow_project,
            "baseline": baseline_report,
            "candidates": candidate_reports,
            "winner": winner,
            "is_improved": improved,
            "winner_strategy": winner.get("strategy")
        }
        
        print("\n🏆 SHADOW EVALUATION WINNER SELECTED 🏆")
        print(f"Winner ID:       {winner.get('prompt_id')}")
        print(f"Winner Strategy: {winner.get('strategy')}")
        print(f"Winner Accuracy: {winner.get('accuracy'):.1%} (Baseline: {baseline_report.get('accuracy'):.1%})")
        print(f"Is Improved?     {improved}")
        
        # Flush traces to Phoenix Cloud
        print("Flushing OpenTelemetry trace provider...")
        tracer_provider.shutdown()
        
        return evaluation_report


if __name__ == "__main__":
    # Quick standalone test with golden dataset only on baseline
    evaluator = ShadowEvaluator()
    baseline = {
        "id": "customer_support",
        "version": "1.0.0",
        "strategy": "baseline",
        "system_instruction": "You are a customer support agent for ElectroGadget Hub, an online electronics store. Help customers with product questions, order status, returns, and recommendations. Be friendly and helpful.",
        "model": "gemini-2.5-flash",
        "parameters": {"temperature": 0.3, "max_output_tokens": 1024}
    }
    
    # Run only baseline test
    report = evaluator._evaluate_candidate(baseline)
    print(f"Baseline Accuracy: {report['accuracy']:.1%}")
