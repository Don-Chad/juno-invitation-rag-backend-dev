"""
RAG State Management Module
Contains global state and state management classes.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from rag_config import (
    THREAD_POOL_WORKERS,
    EMBEDDING_SEMAPHORE_SIZE,
    QUERY_SEMAPHORE_SIZE,
    DOCUMENT_TEXT_CACHE_MAX_SIZE
)


class LazyDocumentTexts:
    """Lazy-loading container for document texts"""
    def __init__(self):
        self._filenames = set()
    
    def __getitem__(self, filename):
        # This will be called asynchronously later
        # Just return None here and let the async function handle it
        return None
    
    def __setitem__(self, filename, text):
        # Mark filename as available
        self._filenames.add(filename)
        # The actual saving happens in an async function
    
    def __contains__(self, filename):
        return filename in self._filenames
    
    def keys(self):
        return self._filenames
    
    def __len__(self):
        return len(self._filenames)
    
    def values(self):
        # This doesn't make sense for lazy loading
        # Return empty list as placeholder
        return []


class IngestionProgress:
    """Track ingestion progress with detailed statistics"""
    def __init__(self):
        self.total_files = 0
        self.files_processed = 0
        self.files_failed = 0
        self.files_skipped = 0
        self.total_chunks = 0
        self.chunks_processed = 0
        self.chunks_failed = 0
        self.current_file = None
        self.current_file_chunks_total = 0
        self.current_file_chunks_done = 0
    
    def start_file(self, filename, total_chunks):
        """Start processing a new file"""
        self.current_file = filename
        self.current_file_chunks_total = total_chunks
        self.current_file_chunks_done = 0
        self.total_chunks += total_chunks
    
    def update_chunks(self, chunks_done):
        """Update chunk progress for current file"""
        self.current_file_chunks_done = chunks_done
        self.chunks_processed = sum([
            self.chunks_processed - self.current_file_chunks_done + chunks_done
        ])
    
    def finish_file(self, success=True, chunks_failed=0):
        """Finish processing current file"""
        if success:
            self.files_processed += 1
        else:
            self.files_failed += 1
        self.chunks_failed += chunks_failed
        self.current_file = None
    
    def skip_file(self):
        """Mark current file as skipped"""
        self.files_skipped += 1
        self.current_file = None
    
    def get_summary(self):
        """Get progress summary string"""
        total = self.total_files
        done = self.files_processed + self.files_failed + self.files_skipped
        
        return (
            f"Files: {done}/{total} "
            f"(✓{self.files_processed} ✗{self.files_failed} ⊘{self.files_skipped}) | "
            f"Chunks: {self.chunks_processed}/{self.total_chunks} "
            f"(✗{self.chunks_failed})"
        )
    
    def get_current_file_progress(self):
        """Get current file progress string"""
        if not self.current_file:
            return ""
        
        progress_pct = (self.current_file_chunks_done / self.current_file_chunks_total * 100) if self.current_file_chunks_total > 0 else 0
        
        return (
            f"Current: {self.current_file} - "
            f"Chunks: {self.current_file_chunks_done}/{self.current_file_chunks_total} "
            f"({progress_pct:.0f}%)"
        )


class RAGState:
    """Centralized state management for the RAG system"""
    def __init__(self):
        self.processed_files = {}  # Track processed files by hash
        self.chunks_metadata = {}  # Store chunk metadata with source info
        self.document_summaries = {}  # Store document summaries
        self.document_texts = LazyDocumentTexts()  # Lazy-loaded document texts
        self.annoy_index = None
        self.rag_enabled = False
        self.update_task = None  # Periodic update task
        self.nlp = None  # spaCy model
        self.embeddings_cache = {}  # Cache for chunk embeddings
        self.last_update_check = 0  # Track last update time
        self.executor = ThreadPoolExecutor(max_workers=THREAD_POOL_WORKERS)
        self.http_session = None  # Reusable aiohttp session
        self._lock = asyncio.Lock()  # For thread-safe operations
        self.embedding_semaphore = asyncio.Semaphore(EMBEDDING_SEMAPHORE_SIZE)
        self.query_semaphore = asyncio.Semaphore(QUERY_SEMAPHORE_SIZE)
        self.is_ingesting = False  # Track if we're in document ingestion mode
        self.ingestion_progress = IngestionProgress()  # Track ingestion progress


# Global state instance
state = RAGState()

# LRU cache for document texts (only keep most recently used in memory)
_document_text_cache = {}
_document_text_cache_order = []  # Track access order for LRU


def get_state():
    """Get the global RAG state instance"""
    return state
