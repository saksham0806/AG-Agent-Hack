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


def simulate(num_runs: int = 20, delay: float = 1.0):
    """
    Run the target app against golden dataset queries.
    
    Args:
        num_runs: Total number of queries to execute
        delay: Seconds to wait between requests (rate limiting)
    """
    entries = load_golden_dataset()
    
    # Shuffle and pick WITHOUT replacement to guarantee 100% uniqueness
    selected_entries = entries.copy()
    random.shuffle(selected_entries)
    
    if num_runs > len(selected_entries):
        print(f"⚠️ Warning: Requested {num_runs} runs but only {len(selected_entries)} unique queries exist.")
        print(f"Capping runs at {len(selected_entries)} to guarantee 100% uniqueness of traces.")
        num_runs = len(selected_entries)
        
    selected_entries = selected_entries[:num_runs]
    
    print(f"🚀 Starting traffic simulation: {num_runs} queries (100% unique, sampled without replacement)")
    print(f"📊 Golden dataset has {len(entries)} unique queries available")
    print(f"⏱️  Delay between requests: {delay}s")
    print("-" * 60)
    
    success_count = 0
    error_count = 0
    
    for i, entry in enumerate(selected_entries):
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
    parser.add_argument("--num-runs", type=int, default=20, help="Number of queries to run")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    args = parser.parse_args()
    
    try:
        simulate(num_runs=args.num_runs, delay=args.delay)
    finally:
        print("\nFlushing and shutting down tracer provider...")
        from src.target_app import tracer_provider
        tracer_provider.shutdown()
        print("Traces flushed successfully!")
