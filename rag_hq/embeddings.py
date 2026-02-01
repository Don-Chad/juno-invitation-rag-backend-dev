"""
Embedding creation and caching functionality.
"""
import time
import asyncio
import aiohttp
import numpy as np
import hashlib
import os
import logging
from functools import lru_cache

from .config import (
    LLAMA_SERVER_URL, VECTOR_DIM, USE_FP16_EMBEDDINGS,
    MAX_EMBEDDING_SIZE_CHARS, MAX_EMBEDDING_TOKENS, EMBEDDINGS_CACHE_PATH,
    CACHE_SAVE_THRESHOLD, CACHE_SAVE_INTERVAL
)
from .state import state

logger = logging.getLogger("rag-assistant-enhanced")

# Import token counter
import tiktoken
_encoding = None

def get_token_count(text: str) -> int:
    """Count actual tokens using tiktoken."""
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return len(_encoding.encode(text))

# Cache tracking
_cache_last_save_time = 0
_cache_changes_since_save = 0


@lru_cache(maxsize=1024)
def _embedding_cache_key(text):
    """Create a cache key for embeddings."""
    return hashlib.md5(text.encode()).hexdigest()


async def get_http_session():
    """Get or create the HTTP session with optimized settings."""
    import os
    
    current_pid = os.getpid()
    
    # Check if session needs to be created/recreated
    # Wrap in try-except to handle event loop issues in multiprocessing
    needs_new_session = False
    
    # Always create new session if we're in a different process (forked child)
    if state.http_session_pid != current_pid:
        logger.debug(f"Process change detected (was {state.http_session_pid}, now {current_pid}), creating new HTTP session")
        needs_new_session = True
        # Don't try to close old session - it belongs to different process/event loop
        state.http_session = None
    
    if not needs_new_session:
        try:
            if state.http_session is None or state.http_session.closed:
                needs_new_session = True
        except RuntimeError:
            # Event loop might be closed, create new session
            needs_new_session = True
            state.http_session = None
    
    if needs_new_session:
        # Verify we have a running event loop
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.error("No running event loop available for HTTP session")
            raise

        # If we are in the same process and there is an existing session object,
        # try to close it before creating a new one to avoid leaking connections.
        # (In a different process, we must never touch it.)
        try:
            if state.http_session_pid == current_pid and state.http_session and not state.http_session.closed:
                await state.http_session.close()
        except RuntimeError:
            # Event loop might be closing/closed; we will just recreate next time.
            pass
        finally:
            # Ensure we don't keep a reference to a dead session
            state.http_session = None
            state.http_session_pid = None
        
        timeout = aiohttp.ClientTimeout(
            total=5,
            connect=0.5,
            sock_read=4.5
        )
        
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            force_close=False,
            keepalive_timeout=30
        )
        
        state.http_session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            auto_decompress=False
        )
        state.http_session_pid = current_pid
        logger.debug(f"Created new HTTP session for process {current_pid}")
    
    return state.http_session


async def close_http_session():
    """Close the HTTP session."""
    import os
    current_pid = os.getpid()
    
    # Only try to close if this session belongs to current process
    if state.http_session_pid == current_pid:
        try:
            if state.http_session and not state.http_session.closed:
                await state.http_session.close()
        except RuntimeError:
            # Event loop already closed, session cleanup not needed
            pass
        finally:
            state.http_session = None
            state.http_session_pid = None
    else:
        # Session belongs to different process, just forget it
        state.http_session = None
        state.http_session_pid = None


async def _reset_http_session(reason: str):
    """Best-effort reset of the shared HTTP session.

    Prefer closing (when owned by this process) to avoid leaking sockets.
    Fall back to forgetting the reference if the event loop is not usable.
    """
    try:
        logger.debug(f"Resetting HTTP session ({reason})")
        await close_http_session()
    except RuntimeError:
        # Event loop might be closed; just drop the reference.
        state.http_session = None
        state.http_session_pid = None
    except Exception:
        # Never allow session reset errors to crash the worker.
        state.http_session = None
        state.http_session_pid = None


