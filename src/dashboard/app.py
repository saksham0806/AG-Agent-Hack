"""
FastAPI Dashboard Application — Serves the UI and exposes REST APIs for the Orchestrator.
"""

import os
import json
import sys
from pathlib import Path
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agent.orchestrator import Orchestrator

load_dotenv()

# Initialize FastAPI App
app = FastAPI(
    title="ElectroGadget Hub Autonomous Prompt Agent Dashboard",
    description="Visual UI for controlling and auditing LLM Eval-to-Improvement Loop Agent",
    version="1.1.0"
)

# Setup directories
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "js").mkdir(parents=True, exist_ok=True)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Initialize Orchestrator Singleton
orchestrator = Orchestrator()


def _get_active_prompt() -> dict:
    """Load the current active customer support prompt configuration."""
    prompts_path = Path("src/prompts.json")
    if not prompts_path.exists():
        return {}
    try:
        with open(prompts_path) as f:
            data = json.load(f)
            return data["prompts"]["customer_support"]
    except Exception:
        return {}


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Serve the primary Single Page Application (SPA) dashboard."""
    active_prompt = _get_active_prompt()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "project_name": os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent-v2"),
            "active_prompt": active_prompt
        }
    )


@app.get("/api/status")
async def get_status():
    """Retrieve current orchestrator state, active logs, active prompt config, and history."""
    active_prompt = _get_active_prompt()
    history = orchestrator.get_history()
    
    # Calculate some aggregated stats for the dashboard overview cards
    last_run_stats = {}
    if history:
        last_run = history[0]
        last_run_stats = {
            "timestamp": last_run.get("timestamp"),
            "status": last_run.get("status"),
            "initial_score": last_run.get("initial_score"),
            "final_score": last_run.get("final_score"),
            "failures_found": last_run.get("failures_found"),
            "winner_strategy": last_run.get("winner_strategy"),
            "mr_url": last_run.get("mr_url"),
            "diagnosed_clusters": last_run.get("diagnosed_clusters", [])
        }

    return JSONResponse(
        content={
            "status": orchestrator.status,
            "logs": orchestrator.logs,
            "active_prompt": active_prompt,
            "last_run": last_run_stats,
            "history": history
        }
    )


@app.post("/api/trigger")
async def trigger_loop(request: Request):
    """Trigger the prompt optimization loop asynchronously."""
    # Parse request JSON payload
    try:
        payload = await request.json()
        force_optimize = payload.get("force_optimize", False)
    except Exception:
        force_optimize = False
        
    project_name = os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent-v2")
    triggered = orchestrator.trigger_loop_async(project_name, force_optimize)
    
    return JSONResponse(
        content={
            "success": triggered,
            "message": "Autonomous optimization loop started successfully." if triggered else "Orchestrator is already running a cycle."
        }
    )


@app.get("/api/history")
async def get_history():
    """Fetch persistent historical runs log."""
    return JSONResponse(content=orchestrator.get_history())


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("DASHBOARD_HOST", "0.0.0.0")
    port = int(os.getenv("DASHBOARD_PORT", "8000"))
    print(f"Starting FastAPI Dashboard on http://{host}:{port}...")
    uvicorn.run(app, host=host, port=port)
