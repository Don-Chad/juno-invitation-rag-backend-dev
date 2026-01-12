#!/usr/bin/env python3
"""
RAG Database Rebuild Script

This script completely rebuilds the RAG vector database from scratch.
Use this when you have new documents or want to force a complete reingest.

Usage:
    python rebuild_rag_database.py              # Rebuild with existing history
    python rebuild_rag_database.py --fresh      # Delete history and rebuild everything
    python rebuild_rag_database.py --clear-all  # Delete ALL database files and rebuild
"""

import asyncio
import os
import sys
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("rebuild-script")

# Import RAG module
from rag_hq import build_vector_database, initialize_rag, cleanup_rag
from rag_hq.config import VECTOR_DB_FOLDER, FILE_HISTORY_PATH, VECTOR_DB_PATH, METADATA_PATH
from rag_hq.database_operations import BM25_INDEX_PATH


def delete_file_if_exists(filepath, description):
    """Delete a file if it exists and log the action."""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            logger.info(f"✓ Deleted {description}: {filepath}")
            return True
        except Exception as e:
            logger.error(f"✗ Failed to delete {description}: {e}")
            return False
    else:
        logger.info(f"  {description} not found (already clean)")
        return True


async def rebuild_database(fresh_start=False, clear_all=False):
    """
    Rebuild the RAG vector database.
    
    Args:
        fresh_start: If True, delete file_history.pkl to force reprocessing all documents
        clear_all: If True, delete ALL database files (complete fresh start)
    """
    logger.info("=" * 80)
    logger.info("RAG DATABASE REBUILD SCRIPT")
    logger.info("=" * 80)
    
    # Check if vector DB folder exists
    if not os.path.exists(VECTOR_DB_FOLDER):
        logger.info(f"Creating vector database folder: {VECTOR_DB_FOLDER}")
        os.makedirs(VECTOR_DB_FOLDER, exist_ok=True)
    
    # Handle fresh start options
    if clear_all:
        logger.info("")
        logger.info("🗑️  CLEAR ALL MODE: Deleting all database files...")
        logger.info("-" * 80)
        
        # Delete all database files
        files_to_delete = [
            (VECTOR_DB_PATH, "Vector database"),
            (VECTOR_DB_PATH + ".map", "Vector database map"),
            (METADATA_PATH, "Chunks metadata"),
            (BM25_INDEX_PATH, "BM25 index"),
            (FILE_HISTORY_PATH, "File history"),
            (os.path.join(VECTOR_DB_FOLDER, "embeddings_cache.npy.npy"), "Embeddings cache"),
            (os.path.join(VECTOR_DB_FOLDER, "embeddings_cache.npy"), "Embeddings cache (alt)"),
            (os.path.join(VECTOR_DB_FOLDER, "document_summaries.pkl"), "Document summaries"),
            (os.path.join(VECTOR_DB_FOLDER, ".ingestionrapport.json"), "Ingestion report"),
        ]
        
        for filepath, description in files_to_delete:
            delete_file_if_exists(filepath, description)
        
        # Delete document texts directory
        doc_texts_dir = os.path.join(VECTOR_DB_FOLDER, "document_texts")
        if os.path.exists(doc_texts_dir):
            import shutil
            try:
                shutil.rmtree(doc_texts_dir)
                logger.info(f"✓ Deleted document texts directory")
            except Exception as e:
                logger.error(f"✗ Failed to delete document texts directory: {e}")
        
        logger.info("-" * 80)
        logger.info("✓ All database files cleared")
        logger.info("")
        
    elif fresh_start:
        logger.info("")
        logger.info("🔄 FRESH START MODE: Clearing file history...")
        logger.info("-" * 80)
        delete_file_if_exists(FILE_HISTORY_PATH, "File history")
        logger.info("-" * 80)
        logger.info("✓ File history cleared - all documents will be reprocessed")
        logger.info("")
    
    # Initialize RAG components (spaCy, caches, etc.)
    logger.info("Initializing RAG components...")
    from rag_hq.text_processing import initialize_spacy
    from rag_hq.embeddings import load_embeddings_cache, get_http_session
    from rag_hq.database import load_processed_files
    from rag_hq.document_management import load_document_summaries
    from rag_hq.config import LLAMA_SERVER_URL
    
    # Check llama-server first
    logger.info(f"Checking llama-server at {LLAMA_SERVER_URL}...")
    try:
        session = await get_http_session()
        async with session.get(LLAMA_SERVER_URL.rsplit('/', 1)[0]) as response:
            if response.status != 200:
                logger.error("✗ Llama-server is not responding!")
                logger.error("  Make sure it's running: systemctl status llama-server.service")
                return False
            else:
                logger.info("✓ Llama-server is accessible")
    except Exception as e:
        logger.error(f"✗ Cannot connect to llama-server: {e}")
        logger.error("  Make sure it's running: systemctl status llama-server.service")
        return False
    
    await initialize_spacy()
    await load_processed_files()
    await load_embeddings_cache()
    await load_document_summaries()
    
    logger.info("")
    logger.info("=" * 80)
    logger.info("STARTING DATABASE BUILD")
    logger.info("=" * 80)
    logger.info("")
    
    # Build the database
    success = await build_vector_database()
    
    if success:
        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ DATABASE REBUILD COMPLETE")
        logger.info("=" * 80)
        logger.info("")
        logger.info("Next steps:")
        logger.info("  1. Restart your agent/worker to load the new database")
        logger.info("  2. Or send SIGUSR1 to trigger reload: kill -USR1 <pid>")
        logger.info("")
        return True
    else:
        logger.error("")
        logger.error("=" * 80)
        logger.error("✗ DATABASE REBUILD FAILED")
        logger.error("=" * 80)
        logger.error("")
        logger.error("Check the logs above for error details")
        logger.error("")
        return False


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Rebuild the RAG vector database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python rebuild_rag_database.py              # Rebuild (only new/modified files)
  python rebuild_rag_database.py --fresh      # Force reprocess all files
  python rebuild_rag_database.py --clear-all  # Complete fresh start (delete everything)
        """
    )
    
    parser.add_argument(
        '--fresh',
        action='store_true',
        help='Delete file history to force reprocessing all documents'
    )
    
    parser.add_argument(
        '--clear-all',
        action='store_true',
        help='Delete ALL database files for a complete fresh start'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.fresh and args.clear_all:
        logger.error("Error: Cannot use both --fresh and --clear-all")
        logger.error("Use --clear-all for complete fresh start, or --fresh to just reprocess files")
        sys.exit(1)
    
    # Run rebuild
    try:
        success = await rebuild_database(
            fresh_start=args.fresh,
            clear_all=args.clear_all
        )
        
        # Cleanup
        await cleanup_rag()
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Interrupted by user")
        await cleanup_rag()
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\n✗ Unexpected error: {e}", exc_info=True)
        await cleanup_rag()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

