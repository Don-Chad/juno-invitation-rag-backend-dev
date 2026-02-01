! Do not write manuals!
! I run the servers. never launch a server yourself. 



# RAG System Critical Rules

## Embedding Model (DO NOT CHANGE!)
- **Current Model**: EmbeddingGemma-300M-Q4_0 (unsloth/embeddinggemma-300m-GGUF)
- **Vector Dimensions**: 768
- **Model Path**: /home/mark/.cache/llama.cpp/embeddinggemma-300m-q4_0.gguf
- **NEVER** change the embedding model without explicit user approval and compatibility testing!
- **Vector DB rebuild required** after any model change (embeddings incompatible)

## Embedding Server Limits (TESTED - October 2025)
- **Server max per request**: 800 tokens (tested with --ubatch-size 1024)
- **Server batch-size**: 1024 tokens (total across ALL concurrent requests!)
- **Target chunk size**: 600 tokens (optimal balance)
- **Safe range**: 400-800 tokens tested and working
- **Concurrency**: Multiple requests supported (tested up to 5 concurrent at 512 tokens)
- **Current configuration**: 600 tokens for chunks
- **NEVER** change chunk size without testing with benchmark tools first 

## Chunk Size Philosophy
- **LARGE CHUNKS ARE VITAL** for quality retrieval
- Current optimal: 600 tokens (~2400 chars)
- Larger chunks = better context and retrieval quality
- Don't make chunks smaller to "fix" problems
- If server rejects, fix truncation/retry logic, NOT chunk size

## What Gets Embedded
- ✅ **YES**: Document chunk text (600 tokens, main RAG vectors)
- ✅ **YES**: Extended summaries (400-600 tokens, for document selection)
- ❌ **NO**: Short summaries (metadata only, not embedded)
- ❌ **NO**: Chunk metadata fields (stored with vectors, not embedded)
- ✅ **YES**: User queries (separate path with is_query=True)

## Summaries
- Short summary: 2-3 sentences (for quick reference)
- Extended summary: ~400 tokens / 1640 chars (for document overview and selection)
- **LLM generates 400 tokens max, hard limit 410 tokens in API call**
- **Extended summaries are embedded separately** (as their own vectors for document selection)
- **Extended summaries are added to RAG contexts** (once per document, before chunks)
- Summaries NOT included in chunk text (separate vectors)

## Error Handling
- 3 retry attempts with 85% truncation on each retry
- Clear error logging with token counts and text previews
- Never silently skip failed chunks
- Log: chunk index, filename, length, preview on failure

## Context Expansion
- Chunk embedded: 600 tokens
- Context expansion: 512 tokens before + 512 after = 1024 tokens
- Total context per result: ~1624 tokens
- Expansion happens at query time, NOT ingestion

## Config Hierarchy
- `/root/workerv14_grace_rag/rag_hq/config.py` - main RAG config
- All other configs should import from here
- Don't duplicate config values

## Testing Changes
- After config changes: `rm local_vector_db_enhanced/file_history.pkl`
- Re-ingest: `python ingest_documents.py`
- Check logs for "Server rejected" warnings
- Verify chunk counts match expected

## Performance Priorities
1. Quality retrieval (large chunks)
2. Fast query response (<100ms)
3. Memory efficiency (FP16 embeddings)
4. Cache hit rate (embeddings cache)
