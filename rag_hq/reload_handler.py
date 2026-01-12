"""
Hot reload handler for RAG database updates.

Allows the worker to reload the database without restarting when new documents are ingested.
"""
import os
import asyncio
import logging
import signal
from typing import Optional

from .state import state
from .database_operations import load_vector_database

logger = logging.getLogger("rag-assistant-enhanced")

# Global flag for reload request
_reload_requested = False
_reload_lock = asyncio.Lock()


def request_reload():
    """Request a database reload (can be called from signal handler)."""
    global _reload_requested
    _reload_requested = True
    logger.info("📥 Database reload requested")


async def check_and_reload():
    """Check if reload is requested and perform it."""
    global _reload_requested
    
    if not _reload_requested:
        return False
    
    async with _reload_lock:
        if not _reload_requested:  # Double-check after acquiring lock
            return False
        
        logger.info("=" * 60)
        logger.info("🔄 RELOADING RAG DATABASE")
        logger.info("=" * 60)
        
        try:
            # Reload the database
            success = await load_vector_database(skip_build_if_missing=True)
            
            if success:
                logger.info("✓ Database reloaded successfully")
                if state.annoy_index:
                    num_vectors = state.annoy_index.index.get_n_items()
                    num_chunks = len(state.chunks_metadata)
                    logger.info(f"  New stats: {num_vectors:,} vectors, {num_chunks:,} chunks")
                logger.info("=" * 60)
                _reload_requested = False
                return True
            else:
                logger.error("✗ Database reload failed")
                logger.info("=" * 60)
                return False
                
        except Exception as e:
            logger.error(f"✗ Error reloading database: {e}")
            logger.info("=" * 60)
            return False


async def periodic_reload_check(interval=60):
    """Periodically check if database needs reloading.
    
    This is a fallback if signal-based reloading isn't working.
    Checks for changes to the database files on disk.
    """
    from .config import VECTOR_DB_PATH, METADATA_PATH
    import aiofiles.os
    
    last_db_mtime = 0
    last_meta_mtime = 0
    
    logger.info(f"Started periodic reload check (every {interval}s)")
    
    while True:
        try:
            await asyncio.sleep(interval)
            
            # Check if database files have been modified
            if await aiofiles.os.path.exists(VECTOR_DB_PATH):
                stat = await aiofiles.os.stat(VECTOR_DB_PATH)
                db_mtime = stat.st_mtime
                
                if last_db_mtime > 0 and db_mtime > last_db_mtime:
                    logger.info(f"📝 Database file updated on disk (mtime: {db_mtime})")
                    request_reload()
                
                last_db_mtime = db_mtime
            
            if await aiofiles.os.path.exists(METADATA_PATH):
                stat = await aiofiles.os.stat(METADATA_PATH)
                meta_mtime = stat.st_mtime
                
                if last_meta_mtime > 0 and meta_mtime > last_meta_mtime:
                    logger.info(f"📝 Metadata file updated on disk (mtime: {meta_mtime})")
                    request_reload()
                
                last_meta_mtime = meta_mtime
            
            # If reload was requested, perform it
            if _reload_requested:
                await check_and_reload()
                
        except asyncio.CancelledError:
            logger.info("Periodic reload check stopped")
            break
        except Exception as e:
            logger.error(f"Error in periodic reload check: {e}")


def setup_signal_handlers():
    """Setup signal handlers for database reload.
    
    Send SIGUSR1 to the worker process to trigger a reload:
        kill -SIGUSR1 <pid>
    """
    def handle_reload_signal(signum, frame):
        """Handle reload signal."""
        logger.info(f"Received signal {signum}, requesting database reload...")
        request_reload()
    
    try:
        # SIGUSR1 for reload
        signal.signal(signal.SIGUSR1, handle_reload_signal)
        logger.info("✓ Signal handler installed: kill -SIGUSR1 <pid> to reload database")
        return True
    except (AttributeError, ValueError) as e:
        logger.warning(f"Could not setup signal handlers: {e}")
        return False
