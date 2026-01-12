"""
Q&A RAG Query Module
Provides semantic search over question-answer pairs
"""
import json
import logging
import asyncio
import pickle
from pathlib import Path
import aiohttp
import numpy as np
from typing import List, Dict, Optional

logger = logging.getLogger("rag_qa")
logger.setLevel(logging.ERROR) # Disabled INFO logs as requested


def filter_safe_text(text: str) -> str:
    """
    Filter and normalize Unicode for TTS compatibility.
    Strategy: Replace problematic Unicode with ASCII equivalents.
    Keep only: ASCII + Latin Extended + essential symbols (€, •)
    """
    import re
    safe_chars = []
    unsafe_found = False
    
    # Unicode replacement mapping - convert to TTS-safe equivalents
    unicode_replacements = {
        # Dashes -> hyphen
        0x2013: '-',   # – En dash
        0x2014: '-',   # — Em dash
        0x2015: '-',   # ― Horizontal bar
        
        # Spaces -> regular space
        0x00A0: ' ',   # Non-breaking space
        0x202F: ' ',   # Narrow no-break space
        0x2009: ' ',   # Thin space
        
        # Ligatures -> letter equivalents
        0xFB00: 'ff',  # ﬀ -> ff
        0xFB01: 'fi',  # ﬁ -> fi
        0xFB02: 'fl',  # ﬂ -> fl
        0xFB03: 'ffi', # ﬃ -> ffi
        0xFB04: 'ffl', # ﬄ -> ffl
        
        # Other symbols
        0x2026: '...',  # … -> ...
        0x00AD: '',     # Soft hyphen -> remove
    }
    
    # Keep these useful symbols as-is (TTS-safe)
    keep_unicode = {
        0x20AC,  # € Euro sign
        0x2022,  # • Bullet point
        0x2018,  # ' Left single quote
        0x2019,  # ' Right single quote
        0x201C,  # " Left double quote
        0x201D,  # " Right double quote
    }
    
    for char in text:
        char_code = ord(char)
        
        # Replace with mapping if exists
        if char_code in unicode_replacements:
            replacement = unicode_replacements[char_code]
            safe_chars.append(replacement)
            continue
        
        # Keep all ASCII printable (32-126)
        if 32 <= char_code <= 126:
            safe_chars.append(char)
        # Keep common whitespace
        elif char in '\n\t\r':
            safe_chars.append(char)
        # Keep Latin letters with diacritics (À-ÿ and extended up to 591)
        elif char.isalpha() and char_code < 591:
            safe_chars.append(char)
        # Keep essential Unicode symbols
        elif char_code in keep_unicode:
            safe_chars.append(char)
        # Block CJK Unified Ideographs (Chinese/Japanese/Korean)
        elif 0x4E00 <= char_code <= 0x9FFF:
            safe_chars.append(' ')
            unsafe_found = True
        # Block Emoji ranges
        elif 0x1F300 <= char_code <= 0x1F9FF:
            safe_chars.append(' ')
            unsafe_found = True
        # Block other high Unicode (>0x3000)
        elif char_code >= 0x3000:
            safe_chars.append(' ')
            unsafe_found = True
        # Replace other low Unicode with space for safety
        else:
            safe_chars.append(' ')
    
    # Log if we filtered anything problematic
    if unsafe_found:
        logger.warning("⚠️ Filtered problematic Unicode (CJK/emoji) from Q&A RAG text")
    
    # Clean up multiple spaces
    result = ''.join(safe_chars)
    result = re.sub(r'\s+', ' ', result)
    return result.strip()

# Configuration
QA_DATA_DIR = Path(__file__).parent / "data"
EMBEDDINGS_FILE = Path(__file__).parent.parent / "qa_vector_db" / "qa_embeddings.pkl"
EMBEDDING_SERVER_URL = "http://localhost:7777/embedding"
TOP_K = 5  # Number of questions to retrieve

# Cache for Q&A pairs
_qa_cache = None
_qa_embeddings_matrix = None  # NumPy matrix for fast similarity
_qa_initialized = False

# Shared aiohttp session
_http_session = None


async def get_embedding(text: str) -> List[float]:
    """Get embedding vector for text using llama.cpp server (async, non-blocking)"""
    global _http_session
    
    # Create session if needed
    if _http_session is None:
        _http_session = aiohttp.ClientSession()
    
    try:
        async with _http_session.post(
            EMBEDDING_SERVER_URL,
            json={"content": text},
            timeout=aiohttp.ClientTimeout(total=5.0)
        ) as response:
            if response.status == 200:
                result = await response.json()
                # Handle nested list format from llama server
                if isinstance(result, list) and len(result) > 0:
                    if isinstance(result[0], dict) and 'embedding' in result[0]:
                        embedding = result[0]['embedding']
                        if isinstance(embedding, list) and len(embedding) > 0:
                            return embedding[0]  # Get the actual embedding vector
                return result
            else:
                logger.error(f"Embedding server error: {response.status}")
                return None
    except Exception as e:
        logger.error(f"Error getting embedding: {e}")
        return None


def cosine_similarity_batch(query_vec: np.ndarray, embeddings_matrix: np.ndarray) -> np.ndarray:
    """
    Calculate cosine similarity between query and all embeddings (vectorized)
    
    Args:
        query_vec: Query embedding vector (1D numpy array)
        embeddings_matrix: Matrix of embeddings (2D numpy array, each row is an embedding)
    
    Returns:
        Array of similarity scores
    """
    # Normalize query vector
    query_norm = query_vec / np.linalg.norm(query_vec)
    
    # Embeddings should already be normalized during load
    # Compute dot product (cosine similarity with normalized vectors)
    similarities = np.dot(embeddings_matrix, query_norm)
    
    return similarities


