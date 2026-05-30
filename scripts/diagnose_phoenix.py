# scripts/diagnose_phoenix.py
import os
import sys
import logging
from dotenv import load_dotenv

# Enable verbose debugging logs for OpenTelemetry and HTTP requests
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.getLogger("opentelemetry").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)

load_dotenv()

from phoenix.otel import register
from opentelemetry import trace

print("--- PHOENIX DIAGNOSTIC SCRIPT ---")
project_name = os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent")
collector_endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
api_key = os.getenv("PHOENIX_API_KEY")

print(f"Project Name: {project_name}")
print(f"Collector Endpoint: {collector_endpoint}")
print(f"API Key (first 10 chars): {api_key[:10] if api_key else 'None'}")
print(f"API Key (length): {len(api_key) if api_key else 0}")
print("-" * 50)

try:
    print("Registering OTel tracer provider...")
    tracer_provider = register(
        project_name=project_name,
        auto_instrument=True
    )
    
    print("Creating diagnostic test span...")
    tracer = trace.get_tracer("diagnose-tracer")
    with tracer.start_as_current_span("diagnostic-test-span") as span:
        span.set_attribute("diagnostics.status", "active")
        print("Span created. Now flushing and shutting down tracer provider...")
        
    tracer_provider.shutdown()
    print("✅ Diagnostic script completed execution successfully!")
    print("If no network errors were printed above, check your Phoenix Cloud workspace.")
except Exception as e:
    print(f"❌ Error during diagnostic run: {e}")
