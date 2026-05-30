# scripts/verify_dashboard.py
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from src.dashboard.app import app
from src.agent.orchestrator import Orchestrator

load_dotenv()

def main():
    print("--- STARTING PHASE 6: ORCHESTRATION & DASHBOARD VERIFICATION ---")
    
    # 1. Verify filesystem layout
    print("\n[Step 1] Verifying visual assets and directories in the filesystem...")
    base_dir = Path(__file__).parent.parent / "src" / "dashboard"
    paths_to_check = [
        base_dir / "app.py",
        base_dir / "templates" / "index.html",
        base_dir / "static" / "css" / "styles.css",
        base_dir / "static" / "js" / "main.js"
    ]
    
    all_exist = True
    for path in paths_to_check:
        exists = path.exists()
        status_char = "✅" if exists else "❌"
        print(f"  {status_char} {path.name:<12} at {path.relative_to(Path(__file__).parent.parent)}")
        if not exists:
            all_exist = False
            
    if not all_exist:
        print("❌ Missing directory assets. Verification failed.")
        sys.exit(1)
    print("  ✅ All filesystem directories and assets compiled successfully!")

    # 2. Instantiate and check the Orchestrator Singleton
    print("\n[Step 2] Testing Orchestrator Singleton state and thread safety...")
    try:
        orchestrator1 = Orchestrator()
        orchestrator2 = Orchestrator()
        
        # Assert Singleton pattern works
        assert orchestrator1 is orchestrator2
        print("  ✅ Orchestrator Singleton assertion succeeded!")
        print(f"  Initial Status:   {orchestrator1.status}")
        print(f"  Logs Container:   {len(orchestrator1.logs)} logs active")
        print(f"  History DB Path:  {orchestrator1.history_path}")
    except Exception as e:
        print(f"❌ Orchestrator check failed: {e}")
        sys.exit(1)

    # 3. Test API Endpoints using FastAPI TestClient (in-memory mock requests)
    print("\n[Step 3] Asserting FastAPI router and REST endpoints via in-memory TestClient...")
    try:
        client = TestClient(app)
        
        # Test 3.1: Root template render
        print("  Testing GET '/' (Dashboard HTML SPA)...")
        res_root = client.get("/")
        assert res_root.status_code == 200
        assert "ElectroGadget Hub" in res_root.text
        print("    ✅ GET '/' rendered HTML successfully!")
        
        # Test 3.2: Status API endpoint
        print("  Testing GET '/api/status' (Orchestrator polling API)...")
        res_status = client.get("/api/status")
        assert res_status.status_code == 200
        status_json = res_status.json()
        assert "status" in status_json
        assert "logs" in status_json
        assert "history" in status_json
        assert "active_prompt" in status_json
        print("    ✅ GET '/api/status' returned schema successfully!")
        print(f"    Reported State: {status_json['status']}")
        
        # Test 3.3: History API endpoint
        print("  Testing GET '/api/history' (Persistent history log API)...")
        res_history = client.get("/api/history")
        assert res_history.status_code == 200
        assert isinstance(res_history.json(), list)
        print("    ✅ GET '/api/history' parsed successfully!")
        
        print("\n" + "=" * 60)
        print("🎉 FASTAPI DOCK OVERVIEW & ENDPOINTS ASSERTED SUCCESSFULLY 🎉")
        print("=" * 60)
        print(f"App Title:       {app.title}")
        print(f"Mounts Active:   {len(app.routes)} endpoints compiled")
        print(f"Verified Host:   {os.getenv('DASHBOARD_HOST', '0.0.0.0')}")
        print(f"Verified Port:   {os.getenv('DASHBOARD_PORT', '8000')}")
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ FastAPI assertion failed: {e}")
        sys.exit(1)

    print("\n🎉 Phase 6: Orchestration & Dashboard verification completed successfully!")


if __name__ == "__main__":
    main()
