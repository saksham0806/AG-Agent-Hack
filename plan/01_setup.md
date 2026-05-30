# Phase 1: Environment & Setup

> **Goal**: Set up the complete development environment, obtain all credentials, scaffold the project structure, and verify connectivity to all external services.
>
> **Estimated Time**: 1-2 hours

---

## 1.1 Prerequisites

### System Requirements
- **OS**: Linux or macOS
- **Python**: 3.11+ (required by Google ADK 1.0)
- **Node.js**: v18+ with npm (for MCP servers via `npx`)
- **Git**: Installed and configured with SSH/HTTPS credentials

### Verify Prerequisites
```bash
python3 --version    # Should be 3.11+
node --version       # Should be v18+
npm --version        # Should be 9+
git --version        # Any recent version
```

---

## 1.2 Obtain Credentials

You need **three** sets of credentials. Collect them before proceeding.

### A. Google Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/apikey)
2. Click **"Create API Key"**
3. Copy the key — it starts with `AIza...`

> [!TIP]
> If you want to use Vertex AI instead (for enterprise features), set `GOOGLE_GENAI_USE_VERTEXAI=TRUE` and authenticate with `gcloud auth application-default login`.

### B. Arize Phoenix Cloud
1. Sign up at [phoenix.arize.com](https://app.phoenix.arize.com) — **free tier** is sufficient
2. Create a **Space** from the dashboard (e.g., `hackathon-2026`)
3. Navigate to **Settings → API Keys → "Add System Key"**
4. Copy the API key
5. Note your **Collector Endpoint** from Settings → General → Hostname:
   ```
   https://app.phoenix.arize.com/s/<your-space-name>/v1/traces
   ```

### C. GitLab Personal Access Token (PAT)
1. Go to [gitlab.com](https://gitlab.com) (or start a [30-day Ultimate trial](https://about.gitlab.com/free-trial/) for Duo features)
2. Navigate to **Settings → Access Tokens**
3. Create a new token with these **scopes**:
   - `api` (full API access)
   - `read_repository`
   - `write_repository`
4. Copy the token — it starts with `glpat-...`
5. Create a **target repository** on GitLab where prompt configs will live (e.g., `your-username/prompt-configs`)

---

## 1.3 Project Scaffold

### Directory Structure
```
AG-Agent-Hack/
├── plan/                          # ← You are here (planning docs)
│
├── .env                           # Environment variables (git-ignored)
├── .env.template                  # Template for team members
├── .gitignore                     # Python + Node.js ignores
├── requirements.txt               # Python dependencies
├── pyproject.toml                 # Optional: for uv/poetry users
├── README.md                      # Project overview + demo instructions
│
├── src/
│   ├── __init__.py
│   ├── prompts.json               # Externalized prompt templates (version-controlled)
│   ├── target_app.py              # Sample LLM app to optimize
│   │
│   ├── agent/                     # Core improvement loop agent
│   │   ├── __init__.py
│   │   ├── agent.py               # ADK root_agent definition
│   │   ├── monitor.py             # Phoenix trace monitoring
│   │   ├── analyzer.py            # Failure diagnosis & clustering
│   │   ├── optimizer.py           # Gemini-powered prompt variant generation
│   │   ├── evaluator.py           # Shadow evaluation engine
│   │   ├── gitlab_deployer.py     # GitLab MCP integration (branch + MR)
│   │   └── orchestrator.py        # Main loop tying all stages
│   │
│   └── dashboard/                 # Web UI
│       ├── app.py                 # FastAPI backend
│       ├── templates/             # Jinja2 HTML templates
│       │   └── index.html
│       └── static/                # Frontend assets
│           ├── css/
│           │   └── index.css
│           └── js/
│               └── index.js
│
├── scripts/
│   ├── simulate_traffic.py        # Traffic generator for seeding traces
│   └── run_evals.py               # Standalone eval runner
│
├── tests/
│   ├── test_monitor.py
│   ├── test_analyzer.py
│   ├── test_optimizer.py
│   └── test_evaluator.py
│
└── data/
    └── golden_dataset.json        # Ground-truth Q&A pairs for shadow evals
```

### Create the Scaffold
```bash
cd /run/media/Saksham/Saksham/Code/Projects/AG-Agent-Hack

# Create directories
mkdir -p src/agent src/dashboard/templates src/dashboard/static/css src/dashboard/static/js
mkdir -p scripts tests data

# Create __init__.py files
touch src/__init__.py src/agent/__init__.py

# Create .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.venv/
venv/
env/
*.egg-info/
dist/
build/

# Environment
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Node
node_modules/

# Phoenix
phoenix_data/
EOF
```

---

## 1.4 Python Environment Setup (using uv)

We use `uv` (an ultra-fast Python package installer and resolver written in Rust) to manage our environment and dependencies.

### Create Virtual Environment
```bash
# Using python3.11 to create the virtual environment:
python3.11 -m venv .venv
source .venv/bin/activate

# Install uv inside the virtual environment:
pip install uv
```

### Install Dependencies
Create `requirements.txt`:
```
# Google ADK & Gemini
google-adk>=1.0.0
google-genai>=1.0.0

# Arize Phoenix (Observability)
arize-phoenix>=8.0.0
arize-phoenix-otel>=0.8.0
openinference-instrumentation-google-adk>=0.1.0

# OpenTelemetry
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp>=1.20.0

# Web Dashboard
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
jinja2>=3.1.2

# Utilities
python-dotenv>=1.0.0
httpx>=0.27.0
pydantic>=2.0.0
pandas>=2.0.0
numpy>=1.24.0
```

Install using `uv` (which installs all packages in seconds):
```bash
uv pip install -r requirements.txt
```

---

## 1.5 Environment Variables

### Create `.env.template`
```bash
cat > .env.template << 'EOF'
# ============================================
# Google Gemini
# ============================================
GOOGLE_API_KEY=your-gemini-api-key
GOOGLE_GENAI_USE_VERTEXAI=FALSE

# ============================================
# Arize Phoenix Cloud
# ============================================
PHOENIX_API_KEY=your-phoenix-api-key
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/<your-space>/v1/traces

# ============================================
# GitLab
# ============================================
GITLAB_PERSONAL_ACCESS_TOKEN=glpat-your-token
GITLAB_API_URL=https://gitlab.com/api/v4
GITLAB_PROJECT_ID=your-username/prompt-configs
GITLAB_DEFAULT_BRANCH=main

# ============================================
# Dashboard
# ============================================
DASHBOARD_HOST=0.0.0.0
DASHBOARD_PORT=8000
EOF
```

### Create Your `.env`
```bash
cp .env.template .env
# Edit .env with your actual credentials
```

---

## 1.6 MCP Server Configuration

Create `mcp_servers.json` for reference (used programmatically by the ADK agent):
```json
{
  "mcpServers": {
    "arize-phoenix": {
      "command": "npx",
      "args": [
        "-y",
        "@arizeai/phoenix-mcp@latest",
        "--baseUrl",
        "https://app.phoenix.arize.com/s/<your-space>",
        "--apiKey",
        "<your-phoenix-api-key>"
      ]
    },
    "gitlab": {
      "command": "npx",
      "args": ["-y", "@structured-world/gitlab-mcp"],
      "env": {
        "GITLAB_PERSONAL_ACCESS_TOKEN": "<your-gitlab-pat>",
        "GITLAB_API_URL": "https://gitlab.com/api/v4"
      }
    }
  }
}
```

> [!IMPORTANT]
> Replace all placeholder values (`<your-...>`) with your actual credentials before proceeding.

---

## 1.7 Verify Connectivity

### Test Gemini API
```python
# scripts/verify_gemini.py
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="Say 'Hello from Gemini!' in exactly 5 words."
)
print("✅ Gemini:", response.text)
```

### Test Phoenix Cloud
```python
# scripts/verify_phoenix.py
import os
from dotenv import load_dotenv
from phoenix.otel import register

load_dotenv()
tracer_provider = register(project_name="connectivity-test")
print("✅ Phoenix Cloud: Connected to", os.getenv("PHOENIX_COLLECTOR_ENDPOINT"))
```

### Test MCP Servers (quick check)
```bash
# Phoenix MCP — should list available tools
npx -y @arizeai/phoenix-mcp@latest --help

# GitLab MCP — should show version
npx -y @structured-world/gitlab-mcp --version
```

### Run All Verifications
```bash
source .venv/bin/activate
python scripts/verify_gemini.py
python scripts/verify_phoenix.py
```

---

## 1.8 Completion Checklist

- [ ] Python 3.11+ installed and working
- [ ] Node.js v18+ installed
- [ ] Virtual environment created and activated
- [ ] All pip dependencies installed without errors
- [ ] `.env` file created with all credentials filled in
- [ ] Gemini API key verified (generates a response)
- [ ] Phoenix Cloud account created, API key obtained, collector endpoint noted
- [ ] GitLab PAT created with correct scopes
- [ ] GitLab target repository created (for prompt configs)
- [ ] MCP servers can be invoked via `npx` without errors
- [ ] Project directory structure scaffolded

---

> **Next Phase**: [Phase 2: Target App & Instrumentation →](02_target_app.md)
