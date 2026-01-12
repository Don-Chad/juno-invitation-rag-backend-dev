# RAG HQ Enhanced - Modular RAG System

A high-performance, modular Retrieval Augmented Generation (RAG) system designed for voice assistants and document search.

## Architecture

The system is organized into logical modules, each under 500 lines:

### Core Modules

1. **config.py** (~100 lines)
   - Configuration constants
   - Path definitions
   - Tuning parameters

2. **state.py** (~100 lines)
   - Global state management
   - Document text lazy loading
   - Thread-safe state operations

3. **vector_index.py** (~200 lines)
   - Enhanced Annoy index wrapper
   - UUID mapping
   - Async query operations
   - Index validation

4. **embeddings.py** (~300 lines)
   - Embedding creation via llama-server
   - HTTP session management
   - Caching layer
   - Retry logic

5. **text_processing.py** (~300 lines)
   - PDF, DOCX, TXT extraction
   - Smart text chunking
   - Sentence segmentation with spaCy
   - Deduplication

6. **document_management.py** (~150 lines)
   - Document summarization via Groq
   - Metadata storage
   - Ingestion reporting

7. **database.py** (~400 lines)
   - File processing pipeline
   - Chunk processing
   - Hash-based change detection
   - Database saving (after each document!)

8. **database_operations.py** (~200 lines)
   - Database building
   - Database loading
   - Periodic update task

9. **query.py** (~350 lines)
   - RAG context enrichment
   - Similarity search
   - Context expansion
   - Result formatting

10. **initialization.py** (~150 lines)
    - Module initialization
    - Cleanup routines
    - Memory diagnostics

11. **__init__.py** (~50 lines)
    - Package exports
    - Public API

## Key Features

### Automatic Saving
**Important**: The database is now saved after **every successfully ingested document**. This ensures:
- No data loss if the process is interrupted
- Incremental updates without full rebuilds
- Immediate availability of newly indexed documents

### Memory Optimization
- FP16 embeddings (50% memory reduction)
- Lazy document text loading (LRU cache)
- Memory-mapped Annoy index
- Periodic cache saves

### Performance
- Async/await throughout
- Connection pooling
- Batched processing
- Semaphore-based rate limiting
- Priority queue for real-time queries

### Robustness
- Atomic file operations
- Backup and rollback
- Comprehensive error handling
- Validation checks

## Usage

### Basic Usage

```python
import asyncio
from rag_hq import initialize_rag, query_rag, cleanup_rag

async def main():
    # Initialize the RAG system
    await initialize_rag()
    
    # Query the database
    results = await query_rag("What is in the documents?", num_results=5)
    print(results)
    
    # Cleanup
    await cleanup_rag()

asyncio.run(main())
```

### Integration with LiveKit Agent

```python
from rag_hq import initialize_rag, enrich_with_rag
from livekit.agents import llm

# In your agent initialization
await initialize_rag()

# In your chat handler
async def handle_chat(agent, chat_ctx: llm.ChatContext):
    # Enrich context with RAG
    await enrich_with_rag(agent, chat_ctx)
    # Continue with normal agent processing
```

## Configuration

Edit `config.py` to customize:
- Chunk sizes and overlap
- Embedding server URL
- Similarity thresholds
- Cache settings
- Batch sizes

## File Structure

```
rag_hq/
├── __init__.py           # Package exports
├── __main__.py           # Test runner
├── config.py             # Configuration
├── state.py              # Global state
├── vector_index.py       # Annoy index wrapper
├── embeddings.py         # Embedding creation
├── text_processing.py    # Text extraction & chunking
├── document_management.py # Summaries & metadata
├── database.py           # File & chunk processing
├── database_operations.py # Build/load operations
├── query.py              # Query & enrichment
└── initialization.py     # Init & cleanup
```

## Migration from Old Module

To migrate from `rag_module_hq_enhanced.py`:

1. Update imports:
   ```python
   # Old
   from rag_module_hq_enhanced import initialize_rag, query_rag
   
   # New
   from rag_hq import initialize_rag, query_rag
   ```

2. The API remains the same, so no code changes needed!

## Testing

Run the module directly to test:

```bash
cd /root/workerv12_grace
python -m rag_hq
```

## Performance Metrics

- Embedding creation: ~50-100ms per chunk
- Vector search: ~5-20ms
- Document processing: ~1-5 seconds per document (depending on size)
- Memory usage: ~200-500MB (depending on index size)

## Troubleshooting

### Llama-server not responding
Ensure the llama-server is running on port 7777:
```bash
systemctl status llama-server.service
```

### Out of memory
Reduce batch sizes in `config.py`:
- `BATCH_SIZE_FILES`
- `BATCH_SIZE_CHUNKS`
- `DOCUMENT_TEXT_CACHE_MAX_SIZE`

### Database corruption
The system maintains backups. Check:
- `local_vector_db_enhanced/vdb_data.backup`
- `local_vector_db_enhanced/metadata.pkl.backup`
