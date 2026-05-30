# scripts/verify_gemini.py
from google import genai
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")
if not api_key or api_key == "your-gemini-api-key":
    print("❌ GOOGLE_API_KEY is not set or is still the default template value.")
    exit(1)

try:
    print("Initializing Google GenAI client...")
    client = genai.Client(api_key=api_key)
    print("Sending content generation request to gemini-2.5-flash...")
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Say 'Hello from Gemini!' in exactly 5 words."
    )
    print("✅ Gemini API call succeeded!")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"❌ Gemini API call failed: {e}")
    exit(1)
