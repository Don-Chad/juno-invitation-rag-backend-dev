"""
RAG Query Handler Functions
Handles Q&A RAG, Chunk RAG, and combined RAG queries
"""
import asyncio
import json
import time
from .context_builders import (
    build_qa_context, build_chunk_context,
    build_combined_qa_context, build_combined_chunk_context_with_budget
)
from .logging_helpers import (
    log_qa_debug, log_chunk_debug, log_qa_timing, log_both_rag_debug
)
from .message_helpers import insert_rag_message


async def query_qa_rag_only(
    agent, chat_ctx, last_user_message, user_id, conversation_id,
    qa_rag_initialized, query_qa_rag_func, rag_num_results,
    document_server_enabled, document_server_base_url,
    rag_debug_mode, rag_debug_print_full,
    estimate_tokens_func, print_chat_history_stats_func,
    rag_query_logger, llm_module, logger
):
    """Query Q&A RAG system only"""
    start_time = time.perf_counter()
    
    if not qa_rag_initialized:
        logger.warning("Q&A RAG not initialized, skipping")
        return
    
    try:
        logger.info(f"🎯 Q&A RAG query: {last_user_message[:200]}...")
        
        results = await asyncio.wait_for(
            query_qa_rag_func(last_user_message, num_results=rag_num_results),
            timeout=0.5
        )
        
        search_time = (time.perf_counter() - start_time) * 1000
        
        if results and "No relevant" not in results:
            try:
                parsed_results = json.loads(results)
                qa_pairs = parsed_results.get("retrieved_qa", [])
                timing_info = parsed_results.get("timing", {})
                
                log_qa_timing(timing_info, search_time, logger)
                
                if qa_pairs:
                    logger.info(f"✅ Q&A RAG: Found {len(qa_pairs)} relevant Q&A pairs")
                    
                    context_build_start = time.perf_counter()
                    context_text = build_qa_context(qa_pairs, document_server_enabled, document_server_base_url)
                    token_count = estimate_tokens_func(context_text)
                    context_build_time = (time.perf_counter() - context_build_start) * 1000
                    logger.info(f"   • Context building: {context_build_time:.2f} ms (~{token_count} tokens)")
                    
                    if rag_debug_mode:
                        log_qa_debug(qa_pairs, context_text, token_count, rag_debug_print_full, logger)
                    else:
                        logger.info(f"📚 Q&A RAG: Added {len(qa_pairs)} Q&A pairs (~{token_count} tokens)")
                    
                    insert_start = time.perf_counter()
                    insert_rag_message(chat_ctx, context_text, llm_module)
                    insert_time = (time.perf_counter() - insert_start) * 1000
                    logger.info(f"   • Context insertion: {insert_time:.2f} ms")
                    
                    total_enrichment_time = (time.perf_counter() - start_time) * 1000
                    logger.info(f"   ⏱️  Total enrichment time: {total_enrichment_time:.2f} ms")
                    
                    # Log to file if logger is enabled
                    if rag_query_logger:
                        rag_query_logger.log_query(
                            query=last_user_message,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            search_time_ms=search_time,
                            results=[{"qa_pairs": qa_pairs}],  # Wrap Q&A pairs in list for logger
                            context_added=context_text,
                            token_count=token_count,
                            num_documents=len(qa_pairs),
                            rag_mode="Q&A RAG"
                        )
                    
                    print_chat_history_stats_func(chat_ctx, label="[AFTER Q&A RAG]")
                    
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing Q&A RAG results: {e}")
                
    except asyncio.TimeoutError:
        logger.warning("⚠️  Q&A RAG query timed out (>500ms)")
        # Reset HTTP session to prevent "Unclosed client session" errors
        try:
            from rag_hq.state import state
            if state.http_session:
                state.http_session = None
                state.http_session_pid = None
        except Exception:
            pass  # Ignore errors during cleanup
    except RuntimeError as e:
        # Handle event loop errors that can occur during timeouts
        if "Event loop" in str(e) or "closed" in str(e).lower():
            logger.warning(f"⚠️  Q&A RAG query failed due to event loop issue (likely timeout): {e}")
            # Reset HTTP session
            try:
                from rag_hq.state import state
                if state.http_session:
                    state.http_session = None
                    state.http_session_pid = None
            except Exception:
                pass
        else:
            logger.error(f"Runtime error in Q&A RAG enrichment: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error in Q&A RAG enrichment: {e}", exc_info=True)


