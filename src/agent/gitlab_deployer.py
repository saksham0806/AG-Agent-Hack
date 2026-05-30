"""
GitLab Deployer Module — Connects to GitLab REST API to automate prompt deployment.

Creates a unique branch, commits the optimized prompts.json configuration,
and opens a descriptive Merge Request containing evaluation metrics and performance tables.
"""

import os
import json
import urllib.parse
import time
from typing import Dict, Any
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class GitLabDeployer:
    def __init__(self):
        self.pat = os.getenv("GITLAB_PERSONAL_ACCESS_TOKEN")
        self.api_url = os.getenv("GITLAB_API_URL", "https://gitlab.com/api/v4")
        self.project_id = os.getenv("GITLAB_PROJECT_ID")
        self.default_branch = os.getenv("GITLAB_DEFAULT_BRANCH", "main")

        if not self.pat:
            raise ValueError("GITLAB_PERSONAL_ACCESS_TOKEN is not set in the environment variables.")
        if not self.project_id:
            raise ValueError("GITLAB_PROJECT_ID is not set in the environment variables.")

        # URL encode the project ID (e.g. sakshamsingh0806alt/llm-eval-agent -> sakshamsingh0806alt%2Fllm-eval-agent)
        self.encoded_project_id = urllib.parse.quote_plus(self.project_id)
        
        # Initialize httpx synchronous client with authentication headers
        self.client = httpx.Client(
            headers={
                "PRIVATE-TOKEN": self.pat,
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

    def _generate_mr_description(self, eval_report: Dict[str, Any]) -> str:
        """
        Generate a rich, visually stunning Markdown description comparing baseline and variants.
        """
        baseline = eval_report.get("baseline", {})
        winner = eval_report.get("winner", {})
        candidates = eval_report.get("candidates", [])

        # Extract accuracy and keyword stats
        base_acc = baseline.get("accuracy", 0.0)
        base_kw = baseline.get("avg_keyword_pass_rate", 0.0)
        base_lat = baseline.get("avg_latency", 0.0)

        winner_strategy = eval_report.get("winner_strategy", "baseline")
        winner_id = winner.get("prompt_id")
        winner_acc = winner.get("accuracy", 0.0)
        winner_version = winner.get("prompt_version", "1.1.0")
        winner_instruction = winner.get("system_instruction", "")

        # Format comparison table rows
        table_rows = []
        
        # Add baseline row
        table_rows.append(
            f"| `customer_support` (baseline) | Baseline | **{base_acc:.1%}** | {base_kw:.1%} | {base_lat:.2f}s |"
        )
        
        # Add candidate rows
        for c in candidates:
            c_name = f"`{c.get('prompt_id')}`"
            c_strategy = c.get("strategy", "candidate")
            c_acc = c.get("accuracy", 0.0)
            c_kw = c.get("avg_keyword_pass_rate", 0.0)
            c_lat = c.get("avg_latency", 0.0)
            
            # Highlight winner
            strategy_label = f"**{c_strategy} (Winner)**" if c_strategy == winner_strategy else c_strategy
            acc_label = f"**{c_acc:.1%}**" if c_strategy == winner_strategy else f"{c_acc:.1%}"
            
            table_rows.append(
                f"| {c_name} | {strategy_label} | {acc_label} | {c_kw:.1%} | {c_lat:.2f}s |"
            )

        table_rows_str = "\n".join(table_rows)
        improvement = winner_acc - base_acc

        mr_desc = f"""# 🤖 Autonomous LLM Prompt Optimization Report

An underperforming prompt has been programmatically optimized and successfully verified on the **golden dataset**!

This Merge Request updates `src/prompts.json` with the winning prompt configuration.

## 📊 Shadow Evaluation Performance Metrics

A shadow evaluation was executed comparing the baseline prompt against 3 distinct prompt engineering candidates:

| Prompt ID & Suffix | Strategy / Variant | Accuracy (Correctness) | Keyword Match Rate | Average Latency |
| :--- | :--- | :--- | :--- | :--- |
{table_rows_str}

> [!NOTE]
> - **Primary Selection Metric**: Overall LLM-as-a-Judge correctness accuracy.
> - **Tiebreaking Metrics**: Average expected keyword pass rate, average response latency, and token efficiency.

## 🏆 Final Verdict

The programmatically selected winner is **`{winner_id}` ({winner_strategy})**, which achieved **{winner_acc:.1%}** accuracy (an absolute improvement of **{improvement:+.1%}** over the baseline correctness of {base_acc:.1%}).

## 📝 Winning Optimized Prompt Instructions (v{winner_version})

```markdown
{winner_instruction}
```

---
*Autonomous MR opened programmatically by Antigravity Eval-to-Improvement Loop Agent.*
"""
        return mr_desc

    def deploy_optimized_prompt(self, optimized_prompts_dict: dict, eval_report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full GitOps lifecycle deployment:
        1. Create new branch off default branch
        2. Commit prompts.json changes to the branch
        3. Create a GitLab Merge Request pointing to default branch with rich descriptions.
        """
        timestamp = int(time.time())
        branch_name = f"optimize-prompt-v1.1.0-{timestamp}"
        winner = eval_report.get("winner", {})
        winner_strategy = eval_report.get("winner_strategy", "baseline")
        
        print(f"\n🚀 Initiating GitLab prompt deployment for project '{self.project_id}'...")
        
        # Step 1: Create a new branch
        print(f"  [1/3] Creating new branch '{branch_name}' branching from '{self.default_branch}'...")
        create_branch_url = f"{self.api_url}/projects/{self.encoded_project_id}/repository/branches"
        try:
            res = self.client.post(
                create_branch_url,
                json={
                    "branch": branch_name,
                    "ref": self.default_branch
                }
            )
            if res.status_code != 201:
                raise httpx.HTTPStatusError(
                    f"GitLab branch creation failed with status {res.status_code}: {res.text}",
                    request=res.request,
                    response=res
                )
            print(f"  ✅ Branch '{branch_name}' created successfully!")
        except Exception as e:
            print(f"  ❌ Error creating branch on GitLab: {e}")
            raise e

        # Step 2: Commit prompts.json modification
        print(f"  [2/3] Committing updated prompts.json config to branch '{branch_name}'...")
        commit_url = f"{self.api_url}/projects/{self.encoded_project_id}/repository/commits"
        
        # Prepare file content
        file_content = json.dumps(optimized_prompts_dict, indent=2)
        
        commit_payload = {
            "branch": branch_name,
            "commit_message": f"chore: optimize customer_support system prompt to version 1.1.0 ({winner_strategy})",
            "actions": [
                {
                    "action": "update",
                    "file_path": "src/prompts.json",
                    "content": file_content
                }
            ]
        }
        
        try:
            res = self.client.post(commit_url, json=commit_payload)
            if res.status_code != 201:
                # If error is that file doesn't exist, retry with "create" action
                err_text = res.text
                if res.status_code == 400 and ("doesn't exist" in err_text or "does not exist" in err_text):
                    print("  ⚠️ File 'src/prompts.json' does not exist remotely. Retrying with 'create' action...")
                    commit_payload["actions"][0]["action"] = "create"
                    res = self.client.post(commit_url, json=commit_payload)
                    if res.status_code != 201:
                        raise httpx.HTTPStatusError(
                            f"GitLab commit retry failed with status {res.status_code}: {res.text}",
                            request=res.request,
                            response=res
                        )
                else:
                    raise httpx.HTTPStatusError(
                        f"GitLab commit failed with status {res.status_code}: {res.text}",
                        request=res.request,
                        response=res
                    )
            print("  ✅ Prompts committed successfully!")
        except Exception as e:
            print(f"  ❌ Error committing prompt configuration: {e}")
            raise e

        # Step 3: Open a Merge Request
        print(f"  [3/3] Opening GitLab Merge Request from '{branch_name}' to '{self.default_branch}'...")
        mr_url = f"{self.api_url}/projects/{self.encoded_project_id}/merge_requests"
        
        title = f"chore(prompt): optimize customer_support system prompt to v1.1.0 ({winner_strategy})"
        description = self._generate_mr_description(eval_report)
        
        mr_payload = {
            "source_branch": branch_name,
            "target_branch": self.default_branch,
            "title": title,
            "description": description,
            "remove_source_branch": True  # Automatically clean up branch after merging
        }
        
        try:
            res = self.client.post(mr_url, json=mr_payload)
            if res.status_code != 201:
                raise httpx.HTTPStatusError(
                    f"GitLab Merge Request creation failed with status {res.status_code}: {res.text}",
                    request=res.request,
                    response=res
                )
            mr_data = res.json()
            mr_web_url = mr_data.get("web_url")
            mr_id = mr_data.get("iid")
            print(f"  ✅ GitLab Merge Request opened successfully!")
            print(f"  🔗 Merge Request URL: {mr_web_url}")
            
            return {
                "branch": branch_name,
                "mr_iid": mr_id,
                "mr_url": mr_web_url,
                "status": "success"
            }
        except Exception as e:
            print(f"  ❌ Error opening Merge Request: {e}")
            raise e


if __name__ == "__main__":
    # Standard dummy test
    try:
        deployer = GitLabDeployer()
        print("GitLabDeployer initialized successfully!")
    except Exception as e:
        print(f"Initialization failed: {e}")
