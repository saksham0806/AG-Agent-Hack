# Phase 7: Polish, Testing & Submission

> **Goal**: Final integration testing, documentation, demo video recording, and Devpost submission preparation. Make everything production-quality.
>
> **Estimated Time**: 2-3 hours

---

## 7.1 Integration Testing

### Full E2E Test Sequence

Run the complete pipeline end-to-end to verify all components work together:

```bash
# Step 1: Activate environment
source .venv/bin/activate

# Step 2: Seed traces (if not already done)
python scripts/simulate_traffic.py --num-runs 30 --delay 1

# Step 3: Verify traces in Phoenix Cloud
# → Open https://app.phoenix.arize.com and check the electrogadget-hub project

# Step 4: Run the full orchestration loop
python -m src.agent.orchestrator --project electrogadget-hub

# Step 5: Verify the GitLab Merge Request
# → Check the MR URL printed by the orchestrator
# → Verify the evaluation report in the MR description
# → Verify the prompts.json diff

# Step 6: Start the dashboard and verify UI
uvicorn src.dashboard.app:app --port 8000
# → Open http://localhost:8000
# → Click "Run Optimization"
# → Watch the pipeline progress
# → Verify run history updates

# Step 7: Test ADK agent via web UI
adk web src/agent
# → Interact with the agent and verify MCP tools work
```

### Multi-Generation Test
Run the optimization loop **twice** to verify:
1. First run: Baseline prompt → Optimized v1.1.0
2. Second run: v1.1.0 may or may not need further optimization
3. Verify version numbering increments correctly
4. Verify GitLab has two separate MRs

```bash
# Run 1
python -m src.agent.orchestrator

# Update local prompts.json with the winner (simulate merge)
# ... or merge the MR on GitLab and pull

# Run 2
python -m src.agent.orchestrator
```

---

## 7.2 Error Handling & Edge Cases

### Test These Scenarios

| Scenario | Expected Behavior |
|---|---|
| No traces in Phoenix | Orchestrator returns "NO_ACTION" status |
| All prompts above threshold | Orchestrator returns "NO_ACTION" |
| Gemini API rate limit | Retry with exponential backoff |
| GitLab MCP connection failure | Graceful error with message |
| All variants perform worse than original | Don't deploy, report to user |
| Phoenix MCP timeout | Fallback to Python client |

### Add Retry Logic
```python
import time
from functools import wraps

def retry(max_attempts=3, delay=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay * (attempt + 1))
        return wrapper
    return decorator
```

---

## 7.3 Documentation

### Update `README.md`

The README should cover:

```markdown
# 🤖 LLM Eval-to-Improvement Loop Agent

> An autonomous AI engineering system that monitors, diagnoses, optimizes, 
> evaluates, and deploys LLM prompt improvements — powered by Gemini, 
> Arize Phoenix, and GitLab MCP.

## 🏆 Google Cloud Rapid Agent Hackathon 2026
**Partner Tracks**: Arize + GitLab

## 🎯 What It Does
[Brief description + architecture diagram]

## 🚀 Quick Start
[5-minute setup guide]

## 📋 Prerequisites
- Python 3.11+
- Node.js v18+
- Google Gemini API key
- Arize Phoenix Cloud account (free)
- GitLab account with PAT

## ⚙️ Installation
[Step-by-step]

## 🎮 Usage
### CLI
### Web Dashboard
### ADK Agent

## 🏗️ Architecture
[Mermaid diagram]

## 🔑 Key Features
- Self-improving agent using own observability data
- Two MCP integrations (Phoenix + GitLab)
- LLM-as-a-Judge evaluation pipeline
- Autonomous GitLab MR creation with rich eval reports
- Premium glassmorphic web dashboard

## 📹 Demo
[Link to demo video]

## 📜 License
MIT
```

### Code Documentation
- Add docstrings to all modules and functions
- Add type hints throughout
- Add inline comments for complex logic
- Ensure all configuration is documented

---

## 7.4 Demo Video

### Recording Plan (2-3 minutes)

**Opening (15s)**:
- Show the project title and hackathon context
- "This agent doesn't just answer questions — it improves itself."

**Problem Statement (20s)**:
- Show the baseline prompt performing poorly
- Highlight failure cases (refund without transaction ID, no escalation)

**Architecture Overview (20s)**:
- Show the architecture diagram
- Highlight: Phoenix MCP + GitLab MCP = two partner integrations

