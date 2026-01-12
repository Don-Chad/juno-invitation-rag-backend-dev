#!/usr/bin/env python3
"""
EmbeddingGemma Latency Test
Tests embedding latency for two sentences in single mode
"""
import requests
import time
import statistics
from typing import List, Tuple

# Configuration
LLAMA_SERVER_URL = "http://localhost:7777/embedding"
NUM_TESTS = 20  # Number of test runs for averaging

# Test sentences (realistic length)
TEST_SENTENCES = [
    "Solar energy is becoming increasingly important for sustainable development.",
    "The Netherlands has ambitious plans for renewable energy transition by 2030."
]

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def test_single_embedding_latency(text: str) -> Tuple[bool, float, int]:
    """
    Test single embedding latency.
    Returns: (success, latency_ms, embedding_dim)
    """
    start_time = time.perf_counter()
    
    try:
        payload = {"content": text}
        response = requests.post(LLAMA_SERVER_URL, json=payload, timeout=10)
        
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                embedding = result[0].get("embedding", [[]])[0]
                return True, latency_ms, len(embedding)
            else:
                return False, latency_ms, 0
        else:
            return False, latency_ms, 0
            
    except Exception as e:
        end_time = time.perf_counter()
        latency_ms = (end_time - start_time) * 1000
        return False, latency_ms, 0

