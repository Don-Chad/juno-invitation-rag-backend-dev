import os
import logging
import time
import hashlib
import json
import gc
import psutil
import random
from typing import Set, Dict, List, Any
from livekit.agents import VoicePipelineAgent
from livekit.agents import llm

# Setup logging
logger = logging.getLogger("rag-module")
logger.setLevel(logging.INFO)

# Global variables for tracking already provided information
previously_added_snippets: Set[str] = set()  # Track added snippet content hashes
previously_added_sources: Set[str] = set()   # Track added source summaries

# Placeholder for the RAG system initialization function
# This function should be implemented based on your specific RAG setup
async def ensure_rag_initialized():
    """Initialize the RAG system"""
    logger.info("Initializing RAG system...")
    # Implementation details specific to your RAG setup
    # Should be moved from the original file
    
async def query_rag(query: str, num_results: int = 3):
    """Query the RAG system for relevant information"""
    logger.info(f"Querying RAG with: {query[:100]}...")
    # Implementation details specific to your RAG setup
    # Should be moved from the original file

async def memory_optimize():
    """Force garbage collection and optimize memory usage"""
    gc.collect()
    memory_info = psutil.Process(os.getpid()).memory_info()
    logger.info(f"Current memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")

def get_last_user_message(chat_ctx: llm.ChatContext) -> str:
    """Get the full last user message (can be multiple sentences)"""
    # Look for the last user message
    for msg in reversed(chat_ctx.messages):
        if hasattr(msg, 'role') and msg.role == 'user' and hasattr(msg, 'content'):
            return msg.content
    return ""

async def enrich_with_rag(agent: VoicePipelineAgent, chat_ctx: llm.ChatContext, 
                         rag_enabled: bool = True, rag_initialized: bool = True):
    """Automatically enrich every user query with RAG context - runs on every message"""
    global previously_added_snippets, previously_added_sources
    
    if not rag_enabled or not rag_initialized:
        logger.debug("RAG mechanism is disabled or not initialized. Skipping automatic enrichment.")
        return

    # Get the full last user message
    last_user_message = get_last_user_message(chat_ctx)
    
    if not last_user_message or len(last_user_message.strip()) < 3:
        logger.debug("No meaningful user message found, skipping automatic RAG enrichment")
        return

    # Start timing for searching
    start_time = time.perf_counter()

    try:
        # Query RAG with the full last user message
        logger.info(f"Automatic RAG query: {last_user_message[:200]}...")
        results = await query_rag(last_user_message, num_results=3)
        
        search_time = (time.perf_counter() - start_time) * 1000
        logger.info(f"Automatic RAG search time: {search_time:.2f} ms")

        if results and "No relevant results found" not in results:
            try:
                # Parse results to JSON
                parsed_results = json.loads(results)
                
                # Process each document to filter out previously seen snippets
                filtered_docs = []
                
                for doc in parsed_results.get("retrieved_docs", []):
                    source = doc.get("source", "")
                    
                    # Create filtered document with new snippets only
                    filtered_doc = {
                        "source": source,
                    }
                    
                    # Only add summary if this source hasn't been seen before
                    if source not in previously_added_sources:
                        filtered_doc["summary"] = doc.get("summary", "No summary available")
                        previously_added_sources.add(source)
                        logger.debug(f"Adding new source summary for: {source}")
                    
                    # Check each snippet and only keep new ones
                    new_snippets_added = False
                    for i in range(1, 4):  # Check snippet_1, snippet_2, snippet_3
                        snippet_key = f"snippet_{i}"
                        if snippet_key in doc:
                            snippet_content = doc[snippet_key]
                            content_hash = hashlib.md5(snippet_content.encode()).hexdigest()
                            
                            # Only add if not seen before
                            if content_hash not in previously_added_snippets:
                                filtered_doc[snippet_key] = snippet_content
                                previously_added_snippets.add(content_hash)
                                new_snippets_added = True
                                logger.debug(f"Adding new snippet {i} from {source}")
                            else:
                                logger.debug(f"Skipping duplicate snippet {i} from {source}")
                    
                    # Only include document if it has at least one new snippet
                    if new_snippets_added:
                        filtered_docs.append(filtered_doc)
                        logger.info(f"Added document {source} with new snippets")
                    else:
                        logger.info(f"Skipping document {source} - all snippets already seen")
                
                # Only proceed if we have documents with new snippets
                if filtered_docs:
                    logger.info(f"Found {len(filtered_docs)} documents with new snippets to add")
                    
                    # Rebuild the context with only new information
                    context_text = "Context:\nHere's relevant information I know (only use if relevant, otherwise ignore):\n\n"
                    
                    for doc in filtered_docs:
                        # Add source and summary
                        context_text += f"Source: {doc['source']}\n"
                        if "summary" in doc:
                            context_text += f"Summary: {doc['summary']}\n"
                        
                        # Add all new snippets
                        for i in range(1, 4):
                            snippet_key = f"snippet_{i}"
                            if snippet_key in doc:
                                context_text += f"{snippet_key}: {doc[snippet_key]}\n\n"
                    
                    # Create and insert the RAG message
                    rag_msg = llm.ChatMessage.create(
                        text=context_text,
                        role="assistant",
                    )
                    
                    # Find position to insert (after system messages)
                    insert_idx = 0
                    for i, msg in enumerate(chat_ctx.messages):
                        if hasattr(msg, 'role') and msg.role == 'system':
                            insert_idx = i + 1
                    
                    # Insert after system message but before user messages
                    chat_ctx.messages.insert(insert_idx, rag_msg)
                    
                    logger.info(f"Added automatic RAG context with {len(filtered_docs)} documents to conversation")
                else:
                    logger.info("No new snippets found - all retrieved information was already provided")
            except json.JSONDecodeError as e:
                logger.error(f"Error parsing RAG results JSON: {e}")
    except Exception as e:
        logger.error(f"Error in automatic RAG enrichment: {e}", exc_info=True)
        # Continue without RAG rather than failing

