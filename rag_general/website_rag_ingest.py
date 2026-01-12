#!/usr/bin/env python3
"""
Website RAG Ingestion Module

Ingests scraped website text files into both:
1. Normal RAG vector database (rag_hq)
2. Q&A RAG vector database (rag_qa)

This script is designed to run after website_scraper.py completes.
It only processes the website text files, not the entire docs folder.

Usage:
    python website_rag_ingest.py              # Ingest all website files
    python website_rag_ingest.py --qa-only    # Only generate Q&A vectors
    python website_rag_ingest.py --rag-only   # Only generate RAG vectors
"""

import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime


# Paths
WEBSITES_FOLDER = "/root/workerv14_grace_rag/docs/websites"
DOCS_FOLDER = "/root/workerv14_grace_rag/docs"


async def ingest_to_rag_hq():
    """Ingest website files into the main RAG vector database."""
    print("\n" + "=" * 80)
    print("INGESTING WEBSITES TO RAG_HQ DATABASE")
    print("=" * 80)
    
    try:
        from rag_hq import initialize_rag
        from rag_hq.database_operations import build_vector_database, load_vector_database
        from rag_hq.state import state
        from rag_hq.config import DOCS_FOLDER as RAG_DOCS_FOLDER
        
        # The system already watches the docs folder, which includes docs/websites/
        # We just need to trigger a rebuild
        print(f"📂 Checking for new documents in: {RAG_DOCS_FOLDER}")
        print(f"   (includes websites subfolder: {WEBSITES_FOLDER})")
        
        # Load existing database first
        await load_vector_database(skip_build_if_missing=False)
        
        # Build/update database (will process new files only)
        print("\n🔄 Building/updating vector database...")
        success = await build_vector_database()
        
        if success:
            num_vectors = state.annoy_index.index.get_n_items() if state.annoy_index else 0
            num_chunks = len(state.chunks_metadata)
            num_docs = len(state.processed_files)
            
            print(f"\n✅ RAG_HQ database updated:")
            print(f"   Vectors: {num_vectors:,}")
            print(f"   Chunks: {num_chunks:,}")
            print(f"   Documents: {num_docs}")
            
            return True
        else:
            print("\n✗ Failed to build RAG_HQ database")
            return False
            
    except Exception as e:
        print(f"\n✗ Error ingesting to RAG_HQ: {e}")
        import traceback
        traceback.print_exc()
        return False


