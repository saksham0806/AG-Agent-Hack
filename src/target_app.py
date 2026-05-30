"""
ElectroGadget Hub - Customer Support LLM Application

A sample LLM application with externalized prompts and full OpenInference
tracing to Arize Phoenix Cloud. This is the "target" that our improvement
loop agent will optimize.
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables (MUST happen before Phoenix imports so OTel can read them)
load_dotenv()

# --- Tracing Setup (MUST come before any LLM client imports) ---
from phoenix.otel import register
from openinference.instrumentation.google_adk import GoogleADKInstrumentor
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

# Register Arize Phoenix tracer provider. 
# It reads PHOENIX_COLLECTOR_ENDPOINT and PHOENIX_API_KEY from environment variables automatically.
tracer_provider = register(
    project_name=os.getenv("PHOENIX_PROJECT_NAME", "llm-eval-agent"),
    auto_instrument=True
)

# Instrument the Google GenAI SDK so all Gemini calls are captured cleanly
# (We comment out GoogleADKInstrumentor to prevent duplicated overlapping spans)
# GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)

# --- Application Code ---
from google import genai

# Load externalized prompts
PROMPTS_PATH = Path(__file__).parent / "prompts.json"

def load_prompts() -> dict:
    """Load prompt templates from the JSON config file."""
    with open(PROMPTS_PATH) as f:
        return json.load(f)

def get_prompt_config(prompt_id: str) -> dict:
    """Retrieve a specific prompt configuration by ID."""
    prompts = load_prompts()
    return prompts["prompts"][prompt_id]

def run_customer_support(query: str, prompt_id: str = "customer_support") -> str:
    """
    Run the customer support LLM with the specified prompt template, with retries on transient errors.
    
    Args:
        query: The customer's question or request
        prompt_id: The prompt template ID to use from prompts.json
    
    Returns:
        The LLM's response string
    """
    import time
    config = get_prompt_config(prompt_id)
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your-gemini-api-key":
        raise ValueError("GOOGLE_API_KEY is not set in the environment variables.")
        
    client = genai.Client(api_key=api_key)
    
    max_retries = 4
    initial_delay = 2.0
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=config["model"],
                contents=query,
                config=genai.types.GenerateContentConfig(
                    system_instruction=config["system_instruction"],
                    temperature=config["parameters"]["temperature"],
                    max_output_tokens=config["parameters"]["max_output_tokens"],
                )
            )
            return response.text
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ Gemini API call failed after {max_retries} attempts: {e}")
                raise e
            err_msg = str(e)
            trimmed_err = err_msg[:120] + "..." if len(err_msg) > 120 else err_msg
            print(f"⚠️ Gemini API transient error (attempt {attempt+1}/{max_retries}): {trimmed_err}. Retrying in {delay:.1f}s...")
            time.sleep(delay)
            delay *= 2.0

if __name__ == "__main__":
    import sys
    query = sys.argv[1] if len(sys.argv) > 1 else "What is your return policy?"
    try:
        print(f"Running Support Agent with query: '{query}'")
        output = run_customer_support(query)
        print("\n--- Support Response ---")
        print(output)
        print("------------------------")
    except Exception as e:
        print(f"❌ Error running support agent: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        print("Flushing and shutting down tracer provider...")
        tracer_provider.shutdown()
