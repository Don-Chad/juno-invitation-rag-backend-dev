"""
Vector database building, loading, and saving functionality.
"""
import os
import time
import uuid
import asyncio
import hashlib
import pickle
import logging
import glob
import numpy as np
import aiofiles
import aiofiles.os

from .config import (
    UPLOADS_FOLDER, VECTOR_DB_PATH, METADATA_PATH, FILE_HISTORY_PATH,
    VECTOR_DB_FOLDER, BATCH_SIZE_FILES, BATCH_SIZE_CHUNKS,
    CHUNK_BATCH_SIZE_NORMAL, INGESTION_DELAY, NORMAL_DELAY
)
from .state import state, save_document_text, get_document_text
from .vector_index import EnhancedAnnoyIndex, validate_index, copy_index_efficiently
from .text_processing import extract_text, smart_chunk_text
from .document_management import (
    generate_document_summary, save_document_summaries,
    update_ingestion_rapport
)
from .embeddings import create_embeddings, save_embeddings_cache, _embedding_cache_key

logger = logging.getLogger("rag-assistant-enhanced")


def log_progress(message, style="info"):
    """Log a progress message with visual formatting."""
    styles = {
        "info": "ℹ️",
        "success": "✓",
        "error": "✗",
        "warning": "⚠️",
        "progress": "⟳",
        "file": "📄",
        "chunk": "📦"
    }
    icon = styles.get(style, "•")
    logger.info(f"{icon} {message}")


async def get_file_hash(file_path):
    """Generate a hash for the file to detect changes asynchronously."""
    def _hash_file():
        try:
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            return file_hash
        except Exception as e:
            logger.error(f"Error generating hash for {file_path}: {e}")
            return None
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(state.executor, _hash_file)


async def get_file_info(file_path):
    """Get file metadata for tracking asynchronously."""
    try:
        stat = await aiofiles.os.stat(file_path)
        file_hash = await get_file_hash(file_path)
        return {
            'size': stat.st_size,
            'mtime': stat.st_mtime,
            'hash': file_hash
        }
    except Exception as e:
        logger.error(f"Error getting file info for {file_path}: {e}")
        return None


async def load_processed_files():
    """Load the history of processed files asynchronously."""
    try:
        if await aiofiles.os.path.exists(FILE_HISTORY_PATH):
            async with aiofiles.open(FILE_HISTORY_PATH, 'rb') as f:
                state.processed_files = pickle.loads(await f.read())
            logger.info(f"Loaded processing history for {len(state.processed_files)} files")
        else:
            state.processed_files = {}
            logger.info("No processing history found, starting fresh")
    except Exception as e:
        logger.error(f"Error loading file history: {e}")
        state.processed_files = {}


async def save_processed_files():
    """Save the history of processed files asynchronously."""
    try:
        async with aiofiles.open(FILE_HISTORY_PATH, 'wb') as f:
            await f.write(pickle.dumps(state.processed_files))
        logger.debug(f"Saved processing history for {len(state.processed_files)} files")
    except Exception as e:
        logger.error(f"Error saving file history: {e}")


