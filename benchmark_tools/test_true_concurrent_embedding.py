#!/usr/bin/env python3
"""
True Concurrent Embedding Test
Tests SIMULTANEOUS embedding requests to stress the batch-size limit
"""
import requests
import json
import time
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

# Configuration
LLAMA_SERVER_URL = "http://localhost:7777/embedding"

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def generate_text(num_tokens: int) -> str:
    """Generate text with approximately the specified number of tokens."""
    words = [
        "energy", "sustainability", "renewable", "solar", "wind", "power",
        "climate", "carbon", "emissions", "electric", "battery", "grid",
        "efficiency", "infrastructure", "policy", "government", "investment",
        "technology", "innovation", "development", "implementation", "strategy"
    ]
    
    text_parts = []
    word_idx = 0
    estimated_tokens = 0
    
    while estimated_tokens < num_tokens:
        word = words[word_idx % len(words)]
        text_parts.append(word)
        estimated_tokens += 1
        word_idx += 1
        
        if len(text_parts) % 10 == 0:
            text_parts.append(".")
        elif len(text_parts) % 5 == 0:
            text_parts.append(",")
    
    return " ".join(text_parts)

def send_single_request(text: str, request_id: int) -> Tuple[int, bool, str, float]:
    """Send a single embedding request. Returns (id, success, message, duration)"""
    start_time = time.time()
    try:
        payload = {"content": text}
        response = requests.post(LLAMA_SERVER_URL, json=payload, timeout=30)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                embedding = result[0].get("embedding", [[]])[0]
                return request_id, True, f"OK - {len(embedding)} dims", duration
            else:
                return request_id, False, "Invalid response format", duration
        else:
            error_text = response.text[:100] if response.text else "Unknown error"
            return request_id, False, f"HTTP {response.status_code}: {error_text}", duration
            
    except Exception as e:
        duration = time.time() - start_time
        return request_id, False, f"Error: {str(e)[:80]}", duration

def test_concurrent_requests(token_count: int, num_concurrent: int) -> Tuple[bool, str, List[float]]:
    """
    Test truly concurrent embedding requests using ThreadPoolExecutor.
    Returns: (all_success, message, durations)
    """
    # Generate texts for concurrent requests
    texts = [generate_text(token_count) for _ in range(num_concurrent)]
    
    print(f"  {Colors.YELLOW}→ Sending {num_concurrent} requests of {token_count} tokens SIMULTANEOUSLY...{Colors.END}")
    
    # Send all requests concurrently
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
        # Submit all requests at once
        futures = [executor.submit(send_single_request, text, i) for i, text in enumerate(texts)]
        
        # Collect results as they complete
        results = []
        durations = []
        
        for future in as_completed(futures):
            request_id, success, message, duration = future.result()
            results.append((request_id, success, message))
            durations.append(duration)
    
    total_time = time.time() - start_time
    
    # Analyze results
    successful = sum(1 for _, success, _ in results if success)
    failed = len(results) - successful
    
    # Sort results by request_id for consistent output
    results.sort(key=lambda x: x[0])
    
    # Print individual results
    for request_id, success, message in results:
        status = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
        print(f"    Request {request_id+1}: {status} {message}")
    
    if successful == num_concurrent:
        avg_duration = sum(durations) / len(durations)
        return True, f"All {num_concurrent} succeeded (avg: {avg_duration:.2f}s, total: {total_time:.2f}s)", durations
    else:
        return False, f"{successful}/{num_concurrent} succeeded, {failed} failed", durations

async def test_async_concurrent_requests(token_count: int, num_concurrent: int) -> Tuple[bool, str, List[float]]:
    """
    Test truly concurrent embedding requests using aiohttp.
    Returns: (all_success, message, durations)
    """
    texts = [generate_text(token_count) for _ in range(num_concurrent)]
    
    print(f"  {Colors.YELLOW}→ Sending {num_concurrent} async requests of {token_count} tokens SIMULTANEOUSLY...{Colors.END}")
    
    async def send_async_request(session, text, request_id):
        start_time = time.time()
        try:
            payload = {"content": text}
            async with session.post(LLAMA_SERVER_URL, json=payload, timeout=30) as response:
                duration = time.time() - start_time
                
                if response.status == 200:
                    result = await response.json()
                    if isinstance(result, list) and len(result) > 0:
                        embedding = result[0].get("embedding", [[]])[0]
                        return request_id, True, f"OK - {len(embedding)} dims", duration
                    else:
                        return request_id, False, "Invalid response format", duration
                else:
                    error_text = await response.text()
                    error_text = error_text[:100] if error_text else "Unknown error"
                    return request_id, False, f"HTTP {response.status}: {error_text}", duration
                    
        except Exception as e:
            duration = time.time() - start_time
            return request_id, False, f"Error: {str(e)[:80]}", duration
    
    start_time = time.time()
    
    # Send all requests concurrently using aiohttp
    async with aiohttp.ClientSession() as session:
        tasks = [send_async_request(session, text, i) for i, text in enumerate(texts)]
        results = await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    # Analyze results
    successful = sum(1 for _, success, _, _ in results if success)
    failed = len(results) - successful
    durations = [duration for _, _, _, duration in results]
    
    # Sort and print results
    results.sort(key=lambda x: x[0])
    
    for request_id, success, message, duration in results:
        status = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
        print(f"    Async Request {request_id+1}: {status} {message} ({duration:.2f}s)")
    
    if successful == num_concurrent:
        avg_duration = sum(durations) / len(durations)
        return True, f"All {num_concurrent} async succeeded (avg: {avg_duration:.2f}s, total: {total_time:.2f}s)", durations
    else:
        return False, f"{successful}/{num_concurrent} async succeeded, {failed} failed", durations

