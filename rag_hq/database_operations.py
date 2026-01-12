"""
Database building and loading operations.
"""
import os
import time
import asyncio
import pickle
import logging
import shutil
import aiofiles
import aiofiles.os

from .config import (
    VECTOR_DB_PATH, METADATA_PATH, UPLOADS_FOLDER, BATCH_SIZE_FILES,
    LLAMA_SERVER_URL, DOCUMENT_TEXTS_DIR, VECTOR_DIM, VECTOR_DB_FOLDER
)
from .state import state
from .vector_index import EnhancedAnnoyIndex, validate_index, copy_index_efficiently
from .text_processing import initialize_spacy
from .embeddings import get_http_session, load_embeddings_cache, save_embeddings_cache
from .document_management import load_document_summaries, save_document_summaries, update_ingestion_rapport
from .database import (
    load_processed_files, save_processed_files, check_for_new_files,
    process_file, cleanup_temp_files, log_progress
)
from .bm25_index import BM25Index

logger = logging.getLogger("rag-assistant-enhanced")

BM25_INDEX_PATH = os.path.join(VECTOR_DB_FOLDER, "bm25_index.pkl")


async def build_vector_database():
    """Build the vector database from documents in the uploads folder."""
    logger.info("=" * 60)
    logger.info("STARTING VECTOR DATABASE BUILD")
    logger.info("=" * 60)
    log_progress("Building vector database...", "progress")
    
    # Check if llama-server is running
    logger.info(f"Checking llama-server connectivity at {LLAMA_SERVER_URL}...")
    try:
        session = await get_http_session()
        async with session.get(LLAMA_SERVER_URL.rsplit('/', 1)[0]) as response:
            if response.status != 200:
                logger.error("✗ Cannot build vector database: llama-server is not responding")
                logger.error(f"  Server returned status: {response.status}")
                return False
            else:
                logger.info(f"✓ Llama-server is accessible and responding")
    except Exception as e:
        logger.error(f"✗ Cannot build vector database: llama-server is not accessible: {e}")
        logger.error(f"  Make sure llama-server is running: systemctl status llama-server.service")
        return False
    
    # Initialize spaCy
    await initialize_spacy()
    
    # Load caches
    await load_processed_files()
    await load_embeddings_cache()
    await load_document_summaries()
    
    # Check if document text directory exists
    if not os.path.exists(DOCUMENT_TEXTS_DIR):
        os.makedirs(DOCUMENT_TEXTS_DIR, exist_ok=True)
        logger.info(f"Created document texts directory at {DOCUMENT_TEXTS_DIR}")
    
    # Load existing index and data if available
    has_existing_data = False
    if await aiofiles.os.path.exists(VECTOR_DB_PATH) and await aiofiles.os.path.exists(METADATA_PATH):
        try:
            state.annoy_index = await EnhancedAnnoyIndex.load_async(VECTOR_DB_PATH, state.executor)
            async with aiofiles.open(METADATA_PATH, "rb") as f:
                state.chunks_metadata = pickle.loads(await f.read())
            logger.info(f"Loaded existing vector database with {len(state.chunks_metadata)} entries")
            has_existing_data = True
        except Exception as e:
            logger.error(f"Error loading existing database, will create new one: {e}")
            has_existing_data = False
    
    # If no existing data, create a new index
    if not has_existing_data:
        state.annoy_index = EnhancedAnnoyIndex(VECTOR_DIM)
        state.chunks_metadata = {}
        logger.info("Created new vector database")
    
    # Check for new or modified files first
    new_or_modified = await check_for_new_files()
    
    # Special case: If database is empty but files exist, force reprocessing
    if not new_or_modified:
        if state.annoy_index and state.annoy_index.index.get_n_items() == 0:
            # Database is empty, check if there are ANY files to process
            if await aiofiles.os.path.exists(UPLOADS_FOLDER):
                all_files = await aiofiles.os.listdir(UPLOADS_FOLDER)
                doc_files = [f for f in all_files if not f.startswith('.') and 
                           os.path.isfile(os.path.join(UPLOADS_FOLDER, f))]
                if doc_files:
                    logger.warning("⚠️  Database is empty but documents exist!")
                    logger.warning(f"   Found {len(doc_files)} documents that should be processed")
                    logger.warning("   Forcing reprocess (clearing history)...")
                    state.processed_files.clear()  # Clear history to force reprocess
                    await save_processed_files()
                    new_or_modified = doc_files
                    logger.info(f"✓ Will reprocess all {len(new_or_modified)} documents")
        
        if not new_or_modified:
            logger.info("No new or modified files found, skipping rebuild")
            state.rag_enabled = True
            return True
    
    log_progress(f"Found {len(new_or_modified)} new or modified files to process", "info")
    for i, filename in enumerate(new_or_modified, 1):
        log_progress(f"  {i}. {filename}", "file")
    
    # Start ingestion rapport
    rapport = {
        "status": "in_progress",
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": None,
        "total_files": len(new_or_modified),
        "files_processed": 0,
        "files_failed": 0,
        "files_skipped": 0,
        "files": {filename: {"status": "pending"} for filename in new_or_modified}
    }
    await update_ingestion_rapport(rapport)
    
    # Mark that we're in ingestion mode
    state.is_ingesting = True
    logger.info("Entering ingestion mode - cleaning up stale vectors and adding new ones")
    
    # Create a new index for the build process
    new_annoy_index = EnhancedAnnoyIndex(VECTOR_DIM)
    
    # Identify which files still exist on disk
    existing_files = set()
    if os.path.exists(UPLOADS_FOLDER):
        existing_files = {f for f in os.listdir(UPLOADS_FOLDER) if os.path.isfile(os.path.join(UPLOADS_FOLDER, f))}
    
    # Clean up processing history for deleted files
    # This fixes the issue where re-uploading a deleted file might be skipped
    history_cleaned = 0
    if state.processed_files:
        files_to_remove_from_history = [f for f in state.processed_files if f not in existing_files]
        for f in files_to_remove_from_history:
            del state.processed_files[f]
            history_cleaned += 1
        
        if history_cleaned > 0:
            logger.info(f"🗑️  Removed {history_cleaned} deleted files from processing history")

    # Filter metadata: Keep only chunks whose source files still exist
    new_chunks_metadata = {}
    stale_count = 0
    for chunk_id, chunk_data in state.chunks_metadata.items():
        source_file = chunk_data.get('metadata', {}).get('filename')
        if source_file in existing_files:
            new_chunks_metadata[chunk_id] = chunk_data
        else:
            stale_count += 1
            
    if stale_count > 0:
        logger.info(f"🧹 Removing {stale_count} stale chunks from deleted files")

    # Initialize BM25 index
    new_bm25_index = BM25Index()
    
    # Only copy items that are still in our filtered metadata
    copied = 0
    if state.annoy_index and state.annoy_index.index.get_n_items() > 0:
        total_items = state.annoy_index.index.get_n_items()
        for j in range(total_items):
            uuid_str = state.annoy_index.uuid_map.get(j)
            if uuid_str in new_chunks_metadata:
                vector = state.annoy_index.index.get_item_vector(j)
                new_annoy_index.add_item(uuid_str, vector)
                new_bm25_index.add_document(uuid_str, new_chunks_metadata[uuid_str]['text'])
                copied += 1
        logger.info(f"✓ Carried forward {copied} active vectors (skipped {total_items - copied} deleted ones)")

    # Process files concurrently in batches
    files_processed = 0
    batch_size = BATCH_SIZE_FILES
    
    # Calculate how many files were removed
    files_removed_count = 0
    if state.annoy_index:
        current_db_files = set()
        for chunk_data in state.chunks_metadata.values():
            fname = chunk_data.get('metadata', {}).get('filename')
            if fname:
                current_db_files.add(fname)
        
        # Files that are in DB but NOT on disk
        files_removed_count = len(current_db_files - existing_files)

    try:
        for i in range(0, len(new_or_modified), batch_size):
            batch = new_or_modified[i:i+batch_size]
            batch_tasks = []
            
            for filename in batch:
                file_path = os.path.join(UPLOADS_FOLDER, filename)
                # NOTE: process_file now handles saving after each document
                batch_tasks.append(process_file(file_path, filename, new_annoy_index, new_chunks_metadata, rapport, new_bm25_index))
            
            results = await asyncio.gather(*batch_tasks)
            files_processed += sum(1 for r in results if r)
            
            # Log batch completion
            processed_so_far = rapport.get('files_processed', 0) + rapport.get('files_failed', 0) + rapport.get('files_skipped', 0)
            log_progress(f"Batch complete: {processed_so_far}/{len(new_or_modified)} files processed", "info")
        
        # Show final summary
        files_succeeded = rapport.get('files_processed', 0)
        files_failed = rapport.get('files_failed', 0)
        files_skipped = rapport.get('files_skipped', 0)
        log_progress(f"Ingestion complete: ✓{files_succeeded} ✗{files_failed} ⊠{files_skipped} of {len(new_or_modified)} files", "info")
        
        # Final save if files were processed OR removed
        if files_processed > 0 or files_removed_count > 0:
            logger.info(f"Database update needed: {files_processed} new/modified, {files_removed_count} removed")
            
            # NOW build the index (only once, after all documents processed)
            logger.info("Building Annoy index with 50 trees...")
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(state.executor, new_annoy_index.build, 50)
            logger.info("✓ Index build complete")
            
            # Swap state and save
            async with state.lock:
                old_index = state.annoy_index
                old_metadata = state.chunks_metadata
                old_bm25 = state.bm25_index
                
                state.annoy_index = new_annoy_index
                state.chunks_metadata = new_chunks_metadata
                state.bm25_index = new_bm25_index
                logger.info(f"✓ BM25 index built with {new_bm25_index.get_num_docs()} documents")
                
                # Save to disk
                from .database import save_database
                save_success = await save_database()
                
                if not save_success:
                    logger.error("Failed to save database, rolling back")
                    state.annoy_index = old_index
                    state.chunks_metadata = old_metadata
                    state.bm25_index = old_bm25
                    raise Exception("Database save failed")
                
                # FORCE UPDATE TIMESTAMP for hot-reload
                # Even if save_database does it, let's be explicit to ensure OS registers change
                try:
                    os.utime(VECTOR_DB_PATH, None)
                    logger.info("✓ Forced timestamp update on database file for hot-reload")
                except Exception as e:
                    logger.warning(f"Could not touch database file: {e}")
                
                logger.info("✓ Database saved to disk")
            
            await save_processed_files()
            await save_embeddings_cache()
            await save_document_summaries()
            
            num_vectors = state.annoy_index.index.get_n_items()
            logger.info(f"✅ Vector database build complete:")
            logger.info(f"   - {num_vectors:,} vectors in index")
            logger.info(f"   - {len(state.chunks_metadata):,} chunks")
            rapport['status'] = 'completed'
        else:
            logger.info("No changes needed (no new files, no deletions), index remains unchanged")
            if history_cleaned > 0:
                await save_processed_files()
                logger.info("✓ Updated processing history to reflect deletions")
            rapport['status'] = 'completed_no_changes'
            
        state.rag_enabled = True
        rapport['end_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
        await update_ingestion_rapport(rapport)
        return True
    
    except Exception as e:
        logger.error(f"Error during vector database build: {e}")
        rapport.update({"status": "failed", "error": str(e), "end_time": time.strftime("%Y-%m-%d %H:%M:%S")})
        await update_ingestion_rapport(rapport)
        return False
    finally:
        # Exit ingestion mode
        state.is_ingesting = False


async def load_vector_database(skip_build_if_missing=False):
    """Load the vector database if it exists.
    
    Args:
        skip_build_if_missing: If True, don't build database if missing (load-only mode).
                              Use True for worker startup to avoid blocking.
                              Use False for manual ingestion script.
    """
    try:
        logger.info("=" * 60)
        logger.info("CHECKING FOR EXISTING VECTOR DATABASE")
        logger.info("=" * 60)
        
        db_exists = await aiofiles.os.path.exists(VECTOR_DB_PATH)
        meta_exists = await aiofiles.os.path.exists(METADATA_PATH)
        
        logger.info(f"Vector DB file exists: {db_exists} ({VECTOR_DB_PATH})")
        logger.info(f"Metadata file exists: {meta_exists} ({METADATA_PATH})")
        
        if db_exists and meta_exists:
            logger.info("✓ Found existing database - loading...")
            
            # Record modification time for hot-reloading (use integer for robust comparison)
            stat = os.stat(VECTOR_DB_PATH)
            state.last_db_modified_time = int(stat.st_mtime)
            logger.info(f"📊 Database timestamp recorded: {state.last_db_modified_time}")
            
            state.annoy_index = await EnhancedAnnoyIndex.load_async(VECTOR_DB_PATH, state.executor)
            async with aiofiles.open(METADATA_PATH, "rb") as f:
                state.chunks_metadata = pickle.loads(await f.read())
            
            # Load BM25 index if it exists
            if await aiofiles.os.path.exists(BM25_INDEX_PATH):
                async with aiofiles.open(BM25_INDEX_PATH, "rb") as f:
                    state.bm25_index = pickle.loads(await f.read())
                logger.info(f"✓ Loaded BM25 index with {state.bm25_index.get_num_docs()} documents")
            else:
                logger.warning("⚠️  BM25 index not found - hybrid search will be disabled")
                state.bm25_index = None
            
            num_vectors = state.annoy_index.index.get_n_items()
            num_chunks = len(state.chunks_metadata)
            logger.info(f"✓ Successfully loaded vector database:")
            logger.info(f"  - {num_vectors:,} vectors in index")
            logger.info(f"  - {num_chunks:,} chunks with metadata")
            
            # Load caches
            await load_embeddings_cache()
            
            state.rag_enabled = True
            logger.info("=" * 60)
            logger.info("RAG DATABASE READY FOR QUERIES")
            logger.info("=" * 60)
            return True
        else:
            logger.warning("=" * 60)
            logger.warning("⚠️  NO EXISTING DATABASE FOUND")
            logger.warning("=" * 60)
            logger.warning("Database files missing:")
            if not db_exists:
                logger.warning(f"  ✗ Vector DB: {VECTOR_DB_PATH}")
            if not meta_exists:
                logger.warning(f"  ✗ Metadata: {METADATA_PATH}")
            
            if skip_build_if_missing:
                logger.warning("=" * 60)
                logger.warning("LOAD-ONLY MODE: Skipping automatic build")
                logger.warning("To build database, run: python ingest_documents.py")
                logger.warning("=" * 60)
                state.rag_enabled = False  # Disable RAG until database is built
                return False
            else:
                logger.info("Starting fresh database build from documents...")
                logger.info("=" * 60)
                return await build_vector_database()
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"✗ FAILED TO LOAD VECTOR DATABASE: {e}")
        logger.error("=" * 60)
        return False


async def update_database_periodically():
    """Periodically check for new files and update the vector database."""
    from .config import UPDATE_INTERVAL
    
    logger.info(f"Starting periodic database update (every {UPDATE_INTERVAL} seconds)")
    
    while True:
        try:
            await asyncio.sleep(UPDATE_INTERVAL)
            
            # Check if enough time has passed since last check
            current_time = time.time()
            if current_time - state.last_update_check < UPDATE_INTERVAL:
                continue
            
            state.last_update_check = current_time
            
            # Check for new files first
            new_or_modified = await check_for_new_files()
            
            if not new_or_modified:
                logger.debug("No new files found during periodic check")
                continue
            
            logger.info(f"Found {len(new_or_modified)} new/modified files during periodic check")
            
            # Build/update the database
            await build_vector_database()
            
        except asyncio.CancelledError:
            logger.info("Update task cancelled")
            break
        except Exception as e:
            logger.error(f"Error during periodic update: {e}")
