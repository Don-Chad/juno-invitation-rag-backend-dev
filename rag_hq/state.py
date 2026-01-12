"""
Global state management for the RAG module.
"""
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
import aiofiles
import aiofiles.os
import logging

logger = logging.getLogger("rag-assistant-enhanced")


class LazyDocumentTexts:
    """Lazy-loading document text storage."""
    def __init__(self):
        self._filenames = set()
    
    def __getitem__(self, filename):
        return None
    
    def __setitem__(self, filename, text):
        self._filenames.add(filename)
    
    def __contains__(self, filename):
        return filename in self._filenames
    
    def keys(self):
        return self._filenames
    
    def __len__(self):
        return len(self._filenames)
    
    def values(self):
        return []


class RAGState:
    """Centralized state management for the RAG system."""
    def __init__(self):
        self.processed_files = {}
        self.chunks_metadata = {}
        self.document_summaries = {}
        self.document_texts = LazyDocumentTexts()
        self.annoy_index = None
        self.bm25_index = None  # Keyword-based search index
        self.rag_enabled = False
        self.update_task = None
        self.nlp = None
        self.embeddings_cache = {}
        self.last_update_check = 0
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.http_session = None
        self.http_session_pid = None  # Track which process owns the session
        self._lock = None
        self._lock_pid = None
        self.embedding_semaphore = None
        self.query_semaphore = None
        self._semaphores_pid = None
        self.is_ingesting = False
        self.last_db_modified_time = 0  # Track when the database file was last loaded
    
    def ensure_locks(self):
        """Ensure locks and semaphores are valid for current process."""
        import os
        current_pid = os.getpid()
        
        # Recreate lock if in different process
        if self._lock_pid != current_pid:
            self._lock = asyncio.Lock()
            self._lock_pid = current_pid
        
        # Recreate semaphores if in different process
        if self._semaphores_pid != current_pid:
            # CRITICAL: Server has --batch-size 512 (total across all concurrent requests)
            # With 410 token chunks: 2 concurrent × 410 = 820 tokens > 512 (exceeds batch!)
            # Must use 1 concurrent request during ingestion to avoid batch size overflow
            self.embedding_semaphore = asyncio.Semaphore(1)  # Changed from 2 to 1
            self.query_semaphore = asyncio.Semaphore(1)
            self._semaphores_pid = current_pid
    
    @property
    def lock(self):
        """Get the lock, ensuring it's valid for current process."""
        self.ensure_locks()
        return self._lock


# Global state instance
state = RAGState()

# Document text cache for LRU
_document_text_cache = {}
_document_text_cache_order = []


async def save_document_text(filename, text):
    """Save document text to disk for lazy loading."""
    from .config import DOCUMENT_TEXTS_DIR
    
    safe_filename = filename.replace('/', '_').replace('\\', '_')
    file_path = os.path.join(DOCUMENT_TEXTS_DIR, safe_filename)
    
    try:
        async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
            await f.write(text)
        logger.debug(f"Saved document text for {filename} to disk")
        return True
    except Exception as e:
        logger.error(f"Error saving document text for {filename}: {e}")
        return False


async def get_document_text(filename):
    """Get document text with lazy loading from disk."""
    from .config import DOCUMENT_TEXTS_DIR, DOCUMENT_TEXT_CACHE_MAX_SIZE
    global _document_text_cache, _document_text_cache_order
    
    # Check cache first
    if filename in _document_text_cache:
        _document_text_cache_order.remove(filename)
        _document_text_cache_order.append(filename)
        return _document_text_cache[filename]
    
    # Load from disk
    safe_filename = filename.replace('/', '_').replace('\\', '_')
    file_path = os.path.join(DOCUMENT_TEXTS_DIR, safe_filename)
    
    try:
        if await aiofiles.os.path.exists(file_path):
            async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = await f.read()
            
            _document_text_cache[filename] = text
            _document_text_cache_order.append(filename)
            
            # Enforce cache size limit
            if len(_document_text_cache) > DOCUMENT_TEXT_CACHE_MAX_SIZE:
                oldest = _document_text_cache_order.pop(0)
                _document_text_cache.pop(oldest)
                logger.debug(f"Removed {oldest} from document text cache (LRU)")
            
            return text
        else:
            logger.warning(f"Document text file not found for {filename}")
            return None
    except Exception as e:
        logger.error(f"Error loading document text for {filename}: {e}")
        return None


async def preload_all_documents():
    """Preload ALL documents into memory cache for instant extensive search access.
    
    This eliminates the 50-100ms disk I/O delay when extensive search needs full documents.
    Call this during RAG initialization if EXTENSIVE_SEARCH_PRELOAD_DOCUMENTS is enabled.
    """
    from .config import DOCUMENT_TEXTS_DIR
    global _document_text_cache, _document_text_cache_order
    
    if not state.document_summaries:
        logger.warning("No document summaries available for preloading")
        return 0
    
    logger.info(f"🔄 Preloading {len(state.document_summaries)} documents into memory...")
    
    start_time = asyncio.get_event_loop().time()
    preloaded_count = 0
    total_size_mb = 0
    
    for filename in state.document_summaries.keys():
        # Skip if already in cache
        if filename in _document_text_cache:
            continue
        
        safe_filename = filename.replace('/', '_').replace('\\', '_')
        file_path = os.path.join(DOCUMENT_TEXTS_DIR, safe_filename)
        
        try:
            if await aiofiles.os.path.exists(file_path):
                async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text = await f.read()
                
                _document_text_cache[filename] = text
                _document_text_cache_order.append(filename)
                
                preloaded_count += 1
                total_size_mb += len(text) / 1024 / 1024
                
            else:
                logger.warning(f"Document text file not found for preloading: {filename}")
        except Exception as e:
            logger.error(f"Error preloading document {filename}: {e}")
    
    elapsed_time = (asyncio.get_event_loop().time() - start_time) * 1000
    
    logger.info(f"✅ Preloaded {preloaded_count} documents in {elapsed_time:.2f} ms")
    logger.info(f"   Total size: {total_size_mb:.2f} MB in memory")
    logger.info(f"   Average per document: {total_size_mb / max(preloaded_count, 1):.2f} MB")
    logger.info(f"   Cache now contains: {len(_document_text_cache)} documents")
    
    return preloaded_count
