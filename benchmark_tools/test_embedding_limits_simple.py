#!/usr/bin/env python3
"""
Simple test script to find the actual token/char limits of the embedding server.
Standalone version that doesn't require the full rag_hq module.
"""
import requests
import tiktoken
import time

EMBEDDING_SERVER = "http://localhost:7777/embedding"

# Initialize tiktoken for accurate token counting
_encoding = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    """Count actual tokens using tiktoken."""
    return len(_encoding.encode(text))

def test_embedding_size(text: str, test_name: str):
    """Test if the embedding server accepts a given text size."""
    char_count = len(text)
    token_count = count_tokens(text)
    
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"Chars: {char_count:,} | Tokens: {token_count}")
    print(f"{'='*60}")
    
    try:
        response = requests.post(
            EMBEDDING_SERVER,
            json={"content": text, "embedding": True},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ SUCCESS - Server accepted input")
            if isinstance(data, list) and len(data) > 0:
                if 'embedding' in data[0]:
                    emb_len = len(data[0]['embedding'])
                    print(f"  Embedding dimension: {emb_len}")
            return True
        else:
            print(f"✗ REJECTED - Status: {response.status_code}")
            print(f"  Server message: {response.text[:200]}")
            return False
            
    except requests.Timeout:
        print(f"✗ TIMEOUT - Server took too long")
        return False
    except Exception as e:
        print(f"✗ ERROR - {e}")
        return False

def find_max_limit():
    """Binary search to find maximum accepted token size."""
    print("\n" + "="*60)
    print("FINDING MAXIMUM TOKEN LIMIT (Binary Search)")
    print("="*60)
    
    # Test with simple repeated text to avoid content issues
    base_text = "This is a test sentence for embedding limits. "
    
    # Binary search between 50 and 2048 tokens
    low = 50
    high = 2048
    max_working = 0
    
    while low <= high:
        mid = (low + high) // 2
        
        # Create text of approximately 'mid' tokens
        target_chars = mid * 4
        repetitions = (target_chars // len(base_text)) + 1
        test_text = (base_text * repetitions)[:target_chars]
        
        actual_tokens = count_tokens(test_text)
        
        print(f"\nTesting {actual_tokens} tokens...")
        
        success = test_embedding_size(test_text, f"Binary search: {actual_tokens} tokens")
        
        if success:
            max_working = actual_tokens
            low = mid + 1
        else:
            high = mid - 1
        
        # Small delay between tests
        time.sleep(0.3)
    
    return max_working

def main():
    print("="*60)
    print("EMBEDDING SERVER LIMIT TEST")
    print("="*60)
    print(f"Server: {EMBEDDING_SERVER}")
    print()
    
    # Check if server is running
    try:
        response = requests.get("http://localhost:7777/health", timeout=2)
        print(f"✓ Server is running (health check: {response.status_code})")
    except:
        print(f"⚠️  Warning: Cannot reach server at {EMBEDDING_SERVER}")
        print("   Make sure the embedding server is running!")
        return
    
    print()
    
    # Test 1: Small text (should work)
    small_text = "This is a small test text."
    test_embedding_size(small_text, "Small text (baseline)")
    time.sleep(0.3)
    
    # Test 2: ~100 tokens
    text_100 = "Test sentence. " * 28
    test_embedding_size(text_100, "~100 tokens")
    time.sleep(0.3)
    
    # Test 3: ~250 tokens
    text_250 = "Test sentence. " * 70
    test_embedding_size(text_250, "~250 tokens")
    time.sleep(0.3)
    
    # Test 4: ~512 tokens (user's desired chunk size)
    text_512 = "Test sentence. " * 140
    test_embedding_size(text_512, "~512 tokens (desired chunk size)")
    time.sleep(0.3)
    
    # Test 5: ~1024 tokens
    text_1024 = "Test sentence. " * 280
    test_embedding_size(text_1024, "~1024 tokens")
    time.sleep(0.3)
    
    # Test 6: ~2048 tokens (MXBai's full context)
    text_2048 = "Test sentence. " * 560
    test_embedding_size(text_2048, "~2048 tokens (MXBai max context)")
    time.sleep(0.3)
    
    # Binary search for exact limit
    print("\n\n")
    max_tokens = find_max_limit()
    
    print("\n" + "="*60)
    print("SUMMARY & RECOMMENDATIONS")
    print("="*60)
    print(f"✓ Maximum working token count: {max_tokens}")
    print(f"  Recommended safe chunk size: {max_tokens - 50} tokens")
    print(f"  Estimated chars for chunks: ~{(max_tokens - 50) * 4}")
    print()
    print("CURRENT CONFIG ISSUES:")
    print("  - MAX_EMBEDDING_TOKENS = 512")
    print("  - MAX_EMBEDDING_SIZE_CHARS = 2100")
    print("  - CHUNK_SIZE_TOKENS = 512")
    print()
    if max_tokens < 512:
        print(f"⚠️  WARNING: Server accepts max {max_tokens} tokens")
        print(f"   This is LESS than configured 512 tokens!")
        print(f"   Reduce CHUNK_SIZE_TOKENS to {max_tokens - 50}")
    else:
        print(f"✓ Server can handle 512 token chunks")
    print("="*60)

if __name__ == "__main__":
    main()
