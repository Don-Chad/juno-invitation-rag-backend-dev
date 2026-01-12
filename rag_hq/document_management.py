"""
Document management including summaries and metadata.
"""
import time
import json
import pickle
import logging
import asyncio
import aiofiles
import aiofiles.os
from groq import Groq
from typing import Dict, Any

from .config import DOCUMENT_SUMMARIES_PATH, INGESTION_RAPPORT_PATH, GROQ_API_KEY
from .state import state

logger = logging.getLogger("rag-assistant-enhanced")


async def call_openai_groq_api(input_message: str, retry_count=3, extended=False) -> Dict[str, Any]:
    """Call Groq API to summarize document and extract keywords with retry logic.
    
    Args:
        input_message: Document text to summarize
        retry_count: Number of retries on failure (default: 3)
        extended: If True, generate extended summary (400 tokens, hard limit 410) instead of short (2-3 sentences)
    
    Returns:
        Dict with 'summary' and 'keywords' keys
    """
    if extended:
        prompt = (
            "You are an expert document analyzer. Analyze the following document and provide:\n"
            "1. An EXTENDED SUMMARY (target 400 tokens / ~1600 characters / 2-3 paragraphs) covering:\n"
            "   - Main topic and purpose of the document\n"
            "   - Key sections, concepts, and arguments\n"
            "   - Important details, procedures, or requirements\n"
            "   - Conclusions or recommendations if present\n"
            "2. Key topics/keywords (10-15 most important)\n\n"
            "CRITICAL: Generate approximately 400 tokens (1600 characters) in the summary.\n"
            "This summary will be used to decide if the full document is relevant for a specific question.\n"
            "Make it comprehensive but focused on what makes this document unique and useful.\n\n"
            "⚠️ CRITICAL - TEXT-TO-SPEECH COMPATIBILITY:\n"
            "Use ONLY these characters:\n"
            "- Latin letters (A-Z, a-z) with diacritics (à, é, ü, etc.)\n"
            "- Numbers (0-9)\n"
            "- ASCII punctuation: . , : ; ! ? ' \" ( ) [ ] - / & %\n"
            "- Essential symbols: € (Euro), • (bullet)\n"
            "- Smart quotes OK: ' ' \" \"\n"
            "FORBIDDEN: Chinese/CJK characters, emoji, en/em dashes (– —), ligatures (ﬁ ﬂ), special Unicode (° ± § ≈)\n"
            "Replace en/em dashes with regular hyphen -, ligatures with letters (fi fl ff), ellipsis … with ...\n\n"
            "Return the response in JSON format:\n"
            '{"summary": "...", "keywords": ["keyword1", "keyword2", ...]}\n\n'
            "Document:\n"
        )
        max_tokens = 410  # HARD LIMIT: 410 tokens (400 token summary + keywords + JSON overhead)
    else:
        prompt = (
            "You are an expert summarizer. Analyze the following document and provide:\n"
            "1. A concise summary (2-3 sentences)\n"
            "2. Key topics/keywords (5-10 most important)\n\n"
            "⚠️ CRITICAL - TEXT-TO-SPEECH COMPATIBILITY:\n"
            "Use ONLY these characters:\n"
            "- Latin letters (A-Z, a-z) with diacritics (à, é, ü)\n"
            "- Numbers (0-9)\n"
            "- ASCII punctuation: . , : ; ! ? ' \" - / & %\n"
            "- Essential symbols: € •\n"
            "FORBIDDEN: Chinese/CJK, emoji, en/em dashes (– —), ligatures (ﬁ ﬂ), special Unicode\n"
            "Replace dashes with -, ligatures with letters, … with ...\n\n"
            "Return the response in JSON format:\n"
            '{"summary": "...", "keywords": ["keyword1", "keyword2", ...]}\n\n'
            "Document:\n"
        )
        max_tokens = 400

    client = Groq(api_key=GROQ_API_KEY)
    
    summary_type = "extended" if extended else "short"
    
    for attempt in range(retry_count + 1):
        start_time = time.perf_counter()
        try:
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt + "\n" + input_message}],
                temperature=0.3,
                max_tokens=max_tokens,
                top_p=1,
                stream=False,
                stop=None,
            )
            inference_time = (time.perf_counter() - start_time) * 1000
            logger.info(f"Groq {summary_type} summary generated in {inference_time:.2f} ms")

            if completion.choices:
                response_text = completion.choices[0].message.content.strip()
                try:
                    result = json.loads(response_text)
                    return result
                except json.JSONDecodeError:
                    return {
                        "summary": response_text,
                        "keywords": []
                    }
            else:
                return {"summary": "Unable to generate summary", "keywords": []}
                
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check for rate limit errors
            if "rate_limit" in error_msg or "429" in error_msg:
                if attempt < retry_count:
                    wait_time = (2 ** attempt) * 2  # Exponential backoff: 2s, 4s, 8s
                    logger.warning(f"⚠️  Groq rate limit hit, waiting {wait_time}s before retry {attempt+1}/{retry_count}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"✗ Groq rate limit exceeded after {retry_count} retries")
                    return {"summary": "Rate limit exceeded", "keywords": []}
            
            # Check for other retryable errors
            elif any(err in error_msg for err in ["timeout", "connection", "temporarily unavailable"]):
                if attempt < retry_count:
                    wait_time = (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"⚠️  Groq API error (retryable), waiting {wait_time}s before retry {attempt+1}/{retry_count}: {e}")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"✗ Groq API failed after {retry_count} retries: {e}")
                    return {"summary": "API error after retries", "keywords": []}
            else:
                # Non-retryable error
                logger.error(f"✗ Groq API error (non-retryable): {e}")
                return {"summary": "Error generating summary", "keywords": []}
    
    # Shouldn't reach here, but just in case
    return {"summary": "Summary generation failed", "keywords": []}


