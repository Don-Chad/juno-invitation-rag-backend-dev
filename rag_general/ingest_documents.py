#!/usr/bin/env python3
"""
Document Ingestion Script for RAG System

This script ingests documents into the RAG vector database.
Run this SEPARATELY from the worker to avoid blocking worker startup.

Usage:
    python ingest_documents.py              # Ingest all new/modified documents once
    python ingest_documents.py --watch      # Watch for new documents continuously
    python ingest_documents.py --force      # Force re-ingest all documents
    python ingest_documents.py --health     # Check system health first
"""
import asyncio
import sys
import argparse
import os
import time
import signal
import subprocess
from pathlib import Path

# Add project root to Python path so we can import rag_hq module
# This allows the script to be run from any directory with absolute path
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def notify_workers_to_reload():
    """Notify running worker processes to reload the database.
    
    Sends SIGUSR1 signal to all agent processes to trigger hot reload.
    """
    try:
        # Find worker processes
        result = subprocess.run(
            ['pgrep', '-f', 'agent_dev.py'],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            print(f"\n📢 Notifying {len(pids)} worker process(es) to reload database...")
            
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGUSR1)
                    print(f"  ✓ Sent reload signal to PID {pid}")
                except (ProcessLookupError, PermissionError) as e:
                    print(f"  ⚠️  Could not signal PID {pid}: {e}")
            
            print("✓ Worker(s) will reload database within 60 seconds")
            print("  (or immediately if using signal)")
        else:
            print("\nℹ️  No running worker processes found")
            print("   Workers will load new database on next start")
            
    except FileNotFoundError:
        print("\n⚠️  'pgrep' command not found, cannot notify workers")
        print("   Restart worker manually: systemctl restart agent_grace.service")
    except Exception as e:
        print(f"\n⚠️  Error notifying workers: {e}")
        print("   Restart worker manually if needed")


