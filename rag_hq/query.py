"""
RAG query functions for context enrichment and search.
"""
import time
import json
import logging
import numpy as np
# LiveKit 1.0 - Agent class is used instead of VoicePipelineAgent
from livekit.agents import Agent, llm

from .config import (
    MAX_EMBEDDING_SIZE_CHARS, RELEVANCE_THRESHOLD, HIGH_RELEVANCE_THRESHOLD,
    CONTEXT_EXPANSION_ENABLED, CONTEXT_EXPANSION_TOKENS, SAFE_EMBEDDING_SIZE_CHARS,
    K_RESULTS,     MAX_CONTEXT_TOKENS, ENABLE_CITATIONS, HYBRID_SEARCH_ENABLED,
    HYBRID_SEMANTIC_WEIGHT, HYBRID_KEYWORD_WEIGHT, VERBOSE_RAG_LOGGING
)
from .state import state, get_document_text
from .embeddings import create_embeddings
from .token_counter import select_chunks_within_budget, count_tokens
from .bm25_index import merge_hybrid_results

logger = logging.getLogger("rag-assistant-enhanced")


def filter_safe_text(text: str) -> str:
    """
    Filter and normalize Unicode for TTS compatibility.
    Strategy: Replace problematic Unicode with ASCII equivalents.
    Keep only: ASCII + Latin Extended + essential symbols (€, •)
    """
    import re
    safe_chars = []
    unsafe_found = False
    
    # Unicode replacement mapping - convert to TTS-safe equivalents
    unicode_replacements = {
        # Dashes -> hyphen
        0x2013: '-',   # – En dash
        0x2014: '-',   # — Em dash
        0x2015: '-',   # ― Horizontal bar
        
        # Spaces -> regular space
        0x00A0: ' ',   # Non-breaking space
        0x202F: ' ',   # Narrow no-break space
        0x2009: ' ',   # Thin space
        
        # Ligatures -> letter equivalents
        0xFB00: 'ff',  # ﬀ -> ff
        0xFB01: 'fi',  # ﬁ -> fi
        0xFB02: 'fl',  # ﬂ -> fl
        0xFB03: 'ffi', # ﬃ -> ffi
        0xFB04: 'ffl', # ﬄ -> ffl
        
        # Other symbols
        0x2026: '...',  # … -> ...
        0x00AD: '',     # Soft hyphen -> remove
    }
    
    # Keep these useful symbols as-is (TTS-safe)
    keep_unicode = {
        0x20AC,  # € Euro sign
        0x2022,  # • Bullet point
        0x2018,  # ' Left single quote
        0x2019,  # ' Right single quote
        0x201C,  # " Left double quote
        0x201D,  # " Right double quote
    }
    
    for char in text:
        char_code = ord(char)
        
        # Replace with mapping if exists
        if char_code in unicode_replacements:
            replacement = unicode_replacements[char_code]
            safe_chars.append(replacement)
            continue
        
        # Keep all ASCII printable (32-126)
        if 32 <= char_code <= 126:
            safe_chars.append(char)
        # Keep common whitespace
        elif char in '\n\t\r':
            safe_chars.append(char)
        # Keep Latin letters with diacritics (À-ÿ and extended up to 591)
        elif char.isalpha() and char_code < 591:
            safe_chars.append(char)
        # Keep essential Unicode symbols
        elif char_code in keep_unicode:
            safe_chars.append(char)
        # Block CJK Unified Ideographs (Chinese/Japanese/Korean)
        elif 0x4E00 <= char_code <= 0x9FFF:
            safe_chars.append(' ')
            unsafe_found = True
        # Block Emoji ranges
        elif 0x1F300 <= char_code <= 0x1F9FF:
            safe_chars.append(' ')
            unsafe_found = True
        # Block other high Unicode (>0x3000)
        elif char_code >= 0x3000:
            safe_chars.append(' ')
            unsafe_found = True
        # Replace other low Unicode with space for safety
        else:
            safe_chars.append(' ')
    
    # Log if we filtered anything problematic
    if unsafe_found:
        logger.warning("⚠️ Filtered problematic Unicode (CJK/emoji) from RAG chunk text")
    
    # Clean up multiple spaces
    result = ''.join(safe_chars)
    result = re.sub(r'\s+', ' ', result)
    return result.strip()


