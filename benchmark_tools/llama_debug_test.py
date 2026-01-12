import requests
import json

# Test the llama-server response format
SERVER_URL = "http://localhost:7777/embedding"
TEST_TEXT = "What is the weather like today?"

print("Testing llama-server response format...")
print(f"URL: {SERVER_URL}")
print(f"Test text: '{TEST_TEXT}'")

try:
    response = requests.post(
        SERVER_URL,
        json={"content": TEST_TEXT, "embedding": True},
        timeout=10
    )
    
    print(f"\nStatus code: {response.status_code}")
    print(f"Response headers: {dict(response.headers)}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\nResponse type: {type(data)}")
        print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        # Pretty print the response
        print("\nFull response:")
        print(json.dumps(data, indent=2)[:500] + "..." if len(json.dumps(data)) > 500 else json.dumps(data, indent=2))
        
        # Check for embedding field
        if isinstance(data, dict) and 'embedding' in data:
            embedding = data['embedding']
            print(f"\nEmbedding type: {type(embedding)}")
            print(f"Embedding length: {len(embedding) if isinstance(embedding, list) else 'N/A'}")
            if isinstance(embedding, list) and len(embedding) > 0:
                print(f"First 5 values: {embedding[:5]}")
    else:
        print(f"Error response: {response.text}")
        
except Exception as e:
    print(f"Error: {e}") 