**Live Demo (90s)**:
1. **Phoenix Cloud** (15s): Show traces with poor evaluation scores
2. **Trigger Optimization** (10s): Click "Run Optimization" on dashboard
3. **Pipeline Progress** (20s): Watch Monitor → Analyze → Optimize → Evaluate → Deploy
4. **GitLab MR** (20s): Show the auto-generated Merge Request with eval tables
5. **Improvement** (15s): Show before/after accuracy comparison
6. **Dashboard** (10s): Show the run history and prompt performance cards

**Closing (15s)**:
- "From eval to improvement — autonomously."
- Tech stack summary

### Recording Tips
- Use OBS Studio or similar
- Record at 1080p minimum
- Use a clean browser with no personal tabs
- Pre-seed data so the demo runs smoothly
- Have fallback screenshots in case of API issues

---

## 7.5 Devpost Submission

### Required Fields

| Field | Content |
|---|---|
| **Project Name** | LLM Eval-to-Improvement Loop Agent |
| **Tagline** | Ship agents that don't just run — they self-improve |
| **Description** | [From README] |
| **What it does** | Monitors LLM traces, diagnoses failures, generates optimized prompts, runs shadow evaluations, and deploys winners via GitLab MR |
| **How we built it** | Google ADK + Gemini 2.5 + Arize Phoenix MCP + GitLab MCP + FastAPI |
| **Challenges** | [Document actual challenges encountered] |
| **What we learned** | [Document learnings] |
| **Built with** | Google ADK, Gemini 2.5, Arize Phoenix, GitLab, FastAPI, Python, OpenInference, MCP |
| **Partner Track** | Arize (primary) + GitLab (secondary) |
| **Video Demo** | [YouTube/Loom link] |
| **GitHub/GitLab Repo** | [Repository URL] |

### Submission Checklist
- [ ] Video demo recorded and uploaded
- [ ] README polished with screenshots
- [ ] Code pushed to public repository
- [ ] Devpost project page created
- [ ] All required fields filled
- [ ] Partner tracks selected (Arize + GitLab)
- [ ] Screenshots/images added to Devpost

---

## 7.6 Judging Criteria Alignment

### Arize Track Criteria

| Criterion | How We Address It |
|---|---|
| **Technical Implementation** | Full ADK multi-agent pipeline with custom tools |
| **Meaningful Use of Tracing** | OpenInference auto-instrumentation, LLM-as-a-Judge evals logged to Phoenix |
| **MCP Integration** | Phoenix MCP for self-introspection at runtime |
| **Self-Improvement Loop** | Agent uses its own trace data to optimize prompts (BONUS) |
| **Overall Impact** | Solves a real production AI problem (prompt optimization) |

### GitLab Track Criteria

| Criterion | How We Address It |
|---|---|
| **MCP Integration** | GitLab MCP for autonomous branching, commits, and MRs |
| **DevSecOps Workflow** | Full Git workflow: branch → commit → MR with eval report |
| **Practical Value** | Automated prompt deployment with human-in-the-loop review |

---

## 7.7 Final Completion Checklist

### Core Functionality
- [ ] Traffic simulator seeds traces into Phoenix Cloud
- [ ] Monitor detects underperforming prompts
- [ ] Analyzer clusters failures and produces diagnostic report
- [ ] Optimizer generates 3 prompt variants
- [ ] Evaluator runs shadow evals and selects winner
- [ ] Deployer creates GitLab branch, commits, and opens MR
- [ ] Orchestrator ties all stages together
- [ ] Dashboard provides UI control panel
- [ ] ADK agent works via `adk web`

### Quality
- [ ] Error handling for all external service calls
- [ ] Retry logic for API rate limits
- [ ] Graceful degradation on MCP server failures
- [ ] All code documented with docstrings
- [ ] Type hints throughout

### Submission
- [ ] README.md comprehensive and polished
- [ ] Demo video recorded (2-3 minutes)
- [ ] Code pushed to public repository
- [ ] Devpost submission created
- [ ] Partner tracks selected
- [ ] Screenshots added

---

## 🎉 Done!

You've built an autonomous LLM Eval-to-Improvement Loop Agent that:

1. **Monitors** LLM traces in Arize Phoenix Cloud
2. **Diagnoses** failure patterns using Gemini
3. **Optimizes** prompts by generating improved variants
4. **Evaluates** variants with LLM-as-a-Judge shadow testing
5. **Deploys** winners via GitLab MCP with rich evaluation reports

**Good luck with the hackathon! 🚀**