def print_header(text: str):
    """Print section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}\n")

def main():
    """Run concurrent embedding tests."""
    print_header("True Concurrent Embedding Test")
    print(f"Server: {LLAMA_SERVER_URL}")
    
    # Check server availability
    try:
        response = requests.get(LLAMA_SERVER_URL.rsplit('/', 1)[0], timeout=5)
        print(f"{Colors.GREEN}✓ Server is reachable{Colors.END}")
    except:
        print(f"{Colors.RED}✗ Warning: Cannot reach server{Colors.END}")
        return
    
    # Test configurations
    test_configs = [
        # (token_count, concurrent_requests)
        (400, 2),   # Small tokens, 2 concurrent
        (400, 3),   # Small tokens, 3 concurrent  
        (400, 4),   # Small tokens, 4 concurrent
        (512, 2),   # Medium tokens, 2 concurrent
        (512, 3),   # Medium tokens, 3 concurrent
        (700, 2),   # Large tokens, 2 concurrent
        (800, 2),   # Very large tokens, 2 concurrent
    ]
    
    # ===========================
    # Test 1: ThreadPoolExecutor (threads)
    # ===========================
    print_header("Test 1: Concurrent Requests (ThreadPoolExecutor)")
    
    thread_results = {}
    
    for token_count, num_concurrent in test_configs:
        print(f"\n{Colors.BOLD}Testing {token_count} tokens × {num_concurrent} concurrent requests:{Colors.END}")
        
        success, message, durations = test_concurrent_requests(token_count, num_concurrent)
        thread_results[(token_count, num_concurrent)] = success
        
        status = f"{Colors.GREEN}✓ SUCCESS{Colors.END}" if success else f"{Colors.RED}✗ FAILED{Colors.END}"
        print(f"  Result: {status} - {message}")
        
        time.sleep(1)  # Brief pause between tests
    
    # ===========================
    # Test 2: AsyncIO (async/await)
    # ===========================
    print_header("Test 2: Concurrent Requests (AsyncIO)")
    
    async_results = {}
    
    async def run_async_tests():
        for token_count, num_concurrent in test_configs:
            print(f"\n{Colors.BOLD}Testing {token_count} tokens × {num_concurrent} async concurrent requests:{Colors.END}")
            
            success, message, durations = await test_async_concurrent_requests(token_count, num_concurrent)
            async_results[(token_count, num_concurrent)] = success
            
            status = f"{Colors.GREEN}✓ SUCCESS{Colors.END}" if success else f"{Colors.RED}✗ FAILED{Colors.END}"
            print(f"  Result: {status} - {message}")
            
            await asyncio.sleep(1)  # Brief pause between tests
    
    # Run async tests
    asyncio.run(run_async_tests())
    
    # ===========================
    # Summary
    # ===========================
    print_header("Test Summary")
    
    print(f"{Colors.BOLD}ThreadPoolExecutor Results:{Colors.END}")
    for (tokens, concurrent), success in thread_results.items():
        status = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
        print(f"  {status} {tokens} tokens × {concurrent} concurrent: {'SUCCESS' if success else 'FAILED'}")
    
    print(f"\n{Colors.BOLD}AsyncIO Results:{Colors.END}")
    for (tokens, concurrent), success in async_results.items():
        status = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
        print(f"  {status} {tokens} tokens × {concurrent} async: {'SUCCESS' if success else 'FAILED'}")
    
    # Find limits
    max_concurrent_threads = 0
    max_concurrent_async = 0
    
    for (tokens, concurrent), success in thread_results.items():
        if success and tokens == 512:  # Focus on 512 token tests
            max_concurrent_threads = max(max_concurrent_threads, concurrent)
    
    for (tokens, concurrent), success in async_results.items():
        if success and tokens == 512:  # Focus on 512 token tests
            max_concurrent_async = max(max_concurrent_async, concurrent)
    
    print(f"\n{Colors.BOLD}Batch Limits (512 tokens):{Colors.END}")
    print(f"  • ThreadPool max concurrent: {Colors.CYAN}{max_concurrent_threads}{Colors.END}")
    print(f"  • AsyncIO max concurrent: {Colors.CYAN}{max_concurrent_async}{Colors.END}")
    
    print(f"\n{Colors.YELLOW}Note: This tests the server's --batch-size limit under true concurrency{Colors.END}")

if __name__ == "__main__":
    main()
