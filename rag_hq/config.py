"""
OPTIMIZED Configuration for RAG module.

Based on thorough review - implements your desired configuration:
- 512 char chunks for embedding (~128 tokens)
- 512 token expansion (256 before + 256 after)
- K=3 results for ~1,920 tokens total context
- 25% overlap for boundary coverage

See RAG_SYSTEM_REVIEW.md for detailed explanation.
"""
import os

# ===========================
# Paths and Folders
# ===========================
UPLOADS_FOLDER = "./docs"
VECTOR_DB_FOLDER = "local_vector_db_enhanced"
VECTOR_DB_PATH = os.path.join(VECTOR_DB_FOLDER, "vdb_data")
METADATA_PATH = os.path.join(VECTOR_DB_FOLDER, "metadata.pkl")
FILE_HISTORY_PATH = os.path.join(VECTOR_DB_FOLDER, "file_history.pkl")
EMBEDDINGS_CACHE_PATH = os.path.join(VECTOR_DB_FOLDER, "embeddings_cache.npy")
DOCUMENT_SUMMARIES_PATH = os.path.join(VECTOR_DB_FOLDER, "document_summaries.pkl")
DOCUMENT_TEXTS_DIR = os.path.join(VECTOR_DB_FOLDER, "document_texts")
INGESTION_RAPPORT_PATH = os.path.join(VECTOR_DB_FOLDER, ".ingestionrapport.json")

# ===========================
# Update Settings
# ===========================
UPDATE_INTERVAL = 30  # seconds

# ===========================
# Chunking Configuration (OPTIMIZED)
# ===========================
CHUNK_SIZE_TOKENS = 128  # Small chunks: 512 chars for precise embedding
CHUNK_OVERLAP_RATIO = 0.25  # 25% overlap for better boundary coverage
MAX_CHUNK_SIZE_CHARS = 520  # Hard limit: 512 + small buffer

# ===========================
# Embedding Server Limits (Your 512 char limit)
# ===========================
MAX_EMBEDDING_TOKENS = 128  # Matches chunk size (512 chars / 4 = 128 tokens)
MAX_EMBEDDING_SIZE_CHARS = 520  # Strict char limit
SAFE_EMBEDDING_SIZE_CHARS = 512  # Safe size for your embedding model

# ===========================
# Context Expansion (Small-to-Large Retrieval)
# ===========================
CONTEXT_EXPANSION_ENABLED = True
CONTEXT_EXPANSION_TOKENS = 512  # 256 tokens BEFORE + 256 tokens AFTER
# Result: 128 (core chunk) + 512 (expansion) = 640 tokens per result

# ===========================
# Extensive Search Summaries
# ===========================
EXTENSIVE_SEARCH_SUMMARY_TOKENS = 500  # Token limit for extended summaries
EXTENSIVE_SEARCH_SUMMARY_CHARS = 6000  # Character limit for text to summarize (500 tokens * 4 chars + margin)

# ===========================
# Llama Server Configuration (Matches existing 768-dim database)
# ===========================
LLAMA_SERVER_URL = "http://localhost:7777/embedding"
VECTOR_DIM = 768  # Updated to match current database on disk

# ===========================
# Memory Optimization
# ===========================
USE_FP16_EMBEDDINGS = True
LAZY_LOAD_DOCUMENT_TEXTS = True

# ===========================
# Groq API Configuration
# ===========================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if GROQ_API_KEY:
    os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# ===========================
# Retrieval Configuration (OPTIMIZED)
# ===========================
K_RESULTS = 3  # Your target: 3 results × 640 tokens = ~1,920 tokens
RELEVANCE_THRESHOLD = 0.5  # Minimum similarity score
HIGH_RELEVANCE_THRESHOLD = 0.7  # High relevance threshold
DEDUP_THRESHOLD = 0.95  # Deduplication threshold
MAX_CONTEXT_TOKENS = 3000  # Maximum total tokens (allows 3×640 + overhead)

# ===========================
# Hybrid Search Configuration
# ===========================
HYBRID_SEARCH_ENABLED = False  # Toggle for hybrid semantic + keyword search
HYBRID_SEMANTIC_WEIGHT = 0.7  # Weight for semantic similarity
HYBRID_KEYWORD_WEIGHT = 0.3  # Weight for keyword (BM25) scoring

# ===========================
# Citation & Metadata
# ===========================
ENABLE_CITATIONS = True  # Add source citations to responses
ENABLE_METADATA_FILTERING = True  # Allow filtering by document metadata

# ===========================
# Logging Configuration
# ===========================
VERBOSE_RAG_LOGGING = False  # Enable verbose RAG query logging

# ===========================
# Cache Settings
# ===========================
CACHE_SAVE_THRESHOLD = 50  # Save after this many new entries
CACHE_SAVE_INTERVAL = 300  # Or this many seconds (5 minutes)
DOCUMENT_TEXT_CACHE_MAX_SIZE = 5  # Keep 5 documents in memory at once

# ===========================
# Processing Settings
# ===========================
BATCH_SIZE_FILES = 2  # Process 2 files at a time
BATCH_SIZE_CHUNKS = 2  # Process 2 chunks at a time during ingestion
CHUNK_BATCH_SIZE_NORMAL = 5  # Normal chunk batch size
INGESTION_DELAY = 0.2  # Delay between batches during ingestion
NORMAL_DELAY = 0.1  # Normal delay between batches

# Create necessary directories
if not os.path.exists(VECTOR_DB_FOLDER):
    os.makedirs(VECTOR_DB_FOLDER)

if not os.path.exists(DOCUMENT_TEXTS_DIR):
    os.makedirs(DOCUMENT_TEXTS_DIR)

# ===========================
# Configuration Summary
# ===========================
"""
OPTIMIZED CONFIGURATION SUMMARY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Chunk (for embedding):     512 chars (128 tokens)
Overlap:                   25% (during ingestion)
Expansion:                 512 tokens (256 before + 256 after)
Total per result:          640 tokens (128 + 512)
K results:                 3
Total to LLM:              ~1,920 tokens
Max budget:                3,000 tokens (allows overhead)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Expected improvements vs current config (450 tokens / 1,800 chars):
- 3.5× more chunks (better granularity)
- More precise retrieval
- Consistent 640-token context per result
- Better boundary coverage (25% vs 15%)
- No truncation (all chunks fit in 512 limit)
"""


