#!/usr/bin/env python3
"""
Embedding Performance Diagnostic Tool

This script helps diagnose why embedding creation time increased from 30ms to 117ms.
It tests various aspects of the embedding pipeline to identify bottlenecks.
"""

import asyncio
import time
import aiohttp
import numpy as np
import statistics
import json
from typing import List, Dict

# Configuration
LLAMA_SERVER_URL = "http://localhost:7777/embedding"
TEST_TEXTS = [
    "Short test query",
    "This is a medium length test query with more words to see if length affects performance",
    "This is a much longer test query that contains significantly more text to test whether the embedding generation time scales linearly with input length or if there are other factors at play in the performance degradation we're seeing",
    "Tell me about banana's in the document right now!",  # Your actual query
]

async def test_raw_server_performance():
    """Test raw llama-server performance without any wrapper code."""
    print("\n=== Testing Raw Server Performance ===")
    
    async with aiohttp.ClientSession() as session:
        for text in TEST_TEXTS:
            times = []
            
            # Run multiple tests
            for i in range(5):
                start = time.perf_counter()
                
                try:
                    async with session.post(
                        LLAMA_SERVER_URL,
                        json={"content": text, "embedding": True},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        data = await response.json()
                        elapsed = (time.perf_counter() - start) * 1000
                        times.append(elapsed)
                        
                        # Verify response
                        if isinstance(data, list) and len(data) > 0:
                            embedding = data[0].get("embedding", [])
                            if isinstance(embedding[0], list):
                                embedding_size = len(embedding[0])
                            else:
                                embedding_size = len(embedding)
                        else:
                            embedding_size = 0
                            
                except Exception as e:
                    print(f"Error: {e}")
                    continue
                
                # Small delay between requests
                await asyncio.sleep(0.1)
            
            if times:
                avg_time = statistics.mean(times)
                std_dev = statistics.stdev(times) if len(times) > 1 else 0
                print(f"\nText length: {len(text)} chars")
                print(f"Embedding size: {embedding_size}")
                print(f"Times (ms): {[f'{t:.1f}' for t in times]}")
                print(f"Average: {avg_time:.1f}ms (±{std_dev:.1f}ms)")

async def test_server_load():
    """Test if server performance degrades under concurrent load."""
    print("\n=== Testing Server Under Load ===")
    
    test_text = "Test query for concurrent load testing"
    
    async def single_request(session, request_id):
        start = time.perf_counter()
        try:
            async with session.post(
                LLAMA_SERVER_URL,
                json={"content": f"{test_text} {request_id}", "embedding": True},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                await response.json()
                return (time.perf_counter() - start) * 1000
        except Exception as e:
            print(f"Request {request_id} failed: {e}")
            return None
    
    async with aiohttp.ClientSession() as session:
        # Test different concurrency levels
        for concurrent_requests in [1, 5, 10]:
            print(f"\nTesting with {concurrent_requests} concurrent requests:")
            
            tasks = []
            for i in range(concurrent_requests):
                tasks.append(single_request(session, i))
            
            start = time.perf_counter()
            results = await asyncio.gather(*tasks)
            total_time = (time.perf_counter() - start) * 1000
            
            valid_results = [r for r in results if r is not None]
            if valid_results:
                avg_time = statistics.mean(valid_results)
                print(f"Individual request average: {avg_time:.1f}ms")
                print(f"Total time for all requests: {total_time:.1f}ms")
                print(f"Throughput: {len(valid_results) / (total_time / 1000):.1f} requests/second")

async def test_network_latency():
    """Test network latency to the server."""
    print("\n=== Testing Network Latency ===")
    
    async with aiohttp.ClientSession() as session:
        # Test with minimal payload
        times = []
        for i in range(10):
            start = time.perf_counter()
            try:
                # Try to hit a health endpoint or use minimal embedding
                async with session.post(
                    LLAMA_SERVER_URL,
                    json={"content": "a", "embedding": True},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    await response.read()
                    elapsed = (time.perf_counter() - start) * 1000
                    times.append(elapsed)
            except Exception as e:
                print(f"Error: {e}")
            
            await asyncio.sleep(0.05)
        
        if times:
            print(f"Minimal request times (ms): {[f'{t:.1f}' for t in times]}")
            print(f"Average network + minimal processing: {statistics.mean(times):.1f}ms")
            print(f"This represents the baseline overhead")

async def check_server_info():
    """Try to get server information."""
    print("\n=== Server Information ===")
    
    async with aiohttp.ClientSession() as session:
        # Try common endpoints
        endpoints = [
            ("http://localhost:7777/", "Root"),
            ("http://localhost:7777/health", "Health"),
            ("http://localhost:7777/v1/models", "Models"),
        ]
        
        for url, name in endpoints:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                    if response.status == 200:
                        text = await response.text()
                        print(f"\n{name} endpoint ({url}):")
                        # Limit output length
                        if len(text) > 200:
                            print(text[:200] + "...")
                        else:
                            print(text)
            except Exception as e:
                print(f"{name} endpoint not available: {e}")

async def compare_with_rag_module():
    """Compare with the actual RAG module performance."""
    print("\n=== Comparing with RAG Module ===")
    
    try:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        import rag_module_hq_enhanced as rag
        
        # Initialize
        await rag.initialize_rag()
        
        # Test the same queries
        for text in TEST_TEXTS:
            times = []
            
            for i in range(3):
                start = time.perf_counter()
                embedding = await rag.create_embeddings(text)
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
                await asyncio.sleep(0.1)
            
            if times:
                print(f"\nText: '{text[:50]}...' ({len(text)} chars)")
                print(f"RAG module times (ms): {[f'{t:.1f}' for t in times]}")
                print(f"Average: {statistics.mean(times):.1f}ms")
        
        # Cleanup
        await rag.cleanup_rag()
        
    except Exception as e:
        print(f"Could not test RAG module: {e}")

async def main():
    """Run all diagnostic tests."""
    print("Embedding Performance Diagnostic Tool")
    print("=" * 50)
    
    # Check basic connectivity first
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:7777",
                timeout=aiohttp.ClientTimeout(total=2)
            ) as response:
                print(f"Server is responding (status: {response.status})")
    except Exception as e:
        print(f"WARNING: Cannot connect to llama-server at localhost:7777: {e}")
        print("Make sure the server is running!")
        return
    
    # Run diagnostic tests
    await check_server_info()
    await test_network_latency()
    await test_raw_server_performance()
    await test_server_load()
    await compare_with_rag_module()
    
    print("\n" + "=" * 50)
    print("Diagnostic complete!")
    print("\nPossible causes for slowdown:")
    print("1. Server is handling more concurrent requests")
    print("2. Server model or configuration changed")
    print("3. System resources (CPU/Memory) are constrained")
    print("4. Network conditions have changed")
    print("5. The embedding model itself was updated")

if __name__ == "__main__":
    asyncio.run(main()) 