async def generate_document_summary(filename: str, text: str, respect_rate_limit=True) -> Dict[str, Any]:
    """Generate BOTH short and extended summaries for a document if not already exists.
    
    Args:
        filename: Name of the document
        text: Full text of the document
        respect_rate_limit: If True, adds small delay to avoid rate limits (default: True)
    
    Returns:
        Dict with 'summary', 'extended_summary', and 'keywords' keys
    """
    # Check if we already have both summaries
    if filename in state.document_summaries:
        cached = state.document_summaries[filename]
        # Check if extended summary exists (backwards compatibility)
        if 'extended_summary' in cached:
            logger.debug(f"Using cached summaries for {filename}")
            return cached
        else:
            logger.info(f"⚠️  Found old summary format for {filename}, regenerating with extended summary...")
    
    logger.info(f"📝 Generating summaries for {filename}...")
    
    # Generate SHORT summary (2-3 sentences, for quick RAG context)
    text_for_short_summary = text[:3000] if len(text) > 3000 else text
    
    if respect_rate_limit:
        await asyncio.sleep(0.5)  # 500ms delay
    
    short_summary_data = await call_openai_groq_api(text_for_short_summary, extended=False)
    
    # Generate EXTENDED summary (max 400 tokens, for document selection in extensive search)
    # Use more text for extended summary
    from .config import EXTENSIVE_SEARCH_SUMMARY_CHARS
    text_for_extended_summary = text[:EXTENSIVE_SEARCH_SUMMARY_CHARS] if len(text) > EXTENSIVE_SEARCH_SUMMARY_CHARS else text
    
    if respect_rate_limit:
        await asyncio.sleep(0.5)  # 500ms delay
    
    extended_summary_data = await call_openai_groq_api(text_for_extended_summary, extended=True)
    
    # Combine both summaries into one entry
    summary_data = {
        'filename': filename,
        'summary': short_summary_data.get('summary', 'No summary available'),
        'extended_summary': extended_summary_data.get('summary', 'No extended summary available'),
        'keywords': short_summary_data.get('keywords', []),
        'extended_keywords': extended_summary_data.get('keywords', []),
        'generated_at': time.time()
    }
    
    state.document_summaries[filename] = summary_data
    await save_document_summaries()
    
    logger.info(f"✓ Short summary generated: {summary_data['summary'][:80]}...")
    logger.info(f"✓ Extended summary generated: {len(summary_data['extended_summary'])} chars")
    
    return summary_data


async def save_document_summaries():
    """Save document summaries to disk."""
    try:
        async with aiofiles.open(DOCUMENT_SUMMARIES_PATH, 'wb') as f:
            await f.write(pickle.dumps(state.document_summaries))
        logger.debug(f"Saved summaries for {len(state.document_summaries)} documents")
    except Exception as e:
        logger.error(f"Error saving document summaries: {e}")


async def load_document_summaries():
    """Load document summaries from disk."""
    try:
        if await aiofiles.os.path.exists(DOCUMENT_SUMMARIES_PATH):
            async with aiofiles.open(DOCUMENT_SUMMARIES_PATH, 'rb') as f:
                state.document_summaries = pickle.loads(await f.read())
            logger.info(f"Loaded summaries for {len(state.document_summaries)} documents")
        else:
            state.document_summaries = {}
    except Exception as e:
        logger.error(f"Error loading document summaries: {e}")
        state.document_summaries = {}


async def update_ingestion_rapport(data: Dict):
    """Update the ingestion rapport file."""
    try:
        async with aiofiles.open(INGESTION_RAPPORT_PATH, 'w') as f:
            await f.write(json.dumps(data, indent=2))
    except Exception as e:
        logger.error(f"Error updating ingestion rapport: {e}")


async def read_ingestion_rapport() -> Dict:
    """Read the ingestion rapport file."""
    if not await aiofiles.os.path.exists(INGESTION_RAPPORT_PATH):
        return {}
    try:
        async with aiofiles.open(INGESTION_RAPPORT_PATH, 'r') as f:
            content = await f.read()
            return json.loads(content)
    except Exception as e:
        logger.error(f"Error reading ingestion rapport: {e}")
        return {}
