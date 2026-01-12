"""
RAG Message Helper Functions
Handles insertion of RAG messages into chat context
"""
import time
from livekit.agents.llm import ChatMessage


def insert_rag_message(chat_ctx, context_text, llm_module):
    """Create and insert a RAG message into chat context as assistant message.
    
    Inserts RAG context right BEFORE the last user message to ensure:
    - System message (top)
    - RAG context (middle) 
    - User question (bottom - always last)
    """
    # Create ChatMessage directly (it's a Pydantic BaseModel, not a factory)
    rag_msg = ChatMessage(role="assistant", content=[context_text])
    rag_msg._is_rag_context = True
    rag_msg._rag_timestamp = time.time()
    
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
    
    # Try to insert, handle read-only contexts
    if hasattr(messages, 'insert'):
        messages.insert(insert_idx, rag_msg)
    elif hasattr(chat_ctx, 'append'):
        # Fallback: use append method if available (but this won't preserve order)
        chat_ctx.append(text=context_text, role="assistant")
    
    return insert_idx

