"""
RAG Logging Helper Functions
Handles debug logging for Q&A RAG, chunk RAG, and combined RAG modes
"""

def log_qa_debug(qa_pairs, context_text, token_count, rag_debug_print_full, logger):
    """Log debug information for Q&A RAG"""
    logger.info("=" * 80)
    logger.info("🎯 Q&A RAG DEBUG: Adding Q&A context to conversation")
    logger.info("=" * 80)
    logger.info(f"Q&A pairs: {len(qa_pairs)}")
    for qa in qa_pairs:
        logger.info(f"  📌 Q: {qa['question'][:100]}...")
        logger.info(f"     A: {qa['answer'][:100]}...")
        logger.info(f"     Source: {qa.get('source', 'Unknown')} (page {qa.get('page', 'N/A')})")
        logger.info(f"     Similarity: {qa.get('similarity', 0):.3f}")
    logger.info(f"Context length: {len(context_text)} chars, ~{token_count} tokens")
    
    if rag_debug_print_full:
        logger.info("\n📄 FULL Q&A RAG CONTEXT:")
        logger.info("-" * 80)
        logger.info(context_text)
        logger.info("-" * 80)
    logger.info("=" * 80)


def log_chunk_debug(docs, context_text, token_count, rag_debug_print_full, logger):
    """Log debug information for chunk RAG"""
    logger.info("=" * 60)
    logger.info("📄 Chunk RAG DEBUG: Adding context to conversation")
    logger.info("=" * 60)
    logger.info(f"Documents: {len(docs)}")
    for doc in docs:
        logger.info(f"  - {doc.get('source', 'Unknown')}")
    logger.info(f"Context length: {len(context_text)} chars, ~{token_count} tokens")
    
    if rag_debug_print_full:
        logger.info("\n📄 FULL CHUNK RAG CONTEXT:")
        logger.info("-" * 60)
        logger.info(context_text)
        logger.info("-" * 60)
    logger.info("=" * 60)


def log_qa_timing(timing_info, search_time, logger):
    """Log timing breakdown for Q&A RAG"""
    if timing_info:
        logger.info(f"⏱️  Q&A RAG Timing Breakdown:")
        logger.info(f"   • Embedding generation: {timing_info.get('embedding_ms', 0):.2f} ms")
        logger.info(f"   • Similarity calculation: {timing_info.get('similarity_calc_ms', 0):.2f} ms ({timing_info.get('qa_pairs_searched', 0)} pairs)")
        logger.info(f"   • Sort & filter: {timing_info.get('sort_filter_ms', 0):.2f} ms")
        logger.info(f"   • Total Q&A RAG: {timing_info.get('total_ms', 0):.2f} ms")
        logger.info(f"   • With timeout overhead: {search_time:.2f} ms")
    else:
        logger.info(f"Q&A RAG search time: {search_time:.2f} ms")


def log_both_rag_debug(combined_context, total_tokens, rag_context_budget_tokens, rag_debug_print_full, logger):
    """Log debug information for both RAG mode"""
    logger.info("=" * 80)
    logger.info("🔄 BOTH RAG DEBUG: Adding combined context")
    logger.info("=" * 80)
    logger.info(f"Total context: ~{total_tokens} / {rag_context_budget_tokens} tokens")
    
    if rag_debug_print_full:
        logger.info("\n📄 FULL COMBINED CONTEXT:")
        logger.info("-" * 80)
        logger.info(combined_context)
        logger.info("-" * 80)
    logger.info("=" * 80)

