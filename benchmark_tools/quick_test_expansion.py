"""
Quick test to check if context expansion will now work with new config
"""
from rag_hq.config import (
    CHUNK_SIZE_TOKENS, 
    SAFE_EMBEDDING_SIZE_CHARS, 
    CONTEXT_EXPANSION_ENABLED,
    CONTEXT_EXPANSION_TOKENS
)

print("=" * 80)
print("CONTEXT EXPANSION CONFIGURATION CHECK")
print("=" * 80)

print(f"\n📊 Current Settings:")
print(f"  CHUNK_SIZE_TOKENS: {CHUNK_SIZE_TOKENS}")
print(f"  Expected base chunk size: ~{CHUNK_SIZE_TOKENS * 4} chars")
print(f"  SAFE_EMBEDDING_SIZE_CHARS: {SAFE_EMBEDDING_SIZE_CHARS}")
print(f"  CONTEXT_EXPANSION_ENABLED: {CONTEXT_EXPANSION_ENABLED}")
print(f"  CONTEXT_EXPANSION_TOKENS: {CONTEXT_EXPANSION_TOKENS}")

print(f"\n🔍 Expansion Calculation:")
typical_chunk_size = 512
max_expansion_size = SAFE_EMBEDDING_SIZE_CHARS - typical_chunk_size
print(f"  Typical chunk size: {typical_chunk_size} chars")
print(f"  Space available for expansion: {max_expansion_size} chars")

if max_expansion_size <= 50:
    print(f"\n❌ PROBLEM: Not enough room for expansion!")
    print(f"   Only {max_expansion_size} chars available")
    print(f"   Expansion will be SKIPPED")
else:
    expansion_tokens = min(CONTEXT_EXPANSION_TOKENS, max_expansion_size // 4)
    expansion_chars = expansion_tokens * 4
    total_expanded = typical_chunk_size + (expansion_chars * 2)  # before + after
    
    print(f"\n✅ SUCCESS: Expansion will work!")
    print(f"   Expansion tokens: {expansion_tokens} (before + after)")
    print(f"   Expansion chars: {expansion_chars} each side")
    print(f"   Total expanded chunk size: ~{total_expanded} chars")
    print(f"   Max allowed: {SAFE_EMBEDDING_SIZE_CHARS} chars")
    
    if total_expanded > SAFE_EMBEDDING_SIZE_CHARS:
        print(f"\n⚠️  Note: Will be trimmed to {SAFE_EMBEDDING_SIZE_CHARS} chars")
    else:
        print(f"\n✅ Full expansion will fit within limits!")

print("\n" + "=" * 80)
print("EXPECTED RESULTS:")
print("=" * 80)
print(f"Before fix: ~500 char snippets (no expansion)")
print(f"After fix:  ~2000-3000 char snippets (with full expansion)")
print("=" * 80)