async def query_chunk_rag_only(
    agent, chat_ctx, last_user_message, user_id, conversation_id,
    rag_initialized, query_rag_func, rag_num_results,
    document_server_enabled, document_server_base_url,
    rag_debug_mode, rag_debug_print_full,
    estimate_tokens_func, print_chat_history_stats_func,
    rag_query_logger, llm_module, logger
):
    """Query chunk-based RAG system only"""
    start_time = time.perf_counter()
    
    if not rag_initialized:
        logger.warning("Chunk RAG not initialized, skipping")
        return
    
    search_error = None

    try:
        logger.info(f"📄 Chunk RAG query: '{last_user_message[:200]}...'")
        logger.info(f"   Requesting {rag_num_results} results")
        try:
            results = await asyncio.wait_for(
                query_rag_func(last_user_message, num_results=rag_num_results),
                timeout=0.5,
            )
            logger.debug(f"   Raw RAG response received: {len(results) if results else 0} chars")
        except asyncio.TimeoutError:
            search_error = "Query timed out (>500ms)"
            logger.warning("⚠️  Chunk RAG query timed out (>500ms), skipping to avoid voice delay")
            print_chat_history_stats_func(chat_ctx, label="[AFTER RAG TIMEOUT]")
            
            # Reset HTTP session to prevent "Unclosed client session" errors
            try:
                from rag_hq.state import state
                if state.http_session:
                    state.http_session = None
                    state.http_session_pid = None
            except Exception:
                pass  # Ignore errors during cleanup
            
            if rag_query_logger:
                search_time = (time.perf_counter() - start_time) * 1000
                rag_query_logger.log_query(
                    query=last_user_message,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    search_time_ms=search_time,
                    error=search_error,
                    rag_mode="CHUNK RAG"
                )
            return
        except RuntimeError as e:
            # Handle event loop errors that can occur during timeouts
            if "Event loop" in str(e) or "closed" in str(e).lower():
                search_error = f"Event loop error (likely timeout): {str(e)}"
                logger.warning(f"⚠️  Chunk RAG query failed due to event loop issue: {e}")
                print_chat_history_stats_func(chat_ctx, label="[AFTER RAG TIMEOUT]")
                
                # Reset HTTP session
                try:
                    from rag_hq.state import state
                    if state.http_session:
                        state.http_session = None
                        state.http_session_pid = None
                except Exception:
                    pass
                
                if rag_query_logger:
                    search_time = (time.perf_counter() - start_time) * 1000
                    rag_query_logger.log_query(
                        query=last_user_message,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        search_time_ms=search_time,
                        error=search_error,
                        rag_mode="CHUNK RAG"
                    )
                return
            else:
                raise  # Re-raise if it's a different RuntimeError
        
        search_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"Chunk RAG search time: {search_time:.2f} ms")

        if results and "No relevant results found" not in results:
            try:
                parsed_results = json.loads(results)
                filtered_docs = parsed_results.get("retrieved_docs", [])
                
                # ALWAYS log what we found (even if empty)
                logger.info(f"📊 Chunk RAG Results: {len(filtered_docs) if filtered_docs else 0} documents retrieved")
                
                if filtered_docs:
                    logger.info(f"✅ Chunk RAG: Found {len(filtered_docs)} documents")
                    
                    # Log document sources
                    sources = [doc.get('source', 'Unknown') for doc in filtered_docs]
                    logger.info(f"   📚 Sources: {', '.join(sources[:3])}{'...' if len(sources) > 3 else ''}")
                    
                    context_text = build_chunk_context(filtered_docs, document_server_enabled, document_server_base_url)
                    token_count = estimate_tokens_func(context_text)
                    
                    # ALWAYS show debug info when debug mode is enabled
                    if rag_debug_mode:
                        log_chunk_debug(filtered_docs, context_text, token_count, rag_debug_print_full, logger)
                    else:
                        logger.info(f"📚 Chunk RAG: Added {len(filtered_docs)} documents (~{token_count} tokens)")
                        # Even in non-debug mode, show a preview if print_full is enabled
                        if rag_debug_print_full:
                            preview = context_text[:500] + "..." if len(context_text) > 500 else context_text
                            logger.info(f"   Preview: {preview}")
                    
                    insert_rag_message(chat_ctx, context_text, llm_module)
                    logger.info(f"✅ Chunk RAG: Context added successfully to chat")
                    
                    if rag_query_logger:
                        rag_query_logger.log_query(
                            query=last_user_message,
                            user_id=user_id,
                            conversation_id=conversation_id,
                            search_time_ms=search_time,
                            results=filtered_docs,
                            context_added=context_text,
                            token_count=token_count,
                            num_documents=len(filtered_docs),
                            rag_mode="CHUNK RAG"
                        )
                    
                    print_chat_history_stats_func(chat_ctx, label="[AFTER CHUNK RAG]")
                else:
                    logger.warning(f"⚠️  Chunk RAG: No documents found in results")
                    logger.debug(f"   Raw results: {results[:500] if results else 'None'}...")
            except json.JSONDecodeError as e:
                logger.error(f"❌ Error parsing Chunk RAG results: {e}")
                logger.error(f"   Raw results (first 500 chars): {results[:500] if results else 'None'}")
        else:
            logger.warning(f"⚠️  Chunk RAG: No relevant results found or empty response")
            if results:
                logger.debug(f"   Response: {results[:200]}...")
                
    except RuntimeError as e:
        # Handle event loop errors that can occur during timeouts
        if "Event loop" in str(e) or "closed" in str(e).lower():
            logger.warning(f"⚠️  Chunk RAG query failed due to event loop issue: {e}")
            # Reset HTTP session
            try:
                from rag_hq.state import state
                if state.http_session:
                    state.http_session = None
                    state.http_session_pid = None
            except Exception:
                pass
        else:
            logger.error(f"Runtime error in Chunk RAG enrichment: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error in Chunk RAG enrichment: {e}", exc_info=True)


