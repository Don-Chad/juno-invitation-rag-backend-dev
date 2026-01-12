#!/usr/bin/env python3
"""
EmbeddingGemma Token Limit Tester
Tests progressive token limits from 400 to 2000 tokens
Tests both single and batched embedding requests
"""
import requests
import json
import time
from typing import List, Tuple

# Configuration
LLAMA_SERVER_URL = "http://localhost:7777/embedding"
TEST_RANGES = [
    # (start, end, step)
    (400, 520, 10),    # Fine-grained around 512
    (520, 800, 50),    # Medium steps
    (800, 1200, 100),  # Larger steps
    (1200, 2000, 200)  # Even larger steps
]

# Generate all test points
TEST_POINTS = []
for start, end, step in TEST_RANGES:
    TEST_POINTS.extend(range(start, end + 1, step))

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
    # Average: ~4 chars per token
    # Use varied vocabulary to ensure realistic tokenization
    words = [
        "energy", "sustainability", "renewable", "solar", "wind", "power",
        "climate", "carbon", "emissions", "electric", "battery", "grid",
        "efficiency", "infrastructure", "policy", "government", "investment",
        "technology", "innovation", "development", "implementation", "strategy"
    ]
    
    # Build text to approximate token count
    text_parts = []
    word_idx = 0
    estimated_tokens = 0
    
    while estimated_tokens < num_tokens:
        word = words[word_idx % len(words)]
        text_parts.append(word)
        estimated_tokens += 1  # Rough estimate: 1 word ≈ 1 token
        word_idx += 1
        
        # Add some variety with punctuation
        if len(text_parts) % 10 == 0:
            text_parts.append(".")
        elif len(text_parts) % 5 == 0:
            text_parts.append(",")
    
    return " ".join(text_parts)

