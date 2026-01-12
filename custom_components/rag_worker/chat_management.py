"""
RAG Chat Management Functions
Handles chat history statistics and RAG context budget management
"""


def print_chat_history_stats(chat_ctx, estimate_tokens_func, label=""):
    """Print detailed statistics about chat history size and token usage."""
    # Get messages list - handle both regular ChatContext and read-only variants
    messages = getattr(chat_ctx, 'messages', None) or getattr(chat_ctx, 'items', None)
    if messages is None:
        # print("Could not access messages from chat context")
        return
    
    total_messages = len(messages)
    total_chars = 0
    total_tokens = 0
    
    # Count by role
    role_counts = {}
    role_tokens = {}
    
    # Track special message types
    rag_messages = 0
    rag_tokens = 0
    extensive_search_messages = 0
    extensive_search_tokens = 0
    
    for msg in messages:
        role = getattr(msg, 'role', 'unknown')
        
        # Get message text - handle different content types
        msg_text = ""
        if hasattr(msg, 'content'):
            content = msg.content
            # Handle content as list or string
            if isinstance(content, list):
                # Extract text from list of content items
                msg_text = " ".join(str(item.get('text', '') if isinstance(item, dict) else item) for item in content)
            elif isinstance(content, str):
                msg_text = content
            else:
                msg_text = str(content) if content else ""
        elif hasattr(msg, 'text'):
            msg_text = msg.text if isinstance(msg.text, str) else str(msg.text)
        
        # Ensure msg_text is a string
        if not isinstance(msg_text, str):
            msg_text = str(msg_text) if msg_text else ""
        
        msg_chars = len(msg_text)
        msg_tokens = estimate_tokens_func(msg_text)
        
        total_chars += msg_chars
        total_tokens += msg_tokens
        
        # Count by role
        role_counts[role] = role_counts.get(role, 0) + 1
        role_tokens[role] = role_tokens.get(role, 0) + msg_tokens
        
        # Check for special message types
        if getattr(msg, '_is_rag_context', False):
            rag_messages += 1
            rag_tokens += msg_tokens
        
        if getattr(msg, '_is_extensive_search_context', False):
            extensive_search_messages += 1
            extensive_search_tokens += msg_tokens
    
    # Print comprehensive stats
    # print("=" * 80)
    # print(f"📊 CHAT HISTORY STATS {label}")
    # print("=" * 80)
    # print(f"Total messages: {total_messages}")
    # print(f"Total characters: {total_chars:,}")
    # print(f"Total tokens (estimated): {total_tokens:,}")
    # print(f"\nBreakdown by role:")
    # for role, count in sorted(role_counts.items()):
    #     tokens = role_tokens.get(role, 0)
    #     print(f"  {role:12s}: {count:3d} messages, {tokens:6,} tokens")
    
    # if rag_messages > 0:
    #     print(f"\nRAG Context:")
    #     print(f"  Messages: {rag_messages}")
    #     print(f"  Tokens: {rag_tokens:,}")
    #     print(f"  % of total: {(rag_tokens / total_tokens * 100):.1f}%")
    
    # if extensive_search_messages > 0:
    #     print(f"\nExtensive Search Context:")
    #     print(f"  Messages: {extensive_search_messages}")
    #     print(f"  Tokens: {extensive_search_tokens:,}")
    #     print(f"  % of total: {(extensive_search_tokens / total_tokens * 100):.1f}%")
    
    # print("=" * 80)
    # print("")


def manage_rag_context_budget(chat_ctx, rag_rolling_budget, rag_context_budget_tokens, rag_debug_mode, estimate_tokens_func, logger):
    """Manage RAG context with a rolling token budget.
    
    Keeps RAG context in history but removes oldest RAG messages when budget is exceeded.
    This allows the LLM to maintain awareness of what information was provided.
    """
    if not rag_rolling_budget:
        return  # Budget management disabled
    
    # Get messages list - handle both regular ChatContext and read-only variants
    messages = getattr(chat_ctx, 'messages', None) or getattr(chat_ctx, 'items', None)
    if messages is None:
        logger.warning("Could not access messages from chat context")
        return
    
    # Count tokens in RAG messages
    rag_messages = []
    rag_token_count = 0
    
    for msg in messages:
        is_rag = getattr(msg, '_is_rag_context', False)
        if is_rag:
            # Get message text - handle different content types
            msg_text = ""
            if hasattr(msg, 'content'):
                content = msg.content
                if isinstance(content, list):
                    msg_text = " ".join(str(item.get('text', '') if isinstance(item, dict) else item) for item in content)
                elif isinstance(content, str):
                    msg_text = content
                else:
                    msg_text = str(content) if content else ""
            elif hasattr(msg, 'text'):
                msg_text = msg.text if isinstance(msg.text, str) else str(msg.text)
            
            # Ensure msg_text is a string
            if not isinstance(msg_text, str):
                msg_text = str(msg_text) if msg_text else ""
            
            msg_tokens = estimate_tokens_func(msg_text)
            rag_messages.append((msg, msg_tokens, getattr(msg, '_rag_timestamp', 0)))
            rag_token_count += msg_tokens
    
    # If we're over budget, remove oldest RAG messages
    if rag_token_count > rag_context_budget_tokens:
        # Sort by timestamp (oldest first)
        rag_messages.sort(key=lambda x: x[2])
        
        removed_count = 0
        tokens_to_remove = rag_token_count - rag_context_budget_tokens
        tokens_removed = 0
        
        messages_to_remove = set()
        for msg, msg_tokens, timestamp in rag_messages:
            if tokens_removed >= tokens_to_remove:
                break
            messages_to_remove.add(id(msg))
            tokens_removed += msg_tokens
            removed_count += 1
        
        # Filter out messages to remove
        filtered_messages = [msg for msg in messages if id(msg) not in messages_to_remove]
        
        # Update messages - handle read-only contexts
        if hasattr(messages, 'clear'):
            messages.clear()
            messages.extend(filtered_messages)
        else:
            logger.warning("Cannot modify messages - chat context is read-only")
        
        if rag_debug_mode:
            logger.info(f"🗑️  RAG BUDGET: Removed {removed_count} oldest RAG message(s) (~{tokens_removed} tokens)")
            logger.info(f"   RAG budget: {rag_token_count - tokens_removed:,} / {rag_context_budget_tokens:,} tokens")
            logger.info(f"   Chat history now has {len(messages)} messages")

