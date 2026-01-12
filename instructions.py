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

def get_combined_instructions() -> str:
    """Combine all instruction components into a single system message."""
    instructions = load_instructions()
    history = load_history()
    art_info = load_art_info()
    
    combined = instructions
    if history:
        combined += "\n\n=== CONVERSATION CONTEXT ===\n" + history
    if art_info:
        combined += "\n\n=== ART & VISUAL STYLE ===\n" + art_info
        
    return combined

# For direct import compatibility
BASE_INSTRUCTIONS = get_combined_instructions()
