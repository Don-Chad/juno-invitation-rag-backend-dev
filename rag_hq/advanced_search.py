"""
Advanced search capabilities with query understanding and multi-hop reasoning.
This is the Tier 2 search system for complex queries.
"""
import time
import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from groq import Groq

from .config import GROQ_API_KEY, K_RESULTS, VECTOR_DIM
from .state import state
from .embeddings import create_embeddings
from .token_counter import count_tokens
from .query import expand_chunk_context

logger = logging.getLogger("rag-assistant-enhanced")


async def analyze_query(query: str) -> Dict[str, Any]:
    """
    Analyze query to extract intent, entities, and determine if multi-hop needed.
    
    Args:
        query: User's search query
        
    Returns:
        Dict with analysis results
    """
    prompt = f"""Analyze this search query and provide structured information:

Query: "{query}"

Return JSON with:
{{
    "intent": "factual|comparison|procedural|analytical",
    "entities": ["list", "of", "key", "entities"],
    "is_complex": true/false,
    "sub_questions": ["if complex, break into sub-questions"],
    "keywords": ["important", "keywords"]
}}"""

    try:
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=300,
        )
        
        if completion.choices:
            response_text = completion.choices[0].message.content.strip()
            try:
                analysis = json.loads(response_text)
                logger.info(f"Query analysis: intent={analysis.get('intent')}, complex={analysis.get('is_complex')}")
                return analysis
            except json.JSONDecodeError:
                logger.warning("Failed to parse query analysis JSON")
                return {"intent": "factual", "entities": [], "is_complex": False, "sub_questions": [], "keywords": []}
    except Exception as e:
        logger.error(f"Query analysis failed: {e}")
    
    return {"intent": "factual", "entities": [], "is_complex": False, "sub_questions": [], "keywords": []}


async def rewrite_query_for_retrieval(query: str) -> List[str]:
    """
    Rewrite/expand query into multiple search variations for better retrieval.
    
    Args:
        query: Original query
        
    Returns:
        List of query variations
    """
    prompt = f"""Given this query, generate 2-3 alternative phrasings optimized for document retrieval.
Keep the same meaning but vary the wording to match different document styles.

Query: "{query}"

Return JSON array of strings: ["variation1", "variation2", "variation3"]"""

    try:
        client = Groq(api_key=GROQ_API_KEY)
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200,
        )
        
        if completion.choices:
            response_text = completion.choices[0].message.content.strip()
            try:
                variations = json.loads(response_text)
                if isinstance(variations, list):
                    logger.info(f"Generated {len(variations)} query variations")
                    return variations
            except json.JSONDecodeError:
                pass
    except Exception as e:
        logger.error(f"Query rewriting failed: {e}")
    
    return [query]  # Fallback to original


async def advanced_search(
    query: str,
    doc_types: Optional[List[str]] = None,
    rewrite_query: bool = True,
    multi_hop: bool = True,
    k: int = 10
) -> Dict[str, Any]:
    """
    Advanced search with query understanding, rewriting, and multi-hop reasoning.
    
    This is the Tier 2 search system for complex questions.
    
    Args:
        query: Search query
        doc_types: Optional list of document types to filter by
        rewrite_query: Whether to rewrite query for better retrieval
        multi_hop: Whether to perform multi-hop reasoning
        k: Number of results to return
        
    Returns:
        Dict with search results and metadata
    """
    start_time = time.time()
    
    if not state.rag_enabled or not state.annoy_index:
        logger.warning("RAG not enabled or index not loaded")
        return {
            "query": query,
            "results": [],
            "analysis": {},
            "search_time_ms": 0
        }
    
    # Step 1: Analyze query
    logger.info(f"Advanced search for: {query}")
    analysis = await analyze_query(query)
    
    # Step 2: Query rewriting/expansion
    queries = [query]
    if rewrite_query:
        variations = await rewrite_query_for_retrieval(query)
        queries.extend(variations[:2])  # Add top 2 variations
        logger.info(f"Using {len(queries)} query variations")
    
    # Step 3: Multi-query retrieval
    all_results = {}
    
    # Check if annoy_index is initialized
    if state.annoy_index is None:
        logger.error("advanced_search failed: Annoy index is not initialized (database not loaded)")
        return []
    
    for q in queries:
        # Create embeddings
        embedding = await create_embeddings(q, is_query=True)
        
        if not np.any(embedding):
            continue
        
        # Search
        results = await state.annoy_index.query_async(embedding, n=k * 2, executor=state.executor)
        
        # Collect results
        for result in results:
            uuid = result.userdata
            if uuid not in all_results or result.cosine_similarity > all_results[uuid]['score']:
                chunk_data = state.chunks_metadata.get(uuid)
                if chunk_data:
                    all_results[uuid] = {
                        'score': result.cosine_similarity,
                        'chunk': chunk_data
                    }
    
    # Step 4: Filter by doc_types if specified
    if doc_types:
        filtered_results = {}
        for uuid, data in all_results.items():
            metadata = data['chunk'].get('metadata', {})
            filename = metadata.get('filename', '')
            # Simple extension-based filtering
            if any(filename.endswith(f".{dt}") for dt in doc_types):
                filtered_results[uuid] = data
        all_results = filtered_results
        logger.info(f"Filtered to {len(all_results)} results matching doc types: {doc_types}")
    
    # Step 5: Sort by score and take top-k
    sorted_results = sorted(
        all_results.items(),
        key=lambda x: x[1]['score'],
        reverse=True
    )[:k]
    
    # Step 6: Format results with expanded context
    formatted_results = []
    for uuid, data in sorted_results:
        chunk = data['chunk']
        metadata = chunk['metadata']
        
        # Expand context
        expanded_text = await expand_chunk_context(chunk['text'], metadata)
        
        formatted_results.append({
            "text": expanded_text,
            "filename": metadata.get('filename', 'unknown'),
            "chunk_index": metadata.get('chunk_index', 0),
            "similarity": data['score'],
            "tokens": count_tokens(expanded_text)
        })
    
    search_time_ms = (time.time() - start_time) * 1000
    
    logger.info(f"Advanced search completed: {len(formatted_results)} results in {search_time_ms:.2f}ms")
    
    return {
        "query": query,
        "query_analysis": analysis,
        "results": formatted_results,
        "search_time_ms": search_time_ms,
        "num_results": len(formatted_results)
    }


# Function call tool schema for LLM
ADVANCED_SEARCH_TOOL_SCHEMA = {
    "name": "advanced_search",
    "description": "Perform an advanced search through documents with query understanding and rewriting. Use this for complex questions that require deeper research or multi-hop reasoning.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query or question"
            },
            "doc_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional: Filter by document types (e.g., ['pdf', 'docx'])"
            },
            "k": {
                "type": "integer",
                "description": "Number of results to return (default: 10)",
                "default": 10
            }
        },
        "required": ["query"]
    }
}

