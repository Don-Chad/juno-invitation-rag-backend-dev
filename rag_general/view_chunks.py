#!/usr/bin/env python3
"""
Elegant Chunk Viewer for RAG Database

View and inspect all document chunks with their metadata.
"""
import os
import pickle
import asyncio
from pathlib import Path
from collections import defaultdict

# Color codes for terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_header(text):
    """Print a styled header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}\n")

def print_subheader(text):
    """Print a styled subheader."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BLUE}{'-'*len(text)}{Colors.END}")

def print_info(label, value):
    """Print a labeled info line."""
    print(f"{Colors.YELLOW}{label}:{Colors.END} {value}")

def print_chunk_preview(text, max_lines=5):
    """Print a preview of chunk text."""
    lines = text.split('\n')
    preview_lines = lines[:max_lines]
    print(f"{Colors.GREEN}{chr(10).join(preview_lines)}{Colors.END}")
    if len(lines) > max_lines:
        print(f"{Colors.YELLOW}... ({len(lines) - max_lines} more lines){Colors.END}")

def load_database():
    """Load the vector database metadata."""
    metadata_path = "local_vector_db_enhanced/metadata.pkl"
    summaries_path = "local_vector_db_enhanced/document_summaries.pkl"
    
    if not os.path.exists(metadata_path):
        print(f"{Colors.RED}✗ Database not found at {metadata_path}{Colors.END}")
        print(f"{Colors.YELLOW}  Run 'python ingest_documents.py' first{Colors.END}")
        return None, None
    
    print(f"{Colors.GREEN}✓ Loading database...{Colors.END}")
    
    with open(metadata_path, 'rb') as f:
        chunks_metadata = pickle.load(f)
    
    summaries = {}
    if os.path.exists(summaries_path):
        with open(summaries_path, 'rb') as f:
            summaries = pickle.load(f)
    
    return chunks_metadata, summaries

def show_statistics(chunks_metadata, summaries):
    """Show database statistics."""
    print_header("DATABASE STATISTICS")
    
    # Group chunks by document
    docs = defaultdict(list)
    for chunk_id, chunk_data in chunks_metadata.items():
        filename = chunk_data['metadata']['filename']
        docs[filename].append(chunk_data)
    
    print_info("Total documents", f"{len(docs)}")
    print_info("Total chunks", f"{len(chunks_metadata):,}")
    print_info("Avg chunks/doc", f"{len(chunks_metadata)/len(docs):.1f}")
    
    # Token statistics
    all_tokens = [chunk['metadata'].get('estimated_tokens', 0) 
                  for chunk in chunks_metadata.values()]
    if all_tokens:
        print_info("Avg chunk size", f"{sum(all_tokens)/len(all_tokens):.0f} tokens")
        print_info("Min chunk size", f"{min(all_tokens)} tokens")
        print_info("Max chunk size", f"{max(all_tokens)} tokens")
    
    print(f"\n{Colors.BOLD}Documents:{Colors.END}")
    for idx, (filename, chunks) in enumerate(sorted(docs.items()), 1):
        chunk_count = len(chunks)
        has_summary = filename in summaries
        summary_indicator = f"{Colors.GREEN}✓{Colors.END}" if has_summary else f"{Colors.RED}✗{Colors.END}"
        print(f"  {idx:2}. {filename:60} ({chunk_count:3} chunks) {summary_indicator}")