async def save_database():
    """Save the current index and metadata to disk."""
    try:
        if state.annoy_index is None or state.annoy_index.index.get_n_items() == 0:
            logger.warning("Cannot save empty database")
            return False
        
        logger.info("Saving database to disk...")
        
        # Save to temporary files first
        temp_db_path = VECTOR_DB_PATH + ".tmp"
        temp_map_path = temp_db_path + ".map"  # Map file created by save_async
        temp_metadata_path = METADATA_PATH + ".tmp"
        
        # Import BM25 path
        from .database_operations import BM25_INDEX_PATH
        temp_bm25_path = BM25_INDEX_PATH + ".tmp"
        
        # This creates both temp_db_path and temp_db_path.map
        await state.annoy_index.save_async(temp_db_path, state.executor)
        async with aiofiles.open(temp_metadata_path, "wb") as f:
            await f.write(pickle.dumps(state.chunks_metadata))
        
        # Save BM25 index if it exists
        if state.bm25_index is not None:
            async with aiofiles.open(temp_bm25_path, "wb") as f:
                await f.write(pickle.dumps(state.bm25_index))
        
        # Atomically swap ALL files (index, map, metadata, and bm25)
        await aiofiles.os.replace(temp_db_path, VECTOR_DB_PATH)
        await aiofiles.os.replace(temp_map_path, VECTOR_DB_PATH + ".map")  # FIX: Rename the map file too!
        await aiofiles.os.replace(temp_metadata_path, METADATA_PATH)
        if state.bm25_index is not None:
            await aiofiles.os.replace(temp_bm25_path, BM25_INDEX_PATH)
        
        logger.info(f"✓ Database saved: {state.annoy_index.index.get_n_items()} vectors, {len(state.chunks_metadata)} chunks")
        if state.bm25_index is not None:
            logger.info(f"  BM25 index: {state.bm25_index.get_num_docs()} documents")
        logger.debug(f"  Saved files: {VECTOR_DB_PATH}, {VECTOR_DB_PATH}.map, {METADATA_PATH}, {BM25_INDEX_PATH}")
        return True
    except Exception as e:
        logger.error(f"Error saving database: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


async def process_chunk(chunk_text, metadata, annoy_index_local, chunks_metadata_local, bm25_index_local=None):
    """Process a single chunk and add it to the index."""
    from .text_processing import clean_text_for_embedding
    
    chunk_id = str(uuid.uuid4())
    
    # Clean text before embedding (remove TOC artifacts, excessive dots, etc.)
    chunk_text_cleaned = clean_text_for_embedding(chunk_text)
    
    # Create embedding for chunk text ONLY (not summaries or metadata)
    embedding = await create_embeddings(chunk_text_cleaned)
    if not np.any(embedding):
        chunk_idx = metadata.get('chunk_index', '?')
        filename = metadata.get('filename', '?')
        logger.error(f"❌ CHUNK EMBEDDING FAILED: Chunk {chunk_idx} from {filename} - got empty vector")
        logger.error(f"   Chunk length: {len(chunk_text)} chars, ~{len(chunk_text)//4} tokens")
        logger.error(f"   Preview: {chunk_text[:150]}...")
        return False
    
    # Add to Annoy index (thread-safe with lock)
    async with state.lock:
        annoy_index_local.add_item(chunk_id, embedding)
        
        chunks_metadata_local[chunk_id] = {
            'text': chunk_text,
            'metadata': metadata,
            'embedding_hash': _embedding_cache_key(chunk_text)
        }
        
        # Add to BM25 index if provided
        if bm25_index_local is not None:
            bm25_index_local.add_document(chunk_id, chunk_text)
    
    return True


async def process_file(file_path, filename, annoy_index_local, chunks_metadata_local, rapport, bm25_index_local=None):
    """Process a single file and add it to the index."""
    try:
        # Calculate progress numbers
        file_num = rapport.get('files_processed', 0) + rapport.get('files_failed', 0) + rapport.get('files_skipped', 0) + 1
        total_files = rapport.get('total_files', '?')
        
        # Get file info for tracking
        file_info = await get_file_info(file_path)
        if file_info is None:
            raise Exception("Failed to get file info")
        
        # Skip if file was already processed and hasn't changed
        if filename in state.processed_files:
            old_info = state.processed_files[filename]
            if (old_info['size'] == file_info['size'] and 
                old_info['mtime'] == file_info['mtime'] and
                old_info['hash'] == file_info['hash']):
                log_progress(f"[{file_num}/{total_files}] Skipping {filename} (unchanged)", "info")
                rapport['files'][filename] = {'status': 'skipped', 'reason': 'unchanged'}
                rapport['files_skipped'] = rapport.get('files_skipped', 0) + 1
                await update_ingestion_rapport(rapport)
                return False
        
        log_progress(f"[{file_num}/{total_files}] Processing: {filename}", "file")
        
        # Extract text from file
        text = await extract_text(file_path)
        if not text:
            raise Exception("No text extracted from file")
        
        # Store document text to disk for lazy loading
        await save_document_text(filename, text)
        
        # Register the document in our tracking system
        state.document_texts[filename] = text
        
        # Generate document summary
        await generate_document_summary(filename, text)
        
        # Smart chunking with metadata
        chunks_with_meta = await smart_chunk_text(text, filename)
        log_progress(f"[{file_num}/{total_files}] Generated {len(chunks_with_meta)} chunks from {filename}", "chunk")
        
        # Update rapport
        rapport['files'][filename] = {
            'status': 'processing',
            'total_chunks': len(chunks_with_meta),
            'chunks_processed': 0,
            'start_time': time.strftime("%Y-%m-%d %H:%M:%S")
        }
        await update_ingestion_rapport(rapport)
        
        # Process chunks in smaller batches
        chunk_batch_size = BATCH_SIZE_CHUNKS if state.is_ingesting else CHUNK_BATCH_SIZE_NORMAL
        chunks_processed = 0
        chunks_failed = 0
        
        for i in range(0, len(chunks_with_meta), chunk_batch_size):
            chunk_batch = chunks_with_meta[i:i+chunk_batch_size]
            chunk_tasks = []
            
            for chunk_text, metadata in chunk_batch:
                chunk_tasks.append(process_chunk(chunk_text, metadata, annoy_index_local, chunks_metadata_local, bm25_index_local))
            
            results = await asyncio.gather(*chunk_tasks, return_exceptions=True)
            
            # Count successes and failures
            for result in results:
                if isinstance(result, Exception):
                    chunks_failed += 1
                    logger.error(f"Chunk processing failed: {result}")
                elif result:
                    chunks_processed += 1
            
            # Update rapport and log progress
            rapport['files'][filename]['chunks_processed'] = chunks_processed
            if chunks_failed > 0:
                rapport['files'][filename]['chunks_failed'] = chunks_failed
            
            # Small delay between batches to avoid overwhelming server
            if i + chunk_batch_size < len(chunks_with_meta):
                await asyncio.sleep(0.05)  # 50ms delay between batches
            await update_ingestion_rapport(rapport)
            
            # Log chunk progress every batch
            progress_pct = (chunks_processed / len(chunks_with_meta)) * 100
            log_progress(f"[{file_num}/{total_files}] {filename}: {chunks_processed}/{len(chunks_with_meta)} chunks ({progress_pct:.0f}%)", "progress")
            
            # Delay between batches
            if i + chunk_batch_size < len(chunks_with_meta):
                delay = INGESTION_DELAY if state.is_ingesting else NORMAL_DELAY
                await asyncio.sleep(delay)
        
        # Add document summary as a special searchable chunk
        if filename in state.document_summaries:
            summary_data = state.document_summaries[filename]
            # Summary text WITHOUT keywords (keywords will be in metadata)
            summary_text = f"Document: {filename}\n\n"
            summary_text += f"Summary: {summary_data.get('summary', '')}"
            
            # Add keywords as structured metadata tags
            summary_metadata = {
                'filename': filename,
                'chunk_index': -1,  # Special marker for summary chunks
                'chunk_type': 'summary',
                'start_sentence': 0,
                'estimated_tokens': len(summary_text) // 4,
                'keywords': summary_data.get('keywords', []),  # Add keywords as metadata
                'extended_keywords': summary_data.get('extended_keywords', [])  # Add extended keywords
            }
            
            # Add summary chunk to index
            summary_success = await process_chunk(summary_text, summary_metadata, annoy_index_local, chunks_metadata_local, bm25_index_local)
            if summary_success:
                chunks_processed += 1
                logger.info(f"✓ Added document summary chunk for {filename} (keywords in metadata)")
        
        # Mark file as processed only if majority of chunks succeeded
        if chunks_processed > chunks_failed:
            state.processed_files[filename] = file_info
            rapport['files'][filename]['status'] = 'completed'
            rapport['files'][filename]['end_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
            rapport['files_processed'] = rapport.get('files_processed', 0) + 1
            log_progress(f"[{file_num}/{total_files}] ✓ Completed {filename}: {chunks_processed} chunks ({chunks_failed} failed)", "success")
            
            # Mark file as processed and save history
            # NOTE: We DON'T save the full database here anymore to avoid building index multiple times
            # The index will be built and saved once at the end of all processing
            logger.info(f"✓ Chunks added to index (will be saved after all files processed)")
            
            await save_processed_files()
            await save_embeddings_cache()
            await save_document_summaries()
        else:
            raise Exception(f"Too many chunk failures: {chunks_failed}/{len(chunks_with_meta)}")
        
        await update_ingestion_rapport(rapport)
        return True
        
    except Exception as e:
        file_num = rapport.get('files_processed', 0) + rapport.get('files_failed', 0) + rapport.get('files_skipped', 0) + 1
        total_files = rapport.get('total_files', '?')
        
        rapport['files'][filename] = {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__,
            'timestamp': time.strftime("%Y-%m-%d %H:%M:%S")
        }
        rapport['files_failed'] = rapport.get('files_failed', 0) + 1
        await update_ingestion_rapport(rapport)
        log_progress(f"[{file_num}/{total_files}] ✗ Failed to process {filename}: {e}", "error")
        return False


async def check_for_new_files():
    """Check for new or modified files in the uploads folder."""
    new_or_modified = []
    
    try:
        if not await aiofiles.os.path.exists(UPLOADS_FOLDER):
            logger.error(f"Uploads folder not found: {UPLOADS_FOLDER}")
            return []
        
        files = await aiofiles.os.listdir(UPLOADS_FOLDER)
        
        # Check each file concurrently
        check_tasks = []
        for filename in files:
            file_path = os.path.join(UPLOADS_FOLDER, filename)
            check_tasks.append(check_file_status(file_path, filename))
        
        results = await asyncio.gather(*check_tasks)
        new_or_modified = [f for f in results if f is not None]
        
        return new_or_modified
    except Exception as e:
        logger.error(f"Error checking for new files: {e}")
        return []


async def check_file_status(file_path, filename):
    """Check if a file is new or modified."""
    if await aiofiles.os.path.isdir(file_path):
        return None
    
    file_info = await get_file_info(file_path)
    if file_info is None:
        return None
    
    if filename not in state.processed_files:
        return filename
    else:
        old_info = state.processed_files[filename]
        if (old_info['size'] != file_info['size'] or 
            old_info['mtime'] != file_info['mtime'] or
            old_info['hash'] != file_info['hash']):
            return filename
    
    return None


async def cleanup_temp_files():
    """Clean up any leftover temporary files from previous runs."""
    temp_patterns = [
        VECTOR_DB_PATH + ".tmp*",
        METADATA_PATH + ".tmp*",
    ]
    
    cleaned = 0
    for pattern in temp_patterns:
        for temp_file in glob.glob(pattern):
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    cleaned += 1
                    logger.info(f"Cleaned up temporary file: {temp_file}")
            except Exception as e:
                logger.warning(f"Could not remove {temp_file}: {e}")
    
    if cleaned > 0:
        logger.info(f"Cleaned up {cleaned} temporary files")
