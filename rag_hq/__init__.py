"""
RAG HQ Enhanced - Modular Retrieval Augmented Generation System

A high-performance RAG system with:
- Async vector database operations
- Document chunking with overlap
- Context expansion on retrieval
- Memory-optimized embeddings
- Automatic periodic updates
"""

import logging

# Setup logger with enhanced formatting for visibility
logger = logging.getLogger("rag-assistant-enhanced")
# logger.setLevel(logging.INFO)
logger.setLevel(logging.ERROR) # Disabled INFO logs as requested
handler = logging.StreamHandler()
# More visible format with RAG prefix
formatter = logging.Formatter('🔍 RAG | %(asctime)s | %(levelname)s | %(message)s', datefmt='%H:%M:%S')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Prevent duplicate logging
logger.propagate = False

# Import main functions
from .initialization import (
    initialize_rag,
    cleanup_rag,
    ensure_rag_initialized
)

from .query import (
    enrich_with_rag,
    query_rag
)

from .database_operations import (
    build_vector_database,
    load_vector_database
)

from .state import state, preload_all_documents

from .health_check import (
    run_health_check,
    quick_check,
    RAGHealthChecker
)

# Public API
__all__ = [
    'initialize_rag',
    'cleanup_rag',
    'ensure_rag_initialized',
    'enrich_with_rag',
    'query_rag',
    'build_vector_database',
    'load_vector_database',
    'run_health_check',
    'quick_check',
    'RAGHealthChecker',
    'state',
    'preload_all_documents',
]

__version__ = '2.0.0'
__author__ = 'RAG HQ Team'
