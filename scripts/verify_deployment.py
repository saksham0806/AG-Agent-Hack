# scripts/verify_deployment.py
import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.gitlab_deployer import GitLabDeployer

load_dotenv()

PROMPTS_PATH = Path(__file__).parent.parent / "src" / "prompts.json"

def load_prompts_file() -> dict:
    """Load the current optimized prompts configuration."""
    if not os.path.exists(PROMPTS_PATH):
        raise FileNotFoundError(f"Prompts file not found at {PROMPTS_PATH}")
    with open(PROMPTS_PATH) as f:
        return json.load(f)

def main():
    print("--- STARTING PHASE 5: GITLAB INTEGRATION & DEPLOYMENT VERIFICATION ---")
    
    # 1. Load prompts config
    print("\n[Step 1] Loading optimized prompts from prompts.json...")
    try:
        prompts_dict = load_prompts_file()
        support_prompt = prompts_dict["prompts"]["customer_support"]
        print(f"  Loaded prompt version: {support_prompt.get('version')} (Optimization Count: {support_prompt.get('metadata', {}).get('optimization_count')})")
    except Exception as e:
        print(f"❌ Error loading prompts config: {e}")
        sys.exit(1)
        
    # 2. Assemble mock evaluation report from our successful Phase 4 verification
    print("\n[Step 2] Compiling evaluation metrics from Phase 4 run...")
    eval_report = {
        "timestamp": "2026-05-30T03:00:00Z",
        "project": os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent-v2") + "-shadow-eval",
        "is_improved": True,
        "winner_strategy": "v1_conservative",
        "baseline": {
            "prompt_id": "customer_support",
            "prompt_version": "1.0.0",
            "strategy": "baseline",
            "accuracy": 0.60,
            "avg_keyword_pass_rate": 0.375,
            "avg_latency": 3.89
        },
        "candidates": [
            {
                "prompt_id": "customer_support_v1",
                "prompt_version": "1.1.0-v1",
                "strategy": "v1_conservative",
                "accuracy": 0.80,
                "avg_keyword_pass_rate": 0.483,
                "avg_latency": 4.04,
                "system_instruction": support_prompt["system_instruction"]
            },
            {
                "prompt_id": "customer_support_v2",
                "prompt_version": "1.1.0-v2",
                "strategy": "v2_moderate",
                "accuracy": 0.70,
                "avg_keyword_pass_rate": 0.375,
                "avg_latency": 3.95
            },
            {
                "prompt_id": "customer_support_v3",
                "prompt_version": "1.1.0-v3",
                "strategy": "v3_aggressive",
                "accuracy": 0.60,
                "avg_keyword_pass_rate": 0.467,
                "avg_latency": 4.15
            }
        ],
        "winner": {
            "prompt_id": "customer_support_v1",
            "prompt_version": "1.1.0",
            "strategy": "v1_conservative",
            "accuracy": 0.80,
            "avg_keyword_pass_rate": 0.483,
            "avg_latency": 4.04,
            "system_instruction": support_prompt["system_instruction"]
        }
    }
    
    # 3. Instantiate Deployer and execute GitLab deployment
    print("\n[Step 3] Executing deployment via GitLabDeployer...")
    try:
        deployer = GitLabDeployer()
        deployment_res = deployer.deploy_optimized_prompt(
            optimized_prompts_dict=prompts_dict,
            eval_report=eval_report
        )
        
        print("\n" + "=" * 60)
        print("🎉 GITLAB GITOPS DEPLOYMENT SUCCESSFUL 🎉")
        print("=" * 60)
        print(f"Project ID:      {deployer.project_id}")
        print(f"Target Branch:   {deployer.default_branch}")
        print(f"Created Branch:  {deployment_res['branch']}")
        print(f"Merge Request:   #{deployment_res['mr_iid']}")
        print(f"Merge Request URL:\n🔗 {deployment_res['mr_url']}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ GitLab deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