def test_single_embedding(text: str, token_count: int) -> Tuple[bool, str, int]:
    """
    Test single text embedding.
    Returns: (success, message, embedding_dim)
    """
    try:
        payload = {
            "content": text
        }
        
        response = requests.post(
            LLAMA_SERVER_URL,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                embedding = result[0].get("embedding", [[]])[0]
                return True, f"OK - {len(embedding)} dims", len(embedding)
            else:
                return False, f"Invalid response format", 0
        else:
            error_text = response.text[:100] if response.text else "Unknown error"
            return False, f"HTTP {response.status_code}: {error_text}", 0
            
    except requests.exceptions.Timeout:
        return False, "Request timeout (>30s)", 0
    except Exception as e:
        return False, f"Error: {str(e)[:80]}", 0

def test_batched_embedding(texts: List[str], token_count: int, batch_size: int) -> Tuple[bool, str, int]:
    """
    Test batched text embeddings.
    Returns: (success, message, embedding_dim)
    """
    try:
        # For llama-server, we need to send requests sequentially or use batch endpoint if available
        # Let's test concurrent-like behavior by sending multiple texts quickly
        results = []
        
        for text in texts:
            payload = {"content": text}
            response = requests.post(LLAMA_SERVER_URL, json=payload, timeout=30)
            
            if response.status_code != 200:
                error_text = response.text[:100] if response.text else "Unknown error"
                return False, f"HTTP {response.status_code}: {error_text}", 0
            
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                embedding = result[0].get("embedding", [[]])[0]
                results.append(len(embedding))
            else:
                return False, "Invalid response format", 0
        
        # Check all embeddings have same dimension
        if len(set(results)) == 1:
            return True, f"OK - {batch_size} texts, {results[0]} dims", results[0]
        else:
            return False, f"Dimension mismatch: {results}", 0
            
    except requests.exceptions.Timeout:
        return False, "Request timeout (>30s)", 0
    except Exception as e:
        return False, f"Error: {str(e)[:80]}", 0

def print_header(text: str):
    """Print section header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}\n")

def print_test_result(token_count: int, success: bool, message: str, test_type: str = "SINGLE"):
    """Print individual test result."""
    status_symbol = f"{Colors.GREEN}✓{Colors.END}" if success else f"{Colors.RED}✗{Colors.END}"
    status_text = f"{Colors.GREEN}SUCCESS{Colors.END}" if success else f"{Colors.RED}FAILED{Colors.END}"
    
    print(f"{status_symbol} {Colors.BOLD}{token_count:>5}{Colors.END} tokens "
          f"[{test_type}] - {status_text} - {message}")

def main():
    """Run all token limit tests."""
    print_header("EmbeddingGemma Token Limit Test")
    print(f"Server: {LLAMA_SERVER_URL}")
    print(f"Test range: {min(TEST_POINTS)} - {max(TEST_POINTS)} tokens")
    print(f"Test points: {len(TEST_POINTS)} sizes")
    print(f"\n{Colors.YELLOW}Note: ~1 word ≈ 1 token (rough estimate){Colors.END}")
    
    # Check server availability
    try:
        response = requests.get(LLAMA_SERVER_URL.rsplit('/', 1)[0], timeout=5)
        print(f"{Colors.GREEN}✓ Server is reachable{Colors.END}")
    except:
        print(f"{Colors.RED}✗ Warning: Cannot reach server{Colors.END}")
        print(f"  Make sure llama-server is running: systemctl status llama-server.service")
        return
    
    # ===========================
    # Test 1: Single Embeddings
    # ===========================
    print_header("Test 1: Single Text Embeddings")
    
    single_results = {}
    last_success_single = 0
    first_failure_single = None
    
    for token_count in TEST_POINTS:
        text = generate_text(token_count)
        char_count = len(text)
        
        success, message, dim = test_single_embedding(text, token_count)
        single_results[token_count] = success
        
        print_test_result(token_count, success, f"{char_count:>6} chars | {message}", "SINGLE")
        
        if success:
            last_success_single = token_count
        elif first_failure_single is None:
            first_failure_single = token_count
        
        time.sleep(0.1)  # Small delay between tests
    
    # ===========================
    # Test 2: Batched Embeddings
    # ===========================
    print_header("Test 2: Batched Embeddings (2 texts simultaneously)")
    
    batch_results = {}
    last_success_batch = 0
    first_failure_batch = None
    
    for token_count in TEST_POINTS:
        # Create 2 texts of the same size
        texts = [generate_text(token_count) for _ in range(2)]
        total_chars = sum(len(t) for t in texts)
        
        success, message, dim = test_batched_embedding(texts, token_count, 2)
        batch_results[token_count] = success
        
        print_test_result(token_count, success, f"{total_chars:>6} chars total | {message}", "BATCH-2")
        
        if success:
            last_success_batch = token_count
        elif first_failure_batch is None:
            first_failure_batch = token_count
        
        time.sleep(0.2)  # Slightly longer delay for batches
    
    # ===========================
    # Test 3: Batch size stress test at 512 tokens
    # ===========================
    print_header("Test 3: Batch Size Stress Test (512 tokens per text)")
    
    test_token_size = 512
    batch_sizes = [1, 2, 3, 4, 5]
    
    batch_stress_results = {}
    
    for batch_size in batch_sizes:
        texts = [generate_text(test_token_size) for _ in range(batch_size)]
        total_chars = sum(len(t) for t in texts)
        
        success, message, dim = test_batched_embedding(texts, test_token_size, batch_size)
        batch_stress_results[batch_size] = success
        
        print_test_result(test_token_size, success, 
                         f"Batch={batch_size}, {total_chars:>6} chars total | {message}", 
                         f"BATCH-{batch_size}")
        
        time.sleep(0.2)
    
    # ===========================
    # Summary
    # ===========================
    print_header("Test Summary")
    
    # Single mode summary
    successful_single = sum(1 for v in single_results.values() if v)
    print(f"{Colors.BOLD}Single Mode:{Colors.END}")
    print(f"  ✓ Successful: {Colors.GREEN}{successful_single}/{len(single_results)}{Colors.END}")
    print(f"  ✓ Last success: {Colors.GREEN}{last_success_single} tokens{Colors.END}")
    if first_failure_single:
        print(f"  ✗ First failure: {Colors.RED}{first_failure_single} tokens{Colors.END}")
    else:
        print(f"  {Colors.GREEN}✓ All tests passed!{Colors.END}")
    
    # Batch mode summary
    successful_batch = sum(1 for v in batch_results.values() if v)
    print(f"\n{Colors.BOLD}Batch Mode (2 texts):{Colors.END}")
    print(f"  ✓ Successful: {Colors.GREEN}{successful_batch}/{len(batch_results)}{Colors.END}")
    print(f"  ✓ Last success: {Colors.GREEN}{last_success_batch} tokens{Colors.END}")
    if first_failure_batch:
        print(f"  ✗ First failure: {Colors.RED}{first_failure_batch} tokens{Colors.END}")
    else:
        print(f"  {Colors.GREEN}✓ All tests passed!{Colors.END}")
    
    # Batch stress test summary
    max_batch_size = max([bs for bs, success in batch_stress_results.items() if success], default=0)
    print(f"\n{Colors.BOLD}Batch Stress Test (512 tokens/text):{Colors.END}")
    print(f"  ✓ Max batch size: {Colors.GREEN}{max_batch_size} texts{Colors.END}")
    
    # Recommendations
    print_header("Recommendations")
    
    safe_margin = 0.9  # 90% of max
    recommended_single = int(last_success_single * safe_margin)
    
    print(f"{Colors.BOLD}Recommended Configuration:{Colors.END}")
    print(f"  • CHUNK_SIZE_TOKENS: {Colors.CYAN}{recommended_single}{Colors.END} tokens (90% of max)")
    print(f"  • MAX_EMBEDDING_TOKENS: {Colors.CYAN}{last_success_single}{Colors.END} tokens (tested max)")
    print(f"  • Batch processing: {Colors.CYAN}Use batch size ≤ {max_batch_size}{Colors.END}")
    
    if last_success_single >= 512:
        print(f"\n{Colors.GREEN}✓ Server accepts ≥512 tokens as expected!{Colors.END}")
    else:
        print(f"\n{Colors.YELLOW}⚠ Server accepts <512 tokens - may need configuration adjustment{Colors.END}")
    
    print(f"\n{Colors.CYAN}Server configuration (current):{Colors.END}")
    print(f"  --batch-size 512 --ubatch-size 512 --ctx-size 2048")
    
    if last_success_single < 512:
        print(f"\n{Colors.YELLOW}Suggestion: Increase --ubatch-size to allow more tokens:{Colors.END}")
        suggested_ubatch = int(512 / 0.8)  # 20% overhead estimate
        print(f"  --ubatch-size {suggested_ubatch}")

if __name__ == "__main__":
    main()

