# scripts/query_graphql.py
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

base_url = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
api_key = os.getenv("PHOENIX_API_KEY")

print("--- PHOENIX GRAPHQL DIAGNOSIS ---")
print(f"Base URL: {base_url}")
print(f"API Key (first 10): {api_key[:10] if api_key else 'None'}")

# Phoenix Cloud GraphQL endpoint is located at the space root URL + /graphql
graphql_url = f"{base_url}/graphql"
print(f"GraphQL URL: {graphql_url}")

# This is the standard GraphQL query Phoenix uses to fetch spans for a project
query = """
query GetProjectSpans($projectId: ID!, $limit: Int!) {
  project(id: $projectId) {
    name
    spans(first: $limit) {
      edges {
        node {
          id
          name
          spanKind
          startTime
          endTime
          attributes
        }
      }
    }
  }
}
"""

variables = {
    "projectId": "UHJvamVjdDoz",  # llm-eval-agent project ID
    "limit": 10
}

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

try:
    print("\nSending raw GraphQL request...")
    with httpx.Client(timeout=10) as client:
        response = client.post(
            graphql_url,
            json={"query": query, "variables": variables},
            headers=headers
        )
        
    print(f"HTTP Status: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n--- Raw GraphQL Response JSON ---")
        print(json.dumps(data, indent=2))
        print("---------------------------------")
    else:
        print(f"❌ GraphQL request failed: {response.text}")
except Exception as e:
    print(f"❌ Error querying GraphQL: {e}")