def view_document_chunks(chunks_metadata, summaries, document_name=None):
    """View all chunks from a specific document."""
    # Group chunks by document
    docs = defaultdict(list)
    for chunk_id, chunk_data in chunks_metadata.items():
        filename = chunk_data['metadata']['filename']
        docs[filename].append((chunk_id, chunk_data))
    
    # If no document specified, show menu
    if not document_name:
        print_header("SELECT DOCUMENT")
        doc_list = sorted(docs.keys())
        for idx, filename in enumerate(doc_list, 1):
            print(f"  {idx}. {filename} ({len(docs[filename])} chunks)")
        
        try:
            choice = input(f"\n{Colors.BOLD}Enter document number (or 'q' to quit): {Colors.END}")
            if choice.lower() == 'q':
                return
            doc_idx = int(choice) - 1
            if 0 <= doc_idx < len(doc_list):
                document_name = doc_list[doc_idx]
            else:
                print(f"{Colors.RED}Invalid choice{Colors.END}")
                return
        except (ValueError, KeyError):
            print(f"{Colors.RED}Invalid input{Colors.END}")
            return
    
    if document_name not in docs:
        print(f"{Colors.RED}Document '{document_name}' not found{Colors.END}")
        return
    
    print_header(f"DOCUMENT: {document_name}")
    
    # Show document summary if available
    if document_name in summaries:
        summary_data = summaries[document_name]
        print_subheader("📄 Document Summary")
        
        if 'extended_summary' in summary_data:
            print(f"{Colors.GREEN}{summary_data['extended_summary']}{Colors.END}\n")
        elif 'summary' in summary_data:
            print(f"{Colors.GREEN}{summary_data['summary']}{Colors.END}\n")
        
        if 'extended_keywords' in summary_data:
            keywords = ', '.join(summary_data['extended_keywords'][:10])
            print_info("Keywords", keywords)
        elif 'keywords' in summary_data:
            keywords = ', '.join(summary_data['keywords'])
            print_info("Keywords", keywords)
    
    # Sort chunks by chunk_index
    chunks = sorted(docs[document_name], key=lambda x: x[1]['metadata']['chunk_index'])
    
    print_info("\nTotal chunks", f"{len(chunks)}")
    
    # View mode
    while True:
        print(f"\n{Colors.BOLD}View options:{Colors.END}")
        print("  1. View all chunks (full text)")
        print("  2. View all chunks (preview)")
        print("  3. View specific chunk")
        print("  4. Search chunks")
        print("  5. Back to document list")
        
        choice = input(f"\n{Colors.BOLD}Choice: {Colors.END}").strip()
        
        if choice == '1':
            view_all_chunks_full(chunks)
        elif choice == '2':
            view_all_chunks_preview(chunks)
        elif choice == '3':
            view_specific_chunk(chunks)
        elif choice == '4':
            search_chunks(chunks)
        elif choice == '5':
            break
        else:
            print(f"{Colors.RED}Invalid choice{Colors.END}")

def view_all_chunks_full(chunks):
    """View all chunks with full text."""
    print_header("ALL CHUNKS - FULL TEXT")
    
    for idx, (chunk_id, chunk_data) in enumerate(chunks, 1):
        metadata = chunk_data['metadata']
        text = chunk_data['text']
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}╔{'═'*78}╗{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}║ CHUNK {idx}/{len(chunks)} {' '*(70-len(str(idx))-len(str(len(chunks))))}║{Colors.END}")
        print(f"{Colors.BOLD}{Colors.CYAN}╚{'═'*78}╝{Colors.END}")
        
        print_info("Chunk ID", chunk_id[:16] + "...")
        print_info("Chunk Index", metadata.get('chunk_index', 'N/A'))
        print_info("Estimated Tokens", metadata.get('estimated_tokens', 'N/A'))
        print_info("Characters", f"{len(text):,}")
        print_info("Position", f"chars {metadata.get('char_start', 0):,} - {metadata.get('char_end', 0):,}")
        
        print(f"\n{Colors.BOLD}Text:{Colors.END}")
        print(f"{Colors.GREEN}{text}{Colors.END}")
        
        if idx < len(chunks):
            input(f"\n{Colors.YELLOW}Press Enter for next chunk (or Ctrl+C to stop)...{Colors.END}")

def view_all_chunks_preview(chunks):
    """View all chunks with text preview."""
    print_header("ALL CHUNKS - PREVIEW")
    
    for idx, (chunk_id, chunk_data) in enumerate(chunks, 1):
        metadata = chunk_data['metadata']
        text = chunk_data['text']
        
        print(f"\n{Colors.BOLD}[{idx}/{len(chunks)}] Chunk {metadata.get('chunk_index', 'N/A')}{Colors.END}")
        print_info("  Tokens", f"{metadata.get('estimated_tokens', 'N/A')}")
        print_info("  Chars", f"{len(text):,}")
        print(f"  {Colors.BOLD}Preview:{Colors.END}")
        print_chunk_preview(text, max_lines=3)

