import time
import requests
import statistics
import json
from typing import List, Dict, Any

# Configuration
SERVER_URL = "http://localhost:7777/embedding"
TEST_TEXT = "What causes lightning?"
NUM_REQUESTS = 10
WARMUP_REQUESTS = 5

def benchmark_embedding(text: str) -> Dict[str, Any]:
    """Send a request to the embedding server and return the response with timing."""
    start_time = time.time()
    
    response = requests.post(
        SERVER_URL,
        json={"content": text, "embedding": True}
    )
    
    end_time = time.time()
    client_time_ms = (end_time - start_time) * 1000
    
    if response.status_code != 200:
        print(f"Error: {response.status_code} - {response.text}")
        return {"success": False, "client_time_ms": client_time_ms}
    
    result = response.json()
    
    embedding = result if isinstance(result, list) else result.get("embedding", [])
    
    return {
        "success": True,
        "client_time_ms": client_time_ms,
        "server_time_ms": None,
        "embedding_size": len(embedding)
    }

def run_benchmark():
    """Run the benchmark multiple times and report statistics."""
    print(f"Benchmarking llama-server embedding with {NUM_REQUESTS} requests...")
    print(f"Test text: '{TEST_TEXT}'")
    
    # Warmup requests
    print(f"\nPerforming {WARMUP_REQUESTS} warmup requests...")
    for i in range(WARMUP_REQUESTS):
        result = benchmark_embedding(TEST_TEXT)
        if not result["success"]:
            print("Failed during warmup. Is the server running?")
            return
        print(f"  Warmup {i+1}: {result['client_time_ms']:.2f} ms (client)")
    
    # Benchmark requests
    print(f"\nRunning {NUM_REQUESTS} benchmark requests...")
    
    client_times = []
    
    for i in range(NUM_REQUESTS):
        result = benchmark_embedding(TEST_TEXT)
        if not result["success"]:
            print(f"Request {i+1} failed")
            continue
            
        client_times.append(result["client_time_ms"])
        
        print(f"  Request {i+1}: {result['client_time_ms']:.2f} ms (client)")
    
    if not client_times:
        print("All benchmark requests failed")
        return
    
    # Calculate statistics
    embedding_size = result["embedding_size"]
    
    print("\nResults:")
    print(f"Embedding size: {embedding_size} dimensions")
    print("\nClient-side timing (includes network latency and embedding generation):")
    print(f"  Min: {min(client_times):.2f} ms")
    print(f"  Max: {max(client_times):.2f} ms")
    print(f"  Mean: {statistics.mean(client_times):.2f} ms")
    print(f"  Median: {statistics.median(client_times):.2f} ms")

if __name__ == "__main__":
    run_benchmark() 