async def ingest_to_qa_database():
    """Generate Q&A pairs from website files and ingest into Q&A database."""
    print("\n" + "=" * 80)
    print("GENERATING Q&A PAIRS FOR WEBSITES")
    print("=" * 80)
    
    try:
        from rag_qa.document_loader import load_document
        from rag_qa.qa_generator import generate_qa_pairs, save_qa_pairs_to_file, count_tokens
        from rag_qa.document_splitter import create_chunks_with_overlap, get_chunk_title
        from rag_qa.deduplication import deduplicate_qa_pairs_llm
        from rag_qa import config
        from rag_qa.processing_report import ProcessingReport
        
        # Get all website text files
        if not os.path.exists(WEBSITES_FOLDER):
            print(f"✗ Websites folder not found: {WEBSITES_FOLDER}")
            return False
        
        website_files = [
            f for f in os.listdir(WEBSITES_FOLDER)
            if f.endswith('.txt') and f != 'scraping_history.json'
        ]
        
        if not website_files:
            print("ℹ️  No website files found to process")
            return True
        
        print(f"📋 Found {len(website_files)} website files to process")
        
        report = ProcessingReport()
        
        for idx, filename in enumerate(website_files, 1):
            filepath = os.path.join(WEBSITES_FOLDER, filename)
            
            print(f"\n[{idx}/{len(website_files)}] Processing: {filename}")
            
            try:
                # Load the website text file
                text, title, year, metadata = load_document(filepath)
                
                if not text:
                    print(f"   ✗ Failed to load file")
                    continue
                
                token_count = count_tokens(text)
                print(f"   ✓ Loaded: {token_count:,} tokens")
                
                # Since we already limited to 10k tokens during scraping,
                # we shouldn't need splitting, but let's check
                needs_splitting = token_count > config.MAX_TOKENS_PER_DOCUMENT
                
                if needs_splitting:
                    chunks = create_chunks_with_overlap(
                        text,
                        chunk_size_tokens=10000,
                        overlap_tokens=500
                    )
                    print(f"   Split into {len(chunks)} chunks")
                else:
                    chunks = [{
                        'text': text,
                        'tokens': token_count,
                        'start_page': None,
                        'end_page': None,
                        'chunk_num': 1,
                        'total_chunks': 1
                    }]
                
                # Generate Q&A pairs for each chunk
                all_qa_pairs = []
                
                for chunk in chunks:
                    chunk_title = get_chunk_title(title, chunk)
                    
                    print(f"   🤖 Generating Q&A pairs...")
                    
                    qa_pairs, stats = await generate_qa_pairs(
                        chunk['text'],
                        chunk_title,
                        year,
                        dev_mode=False,
                        force_language='nl'  # Force Dutch since these are Dutch websites
                    )
                    
                    if stats.get('success') and qa_pairs:
                        all_qa_pairs.extend(qa_pairs)
                        print(f"   ✓ Generated {len(qa_pairs)} Q&A pairs")
                    else:
                        print(f"   ✗ Failed to generate Q&A pairs")
                
                if all_qa_pairs:
                    # Deduplicate
                    unique_qa_pairs, duplicates = await deduplicate_qa_pairs_llm(all_qa_pairs)
                    
                    if duplicates:
                        print(f"   📊 Removed {len(duplicates)} duplicate questions")
                    
                    # Save to Q&A dev output folder
                    output_filename = f"{Path(filepath).stem}_qa.json"
                    output_path = os.path.join(config.QA_DEV_OUTPUT_PATH, output_filename)
                    save_qa_pairs_to_file(unique_qa_pairs, title, output_path)
                    
                    print(f"   ✅ Saved {len(unique_qa_pairs)} Q&A pairs")
                    
                    result = {
                        'filename': filename,
                        'success': True,
                        'qa_count': len(unique_qa_pairs),
                        'duplicates_removed': len(duplicates)
                    }
                else:
                    result = {
                        'filename': filename,
                        'success': False,
                        'error': 'No Q&A pairs generated'
                    }
                
                report.add_document(result)
                
            except Exception as e:
                print(f"   ✗ Error: {e}")
                result = {
                    'filename': filename,
                    'success': False,
                    'error': str(e),
                    'qa_count': 0
                }
                report.add_document(result)
        
        # Print summary
        print("\n" + "=" * 80)
        print("Q&A GENERATION COMPLETE")
        print("=" * 80)
        report.print_summary()
        report.save()
        
        return True
        
    except Exception as e:
        print(f"\n✗ Error generating Q&A pairs: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ingest website content into RAG databases')
    parser.add_argument('--rag-only', action='store_true', help='Only ingest to RAG_HQ database')
    parser.add_argument('--qa-only', action='store_true', help='Only generate Q&A pairs')
    args = parser.parse_args()
    
    print("=" * 80)
    print("WEBSITE RAG INGESTION")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    success = True
    
    # Ingest to RAG_HQ database
    if not args.qa_only:
        rag_success = await ingest_to_rag_hq()
        success = success and rag_success
    
    # Generate Q&A pairs
    if not args.rag_only:
        qa_success = await ingest_to_qa_database()
        success = success and qa_success
    
    print("\n" + "=" * 80)
    if success:
        print("✅ WEBSITE INGESTION COMPLETE")
    else:
        print("⚠️  WEBSITE INGESTION COMPLETED WITH ERRORS")
    print("=" * 80)
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

