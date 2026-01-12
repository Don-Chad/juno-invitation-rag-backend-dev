# LiveKit RAG Voice Assistant - The Invitation Bot

A sophisticated voice assistant system powered by LiveKit, featuring a high-performance RAG (Retrieval Augmented Generation) system for context-aware conversations about "The Invitation" and related topics.

## Overview

This project combines real-time voice communication with advanced document retrieval to create an intelligent conversational AI assistant. The system uses a modular RAG architecture optimized for voice interactions.

## Key Features

- **Real-time Voice Interaction**: Built on LiveKit for low-latency voice communication
- **Advanced RAG System**: High-performance document retrieval with 600-token chunks
- **Modular Architecture**: Clean separation of concerns with sub-500 line modules
- **Optimized Embeddings**: Uses EmbeddingGemma-300M (768 dimensions) with FP16 optimization
- **Context Expansion**: Smart context expansion (512 tokens before/after) for better retrieval
- **Extended Summaries**: Document-level summaries for improved document selection
- **Concurrent Processing**: Async/await throughout with connection pooling
- **Memory Efficient**: Lazy loading, LRU caching, and memory-mapped indices

## System Architecture

### RAG System (`rag_hq/`)

The core RAG system is organized into focused modules:

- `config.py` - Configuration and constants
- `state.py` - Global state management with thread safety
- `embeddings.py` - Embedding creation via llama-server
- `text_processing.py` - Document extraction and chunking
- `vector_index.py` - Enhanced Annoy index wrapper
- `database.py` - Document ingestion pipeline
- `query.py` - RAG query and context enrichment
- `initialization.py` - System initialization and cleanup

### Custom Components (`custom_components/`)

- `rag_worker/` - RAG orchestration for voice assistant
  - `rag_orchestrator.py` - Main RAG coordination
  - `query_handlers.py` - Query processing
  - `context_builders.py` - Context assembly
  - `chat_management.py` - Chat history management
  - `message_helpers.py` - Message formatting
  - `logging_helpers.py` - Logging utilities

### Voice Assistant Frontend (`voice-assistant-frontend/`)

Web-based interface for voice interactions with the assistant.

## RAG System Configuration

### Embedding Model (Critical!)

- **Model**: EmbeddingGemma-300M-Q4_0 (unsloth/embeddinggemma-300m-GGUF)
- **Dimensions**: 768
- **Path**: `/home/mark/.cache/llama.cpp/embeddinggemma-300m-q4_0.gguf`
- **Server Limits**: 800 tokens max per request (tested with --ubatch-size 1024)

⚠️ **Never change the embedding model without explicit approval and compatibility testing!**

### Chunk Configuration

- **Target Chunk Size**: 600 tokens (~2400 chars)
- **Safe Range**: 400-800 tokens (tested and working)
- **Context Expansion**: 512 tokens before + 512 after = 1024 tokens total
- **Philosophy**: Large chunks are vital for quality retrieval

### What Gets Embedded

- ✅ Document chunk text (600 tokens)
- ✅ Extended summaries (400-600 tokens for document selection)
- ✅ User queries (separate path with is_query=True)
- ❌ Short summaries (metadata only)
- ❌ Chunk metadata fields

## Usage

### Building the RAG Database

```bash
# Full rebuild
python rebuild_rag_database.py

# Incremental ingestion
python rag_general/ingest_documents.py
```

### Testing the RAG System

```bash
# Run RAG module tests
python -m rag_hq

# Test embedding server
python test_embed_server.py

# Benchmark tools
python benchmark_tools/test_embedding_latency.py
python benchmark_tools/diagnose_embedding_performance.py
```

### Integration Example

```python
import asyncio
from rag_hq import initialize_rag, query_rag, cleanup_rag

async def main():
    # Initialize
    await initialize_rag()
    
    # Query
    results = await query_rag("What is The Invitation about?", num_results=5)
    print(results)
    
    # Cleanup
    await cleanup_rag()

asyncio.run(main())
```

## Directory Structure

```
.
├── rag_hq/                    # Core RAG system
├── rag_general/               # General RAG utilities
├── rag_qa/                    # Q&A specific RAG
├── custom_components/         # Voice assistant components
│   └── rag_worker/           # RAG orchestration
├── voice-assistant-frontend/  # Web frontend
├── agents/                    # LiveKit agents
├── benchmark_tools/           # Performance testing
├── tools/                     # Utility scripts
├── docs/                      # Documents for RAG (PDFs, etc.)
├── rebuild_rag_database.py   # Database rebuild script
└── test_embed_server.py      # Embedding server test
```

## Performance

- **Embedding Creation**: ~50-100ms per chunk
- **Vector Search**: ~5-20ms
- **Document Processing**: ~1-5 seconds per document
- **Memory Usage**: ~200-500MB (depending on index size)
- **Query Response**: <100ms target

## Error Handling

- 3 retry attempts with 85% truncation on each retry
- Clear error logging with token counts and text previews
- Never silently skip failed chunks
- Atomic file operations with backup/rollback

## Configuration Hierarchy

Main config: `/rag_hq/config.py`

All other configs should import from here to avoid duplication.

## Testing Changes

After config changes:
1. Remove file history: `rm local_vector_db_enhanced/file_history.pkl`
2. Re-ingest: `python rag_general/ingest_documents.py`
3. Check logs for "Server rejected" warnings
4. Verify chunk counts match expected

## Troubleshooting

### Llama-server not responding
Check if the embedding server is running on port 7777

### Out of memory
Reduce batch sizes in `rag_hq/config.py`:
- `BATCH_SIZE_FILES`
- `BATCH_SIZE_CHUNKS`
- `DOCUMENT_TEXT_CACHE_MAX_SIZE`

### Database corruption
The system maintains backups:
- `local_vector_db_enhanced/vdb_data.backup`
- `local_vector_db_enhanced/metadata.pkl.backup`

## Documentation

- `rag_hq/README.md` - RAG system architecture
- `rag_hq/USAGE_GUIDE.md` - Detailed usage guide
- `bobbie_instructions.txt` - System instructions for the assistant

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]

