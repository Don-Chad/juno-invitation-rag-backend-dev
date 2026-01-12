#!/usr/bin/env python3
"""
Q&A Document Ingestion Script - DEVELOPMENT MODE

This script generates question-answer pairs from documents for the Q&A RAG system.

MODES:
  --mode=generate      Generate Q&A pairs only (no vectorization)
  --mode=vectorize     Vectorize existing Q&A pairs only
  --mode=full          Generate + vectorize in one pass
  
DEV OPTIONS:
  --dev                Enable development mode (verbose output, save intermediates)
  --single=FILE        Process only a single document
  --show-prompt        Show the full prompt being sent to Groq
  --skip-validation    Skip Q&A validation (for testing)

EXAMPLES:
  # Generate Q&As for a single document (dev mode)
  python ingest_qa_documents.py --mode=generate --single="Nederland 2024 overzicht energie.pdf" --dev
  
  # Generate Q&As for all documents
  python ingest_qa_documents.py --mode=generate
  
  # Vectorize existing Q&As
  python ingest_qa_documents.py --mode=vectorize
  
  # Full pipeline
  python ingest_qa_documents.py --mode=full
"""
import asyncio
import sys
import os
import json
import time
from pathlib import Path
from typing import Optional


# Global settings (can be set via arguments later)
DEV_MODE = True  # Enable by default for now
MODE = "generate"  # generate, vectorize, full
SINGLE_DOCUMENT = None  # Process only this document
SHOW_PROMPT = False
SKIP_VALIDATION = False


