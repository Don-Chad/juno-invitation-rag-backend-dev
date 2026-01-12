"""
RAG Orchestrator
Main entry point for automatic RAG enrichment
"""
from .chat_management import manage_rag_context_budget, print_chat_history_stats
from .query_handlers import query_qa_rag_only, query_chunk_rag_only, query_both_rags


def get_last_user_message(chat_ctx):
    """Get the full last user message (can be multiple sentences)"""
    # Get messages list - handle both regular ChatContext and read-only variants
    messages = getattr(chat_ctx, 'messages', None) or getattr(chat_ctx, 'items', None)
    if messages is None:
        return ""
    
    # Look for the last user message
    for msg in reversed(messages):
        if hasattr(msg, 'role') and msg.role == 'user':
            # Get message text - handle different content types
            if hasattr(msg, 'content'):
                content = msg.content
                if isinstance(content, list):
                    # Extract text from list of content items
                    msg_text = " ".join(str(item.get('text', '') if isinstance(item, dict) else item) for item in content)
                    return msg_text if msg_text else ""
                elif isinstance(content, str):
                    return content
                else:
                    return str(content) if content else ""
            elif hasattr(msg, 'text'):
                return msg.text if isinstance(msg.text, str) else str(msg.text)
    return ""


async def automatic_rag_enrichment(
    agent, chat_ctx,
    # RAG state
    rag_enabled, rag_mode, qa_rag_initialized, rag_initialized,
    # Query functions
    query_qa_rag_func, query_rag_func,
    # Config values
    rag_num_results, rag_context_budget_tokens, rag_rolling_budget,
    rag_debug_mode, rag_debug_print_full,
    document_server_enabled, document_server_base_url,
    # Helper functions
    estimate_tokens_func, rag_query_logger, llm_module, logger
):
    """Automatically enrich every user query with RAG context - supports multiple modes"""
    
    # First, manage RAG context budget (remove oldest if over limit)
    manage_rag_context_budget(
        chat_ctx, rag_rolling_budget, rag_context_budget_tokens,
        rag_debug_mode, estimate_tokens_func, logger
    )
    
    # Print chat history stats at the start of every request
    print_chat_history_stats(chat_ctx, estimate_tokens_func, label="[BEFORE RAG]")
    
    if not rag_enabled:
        logger.debug("RAG mechanism is disabled. Skipping automatic enrichment.")
        return

    # Get the full last user message
    last_user_message = get_last_user_message(chat_ctx)
    
    if not last_user_message or len(last_user_message.strip()) < 3:
        logger.debug("No meaningful user message found, skipping automatic RAG enrichment")
        return

    # Get user_id and conversation_id for logging
    user_id = getattr(agent, 'user_id', 'unknown')
    conversation_id = getattr(agent, 'room_name', None)

    # Log which RAG mode is being used
    logger.info(f"🔧 RAG MODE: {rag_mode.upper()}")
    
    # Create print_chat_history_stats wrapper
    def print_stats_wrapper(ctx, label=""):
        print_chat_history_stats(ctx, estimate_tokens_func, label)
    
    # Route to appropriate RAG function based on mode
    if rag_mode == "qa":
        await query_qa_rag_only(
            agent, chat_ctx, last_user_message, user_id, conversation_id,
            qa_rag_initialized, query_qa_rag_func, rag_num_results,
            document_server_enabled, document_server_base_url,
            rag_debug_mode, rag_debug_print_full,
            estimate_tokens_func, print_stats_wrapper,
            rag_query_logger, llm_module, logger
        )
    elif rag_mode == "chunk":
        await query_chunk_rag_only(
            agent, chat_ctx, last_user_message, user_id, conversation_id,
            rag_initialized, query_rag_func, rag_num_results,
            document_server_enabled, document_server_base_url,
            rag_debug_mode, rag_debug_print_full,
            estimate_tokens_func, print_stats_wrapper,
            rag_query_logger, llm_module, logger
        )
    elif rag_mode == "both":
        await query_both_rags(
            agent, chat_ctx, last_user_message, user_id, conversation_id,
            qa_rag_initialized, rag_initialized,
            query_qa_rag_func, query_rag_func, rag_num_results,
            rag_context_budget_tokens, rag_debug_mode, rag_debug_print_full,
            estimate_tokens_func, print_stats_wrapper,
            llm_module, logger
        )
    else:
        logger.error(f"Invalid RAG_MODE: {rag_mode}. Must be 'qa', 'chunk', or 'both'")

