"""
RAG module initialization and cleanup.
"""
import os
import logging
import asyncio
import psutil

from .state import state
from .embeddings import (
    get_http_session, close_http_session,
    load_embeddings_cache
)
from .text_processing import initialize_spacy
from .document_management import load_document_summaries
from .database import load_processed_files, cleanup_temp_files
from .database_operations import (
    load_vector_database, build_vector_database,
    update_database_periodically
)
from .config import LLAMA_SERVER_URL, DOCUMENT_TEXTS_DIR, VECTOR_DIM

logger = logging.getLogger("rag-assistant-enhanced")


def print_memory_usage(label):
    """Print current memory usage with a label."""
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    memory_mb = memory_info.rss / 1024 / 1024
    logger.info(f"Memory usage {label}: {memory_mb:.2f} MB")
    return memory_mb


async def start_update_task():
    """Start the task for periodic database updates."""
    if state.update_task is not None and not state.update_task.done():
        logger.info("Update task is already running")
        return
    
    state.update_task = asyncio.create_task(update_database_periodically())
    logger.info("Update task started")


async def stop_update_task():
    """Stop the task for periodic database updates."""
    if state.update_task and not state.update_task.done():
        state.update_task.cancel()
        try:
            await state.update_task
        except asyncio.CancelledError:
            pass
        logger.info("Update task stopped")


async def initialize_rag():
    """Initialize the RAG module."""
    logger.info("=" * 60)
    logger.info("INITIALIZING ENHANCED RAG MODULE")
    logger.info("=" * 60)
    logger.info("This will load documents and prepare the vector database...")
    base_memory = print_memory_usage("before RAG initialization")
    
    # Clean up any leftover temporary files first
    await cleanup_temp_files()
    
    # Check if llama-server is running
    try:
        session = await get_http_session()
        async with session.get(LLAMA_SERVER_URL.rsplit('/', 1)[0]) as response:
            if response.status != 200:
                logger.error("Llama-server is not responding. RAG functionality may be limited.")
    except Exception as e:
        logger.error(f"Llama-server is not accessible: {e}. RAG functionality may be limited.")
    
    # Initialize spaCy
    await initialize_spacy()
    print_memory_usage("after spaCy initialization")
    
    # Load caches
    await load_processed_files()
    print_memory_usage("after loading processed files")
    
    await load_embeddings_cache()
    print_memory_usage("after loading embeddings cache")
    logger.info(f"Embeddings cache contains {len(state.embeddings_cache)} entries")
    logger.info(f"Embeddings cache size in memory: {sum(arr.nbytes for arr in state.embeddings_cache.values()) / (1024*1024):.2f} MB")
    
    await load_document_summaries()
    print_memory_usage("after loading document summaries")
    
    # Check document texts directory
    if not os.path.exists(DOCUMENT_TEXTS_DIR):
        os.makedirs(DOCUMENT_TEXTS_DIR, exist_ok=True)
    
    # Load vector database (LOAD-ONLY mode for worker startup)
    # Skip automatic building to avoid blocking worker initialization
    # Use ingest_documents.py script to build database separately
    await load_vector_database(skip_build_if_missing=True)
    
    print_memory_usage("after loading vector database")
    
    # Preload all documents into memory for instant extensive search (if enabled)
    try:
        from config import EXTENSIVE_SEARCH_PRELOAD_DOCUMENTS
        if EXTENSIVE_SEARCH_PRELOAD_DOCUMENTS:
            from .state import preload_all_documents
            preloaded = await preload_all_documents()
            print_memory_usage("after preloading documents")
        else:
            logger.info("📄 Document preloading: DISABLED (will load on demand)")
    except ImportError:
        # Config doesn't have extensive search settings yet (backwards compatibility)
        logger.debug("Extensive search settings not found in config, skipping preload")
    
    # Display database statistics
    logger.info("=" * 60)
    logger.info("DATABASE STATISTICS")
    logger.info("=" * 60)
    
    if state.annoy_index:
        num_vectors = state.annoy_index.index.get_n_items()
        logger.info(f"📊 Annoy Index:")
        logger.info(f"   - Total vectors: {num_vectors:,}")
        logger.info(f"   - Vector dimension: {VECTOR_DIM}")
    else:
        logger.warning("⚠️  Annoy index not loaded")
    
    num_chunks = len(state.chunks_metadata)
    logger.info(f"📦 Chunks Metadata:")
    logger.info(f"   - Total chunks: {num_chunks:,}")
    
    num_docs = len(set(meta['metadata']['filename'] for meta in state.chunks_metadata.values() if 'metadata' in meta))
    logger.info(f"📄 Documents:")
    logger.info(f"   - Unique documents: {num_docs}")
    logger.info(f"   - Processed files tracked: {len(state.processed_files)}")
    
    num_summaries = len(state.document_summaries)
    logger.info(f"📝 Document Summaries: {num_summaries}")
    
    num_cached_embeddings = len(state.embeddings_cache)
    cache_size_mb = sum(arr.nbytes for arr in state.embeddings_cache.values()) / (1024*1024) if num_cached_embeddings > 0 else 0
    logger.info(f"💾 Embeddings Cache:")
    logger.info(f"   - Cached embeddings: {num_cached_embeddings:,}")
    logger.info(f"   - Cache size: {cache_size_mb:.2f} MB")
    
    logger.info("=" * 60)
    
    # Periodic reload and update tasks DISABLED
    # These can cause issues with worker initialization
    # Use manual reload or restart worker after ingestion instead
    
    # from .reload_handler import periodic_reload_check, setup_signal_handlers
    # setup_signal_handlers()
    # reload_task = asyncio.create_task(periodic_reload_check(interval=60))
    
    logger.info("ℹ️  Periodic reload monitoring: DISABLED (manual reload only)")
    logger.info("   To reload: Restart worker after ingestion")
    
    print_memory_usage("after initialization tasks")
    
    total_memory = print_memory_usage("RAG module initialization complete")
    logger.info(f"💡 Total memory increase: {total_memory - base_memory:.2f} MB")
    
    state.rag_enabled = True
    
    logger.info("=" * 60)
    logger.info("✅ RAG MODULE FULLY OPERATIONAL")
    logger.info("=" * 60)


async def cleanup_rag():
    """Cleanup resources when shutting down."""
    logger.info("Cleaning up RAG module...")
    
    # Stop update task
    await stop_update_task()
    
    # Close HTTP session
    await close_http_session()
    
    # Shutdown thread pool
    state.executor.shutdown(wait=True)
    
    logger.info("RAG module cleanup complete.")


# Module initialization - EAGER MODE (not lazy)
# The module initializes immediately when first imported by the agent
_init_task = None
_is_initialized = False


async def _ensure_initialized():
    """Ensure the RAG module is initialized (EAGER MODE)."""
    global _init_task, _is_initialized
    
    if _is_initialized:
        logger.info("RAG already initialized, skipping")
        return
    
    if _init_task is None:
        logger.info("Starting EAGER RAG initialization (not lazy - loads immediately)")
        _init_task = asyncio.create_task(initialize_rag())
    
    await _init_task
    _is_initialized = True
    logger.info("RAG initialization complete and ready")


async def ensure_rag_initialized():
    """Public function to ensure RAG is initialized.
    
    This starts RAG initialization immediately, not lazily.
    It will load the database and start processing documents right away.
    """
    await _ensure_initialized()
