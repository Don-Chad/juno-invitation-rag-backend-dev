"""
RAG Worker Helper Functions
Centralized helpers for RAG context building, logging, message handling, and orchestration
"""

from .context_builders import (
    build_qa_context,
    build_chunk_context,
    build_combined_qa_context,
    build_combined_chunk_context_with_budget
)

from .logging_helpers import (
    log_qa_debug,
    log_chunk_debug,
    log_qa_timing,
    log_both_rag_debug
)

from .message_helpers import (
    insert_rag_message
)

from .chat_management import (
    print_chat_history_stats,
    manage_rag_context_budget
)

from .query_handlers import (
    query_qa_rag_only,
    query_chunk_rag_only,
    query_both_rags
)

from .rag_orchestrator import (
    automatic_rag_enrichment,
    get_last_user_message
)

__all__ = [
    # Context builders
    'build_qa_context',
    'build_chunk_context',
    'build_combined_qa_context',
    'build_combined_chunk_context_with_budget',
    # Logging helpers
    'log_qa_debug',
    'log_chunk_debug',
    'log_qa_timing',
    'log_both_rag_debug',
    # Message helpers
    'insert_rag_message',
    # Chat management
    'print_chat_history_stats',
    'manage_rag_context_budget',
    # Query handlers
    'query_qa_rag_only',
    'query_chunk_rag_only',
    'query_both_rags',
    # Orchestrator
    'automatic_rag_enrichment',
    'get_last_user_message',
]

