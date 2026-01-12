# Benchmark & Testing Tools

This directory contains all benchmark, testing, and diagnostic tools for the RAG system.

## 📊 Embedding & Performance Tests

### Token Limit Testing
- **`test_embeddinggemma_token_limits.py`** - Progressive token limit testing (400-2000 tokens)
- **`test_embedding_limits_simple.py`** - Simple binary search for max token limit
- **`test_true_concurrent_embedding.py`** - True concurrent request testing (requires aiohttp)

### Performance Monitoring
- **`monitor_embedding_performance.py`** - Real-time embedding performance monitoring
- **`diagnose_embedding_performance.py`** - Comprehensive performance diagnostics
- **`warm_embedding_cache.py`** - Pre-warm embedding cache for faster responses

### LLM Benchmarks
- **`groq_benchmark_temp.py`** - Groq LLM performance benchmarking
- **`llama_cli_test.py`** - Llama CLI interface testing
- **`llama_debug_test.py`** - Llama server debugging utilities
- **`rag_llama_test.py`** - RAG + Llama integration testing

## 🔍 Database & System Health

### Database Inspection
- **`inspect_rag_db.py`** - Comprehensive RAG database inspector
- **`show_vector_examples.py`** - Display vector database examples and statistics
- **`check_rag_health.py`** - RAG system health checker

### Data Quality
- **`find_corrupted_chunks.py`** - Find and report corrupted chunks in vector DB

### Quick Tests
- **`quick_test_expansion.py`** - Test context expansion functionality
- **`test.py`** - Empty test file for quick experiments

## 🚀 Usage Examples

### Test Token Limits
```bash
cd benchmark_tools
python test_embeddinggemma_token_limits.py
```

### Check Database Health
```bash
cd benchmark_tools  
python check_rag_health.py
```

### Inspect Vector Database
```bash
cd benchmark_tools
python inspect_rag_db.py
```

### Monitor Performance
```bash
cd benchmark_tools
python monitor_embedding_performance.py
```

## 📝 Notes

- All tools are designed to work with the current EmbeddingGemma-300M configuration
- Token limit tests reflect the server's `--batch-size` and `--ubatch-size` settings
- Performance tools help optimize embedding server configuration
- Database tools help maintain vector database integrity

## ⚠️ Requirements

Some tools may require additional dependencies:
- `test_true_concurrent_embedding.py` requires `aiohttp`
- Performance monitoring tools may require system monitoring libraries

Install missing dependencies as needed for your testing requirements.
