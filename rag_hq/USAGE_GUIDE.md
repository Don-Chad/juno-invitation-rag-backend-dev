# RAG HQ Enhanced - Usage Guide

## Quick Start

### 1. Check System Health

Before starting, verify everything is working:

```bash
# Quick check (essentials only)
python -m rag_hq --health --quick

# Full health check (recommended)
python -m rag_hq --health

# Or use the standalone script
python check_rag_health.py
python check_rag_health.py --quick
python check_rag_health.py --output health_report.json
```

### 2. Test RAG Module

```bash
# Run the module in test mode
python -m rag_hq
```

### 3. Use in Your Agent

```python
from rag_hq import ensure_rag_initialized, enrich_with_rag, query_rag

# Initialize RAG (call once at startup)
await ensure_rag_initialized()

# Use in your chat handler
async def handle_chat(agent, chat_ctx):
    await enrich_with_rag(agent, chat_ctx)
    # Continue with your agent logic...

# Or query directly
results = await query_rag("What is in the documents?", num_results=5)
```

## Understanding the Logs

### Startup Logs

When RAG initializes, you'll see:

```
🔍 RAG | 10:30:15 | INFO | ============================================================
🔍 RAG | 10:30:15 | INFO | INITIALIZING ENHANCED RAG MODULE
🔍 RAG | 10:30:15 | INFO | ============================================================
🔍 RAG | 10:30:15 | INFO | This will load documents and prepare the vector database...
```

### Database Status

If database exists:
```
🔍 RAG | 10:30:16 | INFO | ✓ Found existing database - loading...
🔍 RAG | 10:30:16 | INFO | ✓ Successfully loaded vector database:
🔍 RAG | 10:30:16 | INFO |   - 1,234 vectors in index
🔍 RAG | 10:30:16 | INFO |   - 1,234 chunks with metadata
```

If no database found:
```
🔍 RAG | 10:30:16 | WARNING | ============================================================
🔍 RAG | 10:30:16 | WARNING | ⚠️  NO EXISTING DATABASE FOUND
🔍 RAG | 10:30:16 | WARNING | ============================================================
🔍 RAG | 10:30:16 | WARNING | Database files missing:
🔍 RAG | 10:30:16 | WARNING |   ✗ Vector DB: local_vector_db_enhanced/vdb_data
🔍 RAG | 10:30:16 | INFO | Starting fresh database build from documents...
```

### Database Statistics at Startup

```
🔍 RAG | 10:30:17 | INFO | ============================================================
🔍 RAG | 10:30:17 | INFO | DATABASE STATISTICS
🔍 RAG | 10:30:17 | INFO | ============================================================
🔍 RAG | 10:30:17 | INFO | 📊 Annoy Index:
🔍 RAG | 10:30:17 | INFO |    - Total vectors: 1,234
🔍 RAG | 10:30:17 | INFO |    - Vector dimension: 1024
🔍 RAG | 10:30:17 | INFO | 📦 Chunks Metadata:
🔍 RAG | 10:30:17 | INFO |    - Total chunks: 1,234
🔍 RAG | 10:30:17 | INFO | 📄 Documents:
🔍 RAG | 10:30:17 | INFO |    - Unique documents: 15
🔍 RAG | 10:30:17 | INFO |    - Processed files tracked: 15
🔍 RAG | 10:30:17 | INFO | 📝 Document Summaries: 15
🔍 RAG | 10:30:17 | INFO | 💾 Embeddings Cache:
🔍 RAG | 10:30:17 | INFO |    - Cached embeddings: 456
🔍 RAG | 10:30:17 | INFO |    - Cache size: 0.89 MB
🔍 RAG | 10:30:17 | INFO | ============================================================
🔍 RAG | 10:30:17 | INFO | 💡 Total memory increase: 123.45 MB
🔍 RAG | 10:30:17 | INFO | ============================================================
🔍 RAG | 10:30:17 | INFO | ✅ RAG MODULE FULLY OPERATIONAL
🔍 RAG | 10:30:17 | INFO | ============================================================
```

### Document Ingestion Logs

When processing documents:

```
🔍 RAG | 10:30:20 | INFO | ⟳ Found 3 new or modified files to process
🔍 RAG | 10:30:20 | INFO | 📄   1. document1.pdf
🔍 RAG | 10:30:20 | INFO | 📄   2. document2.pdf
🔍 RAG | 10:30:20 | INFO | 📄   3. document3.docx
🔍 RAG | 10:30:21 | INFO | 📄 [1/3] Processing: document1.pdf
🔍 RAG | 10:30:22 | INFO | 📦 [1/3] Generated 45 chunks from document1.pdf
🔍 RAG | 10:30:23 | INFO | ⟳ [1/3] document1.pdf: 45/45 chunks (100%)
🔍 RAG | 10:30:24 | INFO | Saving database after processing document1.pdf...
🔍 RAG | 10:30:24 | INFO | Database saved: 45 vectors, 45 chunks
🔍 RAG | 10:30:24 | INFO | ✓ [1/3] Completed document1.pdf: 45 chunks (0 failed)
```

### Query Logs

When performing queries:

