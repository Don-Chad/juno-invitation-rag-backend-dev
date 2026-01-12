"""
Token counting utilities for context window management.
"""
import logging
from typing import List, Tuple

logger = logging.getLogger("rag-assistant-enhanced")

# Approximate token counting (4 chars per token is typical for English)
CHARS_PER_TOKEN = 4


def count_tokens(text: str) -> int:
    """
    Estimate token count from text length.
    This is approximate but fast. For production, consider using tiktoken.
    
    Args:
        text: Input text
        
    Returns:
        Estimated token count
    """
    return len(text) // CHARS_PER_TOKEN


def count_tokens_batch(texts: List[str]) -> List[int]:
    """
    Count tokens for multiple texts.
    
    Args:
        texts: List of input texts
        
    Returns:
        List of token counts
    """
    return [count_tokens(text) for text in texts]


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """
    Truncate text to fit within token limit.
    
    Args:
        text: Input text
        max_tokens: Maximum number of tokens
        
    Returns:
        Truncated text
    """
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    
    # Truncate at last sentence boundary if possible
    truncated = text[:max_chars]
    
    # Try to find last complete sentence
    for punct in ['. ', '? ', '! ', '\n\n']:
        last_punct = truncated.rfind(punct)
        if last_punct > max_chars * 0.8:  # At least 80% of target
            return truncated[:last_punct + len(punct)]
    
    # Otherwise just truncate with ellipsis
    return truncated.rstrip() + "..."


def select_chunks_within_budget(
    chunks: List[Tuple[str, float, dict]],
    max_tokens: int,
    reserve_tokens: int = 100
) -> List[Tuple[str, float, dict]]:
    """
    Select chunks that fit within token budget while prioritizing by similarity.
    
    Args:
        chunks: List of (text, similarity, metadata) tuples, sorted by similarity
        max_tokens: Maximum total tokens allowed
        reserve_tokens: Tokens to reserve for formatting/overhead
        
    Returns:
        List of selected chunks that fit within budget
    """
    available_tokens = max_tokens - reserve_tokens
    selected = []
    total_tokens = 0
    
    for chunk_text, similarity, metadata in chunks:
        chunk_tokens = count_tokens(chunk_text)
        
        if total_tokens + chunk_tokens <= available_tokens:
            selected.append((chunk_text, similarity, metadata))
            total_tokens += chunk_tokens
            logger.debug(
                f"Added chunk from {metadata.get('filename', 'unknown')} "
                f"({chunk_tokens} tokens, total: {total_tokens}/{available_tokens})"
            )
        else:
            # Check if we can fit a truncated version
            remaining_tokens = available_tokens - total_tokens
            if remaining_tokens > 200:  # Only if meaningful amount left
                truncated = truncate_to_token_limit(chunk_text, remaining_tokens)
                if count_tokens(truncated) > 100:  # At least 100 tokens useful
                    selected.append((truncated, similarity, metadata))
                    total_tokens += count_tokens(truncated)
                    logger.debug(
                        f"Added truncated chunk from {metadata.get('filename', 'unknown')} "
                        f"({count_tokens(truncated)} tokens, total: {total_tokens}/{available_tokens})"
                    )
            
            logger.info(
                f"Context budget reached: {total_tokens}/{available_tokens} tokens used, "
                f"{len(chunks) - len(selected)} chunks excluded"
            )
            break
    
    return selected

