"""
Programmatic Golden Dataset Generator — Programmatically generates at least 70 unique customer queries.

Uses Gemini 2.5 Flash with structured Pydantic schemas to generate highly diverse, 
realistic customer support queries for ElectroGadget Hub.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load env
load_dotenv()

# Set paths
PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_PATH = PROJECT_ROOT / "data" / "golden_dataset.json"

class GoldenEntry(BaseModel):
    id: str = Field(description="Unique sequential ID, e.g. q001, q002, etc.")
    category: str = Field(description="One of: 'product_info', 'return_policy', 'refund_request', 'price_match', 'warranty', 'recommendation', 'escalation', 'out_of_scope'")
    query: str = Field(description="Highly specific customer support query, realistic and detailed.")
    expected_answer_contains: List[str] = Field(description="2-4 key words or short phrases that the response must include.")
    difficulty: str = Field(description="One of: 'easy', 'medium', 'hard'")

class CategoryBatch(BaseModel):
    entries: List[GoldenEntry]

def generate_category_queries(client: genai.Client, category: str, start_index: int, count: int = 9) -> List[dict]:
    """Generates a batch of unique queries for a specific category."""
    
    category_prompts = {
        "product_info": "Ask about technical specs, battery life, screen sizes, compatibility, or packaging of products like headphones, smartwatches, or laptops.",
        "return_policy": "Ask about returning items bought at various days ago (e.g. 10, 25, 35, 45, 60 days) to test the strict 30-day return policy limit.",
        "refund_request": "Ask for a refund on recent purchases, broken items, or incorrect shipments. Ensure the customer does not provide the transaction/order ID in their query, so that the agent is forced to ask for it.",
        "price_match": "Ask about price matching products found cheaper at other stores like CompetitorMart, TechGiant, or online platforms.",
        "warranty": "Ask about warranty claims for devices that stopped working, failed screens, or broken batteries, checking covered (under 12 months) and uncovered scenarios.",
        "recommendation": "Ask for suggestions for laptops, headphones, smartwatches, or gaming accessories matching specific budgets, specs, or user profiles (e.g. video editing under $1500, wireless gym headphones).",
        "escalation": "Highly angry or frustrated messages from customers who have contacted support multiple times (e.g. 3rd time, 5th time) or had their packages lost. These should trigger supervisor/manager escalation rules.",
        "out_of_scope": "Ask for programming help (e.g., Python bugs, web scraping), cooking recipes, math tutoring, or life advice to test scope rejection limits."
    }
    
    prompt = f"""
You are a senior data engineer specializing in training customer support LLMs.
Generate exactly {count} distinct, highly realistic, and detailed customer support queries for ElectroGadget Hub.

### Target Category
- **Category Name**: `{category}`
- **Specific Scenarios to Generate**: {category_prompts[category]}

### Design Requirements
1. **Diverse Scenarios**: Every single query must represent a unique customer situation with specific product names (e.g., "UltraSound Pro X", "GamerX 3080 Laptop", "VoltCharge Powerbank") and distinct emotional tones (e.g. polite, urgent, frustrated).
2. **Sequential IDs**: Set the `id` field sequentially starting from `q{start_index:03d}` to `q{start_index + count - 1:03d}`.
3. **Fidelity Constraints**:
   - For `refund_request`, make sure the query does not provide a transaction or order ID.
   - For `return_policy`, vary the time elapsed (e.g., 10 days, 45 days) to test date logic.
   - For `escalation`, simulate angry repeating callers.
   - For `out_of_scope`, request coding, recipes, or math help.
4. **Expected Contents**: Choose 2-4 key words/phrases that must appear in a perfect response. E.g., for return of a 45-day-old purchase: `["30-day", "expired", "cannot"]`.

Generate the output to perfectly match the requested schema structure.
"""

    print(f"📡 Generating batch of {count} queries for category '{category}' (IDs: q{start_index:03d} to q{start_index+count-1:03d})...")
    
    # We call the model with exponential retry logic in case of rate limits
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=CategoryBatch,
                    temperature=0.7  # Higher temperature for creativity and diversity
                )
            )
            # Parse response
            data = json.loads(response.text)
            entries = data.get("entries", [])
            
            # Ensure correct size and category override
            for entry in entries:
                entry["category"] = category
                
            return entries
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"❌ Failed to generate category '{category}' after {max_retries} attempts: {e}")
                raise e
            print(f"⚠️ API error generating batch (attempt {attempt+1}/{max_retries}): {e}. Retrying in 3s...")
            time.sleep(3)
            
    return []

def main():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your-gemini-api-key":
        print("❌ GOOGLE_API_KEY is not set or invalid in environment.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    categories = [
        "product_info",
        "return_policy",
        "refund_request",
        "price_match",
        "warranty",
        "recommendation",
        "escalation",
        "out_of_scope"
    ]
    
    all_entries = []
    current_id_index = 1
    
    print("🚀 Initiating programmatic generation of unique customer support queries...")
    
    for cat in categories:
        batch = generate_category_queries(client, cat, current_id_index, count=9)
        all_entries.extend(batch)
        current_id_index += len(batch)
        time.sleep(1) # Rate limit cooling
        
    # Construct complete dataset
    golden_dataset = {
        "dataset_name": "electrogadget_customer_support_v2_large",
        "description": "Expanded ground-truth Q&A pairs (72 unique items) for ElectroGadget Hub",
        "entries": all_entries
    }
    
    # Save to file
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(golden_dataset, f, indent=2)
        
    print("\n" + "=" * 60)
    print(f"✅ Success! Generated {len(all_entries)} unique queries.")
    print(f"📂 Saved to: {OUTPUT_PATH}")
    print("=" * 60)

if __name__ == "__main__":
    main()