class AssistantFunctions:
    """
    The class defines a set of LLM functions that the assistant can execute.
    """
    
    @staticmethod
    async def deliberate_memory_search(query: str, rag_initialized: bool = True):
        """Called when the user explicitly asks you to search memory or archive.
        For example: "Hey can we talk about X", "Do you remember Y", "Search for Z in your memory"
        
        The query parameter is provided by the LLM based on what it thinks should be searched for.
        """
        # Use a filler message while searching
        filler_messages = [
            "Good question, let me search my memory for that.",
            "Interesting, let me look that up in my knowledge base.",
            "Let me search for information about that.",
            "I'm searching my memory for relevant information.",
        ]
        message = random.choice(filler_messages)

        # Let the user know we're processing
        # Note: In function context, we return the message instead of using agent.say
        # The agent will handle the speech synthesis
        
        # Perform RAG query
        if not rag_initialized:
            return "I'm still preparing my knowledge base. Please ask me again in a moment."

        start_time = time.perf_counter()
        try:
            # First say the filler message
            initial_response = message + "\n\n"
            
            # Use the query parameter provided by the LLM
            logger.info(f"Deliberate memory search for: {query}")
            results = await query_rag(query, num_results=3)  # Get more results for deliberate search
            search_time = (time.perf_counter() - start_time) * 1000
            logger.info(f"Deliberate search completed in {search_time:.2f} ms")

            if results and "No relevant results found" not in results:
                logger.info(f"Found relevant information from documents")
                response = initial_response + f"Based on my memory search, here's what I found: {results}"
                return response
            else:
                return initial_response + "I searched my knowledge base but couldn't find specific information about that topic."
        except Exception as e:
            logger.error(f"Error in deliberate memory search: {e}")
            return initial_response + "I'm having trouble searching my knowledge base right now."