def view_specific_chunk(chunks):
    """View a specific chunk by index."""
    try:
        chunk_num = int(input(f"\n{Colors.BOLD}Enter chunk number (1-{len(chunks)}): {Colors.END}"))
        if 1 <= chunk_num <= len(chunks):
            chunk_id, chunk_data = chunks[chunk_num - 1]
            metadata = chunk_data['metadata']
            text = chunk_data['text']
            
            print_subheader(f"CHUNK {chunk_num}/{len(chunks)}")
            print_info("Chunk ID", chunk_id)
            print_info("Chunk Index", metadata.get('chunk_index', 'N/A'))
            print_info("Estimated Tokens", metadata.get('estimated_tokens', 'N/A'))
            print_info("Characters", f"{len(text):,}")
            print_info("Position", f"chars {metadata.get('char_start', 0):,} - {metadata.get('char_end', 0):,}")
            
            print(f"\n{Colors.BOLD}Full Text:{Colors.END}")
            print(f"{Colors.GREEN}{text}{Colors.END}")
        else:
            print(f"{Colors.RED}Invalid chunk number{Colors.END}")
    except ValueError:
        print(f"{Colors.RED}Invalid input{Colors.END}")

def search_chunks(chunks):
    """Search for text in chunks."""
    query = input(f"\n{Colors.BOLD}Search query: {Colors.END}").strip().lower()
    if not query:
        return
    
    matches = []
    for idx, (chunk_id, chunk_data) in enumerate(chunks, 1):
        if query in chunk_data['text'].lower():
            matches.append((idx, chunk_id, chunk_data))
    
    if not matches:
        print(f"{Colors.YELLOW}No matches found{Colors.END}")
        return
    
    print_subheader(f"SEARCH RESULTS: {len(matches)} matches for '{query}'")
    
    for idx, chunk_id, chunk_data in matches:
        metadata = chunk_data['metadata']
        text = chunk_data['text']
        
        print(f"\n{Colors.BOLD}[Chunk {idx}]{Colors.END}")
        print_info("  Tokens", f"{metadata.get('estimated_tokens', 'N/A')}")
        
        # Show context around match
        text_lower = text.lower()
        match_pos = text_lower.find(query)
        start = max(0, match_pos - 100)
        end = min(len(text), match_pos + len(query) + 100)
        context = text[start:end]
        
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."
        
        # Highlight the match
        context_with_highlight = context.replace(
            text[match_pos:match_pos+len(query)],
            f"{Colors.BOLD}{Colors.RED}{text[match_pos:match_pos+len(query)]}{Colors.END}{Colors.GREEN}"
        )
        
        print(f"  {Colors.GREEN}{context_with_highlight}{Colors.END}")

def main():
    """Main entry point."""
    print_header("RAG CHUNK VIEWER")
    
    chunks_metadata, summaries = load_database()
    if not chunks_metadata:
        return
    
    print(f"{Colors.GREEN}✓ Loaded {len(chunks_metadata):,} chunks from {len(set(c['metadata']['filename'] for c in chunks_metadata.values()))} documents{Colors.END}")
    
    while True:
        print(f"\n{Colors.BOLD}Main Menu:{Colors.END}")
        print("  1. View statistics")
        print("  2. View document chunks")
        print("  3. Search all chunks")
        print("  4. Export chunks to text file")
        print("  5. Quit")
        
        choice = input(f"\n{Colors.BOLD}Choice: {Colors.END}").strip()
        
        try:
            if choice == '1':
                show_statistics(chunks_metadata, summaries)
            elif choice == '2':
                view_document_chunks(chunks_metadata, summaries)
            elif choice == '3':
                search_all_documents(chunks_metadata)
            elif choice == '4':
                export_chunks(chunks_metadata)
            elif choice == '5':
                print(f"\n{Colors.GREEN}Goodbye!{Colors.END}\n")
                break
            else:
                print(f"{Colors.RED}Invalid choice{Colors.END}")
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Operation cancelled{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}Error: {e}{Colors.END}")

