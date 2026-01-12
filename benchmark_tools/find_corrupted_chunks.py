#!/usr/bin/env python3
"""
Diagnostic script to find and report corrupted chunks in RAG database.
Searches for non-Latin characters (Chinese, emoji, etc.) that can crash TTS.
"""
import pickle
import json
import re
from pathlib import Path
from collections import defaultdict


def has_non_latin_chars(text: str) -> tuple[bool, list]:
    """
    Check if text contains PROBLEMATIC Unicode (CJK, emoji, rare symbols).
    SAFE characters: ASCII, Latin Extended, €, •, –, smart quotes, etc.
    Returns (has_unsafe, list_of_unsafe_chars)
    """
    unsafe_chars = []
    
    # Whitelist of useful Unicode formatting characters that are SAFE
    safe_unicode_chars = {
        0x20AC,  # € Euro sign
        0x2022,  # • Bullet point
        0x2013,  # – En dash
        0x2014,  # — Em dash
        0x2018,  # ' Left single quote
        0x2019,  # ' Right single quote
        0x201C,  # " Left double quote
        0x201D,  # " Right double quote
        0x2026,  # … Ellipsis
        0x00B0,  # ° Degree symbol
        0x00B1,  # ± Plus-minus
        0x00A7,  # § Section symbol
        0x00A0,  # Non-breaking space
        0x202F,  # Narrow no-break space
        0x00AD,  # Soft hyphen
        0xFB00,  # ﬀ Latin ligature ff
        0xFB01,  # ﬁ Latin ligature fi
        0xFB02,  # ﬂ Latin ligature fl
        0xFB03,  # ﬃ Latin ligature ffi
        0xFB04,  # ﬄ Latin ligature ffl
    }
    
    for char in text:
        char_code = ord(char)
        
        # ASCII printable (32-126) is always safe
        if 32 <= char_code <= 126:
            continue
        
        # Common whitespace/control chars
        if char in '\n\t\r':
            continue
        
        # Latin letters with diacritics (À-ÿ and extended)
        if char.isalpha() and char_code < 591:
            continue
        
        # Whitelisted useful Unicode formatting
        if char_code in safe_unicode_chars:
            continue
        
        # CJK Unified Ideographs (Chinese/Japanese/Korean) - PROBLEMATIC
        if 0x4E00 <= char_code <= 0x9FFF:
            if char not in unsafe_chars:
                unsafe_chars.append(char)
            continue
        
        # Emoji ranges - PROBLEMATIC
        if 0x1F300 <= char_code <= 0x1F9FF:
            if char not in unsafe_chars:
                unsafe_chars.append(char)
            continue
        
        # Allow other low Unicode (up to 0x2FFF) - these are generally OK
        if char_code < 0x3000:
            continue
        
        # Everything else (high Unicode) is potentially problematic
        if char not in unsafe_chars:
            unsafe_chars.append(char)
    
    return len(unsafe_chars) > 0, unsafe_chars


def scan_chunk_database():
    """Scan the main RAG chunk database for corrupted text"""
    print("=" * 80)
    print("SCANNING CHUNK RAG DATABASE")
    print("=" * 80)
    
    # Try to find the chunks metadata file
    possible_paths = [
        Path("local_vector_db_enhanced/metadata.pkl"),
        Path("rag_hq/data/chunks_metadata.pkl"),
        Path("vector_db/chunks_metadata.pkl"),
        Path("chunks_metadata.pkl"),
    ]
    
    chunks_file = None
    for path in possible_paths:
        if path.exists():
            chunks_file = path
            break
    
    if not chunks_file:
        print("❌ Could not find chunks_metadata.pkl")
        print("   Searched in:", [str(p) for p in possible_paths])
        return
    
    print(f"✓ Found chunks database: {chunks_file}")
    print()
    
    try:
        with open(chunks_file, 'rb') as f:
            chunks_metadata = pickle.load(f)
        
        print(f"Total chunks in database: {len(chunks_metadata):,}")
        print()
        
        # Scan for corrupted chunks
        corrupted_chunks = []
        corruption_by_doc = defaultdict(int)
        char_frequency = defaultdict(int)
        
        for chunk_id, chunk_data in chunks_metadata.items():
            text = chunk_data.get('text', '')
            metadata = chunk_data.get('metadata', {})
            
            has_corruption, unsafe_chars = has_non_latin_chars(text)
            
            if has_corruption:
                filename = metadata.get('filename', 'unknown')
                chunk_idx = metadata.get('chunk_index', '?')
                
                corrupted_chunks.append({
                    'chunk_id': chunk_id,
                    'filename': filename,
                    'chunk_index': chunk_idx,
                    'text_preview': text[:200],
                    'unsafe_chars': unsafe_chars,
                    'unsafe_unicode': [ord(c) for c in unsafe_chars]
                })
                
                corruption_by_doc[filename] += 1
                
                for char in unsafe_chars:
                    char_frequency[char] += 1
        
        # Report results
        print(f"🔍 SCAN RESULTS")
        print(f"   Corrupted chunks found: {len(corrupted_chunks):,}")
        print(f"   Corruption rate: {len(corrupted_chunks) / len(chunks_metadata) * 100:.2f}%")
        print()
        
        if corrupted_chunks:
            print("📊 CORRUPTION BY DOCUMENT:")
            for filename, count in sorted(corruption_by_doc.items(), key=lambda x: x[1], reverse=True):
                print(f"   {count:4d} corrupted chunks - {filename}")
            print()
            
            print("📊 MOST COMMON UNSAFE CHARACTERS:")
            for char, count in sorted(char_frequency.items(), key=lambda x: x[1], reverse=True)[:20]:
                print(f"   '{char}' (U+{ord(char):04X}) - {count:,} occurrences")
            print()
            
            print("📝 SAMPLE CORRUPTED CHUNKS (first 10):")
            print()
            for i, chunk in enumerate(corrupted_chunks[:10], 1):
                print(f"   [{i}] Chunk ID: {chunk['chunk_id'][:16]}...")
                print(f"       Document: {chunk['filename']}")
                print(f"       Chunk #: {chunk['chunk_index']}")
                print(f"       Unsafe chars: {chunk['unsafe_chars']}")
                print(f"       Unicode: {chunk['unsafe_unicode']}")
                print(f"       Preview: {chunk['text_preview'][:150]}...")
                print()
            
            # Save full report to file
            report_file = "corrupted_chunks_report.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'total_chunks': len(chunks_metadata),
                    'corrupted_chunks': len(corrupted_chunks),
                    'corruption_by_document': dict(corruption_by_doc),
                    'character_frequency': {char: count for char, count in char_frequency.items()},
                    'corrupted_chunks_details': corrupted_chunks
                }, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Full report saved to: {report_file}")
        else:
            print("✅ No corrupted chunks found! Database is clean.")
        
    except Exception as e:
        print(f"❌ Error reading chunk database: {e}")
        import traceback
        traceback.print_exc()