def run_latency_tests():
    """Run comprehensive latency tests."""
    print(f"{Colors.BOLD}{Colors.CYAN}EmbeddingGemma Latency Test{Colors.END}")
    print(f"Server: {LLAMA_SERVER_URL}")
    print(f"Test runs: {NUM_TESTS} per sentence")
    print(f"Model: EmbeddingGemma-300M-Q4_0\n")
    
    # Check server availability
    try:
        response = requests.get(LLAMA_SERVER_URL.rsplit('/', 1)[0], timeout=5)
        print(f"{Colors.GREEN}✓ Server is reachable{Colors.END}\n")
    except:
        print(f"{Colors.RED}✗ Cannot reach server{Colors.END}")
        print("Make sure llama-server is running: systemctl status llama-server.service")
        return
    
    all_latencies = []
    
    # Test each sentence
    for i, sentence in enumerate(TEST_SENTENCES, 1):
        print(f"{Colors.BOLD}Sentence {i}:{Colors.END} \"{sentence}\"")
        print(f"Length: {len(sentence)} chars, ~{len(sentence.split())} words\n")
        
        latencies = []
        successful_tests = 0
        
        # Warm-up request (not counted)
        print(f"{Colors.YELLOW}Warming up...{Colors.END}")
        test_single_embedding_latency(sentence)
        time.sleep(0.1)
        
        # Run actual tests
        print(f"{Colors.YELLOW}Running {NUM_TESTS} tests...{Colors.END}")
        
        for test_num in range(NUM_TESTS):
            success, latency_ms, dim = test_single_embedding_latency(sentence)
            
            if success:
                latencies.append(latency_ms)
                successful_tests += 1
                status = f"{Colors.GREEN}✓{Colors.END}"
            else:
                status = f"{Colors.RED}✗{Colors.END}"
            
            # Show progress every 5 tests
            if (test_num + 1) % 5 == 0 or test_num == 0:
                if success:
                    print(f"  Test {test_num+1:2d}: {status} {latency_ms:6.1f}ms (dim: {dim})")
                else:
                    print(f"  Test {test_num+1:2d}: {status} FAILED")
            
            time.sleep(0.05)  # Small delay between tests
        
        # Calculate statistics for this sentence
        if latencies:
            avg_latency = statistics.mean(latencies)
            median_latency = statistics.median(latencies)
            min_latency = min(latencies)
            max_latency = max(latencies)
            std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0
            
            print(f"\n{Colors.BOLD}Results for Sentence {i}:{Colors.END}")
            print(f"  Success rate: {Colors.GREEN}{successful_tests}/{NUM_TESTS}{Colors.END} ({successful_tests/NUM_TESTS*100:.1f}%)")
            print(f"  Average:      {Colors.CYAN}{avg_latency:6.1f}ms{Colors.END}")
            print(f"  Median:       {Colors.CYAN}{median_latency:6.1f}ms{Colors.END}")
            print(f"  Min:          {Colors.GREEN}{min_latency:6.1f}ms{Colors.END}")
            print(f"  Max:          {Colors.RED}{max_latency:6.1f}ms{Colors.END}")
            print(f"  Std Dev:      {Colors.YELLOW}{std_dev:6.1f}ms{Colors.END}")
            
            all_latencies.extend(latencies)
        else:
            print(f"\n{Colors.RED}No successful tests for sentence {i}{Colors.END}")
        
        print(f"\n{'-' * 60}\n")
    
    # Overall statistics
    if all_latencies:
        overall_avg = statistics.mean(all_latencies)
        overall_median = statistics.median(all_latencies)
        overall_min = min(all_latencies)
        overall_max = max(all_latencies)
        overall_std = statistics.stdev(all_latencies) if len(all_latencies) > 1 else 0
        
        print(f"{Colors.BOLD}{Colors.CYAN}OVERALL RESULTS{Colors.END}")
        print(f"Total successful tests: {Colors.GREEN}{len(all_latencies)}/{NUM_TESTS * len(TEST_SENTENCES)}{Colors.END}")
        print(f"Average latency:        {Colors.CYAN}{overall_avg:6.1f}ms{Colors.END}")
        print(f"Median latency:         {Colors.CYAN}{overall_median:6.1f}ms{Colors.END}")
        print(f"Fastest response:       {Colors.GREEN}{overall_min:6.1f}ms{Colors.END}")
        print(f"Slowest response:       {Colors.RED}{overall_max:6.1f}ms{Colors.END}")
        print(f"Standard deviation:     {Colors.YELLOW}{overall_std:6.1f}ms{Colors.END}")
        
        # Performance assessment
        print(f"\n{Colors.BOLD}Performance Assessment:{Colors.END}")
        if overall_avg < 50:
            print(f"  {Colors.GREEN}🚀 EXCELLENT{Colors.END} - Very fast embedding generation")
        elif overall_avg < 100:
            print(f"  {Colors.GREEN}✓ GOOD{Colors.END} - Fast embedding generation")
        elif overall_avg < 200:
            print(f"  {Colors.YELLOW}⚠ MODERATE{Colors.END} - Acceptable embedding speed")
        else:
            print(f"  {Colors.RED}⚠ SLOW{Colors.END} - Consider optimizing server configuration")
        
        # Comparison to target
        target_latency = 100  # Your expected ~100ms
        if overall_avg <= target_latency:
            print(f"  {Colors.GREEN}✓ Meets target{Colors.END} of ≤{target_latency}ms")
        else:
            print(f"  {Colors.RED}✗ Exceeds target{Colors.END} of ≤{target_latency}ms by {overall_avg - target_latency:.1f}ms")
        
        # Percentiles
        sorted_latencies = sorted(all_latencies)
        p50 = sorted_latencies[int(len(sorted_latencies) * 0.5)]
        p90 = sorted_latencies[int(len(sorted_latencies) * 0.9)]
        p95 = sorted_latencies[int(len(sorted_latencies) * 0.95)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        
        print(f"\n{Colors.BOLD}Latency Percentiles:{Colors.END}")
        print(f"  P50 (median): {p50:6.1f}ms")
        print(f"  P90:          {p90:6.1f}ms")
        print(f"  P95:          {p95:6.1f}ms")
        print(f"  P99:          {p99:6.1f}ms")
        
        # Server configuration info
        print(f"\n{Colors.BOLD}Server Configuration:{Colors.END}")
        print(f"  Model: EmbeddingGemma-300M-Q4_0")
        print(f"  Dimensions: 768")
        print(f"  Batch size: 1024")
        print(f"  UBatch size: 1024")
        print(f"  Context size: 1024")
    
    else:
        print(f"{Colors.RED}No successful tests completed{Colors.END}")

if __name__ == "__main__":
    run_latency_tests()