```
🔍 RAG | 10:35:10 | INFO | Starting search query...
🔍 RAG | 10:35:10 | INFO | Search query completed.
🔍 RAG | 10:35:10 | INFO | Time to search: 15.23 ms
🔍 RAG | 10:35:10 | INFO | Added context from document1.pdf (similarity: 0.823)
🔍 RAG | 10:35:10 | INFO | Total RAG operation time: 65.45 ms, context added: True
```

## Health Check Output

### Quick Check
```bash
$ python -m rag_hq --health --quick
🏥 Running quick RAG health check...
🔍 RAG | 10:40:00 | INFO | ✓ Llama Server: Server is responding at http://localhost:7777
🔍 RAG | 10:40:00 | INFO | ✓ RAG State: RAG is enabled and operational
🔍 RAG | 10:40:00 | INFO | ✓ RAG system is operational
```

### Full Health Check
```bash
$ python -m rag_hq --health
🔍 RAG | 10:41:00 | INFO | ============================================================
🔍 RAG | 10:41:00 | INFO | 🏥 RUNNING RAG HEALTH DIAGNOSTICS
🔍 RAG | 10:41:00 | INFO | ============================================================
🔍 RAG | 10:41:00 | INFO | ✓ Llama Server: Server is responding at http://localhost:7777
🔍 RAG | 10:41:00 | INFO | ✓ Database File: Vector DB: File exists (12.34 MB)
🔍 RAG | 10:41:00 | INFO | ✓ Database File: Vector DB Map: File exists (0.05 MB)
🔍 RAG | 10:41:00 | INFO | ✓ Database File: Metadata: File exists (3.45 MB)
🔍 RAG | 10:41:00 | INFO | ✓ Embeddings Cache: Cache file exists (0.89 MB)
🔍 RAG | 10:41:00 | INFO | ✓ Uploads Folder: Found 15 document(s) in uploads
🔍 RAG | 10:41:00 | INFO | ✓ RAG State: RAG is enabled and operational
🔍 RAG | 10:41:00 | INFO | ✓ Annoy Index: Index loaded with 1,234 vectors
🔍 RAG | 10:41:00 | INFO | ✓ Chunks Metadata: Loaded 1,234 chunk(s) metadata
🔍 RAG | 10:41:00 | INFO | ✓ Memory Usage: Memory usage is normal: 345.67 MB
🔍 RAG | 10:41:00 | INFO | ============================================================
🔍 RAG | 10:41:00 | INFO | 📊 HEALTH CHECK SUMMARY
🔍 RAG | 10:41:00 | INFO | ============================================================
🔍 RAG | 10:41:00 | INFO | ✓ Passed:   12
🔍 RAG | 10:41:00 | INFO | ✗ Failed:   0
🔍 RAG | 10:41:00 | INFO | ⚠️  Warnings: 0
🔍 RAG | 10:41:00 | INFO | Overall Status: HEALTHY
🔍 RAG | 10:41:00 | INFO | ============================================================
```

## Understanding EAGER vs LAZY Mode

### EAGER MODE (Current - Recommended)
- RAG initializes **immediately** when `ensure_rag_initialized()` is called
- Database loads right away at agent startup
- Documents are processed even before first conversation
- **Benefit**: Ready to answer questions instantly
- **Used by default now**

### LAZY MODE (Old behavior)
- RAG only initializes when first query arrives
- First user has to wait for initialization
- Documents process on-demand
- **Downside**: Slow first response

**Current Status**: You're using **EAGER MODE** - RAG is always ready!

## Troubleshooting

### Problem: "NO EXISTING DATABASE FOUND"
**Solution**: Normal on first run. RAG will build from documents in `./docs/`

### Problem: "llama-server is not accessible"
**Solution**: 
```bash
# Check if server is running
systemctl status llama-server.service

# Restart if needed
systemctl restart llama-server.service
```

### Problem: High memory usage warning
**Solution**: Reduce cache sizes in `config.py`:
- `DOCUMENT_TEXT_CACHE_MAX_SIZE = 3`  (was 5)
- `BATCH_SIZE_CHUNKS = 1`  (was 2)

### Problem: No documents being processed
**Solution**: 
1. Check `./docs/` folder exists and has files
2. Check permissions: `ls -la ./docs/`
3. Run health check: `python -m rag_hq --health`

## Integration Example

```python
# In your agent_dev.py

from rag_hq import (
    ensure_rag_initialized, 
    enrich_with_rag, 
    query_rag,
    run_health_check
)

# At startup (before agent creation)
async def startup():
    # Initialize RAG eagerly
    await ensure_rag_initialized()
    
    # Optional: Run health check
    health = await run_health_check()
    if health['overall_status'] != 'healthy':
        logger.warning("RAG system is not fully healthy")

# In your entrypoint function
async def entrypoint(ctx: JobContext):
    # RAG is already initialized, just use it
    
    async def handle_user_message(agent, chat_ctx):
        # Enrich with RAG context
        await enrich_with_rag(agent, chat_ctx)
        # Agent will now have document context!
```

## Command Reference

```bash
# Test RAG module
python -m rag_hq

# Health checks
python -m rag_hq --health              # Full check
python -m rag_hq --health --quick      # Quick check
python check_rag_health.py             # Standalone full check
python check_rag_health.py --quick     # Standalone quick check
python check_rag_health.py -o report.json  # Save to file

# Run health check from Python
from rag_hq import run_health_check, quick_check
await run_health_check()  # Full
await quick_check()       # Quick
```