async def create_embeddings(input_text, is_query=False):
    """Create embeddings using async HTTP request with performance optimizations."""
    start_time = time.perf_counter()
    
    if not input_text or not input_text.strip():
        return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
    
    # Ensure semaphores are valid for current process
    state.ensure_locks()
    
    # Use different semaphores based on context
    semaphore = state.query_semaphore if is_query else state.embedding_semaphore
    
    async with semaphore:
        # Token-based truncation with retry
        token_count = get_token_count(input_text)
        
        # Truncate if needed (with retries for edge cases)
        # Server limit tested at 418 tokens, config uses 410 for safety
        max_attempts = 3
        for truncate_attempt in range(max_attempts):
            if token_count <= MAX_EMBEDDING_TOKENS:
                break
            
            # Calculate truncation ratio with safety margin
            truncate_ratio = (MAX_EMBEDDING_TOKENS - 10) / token_count  # -10 for safety margin
            new_length = int(len(input_text) * truncate_ratio)
            input_text = input_text[:new_length]
            token_count = get_token_count(input_text)
            
            if truncate_attempt == 0:
                logger.debug(f"Pre-truncation: {token_count} -> target {MAX_EMBEDDING_TOKENS} tokens")
        
        if token_count > MAX_EMBEDDING_TOKENS:
            logger.warning(f"⚠️  Failed to truncate to {MAX_EMBEDDING_TOKENS} tokens after {max_attempts} attempts, attempting with {token_count} tokens")
        
        # Check cache first
        cache_key = _embedding_cache_key(input_text)
        if cache_key in state.embeddings_cache:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.debug(f"Embedding cache hit: {elapsed:.2f}ms")
            return state.embeddings_cache[cache_key]
        
        # Retry mechanism for server errors
        max_retries = 2
        retry_delay = 0.25
        
        for attempt in range(max_retries + 1):
            try:
                session = await get_http_session()
                
                logger.debug(f"Sending {len(input_text)} chars (~{token_count} tokens) to embedding server")
                
                async with session.post(
                    LLAMA_SERVER_URL,
                    json={"content": input_text, "embedding": True},
                    timeout=10.0
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        if "input is too large" in text.lower() or "input is larger" in text.lower():
                            # Server rejected - truncate more aggressively and retry
                            if attempt < max_retries:
                                old_count = token_count
                                input_text = input_text[:int(len(input_text) * 0.85)]
                                token_count = get_token_count(input_text)
                                logger.warning(f"❌ Server rejected {old_count} tokens - retrying with {token_count} tokens (attempt {attempt+2}/{max_retries+1})")
                                await asyncio.sleep(retry_delay)
                                continue
                            else:
                                logger.error(f"❌ EMBEDDING FAILED: Server rejected input after {max_retries+1} attempts (final: {token_count} tokens, {len(input_text)} chars)")
                                logger.error(f"   Text preview: {input_text[:100]}...")
                                return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
                        logger.error(f"Error from llama-server: {response.status} - {text}")
                        if attempt < max_retries:
                            await asyncio.sleep(retry_delay)
                            continue
                        return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
                    
                    data = await response.json()
                    
                    # Parse the response
                    if isinstance(data, list) and len(data) > 0:
                        embedding_data = data[0].get("embedding", [])
                        
                        if isinstance(embedding_data, list) and len(embedding_data) > 0:
                            if isinstance(embedding_data[0], list):
                                embedding = np.array(embedding_data[0], dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
                            else:
                                embedding = np.array(embedding_data, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
                        else:
                            logger.error(f"Unexpected embedding format: {type(embedding_data)}")
                            return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
                    else:
                        logger.error(f"Unexpected response format: {type(data)}")
                        return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
                    
                    # Verify dimension
                    if len(embedding) != VECTOR_DIM:
                        logger.warning(f"Embedding dimension mismatch: expected {VECTOR_DIM}, got {len(embedding)}")
                        if len(embedding) > VECTOR_DIM:
                            embedding = embedding[:VECTOR_DIM]
                        else:
                            embedding = np.pad(embedding, (0, VECTOR_DIM - len(embedding)), 'constant')
                    
                    # Normalize for cosine similarity
                    norm = np.linalg.norm(embedding)
                    if norm > 0:
                        embedding = embedding / norm
                    
                    # Cache the result
                    state.embeddings_cache[cache_key] = embedding
                    
                    # Save cache periodically
                    await maybe_save_embeddings_cache()
                    
                    elapsed = (time.perf_counter() - start_time) * 1000
                    logger.debug(f"Embedding server request: {elapsed:.2f}ms, text length: {len(input_text)} chars")
                    
                    return embedding
                
            except asyncio.TimeoutError:
                logger.warning(f"Timeout while getting embeddings (attempt {attempt+1}/{max_retries+1})")
                await _reset_http_session("embedding timeout")
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                else:
                    return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
            except RuntimeError as e:
                if "Event loop is closed" in str(e) or "closed event loop" in str(e).lower():
                    logger.warning(f"Event loop error detected - forcing HTTP session reset")
                    await _reset_http_session("event loop closed")
                    if attempt < max_retries:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
                else:
                    logger.error(f"Runtime error creating embeddings: {e}")
                    await _reset_http_session("runtime error")
                    return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)
            except Exception as e:
                logger.error(f"Error creating embeddings from llama-server: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                else:
                    return np.zeros(VECTOR_DIM, dtype=np.float16 if USE_FP16_EMBEDDINGS else np.float32)


async def save_embeddings_cache():
    """Save embeddings cache to disk for faster loading."""
    try:
        if state.embeddings_cache:
            cache_data = {
                'keys': list(state.embeddings_cache.keys()),
                'values': np.array(list(state.embeddings_cache.values()))
            }
            
            def _save_cache():
                temp_path = EMBEDDINGS_CACHE_PATH + '.temp.npy'
                np.save(temp_path, cache_data)
                os.replace(temp_path, EMBEDDINGS_CACHE_PATH + '.npy')
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(state.executor, _save_cache)
            logger.debug(f"Saved {len(state.embeddings_cache)} embeddings to cache")
    except Exception as e:
        logger.error(f"Error saving embeddings cache: {e}")


async def maybe_save_embeddings_cache():
    """Save embeddings cache if enough changes or time has passed."""
    global _cache_last_save_time, _cache_changes_since_save
    
    current_time = time.time()
    _cache_changes_since_save += 1
    
    if (_cache_changes_since_save >= CACHE_SAVE_THRESHOLD or 
            current_time - _cache_last_save_time > CACHE_SAVE_INTERVAL):
        await save_embeddings_cache()
        _cache_last_save_time = current_time
        _cache_changes_since_save = 0


async def load_embeddings_cache():
    """Load embeddings cache from disk asynchronously."""
    global _cache_last_save_time
    
    try:
        cache_file = EMBEDDINGS_CACHE_PATH + '.npy'
        if os.path.exists(cache_file):
            def _load_cache():
                try:
                    return np.load(cache_file, allow_pickle=True).item()
                except Exception as e:
                    logger.error(f"Error loading cache file: {e}")
                    backup_file = EMBEDDINGS_CACHE_PATH + '.backup.npy'
                    if os.path.exists(backup_file):
                        logger.info("Trying to load backup cache file")
                        return np.load(backup_file, allow_pickle=True).item()
                    return {'keys': [], 'values': np.array([])}
            
            loop = asyncio.get_running_loop()
            cache_data = await loop.run_in_executor(state.executor, _load_cache)
            
            if 'keys' in cache_data and 'values' in cache_data and len(cache_data['keys']) > 0:
                state.embeddings_cache = dict(zip(cache_data['keys'], cache_data['values']))
                logger.info(f"Loaded {len(state.embeddings_cache)} embeddings from cache")
                
                # Create backup
                def _backup_cache():
                    import shutil
                    shutil.copy2(cache_file, EMBEDDINGS_CACHE_PATH + '.backup.npy')
                
                await loop.run_in_executor(state.executor, _backup_cache)
            else:
                logger.warning("Cache file exists but contains no valid data")
                state.embeddings_cache = {}
            
            _cache_last_save_time = time.time()
        else:
            state.embeddings_cache = {}
    except Exception as e:
        logger.error(f"Error loading embeddings cache: {e}")
        state.embeddings_cache = {}
