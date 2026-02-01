"""
RAG Message Helper Functions
Handles insertion of RAG messages into chat context
"""
import time
from livekit.agents import llm


def insert_rag_message(chat_ctx, context_text, llm_module):
    """Create and insert a RAG message into chat context as assistant message.
    
    Inserts RAG context right BEFORE the last user message to ensure:
    - System message (top)
    - RAG context (middle) 
    - User question (bottom - always last)
    """
    # Use ChatContext.add_message if it's available, otherwise fallback to direct insertion
    if hasattr(chat_ctx, 'add_message'):
        # Note: add_message appends to the end. Since we want to insert, 
        # we might need to handle this differently if order matters.
        # However, ChatContext.insert is available in this environment.
        rag_msg = llm.ChatMessage(role="assistant", content=[context_text])
        try:
            rag_msg._is_rag_context = True
            rag_msg._rag_timestamp = time.time()
        except Exception:
            pass
        
        # We'll use the items.insert logic below which is more precise
    else:
        # Fallback for other environments
        rag_msg = llm.ChatMessage.create(role="assistant", text=context_text)
    
    # Get messages list - handle both regular ChatContext and read-only variants
    messages = getattr(chat_ctx, 'messages', None) or getattr(chat_ctx, 'items', None)
    if messages is None:
        return 0
    
    # Find the last user message index (user question should always be at bottom)
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if hasattr(msg, 'role') and msg.role == 'user':
            last_user_idx = i
            break
    
    # Determine insertion point:
    # - If user message exists: insert right before it (so user stays at bottom)
    # - Otherwise: insert after system message (if exists) or at beginning
    if last_user_idx is not None:
        insert_idx = last_user_idx  # Insert right before user message
    else:
        # No user message found, insert after system message
        insert_idx = 0
        for i, msg in enumerate(messages):
            if hasattr(msg, 'role') and msg.role == 'system':
                insert_idx = i + 1
                break
    
    # Insert into messages list (ChatContext.messages is always mutable)
    if hasattr(messages, 'insert'):
        messages.insert(insert_idx, rag_msg)
    
    return insert_idx

