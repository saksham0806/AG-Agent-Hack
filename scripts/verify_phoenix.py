# scripts/verify_phoenix.py
import os
from dotenv import load_dotenv
from phoenix.otel import register

load_dotenv()

collector_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
api_key = os.getenv("PHOENIX_API_KEY")

if not collector_endpoint or "your-space" in collector_endpoint:
    print("❌ PHOENIX_COLLECTOR_ENDPOINT is not set properly or contains template placeholders.")
    exit(1)

if not api_key or api_key == "your-phoenix-api-key":
    print("❌ PHOENIX_API_KEY is not set or is still the default template value.")
    exit(1)

try:
    print(f"Registering OpenTelemetry trace provider for Arize Phoenix...")
    print(f"Collector Endpoint: {collector_endpoint}")
    tracer_provider = register(project_name="connectivity-test")
    print(f"✅ Arize Phoenix tracing registered successfully!")
except Exception as e:
    print(f"❌ Arize Phoenix registration failed: {e}")
    exit(1)