def search_all_documents(chunks_metadata):
    """Search across all documents."""
    query = input(f"\n{Colors.BOLD}Search query: {Colors.END}").strip().lower()
    if not query:
        return
    
    print_subheader(f"SEARCHING ALL DOCUMENTS FOR '{query}'")
    
    matches_by_doc = defaultdict(list)
    for chunk_id, chunk_data in chunks_metadata.items():
        if query in chunk_data['text'].lower():
            filename = chunk_data['metadata']['filename']
            matches_by_doc[filename].append((chunk_id, chunk_data))
    
    if not matches_by_doc:
        print(f"{Colors.YELLOW}No matches found{Colors.END}")
        return
    
    print(f"\n{Colors.GREEN}Found {sum(len(m) for m in matches_by_doc.values())} matches in {len(matches_by_doc)} documents{Colors.END}")
    
    for filename in sorted(matches_by_doc.keys()):
        matches = matches_by_doc[filename]
        print(f"\n{Colors.BOLD}{Colors.CYAN}📄 {filename}{Colors.END} ({len(matches)} matches)")
        
        for chunk_id, chunk_data in matches[:3]:  # Show first 3 matches per document
            metadata = chunk_data['metadata']
            text = chunk_data['text']
            
            print(f"  {Colors.YELLOW}Chunk {metadata.get('chunk_index', 'N/A')}{Colors.END}")
            
            # Show context around match
            text_lower = text.lower()
            match_pos = text_lower.find(query)
            start = max(0, match_pos - 80)
            end = min(len(text), match_pos + len(query) + 80)
            context = text[start:end]
            
            if start > 0:
                context = "..." + context
            if end < len(text):
                context = context + "..."
            
            print(f"  {Colors.GREEN}{context}{Colors.END}")
        
        if len(matches) > 3:
            print(f"  {Colors.YELLOW}... and {len(matches) - 3} more matches{Colors.END}")

def export_chunks(chunks_metadata):
    """Export all chunks to a text file."""
    output_file = input(f"\n{Colors.BOLD}Output filename (default: chunks_export.txt): {Colors.END}").strip()
    if not output_file:
        output_file = "chunks_export.txt"
    
    print(f"{Colors.YELLOW}Exporting...{Colors.END}")
    
    # Group by document
    docs = defaultdict(list)
    for chunk_id, chunk_data in chunks_metadata.items():
        filename = chunk_data['metadata']['filename']
        docs[filename].append((chunk_id, chunk_data))
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("RAG DATABASE CHUNK EXPORT\n")
        f.write("="*80 + "\n\n")
        
        for filename in sorted(docs.keys()):
            chunks = sorted(docs[filename], key=lambda x: x[1]['metadata']['chunk_index'])
            
            f.write(f"\n{'='*80}\n")
            f.write(f"DOCUMENT: {filename}\n")
            f.write(f"{'='*80}\n")
            f.write(f"Total chunks: {len(chunks)}\n\n")
            
            for idx, (chunk_id, chunk_data) in enumerate(chunks, 1):
                metadata = chunk_data['metadata']
                text = chunk_data['text']
                
                f.write(f"\n{'-'*80}\n")
                f.write(f"Chunk {idx}/{len(chunks)} (Index: {metadata.get('chunk_index', 'N/A')})\n")
                f.write(f"{'-'*80}\n")
                f.write(f"Tokens: {metadata.get('estimated_tokens', 'N/A')}\n")
                f.write(f"Characters: {len(text):,}\n")
                f.write(f"Position: {metadata.get('char_start', 0):,} - {metadata.get('char_end', 0):,}\n")
                f.write(f"\n{text}\n")
    
    print(f"{Colors.GREEN}✓ Exported to {output_file}{Colors.END}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Interrupted by user{Colors.END}\n")
    except Exception as e:
        print(f"\n{Colors.RED}Fatal error: {e}{Colors.END}\n")
        import traceback
        traceback.print_exc()

