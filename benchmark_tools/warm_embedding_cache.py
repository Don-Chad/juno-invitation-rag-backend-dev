#!/usr/bin/env python3
"""
Embedding Cache Warmer for RAG System

This script pre-warms the embedding cache by processing all documents
without rebuilding the entire vector database. This can significantly
improve embedding creation time during regular operation.

Usage:
    python warm_embedding_cache.py
"""

import asyncio
import os
import sys
import time
import logging
from tqdm import tqdm  # for progress bars

# Import the RAG module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rag_module_hq_enhanced as rag

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("cache-warmer")

async def warm_cache():
    """Process all documents and build embedding cache without rebuilding database."""
    print("Starting embedding cache warming process...")
    
    # Initialize the RAG system
    await rag.initialize_rag()
    
    # Get list of all files in uploads folder
    if not os.path.exists(rag.UPLOADS_FOLDER):
        logger.error(f"Uploads folder not found: {rag.UPLOADS_FOLDER}")
        return
    
    files = os.listdir(rag.UPLOADS_FOLDER)
    logger.info(f"Found {len(files)} files to process")
    
    start_time = time.time()
    cache_size_before = len(rag.state.embeddings_cache)
    
    # Process each file, but don't rebuild the index
    for filename in tqdm(files, desc="Processing files"):
        file_path = os.path.join(rag.UPLOADS_FOLDER, filename)
        
        # Skip directories
        if os.path.isdir(file_path):
            continue
        
        # Extract text
        text = await rag.extract_text(file_path)
        if not text:
            logger.warning(f"No text extracted from {filename}")
            continue
        
        # Create chunks but don't add to index
        logger.info(f"Processing {filename}...")
        chunks_with_meta = await rag.smart_chunk_text(text, filename)
        
        # Get embeddings for each chunk (will be cached)
        for chunk_text, _ in tqdm(chunks_with_meta, desc=f"Warming cache for {filename}"):
            await rag.create_embeddings(chunk_text)
    
    # Save the cache
    await rag.save_embeddings_cache()
    
    # Print statistics
    cache_size_after = len(rag.state.embeddings_cache)
    new_entries = cache_size_after - cache_size_before
    elapsed = time.time() - start_time
    
    print(f"\nCache warming completed in {elapsed:.2f} seconds")
    print(f"Cache size before: {cache_size_before} entries")
    print(f"Cache size after: {cache_size_after} entries")
    print(f"New entries added: {new_entries} entries")
    
    # Clean up
    await rag.cleanup_rag()

if __name__ == "__main__":
    asyncio.run(warm_cache()) 