async def run_ingestion(force=False):
    """Run a single ingestion cycle."""
    try:
        from rag_hq import initialize_rag, run_health_check
        from rag_hq.database_operations import build_vector_database
        from rag_hq.state import state
    except ImportError as e:
        print(f"✗ Error importing RAG module: {e}")
        print("Make sure you're in the correct directory with rag_hq module")
        return False
    
    # Force re-ingest option
    if force:
        print("⚠️  Force mode: Clearing processing history...")
        from rag_hq.config import FILE_HISTORY_PATH
        if os.path.exists(FILE_HISTORY_PATH):
            os.remove(FILE_HISTORY_PATH)
            print("✓ Processing history cleared\n")
    
    try:
        # Load or build database
        from rag_hq.database_operations import load_vector_database
        
        # First load existing database if present
        await load_vector_database(skip_build_if_missing=False)
        
        # If no database was loaded, build it
        if not state.rag_enabled or state.annoy_index is None:
            print("\nNo database found, building from documents...")
            success = await build_vector_database()
            if not success:
                print("\n✗ Database build failed!")
                return False
        
        # Now check for new documents and ingest them
        print("\nChecking for new/modified documents...")
        success = await build_vector_database()
        
        if success:
            # Show detailed statistics
            if state.annoy_index:
                num_vectors = state.annoy_index.index.get_n_items()
                num_chunks = len(state.chunks_metadata)
                num_docs = len(state.processed_files)
                
                print(f"\n{'='*60}")
                print(f"✓ DATABASE UPDATE COMPLETE")
                print(f"{'='*60}")
                print(f"Vectors in index:    {num_vectors:,}")
                print(f"Chunks with metadata: {num_chunks:,}")
                print(f"Documents processed:  {num_docs}")
                
                # Calculate average chunks per document
                if num_docs > 0:
                    avg_chunks = num_chunks / num_docs
                    print(f"Avg chunks/document:  {avg_chunks:.1f}")
                
                # Check for failed embeddings (chunks with zero vectors)
                failed_count = num_chunks - num_vectors
                if failed_count > 0:
                    print(f"\n⚠️  WARNING: {failed_count} chunks failed to embed!")
                    print(f"   Check logs above for '❌ CHUNK EMBEDDING FAILED' messages")
                
                print(f"{'='*60}\n")
            
            # Notify running workers to reload database
            notify_workers_to_reload()
            
            return True
        else:
            print("\n✗ Ingestion failed! Check logs above for errors")
            return False
            
    except Exception as e:
        print(f"✗ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
        return False


async def watch_mode():
    """Watch for new documents and ingest them automatically."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print("✗ watchdog module not installed")
        print("Install with: pip install watchdog")
        sys.exit(1)
    
    print("=" * 60)
    print("📂 WATCH MODE: Monitoring for new documents")
    print("=" * 60)
    print(f"Watching: ./docs/")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    # Track last ingestion time to debounce
    last_ingestion = 0
    ingestion_cooldown = 60  # Wait 60 seconds between ingestions
    pending_files = set()
    
    class DocumentHandler(FileSystemEventHandler):
        def on_created(self, event):
            if event.is_directory:
                return
            
            # Only watch for document files
            ext = os.path.splitext(event.src_path)[1].lower()
            if ext in ['.pdf', '.docx', '.doc', '.txt', '.md']:
                filename = os.path.basename(event.src_path)
                pending_files.add(filename)
                print(f"📄 New file detected: {filename}")
        
        def on_modified(self, event):
            if event.is_directory:
                return
            
            ext = os.path.splitext(event.src_path)[1].lower()
            if ext in ['.pdf', '.docx', '.doc', '.txt', '.md']:
                filename = os.path.basename(event.src_path)
                pending_files.add(filename)
                print(f"📝 File modified: {filename}")
    
    # Setup file watcher
    event_handler = DocumentHandler()
    observer = Observer()
    observer.schedule(event_handler, "./docs", recursive=False)
    observer.start()
    
    print("✓ File watcher started")
    print()
    
    try:
        # Initial ingestion
        print("Running initial ingestion...")
        await run_ingestion(force=False)
        print()
        
        # Watch loop
        while True:
            await asyncio.sleep(10)  # Check every 10 seconds
            
            current_time = time.time()
            
            # If there are pending files and cooldown has passed
            if pending_files and (current_time - last_ingestion) >= ingestion_cooldown:
                print("=" * 60)
                print(f"🔄 Processing {len(pending_files)} changed file(s)...")
                print("=" * 60)
                
                success = await run_ingestion(force=False)
                
                if success:
                    print(f"✓ Ingestion complete")
                    pending_files.clear()
                    last_ingestion = current_time
                else:
                    print("⚠️  Ingestion failed, will retry on next cycle")
                
                print()
            elif pending_files:
                wait_time = int(ingestion_cooldown - (current_time - last_ingestion))
                print(f"⏳ {len(pending_files)} file(s) pending, waiting {wait_time}s before ingesting...")
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Stopping file watcher...")
        observer.stop()
        observer.join()
        print("✓ File watcher stopped")
        sys.exit(0)


async def main():
    parser = argparse.ArgumentParser(description='Ingest documents into RAG database')
    parser.add_argument('--watch', action='store_true', help='Watch for new documents continuously')
    parser.add_argument('--force', action='store_true', help='Force re-ingest all documents (clears history)')
    parser.add_argument('--health', action='store_true', help='Run health check before ingestion')
    args = parser.parse_args()
    
    print("=" * 60)
    print("RAG DOCUMENT INGESTION SCRIPT")
    print("=" * 60)
    
    # Import config to show current settings
    try:
        from rag_hq.config import (
            CHUNK_SIZE_TOKENS, MAX_CHUNK_SIZE_CHARS, CHUNK_OVERLAP_RATIO,
            MAX_EMBEDDING_TOKENS, EXTENDED_SUMMARY_TARGET_TOKENS,
            CHARS_PER_TOKEN
        )
        
        print(f"Chunk size: {CHUNK_SIZE_TOKENS} tokens (~{MAX_CHUNK_SIZE_CHARS} chars)")
        print(f"Extended summary: {EXTENDED_SUMMARY_TARGET_TOKENS} tokens (~{EXTENDED_SUMMARY_TARGET_TOKENS * CHARS_PER_TOKEN} chars)")
        print(f"Server limit: {MAX_EMBEDDING_TOKENS} tokens (configured max)")
        print(f"Overlap: {int(CHUNK_OVERLAP_RATIO * 100)}%")
        print(f"Chars per token: ~{CHARS_PER_TOKEN}")
    except ImportError:
        print("Configuration values from rag_hq.config")
    
    print("=" * 60)
    
    # Optional health check
    if args.health:
        from rag_hq import run_health_check
        print("\n🏥 Running health check...")
        result = await run_health_check()
        if result['overall_status'] not in ['healthy', 'degraded']:
            print(f"\n✗ Health check failed: {result['overall_status']}")
            print("Fix issues before ingesting documents")
            sys.exit(1)
        print("✓ Health check passed\n")
    
    # Watch mode - continuous monitoring
    if args.watch:
        await watch_mode()
        return
    
    # One-time ingestion mode
    print("Starting document ingestion...")
    print("This may take several minutes for large documents")
    print("=" * 60)
    print()
    
    try:
        success = await run_ingestion(force=args.force)
        
        if success:
            print("\n" + "=" * 60)
            print("✅ INGESTION COMPLETE")
            print("=" * 60)
            
            from rag_hq.state import state
            
            # Show detailed statistics
            if state.annoy_index:
                num_vectors = state.annoy_index.index.get_n_items()
                num_chunks = len(state.chunks_metadata)
                num_docs = len(state.processed_files)
                
                print(f"\n📊 DATABASE STATISTICS:")
                print(f"   Vectors in index:    {num_vectors:,}")
                print(f"   Chunks with metadata: {num_chunks:,}")
                print(f"   Documents processed:  {num_docs}")
                
                if num_docs > 0:
                    avg_chunks = num_chunks / num_docs
                    print(f"   Avg chunks/document:  {avg_chunks:.1f}")
                
                # Check for embedding failures
                failed_count = num_chunks - num_vectors
                if failed_count > 0:
                    print(f"\n   ⚠️  WARNING: {failed_count} chunks failed to embed")
                    print(f"      Search logs for '❌ CHUNK EMBEDDING FAILED'")
                else:
                    print(f"   ✅ All chunks successfully embedded")
            
            print("\n✓ You can now start the worker")
            print("  The worker will load this pre-built database quickly")
            print("\nTip: Use --watch to monitor for new documents automatically")
            sys.exit(0)
        else:
            print("\n✗ Ingestion failed! Check logs above for details")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Ingestion interrupted by user")
        print("Run the script again to complete ingestion")
        sys.exit(130)
    except Exception as e:
        print(f"\n✗ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Ensure we're in the right directory
    if not os.path.exists("./docs"):
        print("⚠️  Warning: ./docs folder not found")
        print("Make sure you're running this from the worker directory")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            sys.exit(1)
    
    asyncio.run(main())
