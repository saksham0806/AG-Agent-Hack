"""
GitLab Deployer Module — Connects to GitLab REST API to automate prompt deployment.

Creates a unique branch, commits the optimized prompts.json configuration,
and opens a descriptive Merge Request containing evaluation metrics and performance tables.
"""

import os
import json
import urllib.parse
import time
import base64
from typing import Dict, Any
from dotenv import load_dotenv
from google.adk.tools import McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams
from mcp import StdioServerParameters

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

        # Sanitize GitLab URL (Strip trailing /api/v4 or api/v4 if present)
        # E.g. https://gitlab.com/api/v4 -> https://gitlab.com
        base_url = self.api_url
        if base_url.endswith("/api/v4"):
            base_url = base_url[:-7]
        elif base_url.endswith("api/v4"):
            base_url = base_url[:-6]
        base_url = base_url.rstrip("/")

        # Initialize GitLab MCP parameters
        self.gitlab_params = StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", "@structured-world/gitlab-mcp"],
                env={
                    "GITLAB_PERSONAL_ACCESS_TOKEN": self.pat,
                    "GITLAB_TOKEN": self.pat,
                    "GITLAB_PROJECT_ID": self.project_id,
                    "GITLAB_API_URL": base_url,
                    "GITLAB_BASE_URL": base_url,
                    "PATH": os.getenv("PATH", "")
                }
            ),
            timeout=15.0
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

    async def deploy_optimized_prompt(self, optimized_prompts_dict: dict, eval_report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Full GitOps lifecycle deployment using GitLab MCP server:
        1. Create new branch off default branch
        2. Commit prompts.json changes to the branch
        3. Create a GitLab Merge Request pointing to default branch with rich descriptions.
        """
        timestamp = int(time.time())
        branch_name = f"optimize-prompt-v1.1.0-{timestamp}"
        winner = eval_report.get("winner", {})
        winner_strategy = eval_report.get("winner_strategy", "baseline")
        
        print(f"\n🚀 Initiating GitLab prompt deployment via MCP for project '{self.project_id}'...")
        
        # Initialize toolset
        toolset = McpToolset(connection_params=self.gitlab_params)
        try:
            # Load tools from MCP server
            await toolset.get_tools()
            session = toolset._mcp_session_manager._sessions['stdio_session'][0]
            
            # Step 1: Create a new branch
            print(f"  [1/3] Creating new branch '{branch_name}' branching from '{self.default_branch}' via MCP...")
            create_branch_res = await session.call_tool(
                "create_branch",
                {
                    "project_id": self.project_id,
                    "branch": branch_name,
                    "ref": self.default_branch
                }
            )
            if create_branch_res.isError:
                err_text = create_branch_res.content[0].text if create_branch_res.content else "Unknown error"
                raise RuntimeError(f"GitLab branch creation failed: {err_text}")
            print(f"  ✅ Branch '{branch_name}' created successfully via MCP!")

            # Step 2: Commit prompts.json modification
            print(f"  [2/3] Committing updated prompts.json config to branch '{branch_name}' via MCP...")
            file_content = json.dumps(optimized_prompts_dict, indent=2)
            # Base64 encode file content as required by the GitLab MCP tool
            encoded_content = base64.b64encode(file_content.encode("utf-8")).decode("utf-8")
            
            # URL-encode the file path as expected by GitLab and the MCP schema
            encoded_file_path = urllib.parse.quote("src/prompts.json", safe="")
            
            commit_msg = f"chore: optimize customer_support system prompt to version 1.1.0 ({winner_strategy})"
            commit_res = await session.call_tool(
                "create_or_update_file",
                {
                    "project_id": self.project_id,
                    "file_path": encoded_file_path,
                    "branch": branch_name,
                    "content": encoded_content,
                    "encoding": "base64",
                    "commit_message": commit_msg
                }
            )
            if commit_res.isError:
                err_text = commit_res.content[0].text if commit_res.content else "Unknown error"
                raise RuntimeError(f"GitLab commit failed: {err_text}")
            print("  ✅ Prompts committed successfully via MCP!")

            # Step 3: Open a Merge Request
            print(f"  [3/3] Opening GitLab Merge Request from '{branch_name}' to '{self.default_branch}' via MCP...")
            title = f"chore(prompt): optimize customer_support system prompt to v1.1.0 ({winner_strategy})"
            description = self._generate_mr_description(eval_report)
            
            mr_res = await session.call_tool(
                "create_merge_request",
                {
                    "project_id": self.project_id,
                    "title": title,
                    "source_branch": branch_name,
                    "target_branch": self.default_branch,
                    "description": description
                }
            )
            if mr_res.isError:
                err_text = mr_res.content[0].text if mr_res.content else "Unknown error"
                raise RuntimeError(f"GitLab Merge Request creation failed: {err_text}")
                
            mr_data_text = mr_res.content[0].text if mr_res.content else "{}"
            mr_data = json.loads(mr_data_text)
            
            mr_web_url = mr_data.get("web_url", "")
            mr_id = mr_data.get("iid", 0)
            print(f"  ✅ GitLab Merge Request opened successfully via MCP!")
            print(f"  🔗 Merge Request URL: {mr_web_url}")
            
            return {
                "branch": branch_name,
                "mr_iid": mr_id,
                "mr_url": mr_web_url,
                "status": "success"
            }
        except Exception as e:
            print(f"  ❌ Error deploying via GitLab MCP: {e}")
            raise e
        finally:
            print("  Closing GitLab MCP Toolset session...")
            await toolset.close()


if __name__ == "__main__":
    # Standard dummy test
    try:
        deployer = GitLabDeployer()
        print("GitLabDeployer initialized successfully!")
    except Exception as e:
        print(f"Initialization failed: {e}")