def scan_qa_database():
    """Scan the Q&A RAG database for corrupted text"""
    print()
    print("=" * 80)
    print("SCANNING Q&A RAG DATABASE")
    print("=" * 80)
    
    qa_file = Path("qa_vector_db/qa_embeddings.pkl")
    
    if not qa_file.exists():
        print("❌ Q&A database not found at:", qa_file)
        return
    
    print(f"✓ Found Q&A database: {qa_file}")
    print()
    
    try:
        with open(qa_file, 'rb') as f:
            qa_pairs = pickle.load(f)
        
        print(f"Total Q&A pairs: {len(qa_pairs):,}")
        print()
        
        # Scan for corruption
        corrupted_qa = []
        corruption_by_doc = defaultdict(int)
        
        for i, qa in enumerate(qa_pairs):
            question = qa.get('question', '')
            answer = qa.get('answer', '')
            context = qa.get('context', '')
            source = qa.get('source', 'unknown')
            
            # Check all text fields
            has_q_corruption, unsafe_q = has_non_latin_chars(question)
            has_a_corruption, unsafe_a = has_non_latin_chars(answer)
            has_c_corruption, unsafe_c = has_non_latin_chars(context)
            
            if has_q_corruption or has_a_corruption or has_c_corruption:
                all_unsafe = list(set(unsafe_q + unsafe_a + unsafe_c))
                
                corrupted_qa.append({
                    'index': i,
                    'source': source,
                    'question': question[:200],
                    'answer': answer[:200],
                    'unsafe_chars': all_unsafe,
                    'unsafe_unicode': [ord(c) for c in all_unsafe]
                })
                
                corruption_by_doc[source] += 1
        
        # Report
        print(f"🔍 SCAN RESULTS")
        print(f"   Corrupted Q&A pairs found: {len(corrupted_qa):,}")
        print(f"   Corruption rate: {len(corrupted_qa) / len(qa_pairs) * 100:.2f}%")
        print()
        
        if corrupted_qa:
            print("📊 CORRUPTION BY DOCUMENT:")
            for source, count in sorted(corruption_by_doc.items(), key=lambda x: x[1], reverse=True):
                print(f"   {count:4d} corrupted Q&A - {source}")
            print()
            
            print("📝 SAMPLE CORRUPTED Q&A (first 5):")
            print()
            for i, qa in enumerate(corrupted_qa[:5], 1):
                print(f"   [{i}] Source: {qa['source']}")
                print(f"       Unsafe chars: {qa['unsafe_chars']}")
                print(f"       Unicode: {qa['unsafe_unicode']}")
                print(f"       Question: {qa['question'][:100]}...")
                print(f"       Answer: {qa['answer'][:100]}...")
                print()
            
            # Save report
            report_file = "corrupted_qa_report.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'total_qa_pairs': len(qa_pairs),
                    'corrupted_pairs': len(corrupted_qa),
                    'corruption_by_source': dict(corruption_by_doc),
                    'corrupted_qa_details': corrupted_qa
                }, f, indent=2, ensure_ascii=False)
            
            print(f"💾 Full report saved to: {report_file}")
        else:
            print("✅ No corrupted Q&A pairs found! Database is clean.")
        
    except Exception as e:
        print(f"❌ Error reading Q&A database: {e}")
        import traceback
        traceback.print_exc()


def main():
    print()
    print("🔍 RAG DATABASE CORRUPTION SCANNER")
    print("   Searching for non-Latin characters that can crash TTS")
    print()
    
    # Scan both databases
    scan_chunk_database()
    scan_qa_database()
    
    print()
    print("=" * 80)
    print("SCAN COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()