async def expand_chunk_context(chunk_text: str, metadata: dict) -> str:
    """Expand a chunk with surrounding context from the original document."""
    if not CONTEXT_EXPANSION_ENABLED:
        return chunk_text
    
    filename = metadata.get('filename')
    if not filename or filename not in state.document_texts:
        logger.debug(f"Cannot expand context: document not registered for {filename}")
        return chunk_text
    
    # Lazy-load the document text
    full_text = await get_document_text(filename)
    if not full_text:
        logger.debug(f"Cannot expand context: failed to load document text for {filename}")
        return chunk_text
    
    # Use character positions if available
    if 'char_start' in metadata and 'char_end' in metadata:
        char_start = metadata['char_start']
        char_end = metadata['char_end']
    else:
        # Fallback: find the chunk in the full text
        chunk_pos = full_text.find(chunk_text)
        if chunk_pos == -1:
            logger.debug(f"Cannot expand context: chunk not found in document")
            return chunk_text
        char_start = chunk_pos
        char_end = chunk_pos + len(chunk_text)
    
    # Calculate expansion boundaries
    chars_per_token = 4
    
    # First check if chunk itself needs truncation
    if len(chunk_text) > SAFE_EMBEDDING_SIZE_CHARS:
        logger.debug(f"Chunk too large ({len(chunk_text)} chars), truncating to {SAFE_EMBEDDING_SIZE_CHARS}")
        return chunk_text[:SAFE_EMBEDDING_SIZE_CHARS]
    
    # Calculate how much space we have for expansion
    max_expansion_size = SAFE_EMBEDDING_SIZE_CHARS - len(chunk_text)
    if max_expansion_size <= 50:
        logger.debug(f"Not enough room for expansion ({max_expansion_size} chars available)")
        return chunk_text
        
    # Limit expansion tokens based on available space
    expansion_tokens = min(CONTEXT_EXPANSION_TOKENS, max_expansion_size // chars_per_token)
    expansion_chars = expansion_tokens * chars_per_token
    
    # Expand boundaries
    expanded_start = max(0, char_start - expansion_chars)
    expanded_end = min(len(full_text), char_end + expansion_chars)
    
    # Try to find sentence boundaries for cleaner expansion
    if expanded_start > 0:
        for punct in ['. ', '? ', '! ', '\n\n', '\n']:
            pos = full_text.rfind(punct, expanded_start, char_start)
            if pos != -1:
                expanded_start = pos + len(punct)
                break
    
    if expanded_end < len(full_text):
        for punct in ['. ', '? ', '! ', '\n\n', '\n']:
            pos = full_text.find(punct, char_end, expanded_end)
            if pos != -1:
                expanded_end = pos + len(punct.rstrip())
                break
    
    # Extract expanded text
    expanded_text = full_text[expanded_start:expanded_end].strip()
    
    # Add markers to show original chunk boundaries
    if expanded_start < char_start or expanded_end > char_end:
        pre_context = full_text[expanded_start:char_start].strip()
        post_context = full_text[char_end:expanded_end].strip()
        
        if pre_context or post_context:
            expanded_text = f"[...{pre_context}] {chunk_text} [{post_context}...]"
    
    # Final check to ensure text is not too large
    if len(expanded_text) > SAFE_EMBEDDING_SIZE_CHARS:
        logger.debug(f"Trimming expanded text from {len(expanded_text)} to {SAFE_EMBEDDING_SIZE_CHARS} chars")
        if len(chunk_text) <= (SAFE_EMBEDDING_SIZE_CHARS // 2):
            remaining = SAFE_EMBEDDING_SIZE_CHARS - len(chunk_text)
            pre_size = remaining // 2
            post_size = remaining - pre_size
            
            chunk_pos = expanded_text.find(chunk_text)
            if chunk_pos != -1 and chunk_pos + len(chunk_text) <= len(expanded_text):
                pre_text = expanded_text[:chunk_pos]
                post_text = expanded_text[chunk_pos + len(chunk_text):]
                
                if len(pre_text) > pre_size:
                    pre_text = "..." + pre_text[-pre_size:]
                if len(post_text) > post_size:
                    post_text = post_text[:post_size] + "..."
                
                expanded_text = pre_text + chunk_text + post_text
            else:
                expanded_text = expanded_text[:SAFE_EMBEDDING_SIZE_CHARS]
        else:
            expanded_text = expanded_text[:SAFE_EMBEDDING_SIZE_CHARS]
    
    # Absolute final safeguard
    if len(expanded_text) > SAFE_EMBEDDING_SIZE_CHARS:
        logger.warning(f"CRITICAL: Expanded text still too large ({len(expanded_text)}), force truncating")
        expanded_text = expanded_text[:SAFE_EMBEDDING_SIZE_CHARS]
    
    return expanded_text


async def enrich_with_rag(agent: Agent, chat_ctx: llm.ChatContext):
    """Enrich the chat context with RAG results for the user's message."""
    try:
        if not state.rag_enabled:
            logger.info("RAG mechanism is disabled. Skipping enrichment.")
            return
        
        # Check if annoy_index is initialized
        if state.annoy_index is None:
            logger.error("enrich_with_rag failed: Annoy index is not initialized (database not loaded)")
            return
        
        # Support both LiveKit Agents v1 (items) and older (messages) ChatContext
        messages = getattr(chat_ctx, "messages", None)
        if messages is None:
            messages = getattr(chat_ctx, "items", [])
            
        user_msg = messages[-1]
        
        # Create embeddings for the user's message
        start_time = time.perf_counter()
        
        # Limit user message size for embedding
        if len(user_msg.content) > MAX_EMBEDDING_SIZE_CHARS:
            logger.info(f"Truncating user message from {len(user_msg.content)} to {MAX_EMBEDDING_SIZE_CHARS} chars")
            user_content_for_embedding = user_msg.content[:MAX_EMBEDDING_SIZE_CHARS]
        else:
            user_content_for_embedding = user_msg.content
            
        user_embedding = await create_embeddings(user_content_for_embedding, is_query=True)
        embedding_time = (time.perf_counter() - start_time) * 1000
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Time to create embeddings: {embedding_time:.2f} ms")
        
        # If embedding is empty, skip RAG enrichment
        if not np.any(user_embedding):
            logger.info("Empty user embedding; skipping RAG enrichment")
            return
        
        # Query the vector database
        start_time = time.perf_counter()
        k = K_RESULTS
        
        # Semantic search
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Starting semantic search (k={k})...")
        semantic_results = await state.annoy_index.query_async(user_embedding, n=k * 2, executor=state.executor)
        
        # Convert to (uuid, score) format for hybrid merging
        semantic_scores = [(r.userdata, r.cosine_similarity) for r in semantic_results]
        
        # Hybrid search: combine with BM25 if enabled
        if HYBRID_SEARCH_ENABLED and state.bm25_index and state.bm25_index.get_num_docs() > 0:
            if VERBOSE_RAG_LOGGING:
                logger.info("Performing hybrid search (semantic + keyword)...")
            
            # BM25 search
            bm25_results = state.bm25_index.search(user_msg.content, n=k * 2)
            
            # Merge results
            merged_results = merge_hybrid_results(
                semantic_scores,
                bm25_results,
                semantic_weight=HYBRID_SEMANTIC_WEIGHT,
                bm25_weight=HYBRID_KEYWORD_WEIGHT
            )
            
            # Convert back to result objects with combined scores
            results = []
            for uuid, combined_score in merged_results:
                result = type('QueryResult', (), {
                    'userdata': uuid,
                    'cosine_similarity': combined_score  # Using combined score as similarity
                })
                results.append(result)
            
            if VERBOSE_RAG_LOGGING:
                logger.info(f"Hybrid search completed (weights: semantic={HYBRID_SEMANTIC_WEIGHT}, keyword={HYBRID_KEYWORD_WEIGHT})")
        else:
            results = semantic_results
            if VERBOSE_RAG_LOGGING:
                logger.info("Semantic search completed.")
        
        search_time = (time.perf_counter() - start_time) * 1000
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Time to search: {search_time:.2f} ms")
        
        # Collect candidate chunks above threshold
        candidate_chunks = []
        for result in results:
            chunk_data = state.chunks_metadata.get(result.userdata)
            if chunk_data and result.cosine_similarity > RELEVANCE_THRESHOLD:
                chunk_text = chunk_data['text']
                metadata = chunk_data['metadata']
                
                # Expand chunk with surrounding context
                expanded_text = await expand_chunk_context(chunk_text, metadata)
                
                # Filter out unsafe characters (Chinese, emojis, etc.) that can crash TTS
                expanded_text = filter_safe_text(expanded_text)
                
                candidate_chunks.append((expanded_text, result.cosine_similarity, metadata))
                
                if len(candidate_chunks) >= k:
                    break
        
        # Apply context window budget
        selected_chunks = select_chunks_within_budget(
            candidate_chunks,
            max_tokens=MAX_CONTEXT_TOKENS,
            reserve_tokens=100
        )
        
        # Add selected chunks to chat context
        # Group chunks by document to add extended summary once per document
        docs_seen = set()
        context_added = False
        citation_num = 1
        
        for chunk_text, similarity, metadata in selected_chunks:
            filename = metadata['filename']
            
            # Add extended summary once per document (first time we see it)
            if filename not in docs_seen:
                docs_seen.add(filename)
                summary_data = state.document_summaries.get(filename, {})
                extended_summary = summary_data.get("extended_summary", "")
                
                if extended_summary and extended_summary != "No extended summary available":
                    # Add extended summary as context
                    summary_msg = f"📄 Document: {filename}\n\nSamenvatting:\n{extended_summary}\n\n---\n"
                    # Support both old and new LiveKit versions
                    if hasattr(chat_ctx, 'add_message'):
                        chat_ctx.add_message(
                            role="assistant",
                            content=f"Context (automatically added from documents):\n{summary_msg}"
                        )
                        # We need to find the new message in items to re-insert it if needed,
                        # but enrich_with_rag seems to manipulate the list directly.
                        # Let's check where 'messages' comes from.
                    else:
                        rag_msg_summary = llm.ChatMessage.create(
                            text=f"Context (automatically added from documents):\n{summary_msg}",
                            role="assistant",
                        )
                        messages.append(rag_msg_summary)
                    
                    if VERBOSE_RAG_LOGGING:
                        logger.info(f"Added extended summary for {filename} (~{count_tokens(extended_summary)} tokens)")
            
            # Format chunk context with citation if enabled
            if ENABLE_CITATIONS:
                context_msg = f"[{citation_num}] Bron: {filename}, chunk {metadata['chunk_index']}\nRelevantie: {similarity:.2f}\n\n{chunk_text}"
                citation_num += 1
            else:
                context_msg = f"[Bron: {filename}, chunk {metadata['chunk_index']}]\n{chunk_text}"
            
            if VERBOSE_RAG_LOGGING:
                logger.info(f"Added chunk from {filename} (similarity: {similarity:.3f}, tokens: ~{count_tokens(chunk_text)})")
            
            # Support both old and new LiveKit versions
            if hasattr(chat_ctx, 'add_message'):
                chat_ctx.add_message(
                    role="assistant",
                    content=f"Context (automatically added from documents):\n{context_msg}"
                )
            else:
                rag_msg = llm.ChatMessage.create(
                    text=f"Context (automatically added from documents):\n{context_msg}",
                    role="assistant",
                )
                messages.append(rag_msg)
            
            context_added = True
        
        # Re-add the user message to maintain conversation flow
        messages.append(user_msg)
        
        total_time = embedding_time + search_time
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Total RAG operation time: {total_time:.2f} ms, context added: {context_added}")
    except Exception as e:
        logger.error(f"enrich_with_rag failed: {e}")
        return


async def query_rag(search_string: str, num_results: int = 5) -> str:
    """Query the RAG database with a search string and return results as formatted JSON."""
    try:
        if not state.rag_enabled:
            logger.info("RAG mechanism is disabled. Skipping query.")
            return json.dumps({"query": search_string, "retrieved_docs": [], "search_time_ms": 0, "num_results": 0}, indent=2)
        
        # Check if annoy_index is initialized
        if state.annoy_index is None:
            import os
            from .config import VECTOR_DB_PATH, METADATA_PATH, VECTOR_DB_FOLDER
            
            logger.error("=" * 60)
            logger.error("query_rag failed: Annoy index is not initialized (database not loaded)")
            logger.error("=" * 60)
            logger.error(f"Current process PID: {os.getpid()}")
            logger.error(f"RAG enabled: {state.rag_enabled}")
            logger.error(f"Working directory: {os.getcwd()}")
            logger.error(f"Vector DB folder exists: {os.path.exists(VECTOR_DB_FOLDER)}")
            logger.error(f"Vector DB file exists: {os.path.exists(VECTOR_DB_PATH)}")
            logger.error(f"Metadata file exists: {os.path.exists(METADATA_PATH)}")
            logger.error(f"Map file exists: {os.path.exists(VECTOR_DB_PATH + '.map')}")
            logger.error("=" * 60)
            logger.error("DIAGNOSIS: RAG was not properly initialized in this worker process")
            logger.error("Check the worker startup logs for initialization errors")
            logger.error("=" * 60)
            
            return json.dumps({
                "query": search_string, 
                "retrieved_docs": [], 
                "search_time_ms": 0, 
                "num_results": 0, 
                "error": "Database not initialized",
                "diagnostics": {
                    "rag_enabled": state.rag_enabled,
                    "annoy_index_is_none": True,
                    "vector_db_exists": os.path.exists(VECTOR_DB_PATH),
                    "metadata_exists": os.path.exists(METADATA_PATH),
                    "working_dir": os.getcwd()
                }
            }, indent=2)
        
        # Create embeddings for the search string
        start_time = time.perf_counter()
        
        # Limit search string size for embedding
        if len(search_string) > MAX_EMBEDDING_SIZE_CHARS:
            logger.info(f"Truncating search query from {len(search_string)} to {MAX_EMBEDDING_SIZE_CHARS} chars")
            search_string_for_embedding = search_string[:MAX_EMBEDDING_SIZE_CHARS]
        else:
            search_string_for_embedding = search_string
            
        # Mark this as a query to use priority semaphore
        search_embedding = await create_embeddings(search_string_for_embedding, is_query=True)
        embedding_time = (time.perf_counter() - start_time) * 1000
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Time to create embeddings: {embedding_time:.2f} ms")
        
        # If embedding is empty, return empty results
        if not np.any(search_embedding):
            return json.dumps({"query": search_string, "retrieved_docs": [], "search_time_ms": embedding_time, "num_results": 0}, indent=2)
        
        # Query the vector database
        start_time = time.perf_counter()
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Starting search query for: {search_string}")
        # Request more results to see what we're getting (even below threshold)
        results = await state.annoy_index.query_async(search_embedding, n=num_results * 3, executor=state.executor)
        if VERBOSE_RAG_LOGGING:
            logger.info("Search query completed.")
        search_time = (time.perf_counter() - start_time) * 1000
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Time to search: {search_time:.2f} ms")
        
        # DEBUG: Log top similarity scores (even if below threshold)
        if results:
            top_scores = [f"{r.cosine_similarity:.3f}" for r in results[:5]]
            logger.info(f"🔍 Top 5 similarity scores: {', '.join(top_scores)}")
            logger.info(f"   Threshold: {RELEVANCE_THRESHOLD} (results above threshold will be included)")
        
        # Organize results by document
        documents_data = {}
        results_above_threshold = 0
        results_below_threshold = 0
        
        for result in results:
            chunk_data = state.chunks_metadata.get(result.userdata)
            if chunk_data:
                if result.cosine_similarity > RELEVANCE_THRESHOLD:
                    results_above_threshold += 1
                    metadata = chunk_data['metadata']
                    filename = metadata['filename']
                    
                    # Initialize document entry if not exists
                    if filename not in documents_data:
                        summary_data = state.document_summaries.get(filename, {})
                        # Use extended summary (350 tokens) instead of short one-liner
                        extended_summary = summary_data.get("extended_summary", summary_data.get("summary", "No summary available"))
                        documents_data[filename] = {
                            "source": filename,
                            "summary": extended_summary,
                            "keywords": ", ".join(summary_data.get("extended_keywords", summary_data.get("keywords", []))),
                            "snippets": [],
                            "max_similarity": result.cosine_similarity
                        }
                    
                    # Expand chunk with surrounding context
                    expanded_text = await expand_chunk_context(chunk_data['text'], metadata)
                    
                    # Filter out unsafe characters (Chinese, emojis, etc.) that can crash TTS
                    expanded_text = filter_safe_text(expanded_text)
                    
                    # Add snippet
                    snippet_data = {
                        "text": expanded_text,
                        "similarity": result.cosine_similarity,
                        "chunk_index": metadata['chunk_index']
                    }
                    documents_data[filename]["snippets"].append(snippet_data)
                    
                    # Update max similarity
                    if result.cosine_similarity > documents_data[filename]["max_similarity"]:
                        documents_data[filename]["max_similarity"] = result.cosine_similarity
                else:
                    results_below_threshold += 1
        
        # Log filtering results
        if results_above_threshold == 0 and results_below_threshold > 0:
            logger.warning(f"⚠️  All {results_below_threshold} results were below threshold {RELEVANCE_THRESHOLD}")
            logger.warning(f"   Consider lowering RELEVANCE_THRESHOLD or checking if query matches document content")
        
        # Format results
        retrieved_docs = []
        for filename, doc_data in documents_data.items():
            # Sort snippets by similarity
            doc_data["snippets"].sort(key=lambda x: x["similarity"], reverse=True)
            
            # Format document entry
            doc_entry = {
                "source": doc_data["source"],
                "summary": f"{doc_data['summary']}\nkeywords: {doc_data['keywords']}",
            }
            
            # Add top snippets (use full expanded context, up to 2000 chars)
            for i, snippet in enumerate(doc_data["snippets"][:3]):
                snippet_text = snippet["text"]
                # Use full expanded context (truncate only if extremely long)
                if len(snippet_text) > 2000:
                    doc_entry[f"snippet_{i+1}"] = snippet_text[:2000] + "..."
                else:
                    doc_entry[f"snippet_{i+1}"] = snippet_text
            
            retrieved_docs.append(doc_entry)
            
            if len(retrieved_docs) >= num_results:
                break
        
        # Create final response
        response = {
            "query": search_string,
            "retrieved_docs": retrieved_docs,
            "search_time_ms": embedding_time + search_time,
            "num_results": len(retrieved_docs)
        }
        
        total_time = embedding_time + search_time
        if VERBOSE_RAG_LOGGING:
            logger.info(f"Total RAG query time: {total_time:.2f} ms, found {len(retrieved_docs)} relevant documents")
        
        return json.dumps(response, indent=2)
    except Exception as e:
        logger.error(f"query_rag failed: {e}")
        return json.dumps({"query": search_string, "retrieved_docs": [], "search_time_ms": 0, "num_results": 0}, indent=2)
