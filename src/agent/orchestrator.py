"""
Orchestrator Module — Coordinates the autonomous LLM Eval-to-Improvement Loop.

Manages running states, streams execution logs, aggregates metrics,
and persists execution history to data/history.json.
"""

import os
import json
import time
import threading
import asyncio
from datetime import datetime
from typing import Dict, Any, List
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from src.agent.monitor import PromptMonitor
from src.agent.analyzer import FailureAnalyzer
from src.agent.optimizer import PromptOptimizer
from src.agent.evaluator import ShadowEvaluator
from src.agent.gitlab_deployer import GitLabDeployer

# Load environment variables
load_dotenv()


class Orchestrator:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Thread-safe singleton pattern for the orchestrator."""
        with cls._lock:
            if not cls._instance:
                cls._instance = super(Orchestrator, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, history_path: str = "data/history.json"):
        if self._initialized:
            return
        self.history_path = Path(history_path)
        self.status = "IDLE"  # IDLE, FETCHING_SPANS, RUNNING_JUDGES, DIAGNOSING_FAILURES, OPTIMIZING_PROMPTS, SHADOW_EVALUATIONS, OPENING_MERGE_REQUEST, COMPLETED, FAILED
        self.logs: List[str] = []
        self.current_run: Dict[str, Any] = {}
        self.active_thread = None
        self._initialized = True
        
        # Initialize MongoDB connection or fallback
        self.use_mongodb = False
        self.mongo_client = None
        self.db = None
        self.history_collection = None
        self._init_mongodb()
        
        self._ensure_history_exists()

    def _init_mongodb(self):
        """Attempts to connect to MongoDB Cloud Atlas, falls back to local history.json."""
        connection_string = os.getenv("MONGODB_CONNECTION_STRING")
        if not connection_string:
            self.log("ℹ️ MONGODB_CONNECTION_STRING not set in .env. Using local JSON history database.")
            return

        try:
            from pymongo import MongoClient
            self.log("🔌 Attempting to connect to MongoDB Cloud Atlas...")
            # We set a 5 second server selection timeout to fail fast if connection cannot be made
            self.mongo_client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            # Trigger a quick connection test (ping)
            self.mongo_client.admin.command("ping")
            
            self.db = self.mongo_client["prompt_agent_db"]
            self.history_collection = self.db["history"]
            self.use_mongodb = True
            self.log("✅ Successfully connected to MongoDB Cloud! Saving logs to cluster...")
        except Exception as e:
            self.log(f"⚠️ Failed to connect to MongoDB Cloud Atlas ({e}). Falling back to local JSON history database.")
            self.use_mongodb = False
            self.mongo_client = None
            self.db = None
            self.history_collection = None

    def _ensure_history_exists(self):
        """Ensure the local history JSON file exist (always keep for local fallback)."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.history_path.exists():
            with open(self.history_path, "w") as f:
                json.dump([], f)

    def log(self, message: str):
        """Log a message with a timestamp to console and memory logs."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        self.logs.append(log_entry)

    def _serialize_mongo_document(self, doc: dict) -> dict:
        """Convert BSON ObjectIds to standard strings for JSON-serializable API responses."""
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def get_history(self) -> List[Dict[str, Any]]:
        """Retrieve execution history from MongoDB Cloud or local JSON store."""
        if self.use_mongodb:
            try:
                cursor = self.history_collection.find().sort("timestamp", -1)
                return [self._serialize_mongo_document(doc) for doc in cursor]
            except Exception as e:
                self.log(f"⚠️ Error reading from MongoDB, falling back to local JSON history: {e}")
                
        # Local JSON fallback
        try:
            with open(self.history_path) as f:
                return json.load(f)
        except Exception:
            return []

    def _save_to_history(self, run_record: Dict[str, Any]):
        """Save a completed run record to MongoDB Cloud or local JSON store."""
        if self.use_mongodb:
            try:
                # Save to Cloud Atlas
                self.history_collection.insert_one(run_record.copy())
                self.log("💾 Run execution history saved successfully to MongoDB Cloud!")
                return
            except Exception as e:
                self.log(f"⚠️ Error writing to MongoDB, falling back to local JSON: {e}")

        # Local JSON fallback
        history = self.get_history()
        # Ensure we don't save MongoDB BSON objects back to JSON
        clean_record = run_record.copy()
        if "_id" in clean_record:
            del clean_record["_id"]
            
        history.insert(0, clean_record)
        with open(self.history_path, "w") as f:
            json.dump(history, f, indent=2)
        self.log("💾 Run execution history saved locally to history.json.")

    def trigger_loop_async(self, project_name: str, force_optimize: bool = False):
        """
        Trigger the autonomous loop asynchronously in a separate thread.
        Returns True if triggered successfully, False if already running.
        """
        with self._lock:
            if self.status not in ["IDLE", "COMPLETED", "FAILED"]:
                self.log("⚠️ Orchestrator is already running. Trigger rejected.")
                return False
            
            self.status = "STARTING"
            self.logs = []
            self.current_run = {}
            self.active_thread = threading.Thread(
                target=self._run_autonomous_loop_sync,
                args=(project_name, force_optimize),
                daemon=True
            )
            self.active_thread.start()
            return True

    def _run_autonomous_loop_sync(self, project_name: str, force_optimize: bool = False):
        """
        Synchronous loop execution, coordinates all agents.
        """
        self.log(f"🚀 Starting autonomous optimization cycle for Phoenix project: '{project_name}'...")
        start_time = time.time()
        
        run_record = {
            "timestamp": datetime.now().isoformat(),
            "project": project_name,
            "status": "FAILED",
            "initial_score": 0.0,
            "final_score": 0.0,
            "winner_strategy": "N/A",
            "mr_url": "N/A",
            "failures_found": 0,
            "diagnosed_clusters": []
        }

        try:
            # Step 1: FETCHING_SPANS
            self.status = "FETCHING_SPANS"
            self.log("[Step 1/6] Querying conversation trace spans from Arize Phoenix Cloud via MCP...")
            monitor = PromptMonitor()
            spans_df = asyncio.run(monitor.fetch_recent_spans(project_name))
            
            # Step 2: RUNNING_JUDGES
            self.status = "RUNNING_JUDGES"
            self.log("[Step 2/6] Auditing trace correctness using LLM-as-a-Judge...")
            
            if spans_df.empty:
                self.log("⚠️ No spans found in Phoenix project. Proceeding with mock failures injection for verification...")
                failing_spans = pd.DataFrame()
                initial_score = 0.90
            else:
                eval_results = monitor.run_evaluations(spans_df)
                monitor.log_evaluations_back(project_name, eval_results)
                
                # Check performance reports
                reports = monitor.analyze_performance(eval_results, spans_df)
                initial_score = reports[0].eval_score if reports else 1.0
                
                # Filter failures
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

            run_record["initial_score"] = initial_score
            self.log(f"   Current Correctness Score: {initial_score:.1%} (Threshold: 85.0%)")

            # Check if optimization is needed
            needs_optimization = initial_score < 0.85 or force_optimize
            
            # Inject mock failures to guarantee optimization path works if forced or empty
            if (failing_spans.empty and force_optimize) or (spans_df.empty):
                self.log("⚠️ Injecting typical retail policy failures to drive prompt optimization...")
                mock_failures = [
                    {
                        "input": "I need a refund for my broken headphones. Give me my money back now.",
                        "output": "I am so sorry to hear that. I've processed a refund for your broken headphones. Have a great day!",
                        "eval_explanation": "Fails procedural compliance: immediately processed refund without asking for transaction ID or order number."
                    },
                    {
                        "input": "Can you help me fix a bug in my Python code?",
                        "output": "Sure! A KeyError happens when you search for a key that does not exist in the dictionary. Here is how you can fix it: `if key in my_dict: ...`",
                        "eval_explanation": "Fails scope awareness: answered a general coding question completely outside store electronics support boundaries."
                    }
                ]
                failing_spans = pd.DataFrame(mock_failures)
                failing_spans.index = ["mock-refund-failure", "mock-coding-failure"]

            run_record["failures_found"] = len(failing_spans)

            if not needs_optimization and len(failing_spans) == 0:
                self.status = "COMPLETED"
                self.log("✅ Current prompt correctness is above the 85% threshold. No optimization needed!")
                run_record["status"] = "SUCCESS"
                run_record["winner_strategy"] = "baseline"
                run_record["final_score"] = initial_score
                self._save_to_history(run_record)
                return

            # Step 3: DIAGNOSING_FAILURES
            self.status = "DIAGNOSING_FAILURES"
            self.log(f"[Step 3/6] Compiling failure diagnostics for {len(failing_spans)} failing interactions...")
            
            # Load baseline prompt config
            prompts_path = Path("src/prompts.json")
            with open(prompts_path) as f:
                prompts_data = json.load(f)
            baseline_config = prompts_data["prompts"]["customer_support"]
            
            analyzer = FailureAnalyzer()
            report = analyzer.analyze_failures(
                failing_spans_df=failing_spans,
                prompt_config=baseline_config,
                overall_score=initial_score
            )
            
            # Record diagnosed clusters
            diagnosed_clusters = []
            for cluster in report.failure_clusters:
                diagnosed_clusters.append({
                    "category": cluster.category,
                    "failure_pattern": cluster.failure_pattern,
                    "count": cluster.count
                })
            run_record["diagnosed_clusters"] = diagnosed_clusters

            # Step 4: OPTIMIZING_PROMPTS
            self.status = "OPTIMIZING_PROMPTS"
            self.log("[Step 4/6] Programmatically generating prompt variants using Gemini...")
            optimizer = PromptOptimizer()
            variants = optimizer.optimize_prompt(report)

            # Step 5: SHADOW_EVALUATIONS
            self.status = "SHADOW_EVALUATIONS"
            self.log("[Step 5/6] Executing Shadow Evaluations against the golden dataset...")
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
            
            winner = eval_report["winner"]
            is_improved = eval_report["is_improved"]
            winner_strategy = eval_report["winner_strategy"]
            winner_acc = winner.get("accuracy", 0.0)
            baseline_acc = eval_report["baseline"]["accuracy"]
            
            # Align initial_score and final_score to represent golden dataset evaluations
            run_record["initial_score"] = baseline_acc
            run_record["final_score"] = winner_acc
            run_record["winner_strategy"] = winner_strategy
            run_record["production_score"] = initial_score
            
            self.log(f"   Evaluation Winner: {winner.get('prompt_id')} ({winner_strategy})")
            self.log(f"   Accuracy: {winner_acc:.1%} (Baseline (Golden): {baseline_acc:.1%})")

            # Step 6: OPENING_MERGE_REQUEST
            if is_improved and winner_strategy != "baseline":
                self.status = "OPENING_MERGE_REQUEST"
                self.log("[Step 6/6] Initiating GitOps prompt deployment to GitLab...")
                
                # 1. Update prompts.json locally
                opt_count = baseline_config.get("metadata", {}).get("optimization_count", 0) + 1
                updated_cs = {
                    "id": "customer_support",
                    "version": "1.1.0",
                    "description": "ElectroGadget Hub customer support system prompt - Optimized",
                    "system_instruction": winner["system_instruction"],
                    "model": winner.get("model", baseline_config["model"]),
                    "parameters": {
                        "temperature": winner.get("parameters", {}).get("temperature", baseline_config["parameters"]["temperature"]),
                        "max_output_tokens": winner.get("parameters", {}).get("max_output_tokens", baseline_config["parameters"]["max_output_tokens"])
                    },
                    "metadata": {
                        "created_at": baseline_config.get("metadata", {}).get("created_at", "2026-05-28T00:00:00Z"),
                        "created_by": baseline_config.get("metadata", {}).get("created_by", "initial_setup"),
                        "optimization_count": opt_count,
                        "optimized_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "optimized_by": f"evaluation_agent_v2 ({winner_strategy})"
                    }
                }
                prompts_data["prompts"]["customer_support"] = updated_cs
                with open(prompts_path, "w") as f:
                    json.dump(prompts_data, f, indent=2)
                self.log("   Updated prompts.json locally.")

                # 2. Deploy to GitLab
                deployer = GitLabDeployer()
                deploy_res = asyncio.run(deployer.deploy_optimized_prompt(prompts_data, eval_report))
                mr_url = deploy_res.get("mr_url", "N/A")
                run_record["mr_url"] = mr_url
                self.log(f"   GitLab Merge Request successfully opened via MCP! MR URL: {mr_url}")
            else:
                self.log("⚠️ Optimization did not beat baseline or baseline was selected. Local prompt config kept.")
                run_record["mr_url"] = "N/A"

            self.status = "COMPLETED"
            self.log(f"✅ Autonomous optimization cycle completed successfully in {time.time() - start_time:.1f}s!")
            run_record["status"] = "SUCCESS"
            self._save_to_history(run_record)

        except Exception as e:
            self.status = "FAILED"
            self.log(f"❌ Autonomous cycle failed: {e}")
            run_record["status"] = "FAILED"
            self._save_to_history(run_record)


if __name__ == "__main__":
    # Quick test execution
    orchestrator = Orchestrator()
    print("Orchestrator instance initialized successfully!")
    print(f"Current Orchestrator Status: {orchestrator.status}")
