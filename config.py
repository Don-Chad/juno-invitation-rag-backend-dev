import logging
import sys
import os

####





LLM_REDUNDANCY_MODE = True
LLM_REDUNDANCY_GRACE_TIME = 350
PRINT_FULL_LLM_MESSAGE = True

# Controls whether the AI should continue conversations or introduce new topics 
# after brief silences. When True, the AI will naturally extend conversations 
# by adding related points or introducing new topics if the user hasn't responded.
AI_CONVERSATION_CONTINUATION = False  # DISABLED - No automatic reminders or conversation continuation

DEV_MODE = True
LOGGING_LEVEL = logging.DEBUG
LOGGING_TO_DISK = True

# TTS Character Safety Mode
# ULTRA_STRICT: Only basic ASCII (a-z, A-Z, 0-9, basic punctuation) - SAFEST
# NORMAL: Includes €, •, smart quotes, diacritics - RECOMMENDED
ULTRA_STRICT_CHARACTER_FILTER = True  # Set to True to debug TTS crashes



DEBUG_LLM = True

# ===========================
# RAG Configuration
# ===========================
# Now controlled via environment variable RAG_ENABLED (default: False)
# Set RAG_ENABLED=true in .env to enable
RAG_ENABLED = os.getenv("RAG_ENABLED", "false").lower() == "true"
RAG_MODE = "chunk"  # Options: "qa" (Q&A only), "chunk" (original chunk-based), "both" (use both systems)
RAG_DEBUG_MODE = True  # Show what RAG context is being added - FORCE ENABLED
RAG_DEBUG_PRINT_FULL = True  # Print full RAG context that's being added - FORCE ENABLED
RAG_TRIM_FROM_HISTORY = False  # Keep RAG context in history (managed by budget)
RAG_MAX_CONTEXT_AGE_MESSAGES = 10  # Keep trimming RAG for last N message cycles
RAG_NUM_RESULTS = 5  # Number of RAG documents to retrieve
RAG_CONTEXT_BUDGET_TOKENS = 6000  # Maximum tokens reserved for RAG context
RAG_ROLLING_BUDGET = True  # Remove oldest RAG messages when budget exceeded
RAG_RELEVANCE_THRESHOLD = 0.2  # Minimum similarity score for document retrieval (0.0-1.0, lower = more results)

# RAG Query Logging - FORCE ENABLED for comprehensive debugging
RAG_QUERY_LOG_ENABLED = True  # Enable detailed RAG query logging to file - FORCE ENABLED
RAG_QUERY_LOG_FILE = "rag_query_log.txt"  # Log file name (in working directory)

MAX_TOKENS = 15000  # Maximum context length in tokens

# ===========================
# Extensive Search Configuration
# ===========================
EXTENSIVE_SEARCH_ENABLED = False  # Enable function calling for deep document search
EXTENSIVE_SEARCH_MAX_DOCS = 3  # Maximum number of full documents to retrieve
EXTENSIVE_SEARCH_MAX_TOKENS_PER_DOC = 3000  # Maximum tokens per document (truncate if longer)
EXTENSIVE_SEARCH_DEBUG = True  # Extensive debug output for testing
EXTENSIVE_SEARCH_SUMMARY_TOKENS = 500  # Token limit for extended summaries (for document selection)
EXTENSIVE_SEARCH_SUMMARY_CHARS = 6000  # Character limit for text to summarize (500 tokens * 4 chars + margin)

# Document Selection Method
EXTENSIVE_SEARCH_SELECTION_METHOD = "vector"  # Options: "llm", "vector", "hybrid"
# - "llm": LLM picks documents from summaries (~150-200ms, most accurate)
# - "vector": Semantic search on summary embeddings (~10-20ms, fastest)
# - "hybrid": Vector search top 5 → LLM picks best 2 (~100ms, balanced)

# Context Management
EXTENSIVE_SEARCH_CLEANUP_CONTEXT = True  # Remove extensive search context after answer (prevents bloat)
EXTENSIVE_SEARCH_PRELOAD_DOCUMENTS = True  # Preload all documents in memory for instant retrieval

# ===========================
# Document Server Configuration
# ===========================
DOCUMENT_SERVER_ENABLED = False  # DISABLED - caused process hangs during RAG queries
DOCUMENT_SERVER_PORT = 8888  # Port for document server
DOCUMENT_SERVER_BASE_URL = "http://64.23.171.50:8888"  # Base URL for document downloads




# ===========================
# Active Memory Configuration
# ===========================
MEMORY_ENABLED = False  # Set to True to enable memory formation
MEMORY_THRESHOLD_MESSAGES = 10  # Trigger memory formation after this many messages
MEMORY_MAX_ITEMS = 100  # Maximum number of memories to store per user
MEMORY_MODEL = "llama-3.3-70b-versatile"  # High quality model for extraction
MEMORY_PII_PROTECTION = True  # Enable strict PII filtering

# LLM Debug Settings
PRINT_FULL_LLM_MESSAGE = False  # Set to True to enable detailed LLM message logging
PRINT_LLM_TIMING = False  # Set to True to enable LLM timing metrics















# Self-validate the voice configuration when module is loaded
# if SPEAKER_OVERRIDE:
#     try:
#         from character_configs import get_character_config
#         character_config = get_character_config(SPEAKER_OVERRIDE)
#         validate_voice_config(character_config)
#     except ImportError:
#         logging.warning("Could not import character_configs module for validation")
#     except Exception as e:
#         raise ValueError(f"Invalid voice configuration for SPEAKER_OVERRIDE={SPEAKER_OVERRIDE}: {str(e)}")


