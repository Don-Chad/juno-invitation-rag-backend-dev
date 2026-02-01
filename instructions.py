"""
Hot-reloadable system instructions for the agent.
Reads from invitation_instructions.txt, conversation_history.txt, and art_info.txt.
"""

import os
import logging

logger = logging.getLogger("instructions")

def load_file_content(filename: str, default_text: str = "") -> str:
    """Load content from a text file with hot-reloading."""
    path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(path):
        return default_text
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        logger.error(f"Error reading {filename}: {e}")
        return default_text

def load_instructions() -> str:
    """Load main system instructions."""
    return load_file_content("invitation_instructions.txt", "You are a helpful AI assistant.")

def load_history() -> str:
    """Load additional conversation context/history."""
    return load_file_content("conversation_history.txt", "")

def load_art_info() -> str:
    """Load art and visual information."""
    return load_file_content("art_info.txt", "")

def get_combined_instructions(user_id: str = None) -> str:
    """Combine all instruction components into a single system message."""
    instructions = load_instructions()
    history = load_history()
    art_info = load_art_info()
    
    combined = instructions
    
    # Load and append user memories if user_id is provided
    if user_id:
        try:
            from custom_components.firebase_user_manager import get_firebase_manager
            import asyncio
            
            # Since this is a sync function called in various places, we use a small trick
            # to run the async load_memories in a sync way if needed, or better, 
            # we just accept that memories might be injected elsewhere if this is too complex.
            # However, for LiveKit agents, we usually want this to be fast.
            
            # For now, let's assume we want to inject them here.
            # We'll use a sync wrapper or just log that we're loading them.
            mgr = get_firebase_manager()
            # Note: Firestore doc.get() is actually sync in the firebase_admin SDK!
            # Our firebase_user_manager.load_memories is async but it calls sync db.get()
            
            doc = mgr.db.collection('users').document(user_id).get()
            if doc.exists:
                memories = doc.to_dict().get('memories', [])
                if memories:
                    memory_text = "\n".join([f"- {m}" for m in memories])
                    combined += "\n\n=== USER MEMORIES (LONG-TERM) ===\n"
                    combined += "The following are facts you've remembered about the user from previous sessions. Use them to provide a personalized experience:\n"
                    combined += memory_text
        except Exception as e:
            logger.error(f"Error loading memories in instructions: {e}")

    if history:
        combined += "\n\n=== CONVERSATION CONTEXT ===\n" + history
    if art_info:
        combined += "\n\n=== ART & VISUAL STYLE ===\n" + art_info
        
    return combined

# For direct import compatibility
BASE_INSTRUCTIONS = get_combined_instructions()