async def query_both_rags(
    agent, chat_ctx, last_user_message, user_id, conversation_id,
    qa_rag_initialized, rag_initialized,
    query_qa_rag_func, query_rag_func, rag_num_results,
    rag_context_budget_tokens, rag_debug_mode, rag_debug_print_full,
    estimate_tokens_func, print_chat_history_stats_func,
    llm_module, logger
):
    """Query both Q&A and chunk-based RAG systems (respecting token budget)"""
    start_time = time.perf_counter()
    
    logger.info(f"🔄 Querying BOTH RAG systems...")
    
    combined_context = ""
    total_tokens = 0
    
    # Query Q&A RAG first (higher priority for precise answers)
    if qa_rag_initialized:
        try:
            qa_results = await asyncio.wait_for(
                query_qa_rag_func(last_user_message, num_results=rag_num_results),
                timeout=0.5
            )
            
            if qa_results and "No relevant" not in qa_results:
                parsed_qa = json.loads(qa_results)
                qa_pairs = parsed_qa.get("retrieved_qa", [])
                
                if qa_pairs:
                    logger.info(f"✅ Q&A RAG: Found {len(qa_pairs)} Q&A pairs")
                    
                    qa_context = build_combined_qa_context(qa_pairs)
                    combined_context += qa_context
                    total_tokens = estimate_tokens_func(combined_context)
                    logger.info(f"📊 Q&A context: ~{total_tokens} tokens")
                    
        except asyncio.TimeoutError:
            logger.warning("⚠️  Q&A RAG query timed out (>500ms)")
            # Reset HTTP session to prevent "Unclosed client session" errors
            try:
                from rag_hq.state import state
                if state.http_session:
                    state.http_session = None
                    state.http_session_pid = None
            except Exception:
                pass
        except RuntimeError as e:
            # Handle event loop errors that can occur during timeouts
            if "Event loop" in str(e) or "closed" in str(e).lower():
                logger.warning(f"⚠️  Q&A RAG query failed due to event loop issue: {e}")
                # Reset HTTP session
                try:
                    from rag_hq.state import state
                    if state.http_session:
                        state.http_session = None
                        state.http_session_pid = None
                except Exception:
                    pass
            else:
                logger.warning(f"Q&A RAG failed: {e}")
        except Exception as e:
            logger.warning(f"Q&A RAG failed: {e}")
    
    # Query chunk RAG if we have budget left
    remaining_budget = rag_context_budget_tokens - total_tokens
    
    if rag_initialized and remaining_budget > 1000:
        try:
            chunk_results = await asyncio.wait_for(
                query_rag_func(last_user_message, num_results=rag_num_results),
                timeout=0.5
            )
            
            if chunk_results and "No relevant" not in chunk_results:
                parsed_chunks = json.loads(chunk_results)
                docs = parsed_chunks.get("retrieved_docs", [])
                
                if docs:
                    logger.info(f"✅ Chunk RAG: Found {len(docs)} documents")
                    
                    chunk_context = build_combined_chunk_context_with_budget(
                        docs, combined_context, rag_context_budget_tokens, estimate_tokens_func, logger
                    )
                    
                    combined_context += chunk_context
                    total_tokens = estimate_tokens_func(combined_context)
                    logger.info(f"📊 Combined context: ~{total_tokens} tokens")
                    
        except asyncio.TimeoutError:
            logger.warning("⚠️  Chunk RAG query timed out (>500ms)")
            # Reset HTTP session to prevent "Unclosed client session" errors
            try:
                from rag_hq.state import state
                if state.http_session:
                    state.http_session = None
                    state.http_session_pid = None
            except Exception:
                pass
        except RuntimeError as e:
            # Handle event loop errors that can occur during timeouts
            if "Event loop" in str(e) or "closed" in str(e).lower():
                logger.warning(f"⚠️  Chunk RAG query failed due to event loop issue: {e}")
                # Reset HTTP session
                try:
                    from rag_hq.state import state
                    if state.http_session:
                        state.http_session = None
                        state.http_session_pid = None
                except Exception:
                    pass
            else:
                logger.warning(f"Chunk RAG failed: {e}")
        except Exception as e:
            logger.warning(f"Chunk RAG failed: {e}")
    
    # Add combined context if we have any
    if combined_context:
        combined_context += "\n[Instructie]: Gebruik deze informatie als deze relevant is.\n"
        
        if rag_debug_mode:
            log_both_rag_debug(combined_context, total_tokens, rag_context_budget_tokens, rag_debug_print_full, logger)
        else:
            logger.info(f"📚 Both RAG: Added combined context (~{total_tokens} tokens)")
        
        insert_rag_message(chat_ctx, combined_context, llm_module)
        print_chat_history_stats_func(chat_ctx, label="[AFTER BOTH RAG]")
    else:
        logger.info("⚠️  No results from either RAG system")
    
    search_time = (time.perf_counter() - start_time) * 1000
    logger.info(f"Both RAG total time: {search_time:.2f} ms")