async def generate_qa_for_document(document_path: str, dev_mode: bool = True) -> dict:
    """
    Generate Q&A pairs for a single document with splitting and error handling.
    
    Returns:
        dict with processing results (success, qa_count, errors, etc.)
    """
    
    from rag_qa.document_loader import load_document
    from rag_qa.qa_generator import generate_qa_pairs, save_qa_pairs_to_file, count_tokens
    from rag_qa.document_splitter import create_chunks_with_overlap, get_chunk_title
    from rag_qa.error_handling import retry_with_backoff
    from rag_qa import config
    from rag_qa.state import state
    
    filename = os.path.basename(document_path)
    result = {
        'filename': filename,
        'success': False,
        'qa_count': 0,
        'tokens_sent': 0,
        'tokens_received': 0,
        'chunks_processed': 0
    }
    
    print("\n" + "="*80)
    print(f"PROCESSING DOCUMENT: {filename}")
    print("="*80)
    
    # Load document
    print("\n📄 Loading document...")
    text, title, year, metadata = load_document(document_path)
    
    if not text:
        result['error'] = f"Failed to load document: {document_path}"
        print(f"✗ {result['error']}")
        return result
    
    token_count = count_tokens(text)
    print(f"✓ Loaded: {title}")
    print(f"  Year: {year or 'Not detected'}")
    print(f"  Extension: {metadata.get('extension', 'unknown')}")
    print(f"  Tokens: {token_count:,}")
    
    if 'page_count' in metadata:
        print(f"  Pages: {metadata['page_count']}")
    
    # Check if document needs splitting
    needs_splitting = token_count > config.MAX_TOKENS_PER_DOCUMENT
    
    if needs_splitting:
        print(f"\n📄 Document exceeds {config.MAX_TOKENS_PER_DOCUMENT:,} tokens")
        print(f"   Splitting into ~10k token chunks with overlap...")
        
        chunks = create_chunks_with_overlap(
            text, 
            chunk_size_tokens=10000,
            overlap_tokens=500,
            page_texts=metadata.get('page_texts')
        )
        
        print(f"✓ Created {len(chunks)} chunks")
        for chunk in chunks:
            pages = f"p{chunk['start_page']}-{chunk['end_page']}" if chunk['start_page'] else ""
            print(f"   - Chunk {chunk['chunk_num']}/{chunk['total_chunks']}: {chunk['tokens']:,} tokens {pages}")
    else:
        # Single chunk
        chunks = [{
            'text': text,
            'tokens': token_count,
            'start_page': None,
            'end_page': None,
            'chunk_num': 1,
            'total_chunks': 1
        }]
    
    # Process chunks with retry logic
    from rag_qa import config as qa_config
    from rag_qa.deduplication import deduplicate_qa_pairs
    
    force_lang = qa_config.FORCE_OUTPUT_LANGUAGE if hasattr(qa_config, 'FORCE_OUTPUT_LANGUAGE') else None
    
    all_qa_pairs = []
    
    for chunk in chunks:
        chunk_title = get_chunk_title(title, chunk)
        
        print(f"\n🤖 Generating Q&A pairs for chunk {chunk['chunk_num']}/{chunk['total_chunks']}...")
        
        # Wrap generate_qa_pairs with retry logic
        async def generate_with_retry():
            return await generate_qa_pairs(
                chunk['text'],
                chunk_title,
                year,
                dev_mode=dev_mode,
                force_language=force_lang
            )
        
        qa_result, retry_meta = await retry_with_backoff(
            generate_with_retry,
            operation_name=f"Q&A generation for {chunk_title}"
        )
        
        if qa_result is None:
            result['error'] = f"Failed to generate Q&As for chunk {chunk['chunk_num']}: {retry_meta.get('error', 'Unknown')}"
            print(f"✗ {result['error']}")
            return result
        
        qa_pairs, stats = qa_result
        
        if not stats.get('success', False):
            result['error'] = f"Q&A generation failed for chunk {chunk['chunk_num']}: {stats.get('error', 'Unknown')}"
            print(f"✗ {result['error']}")
            return result
        
        if not qa_pairs:
            print(f"⚠️  No Q&A pairs generated for chunk {chunk['chunk_num']}")
            continue
        
        all_qa_pairs.extend(qa_pairs)
        result['tokens_sent'] += stats.get('tokens_sent', 0)
        result['tokens_received'] += stats.get('tokens_received', 0)
        result['chunks_processed'] += 1
    
    if not all_qa_pairs:
        result['error'] = "No valid Q&A pairs generated from any chunks"
        print(f"✗ {result['error']}")
        return result
    
    # Deduplicate Q&A pairs using LLM (smarter than similarity threshold)
    from rag_qa.deduplication import deduplicate_qa_pairs_llm
    unique_qa_pairs, duplicates = await deduplicate_qa_pairs_llm(all_qa_pairs)
    
    if duplicates:
        print(f"\n📊 Deduplication removed {len(duplicates)} redundant questions")
        result['duplicates_removed'] = len(duplicates)
    
    # Use deduplicated pairs
    all_qa_pairs = unique_qa_pairs
    
    # Save combined results to dev output file
    output_filename = f"{Path(document_path).stem}_qa.json"
    output_path = os.path.join(config.QA_DEV_OUTPUT_PATH, output_filename)
    save_qa_pairs_to_file(all_qa_pairs, title, output_path)
    
    # Show sample Q&As with context
    print(f"\n{'='*80}")
    print(f"SAMPLE Q&A PAIRS ({min(3, len(all_qa_pairs))} of {len(all_qa_pairs)})")
    print("="*80)
    
    for idx, qa in enumerate(all_qa_pairs[:3], 1):
        print(f"\n[Q&A {idx}]")
        print(f"Q: {qa['question']}")
        print(f"A: {qa['answer']}")
        if 'context' in qa and qa['context']:
            context_preview = qa['context'][:200] + "..." if len(qa['context']) > 200 else qa['context']
            print(f"C: {context_preview}")
        if 'page_hint' in qa:
            print(f"   (Page: {qa['page_hint']})")
    
    if len(all_qa_pairs) > 3:
        print(f"\n... and {len(all_qa_pairs) - 3} more Q&A pairs")
    
    print(f"\n{'='*80}")
    print("✅ DOCUMENT PROCESSING COMPLETE")
    print("="*80)
    
    # Update state and result
    state.stats.total_documents_processed += 1
    result['success'] = True
    result['qa_count'] = len(all_qa_pairs)
    
    return result


