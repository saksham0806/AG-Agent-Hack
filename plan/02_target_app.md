# Phase 2: Target App & Instrumentation

> **Goal**: Build a representative LLM application with externalized prompts, instrument it with OpenInference for Phoenix Cloud tracing, and seed the trace store with realistic traffic (including deliberate failure cases).
>
> **Estimated Time**: 2-3 hours

---

## 2.1 Design the Target Application

We'll build an **"ElectroGadget Hub" Customer Support Agent** — a realistic Q&A service that answers product questions, handles returns, and provides recommendations.

### Why This App?
- **Realistic domain**: Customer support is a common LLM use case
- **Clear failure modes**: The baseline prompt will deliberately lack constraints (e.g., doesn't ask for transaction IDs for refunds), creating measurable optimization targets
- **Easy to evaluate**: Correctness can be judged by ground-truth answers

### Externalized Prompt Architecture
Prompts are stored in `src/prompts.json`, NOT hardcoded. This is critical because:
1. The agent modifies prompts programmatically
2. Version tracking enables before/after comparison
3. GitLab MRs will diff prompt changes clearly

---

## 2.2 Create the Prompt Configuration

### `src/prompts.json`
```json
{
  "prompts": {
    "customer_support": {
      "id": "customer_support",
      "version": "1.0.0",
      "description": "ElectroGadget Hub customer support system prompt",
      "system_instruction": "You are a customer support agent for ElectroGadget Hub, an online electronics store. Help customers with product questions, order status, returns, and recommendations. Be friendly and helpful.",
      "model": "gemini-2.5-flash",
      "parameters": {
        "temperature": 0.3,
        "max_output_tokens": 1024
      },
      "metadata": {
        "created_at": "2026-05-28T00:00:00Z",
        "created_by": "initial_setup",
        "optimization_count": 0
      }
    }
  }
}
```

> [!NOTE]
> The baseline prompt is **intentionally weak** — it doesn't specify:
> - How to handle refund requests (no transaction ID validation)
> - Price matching policies
> - Warranty claim procedures
> - Escalation triggers
> 
> This gives the optimizer agent clear room to improve.

---

## 2.3 Build the Target App

### `src/target_app.py`

```python
"""
ElectroGadget Hub - Customer Support LLM Application

A sample LLM application with externalized prompts and full OpenInference
tracing to Arize Phoenix Cloud. This is the "target" that our improvement
loop agent will optimize.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# --- Tracing Setup (MUST come before any LLM imports) ---
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

load_dotenv()

tracer_provider = register(
    project_name="electrogadget-hub",
    auto_instrument=True
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# --- Application Code ---
from google import genai

# Load externalized prompts
PROMPTS_PATH = Path(__file__).parent / "prompts.json"

def load_prompts() -> dict:
    """Load prompt templates from the JSON config file."""
    with open(PROMPTS_PATH) as f:
        return json.load(f)

def get_prompt_config(prompt_id: str) -> dict:
    """Retrieve a specific prompt configuration by ID."""
    prompts = load_prompts()
    return prompts["prompts"][prompt_id]

def run_customer_support(query: str, prompt_id: str = "customer_support") -> str:
    """
    Run the customer support LLM with the specified prompt template.
    
    Args:
        query: The customer's question or request
        prompt_id: The prompt template ID to use from prompts.json
    
    Returns:
        The LLM's response string
    """
    config = get_prompt_config(prompt_id)
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    
    response = client.models.generate_content(
        model=config["model"],
        contents=query,
        config=genai.types.GenerateContentConfig(
            system_instruction=config["system_instruction"],
            temperature=config["parameters"]["temperature"],
            max_output_tokens=config["parameters"]["max_output_tokens"],
        )
    )
    
    return response.text

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "What is your return policy?"
    print(run_customer_support(query))
```

---

## 2.4 Create the Golden Dataset

This dataset serves two purposes:
1. **Traffic simulation** — seeds Phoenix with realistic traces
2. **Shadow evaluation benchmark** — ground-truth for comparing prompt variants

### `data/golden_dataset.json`
```json
{
  "dataset_name": "electrogadget_customer_support_v1",
  "description": "Ground-truth Q&A pairs for ElectroGadget Hub customer support",
  "entries": [
    {
      "id": "q001",
      "category": "product_info",
      "query": "What's the battery life of the UltraSound Pro X headphones?",
      "expected_answer_contains": ["40 hours", "battery", "ANC"],
      "difficulty": "easy"
    },
    {
      "id": "q002",
      "category": "return_policy",
      "query": "I want to return a laptop I bought 45 days ago. Is that possible?",
      "expected_answer_contains": ["30-day", "return window", "expired", "cannot"],
      "difficulty": "medium"
    },
    {
      "id": "q003",
      "category": "refund_request",
      "query": "I need a refund for my broken headphones. Give me my money back now.",
      "expected_answer_contains": ["transaction ID", "order number", "verify", "process"],
      "difficulty": "hard",
      "notes": "Baseline prompt will FAIL this — doesn't ask for transaction ID"
    },
    {
      "id": "q004",
      "category": "price_match",
      "query": "I found the GamerX 3080 for $200 cheaper at CompetitorMart. Can you match?",
      "expected_answer_contains": ["price match", "policy", "verification"],
      "difficulty": "hard",
      "notes": "Baseline prompt has no price-match policy — should fail"
    },
    {
      "id": "q005",
      "category": "warranty",
      "query": "My TV stopped working after 8 months. Is it under warranty?",
      "expected_answer_contains": ["warranty", "12 months", "covered", "claim"],
      "difficulty": "medium"
    },
    {
      "id": "q006",
      "category": "recommendation",
      "query": "I need a good laptop for video editing under $1500",
      "expected_answer_contains": ["recommend", "specs", "GPU", "RAM"],
      "difficulty": "easy"
    },
    {
      "id": "q007",
      "category": "escalation",
      "query": "This is the fifth time I'm calling about my broken order #98765. I want to speak to a manager RIGHT NOW!",
      "expected_answer_contains": ["escalate", "manager", "supervisor", "priority"],
      "difficulty": "hard",
      "notes": "Baseline prompt doesn't have escalation procedures"
    },
    {
      "id": "q008",
      "category": "order_status",
      "query": "Where is my order? I placed it 3 days ago.",
      "expected_answer_contains": ["order number", "tracking", "status"],
      "difficulty": "easy"
    },
    {
      "id": "q009",
      "category": "refund_request",
      "query": "I returned my item two weeks ago but haven't received my refund yet.",
      "expected_answer_contains": ["processing time", "5-10 business days", "check status"],
      "difficulty": "medium"
    },
    {
      "id": "q010",
      "category": "out_of_scope",
      "query": "Can you help me fix a bug in my Python code?",
      "expected_answer_contains": ["electronics", "outside scope", "cannot help", "support"],
      "difficulty": "medium"
    }
  ]
}
```

---

## 2.5 Build the Traffic Simulator

### `scripts/simulate_traffic.py`
```python
"""
Traffic Simulator — Seeds Phoenix Cloud with realistic traces.

Runs the target app against the golden dataset to populate the trace store
with both successful and failing interactions.

Usage:
    python scripts/simulate_traffic.py --num-runs 50
    python scripts/simulate_traffic.py --num-runs 10 --delay 2
"""

import argparse
import json
import random
import time
from pathlib import Path

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.target_app import run_customer_support


def load_golden_dataset() -> list[dict]:
    """Load the golden dataset entries."""
    dataset_path = Path(__file__).parent.parent / "data" / "golden_dataset.json"
    with open(dataset_path) as f:
        data = json.load(f)
    return data["entries"]


def simulate(num_runs: int = 50, delay: float = 1.0):
    """
    Run the target app against golden dataset queries.
    
    Args:
        num_runs: Total number of queries to execute
        delay: Seconds to wait between requests (rate limiting)
    """
    entries = load_golden_dataset()
    
    print(f"🚀 Starting traffic simulation: {num_runs} queries")
    print(f"📊 Golden dataset has {len(entries)} unique queries")
    print(f"⏱️  Delay between requests: {delay}s")
    print("-" * 60)
    
    success_count = 0
    error_count = 0
    
    for i in range(num_runs):
        # Pick a random entry (weighted toward harder ones)
        entry = random.choice(entries)
        query = entry["query"]
        
        print(f"\n[{i+1}/{num_runs}] Category: {entry['category']} | Difficulty: {entry['difficulty']}")
        print(f"  Query: {query[:80]}...")
        
        try:
            response = run_customer_support(query)
            print(f"  Response: {response[:120]}...")
            success_count += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            error_count += 1
        
        if i < num_runs - 1:
            time.sleep(delay)
    
    print("\n" + "=" * 60)
    print(f"✅ Simulation complete: {success_count} successes, {error_count} errors")
    print(f"📡 Check Phoenix Cloud dashboard for traces")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate customer support traffic")
    parser.add_argument("--num-runs", type=int, default=50, help="Number of queries to run")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    args = parser.parse_args()
    
    simulate(num_runs=args.num_runs, delay=args.delay)
```

---

## 2.6 Verify Instrumentation

### Step 1: Run a Single Query
```bash
source .venv/bin/activate
python -m src.target_app "What is your return policy?"
```

### Step 2: Check Phoenix Cloud
1. Open [phoenix.arize.com](https://app.phoenix.arize.com)
2. Navigate to your project (`electrogadget-hub`)
3. Verify that a trace appears with:
   - LLM span with model name
   - Input/output captured
   - Latency metrics

### Step 3: Run the Traffic Simulator
```bash
python scripts/simulate_traffic.py --num-runs 20 --delay 1.5
```

### Step 4: Verify Trace Volume
Check Phoenix Cloud — you should see 20 traces with:
- Varied query categories
- Different response patterns
- Latency distribution

---

## 2.7 Completion Checklist

- [ ] `src/prompts.json` created with baseline "customer_support" prompt
- [ ] `src/target_app.py` implemented with OpenInference instrumentation
- [ ] `data/golden_dataset.json` created with 10+ ground-truth Q&A pairs
- [ ] `scripts/simulate_traffic.py` implemented and tested
- [ ] Single query runs successfully and appears in Phoenix Cloud
- [ ] Traffic simulator seeds 20+ traces into Phoenix
- [ ] Traces visible in Phoenix Cloud dashboard with correct project name
- [ ] Spans show input queries and LLM responses

---

> **Next Phase**: [Phase 3: Phoenix Introspection & Diagnostics →](03_phoenix_introspection.md)