def load_qa_cache():
    """Load pre-computed Q&A embeddings from disk (instant loading)"""
    global _qa_cache, _qa_embeddings_matrix, _qa_initialized
    
    if _qa_initialized:
        return _qa_cache
    
    logger.info("Loading Q&A pairs from pre-computed embeddings...")
    
    # Check if embeddings file exists
    if not EMBEDDINGS_FILE.exists():
        logger.error(f"Embeddings file not found: {EMBEDDINGS_FILE}")
        logger.error("Please run: python precompute_qa_embeddings.py")
        _qa_cache = []
        _qa_embeddings_matrix = np.array([])
        _qa_initialized = True
        return _qa_cache
    
    try:
        with open(EMBEDDINGS_FILE, 'rb') as f:
            qa_pairs = pickle.load(f)
        
        _qa_cache = qa_pairs
        
        # Build normalized embeddings matrix for fast similarity calculation
        embeddings_list = [np.array(qa['embedding']) for qa in qa_pairs]
        embeddings_matrix = np.vstack(embeddings_list)
        
        # Pre-normalize all embeddings (for cosine similarity)
        norms = np.linalg.norm(embeddings_matrix, axis=1, keepdims=True)
        _qa_embeddings_matrix = embeddings_matrix / norms
        
        _qa_initialized = True
        
        logger.info(f"✓ Loaded {len(qa_pairs)} Q&A pairs with embeddings")
        logger.info(f"  Embeddings matrix shape: {_qa_embeddings_matrix.shape}")
        
        return _qa_cache
    
    except Exception as e:
        logger.error(f"Error loading embeddings: {e}")
        _qa_cache = []
        _qa_embeddings_matrix = np.array([])
        _qa_initialized = True
        return _qa_cache


def ensure_qa_initialized():
    """Ensure Q&A cache is initialized"""
    global _qa_initialized
    
    if not _qa_initialized:
        load_qa_cache()
    
    return _qa_initialized


async def query_qa_rag(query: str, num_results: int = TOP_K) -> str:
    """
    Query the Q&A RAG system (fully async, non-blocking)
    
    Args:
        query: User's question
        num_results: Number of results to return
    
    Returns:
        JSON string with retrieved Q&A pairs and timing info
    """
    import time
    total_start = time.perf_counter()
    
    # Ensure cache is loaded
    if not ensure_qa_initialized():
        return json.dumps({"error": "Q&A RAG not initialized", "retrieved_qa": []})
    
    # Get embedding for query (async, non-blocking)
    embed_start = time.perf_counter()
    query_embedding = await get_embedding(query)
    embed_time_ms = (time.perf_counter() - embed_start) * 1000
    
    if not query_embedding:
        return json.dumps({"error": "Failed to get query embedding", "retrieved_qa": []})
    
    # Calculate similarities (vectorized with NumPy - super fast!)
    similarity_start = time.perf_counter()
    query_vec = np.array(query_embedding)
    similarities = cosine_similarity_batch(query_vec, _qa_embeddings_matrix)
    similarity_time_ms = (time.perf_counter() - similarity_start) * 1000
    
    # Sort by similarity and take top K
    sort_start = time.perf_counter()
    # Use argsort for efficient top-k selection
    top_indices = np.argsort(similarities)[::-1][:num_results]
    
    # Build results for top K
    filtered_results = []
    for idx in top_indices:
        sim_score = float(similarities[idx])
        # Filter out low similarity results (< 0.5)
        if sim_score >= 0.5:
            qa = _qa_cache[idx]
            # Filter unsafe characters from Q&A text
            filtered_results.append({
                'question': filter_safe_text(qa['question']),
                'answer': filter_safe_text(qa['answer']),
                'context': filter_safe_text(qa['context']),
                'source': qa['source'],
                'page': qa['page'],
                'similarity': sim_score
            })
    
    sort_time_ms = (time.perf_counter() - sort_start) * 1000
    
    total_time_ms = (time.perf_counter() - total_start) * 1000
    
    if not filtered_results:
        return json.dumps({
            "message": "No relevant Q&A pairs found", 
            "retrieved_qa": [],
            "timing": {
                "embedding_ms": round(embed_time_ms, 2),
                "similarity_calc_ms": round(similarity_time_ms, 2),
                "sort_filter_ms": round(sort_time_ms, 2),
                "total_ms": round(total_time_ms, 2)
            }
        })
    
    return json.dumps({
        "retrieved_qa": filtered_results,
        "total_results": len(filtered_results),
        "timing": {
            "embedding_ms": round(embed_time_ms, 2),
            "similarity_calc_ms": round(similarity_time_ms, 2),
            "sort_filter_ms": round(sort_time_ms, 2),
            "total_ms": round(total_time_ms, 2),
            "qa_pairs_searched": len(_qa_cache)
        }
    }, ensure_ascii=False)


# Initialize on module import for faster queries
def init_qa_rag():
    """Initialize Q&A RAG system (call once on startup)"""
    try:
        load_qa_cache()
        logger.info("✓ Q&A RAG initialized successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Failed to initialize Q&A RAG: {e}")
        return False