async def main():
    """Main entry point."""
    
    # Parse simple arguments
    import sys
    
    global DEV_MODE, MODE, SINGLE_DOCUMENT, SHOW_PROMPT, SKIP_VALIDATION
    
    for arg in sys.argv[1:]:
        if arg == '--dev':
            DEV_MODE = True
        elif arg.startswith('--mode='):
            MODE = arg.split('=', 1)[1]
        elif arg.startswith('--single='):
            SINGLE_DOCUMENT = arg.split('=', 1)[1]
        elif arg == '--show-prompt':
            SHOW_PROMPT = True
        elif arg == '--skip-validation':
            SKIP_VALIDATION = True
        elif arg in ['--help', '-h']:
            print(__doc__)
            sys.exit(0)
    
    print("="*80)
    print("Q&A DOCUMENT INGESTION - DEVELOPMENT MODE")
    print("="*80)
    print(f"Mode: {MODE}")
    print(f"Dev Mode: {DEV_MODE}")
    if SINGLE_DOCUMENT:
        print(f"Single Document: {SINGLE_DOCUMENT}")
    print("="*80)
    
    # Import after printing header
    from rag_qa import config, state
    
    # Handle single document mode
    if SINGLE_DOCUMENT:
        document_path = os.path.join(config.DOCS_FOLDER, SINGLE_DOCUMENT)
        
        if not os.path.exists(document_path):
            print(f"\n✗ Document not found: {document_path}")
            print(f"\nAvailable documents in {config.DOCS_FOLDER}:")
            for f in os.listdir(config.DOCS_FOLDER):
                if f.endswith(('.pdf', '.docx', '.doc', '.txt', '.md')):
                    print(f"  - {f}")
            sys.exit(1)
        
        # Process single document
        if MODE == 'generate':
            from rag_qa.processing_report import ProcessingReport
            
            report = ProcessingReport()
            result = await generate_qa_for_document(document_path, dev_mode=DEV_MODE)
            report.add_document(result)
            
            # Print final statistics
            print("\n")
            state.stats.print_summary()
            report.print_summary()
            report.save()
            
            sys.exit(0 if result['success'] else 1)
        else:
            print(f"\n⚠️  Mode '{MODE}' not yet implemented for single document")
            sys.exit(1)
    
    # Multi-document mode - process all documents
    print("\nProcessing all documents in docs folder...")
    print("=" * 60)
    
    from rag_qa import config
    from rag_qa.processing_report import ProcessingReport
    import os
    
    # Get all document files
    doc_files = []
    for filename in os.listdir(config.DOCS_FOLDER):
        if filename.endswith(('.pdf', '.docx', '.doc', '.txt', '.md')):
            doc_files.append(filename)
    
    if not doc_files:
        print("✗ No documents found in docs folder")
        sys.exit(1)
    
    print(f"Found {len(doc_files)} documents to process:")
    for i, filename in enumerate(doc_files, 1):
        print(f"  {i}. {filename}")
    print("=" * 60)
    
    # Confirm with user
    if MODE == 'generate':
        response = input(f"\nProcess all {len(doc_files)} documents? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled by user")
            sys.exit(0)
    
    # Process all documents
    report = ProcessingReport()
    
    for i, filename in enumerate(doc_files, 1):
        print(f"\n\n{'='*80}")
        print(f"DOCUMENT {i}/{len(doc_files)}: {filename}")
        print("="*80)
        
        document_path = os.path.join(config.DOCS_FOLDER, filename)
        
        try:
            result = await generate_qa_for_document(document_path, dev_mode=DEV_MODE)
            report.add_document(result)
            
            if result['success']:
                print(f"✓ Completed: {result['qa_count']} Q&As generated")
            else:
                print(f"✗ Failed: {result.get('error', 'Unknown error')}")
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Processing interrupted by user")
            print(f"Processed {i-1}/{len(doc_files)} documents")
            report.print_summary()
            report.save()
            sys.exit(130)
        
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            
            result = {
                'filename': filename,
                'success': False,
                'error': str(e),
                'qa_count': 0,
                'tokens_sent': 0,
                'tokens_received': 0,
                'chunks_processed': 0
            }
            report.add_document(result)
    
    # Print final summary
    print("\n\n" + "="*80)
    print("ALL DOCUMENTS PROCESSED")
    print("="*80)
    
    state.stats.print_summary()
    report.print_summary()
    report.save()
    
    # Exit with error code if any documents failed
    summary = report.get_summary()
    sys.exit(0 if summary['failed'] == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())

