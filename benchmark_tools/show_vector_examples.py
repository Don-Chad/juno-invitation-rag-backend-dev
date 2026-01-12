#!/usr/bin/env python3
"""
Vector Embedding Examples Viewer
Displays 5 example vector embeddings from the RAG system with nice formatting
"""

import pickle
import os
import sys
from datetime import datetime

# ANSI color codes for terminal styling
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
    DIM = '\033[2m'

def format_number(num):
    """Format numbers with spaces every 3 digits"""
    return f"{num:,}".replace(',', ' ')

def print_header(text, char="=", width=100):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{char * width}{Colors.END}")
    padding = (width - len(text)) // 2
    print(f"{Colors.BOLD}{Colors.YELLOW}{' ' * padding}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{char * width}{Colors.END}\n")

def print_section(title, icon=""):
    """Print a section title"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}{icon} {title}{Colors.END}")

def print_metadata_item(label, value, indent=3):
    """Print a metadata item with formatting"""
    spaces = " " * indent
    print(f"{spaces}{Colors.CYAN}•{Colors.END} {Colors.BOLD}{label}:{Colors.END} {value}")

def print_text_box(text, width=96, max_length=600):
    """Print text in a nice box"""
    print(f"   {Colors.DIM}{'─' * width}{Colors.END}")
    
    # Clean and format text
    text_clean = text.replace('\n', ' ').replace('  ', ' ').strip()
    
    if len(text_clean) > max_length:
        display_text = text_clean[:max_length] + "..."
        remaining = len(text_clean) - max_length
        print(f"   {text_clean[:max_length]}...")
        print(f"   {Colors.DIM}[...{format_number(remaining)} more characters]{Colors.END}")
    else:
        print(f"   {text_clean}")
    
    print(f"   {Colors.DIM}{'─' * width}{Colors.END}")

def display_vector_info(index_path, uuid_map_path):
    """Display vector information if available"""
    try:
        import numpy as np
        from annoy import AnnoyIndex
        
        # Load index
        index = AnnoyIndex(1024, 'angular')
        index.load(index_path)
        
        # Load UUID map
        with open(uuid_map_path, 'rb') as f:
            uuid_map = pickle.load(f)
        
        return index, uuid_map
    except Exception as e:
        return None, None

def show_vector_stats(vector):
    """Display vector statistics"""
    import numpy as np
    
    print(f"\n{Colors.BOLD}{Colors.BLUE}   📊 VECTOR STATISTICS:{Colors.END}")
    print_metadata_item("Dimension", f"{len(vector)} values", 6)
    print_metadata_item("L2 Norm", f"{np.linalg.norm(vector):.6f}", 6)
    print_metadata_item("Min value", f"{np.min(vector):.6f}", 6)
    print_metadata_item("Max value", f"{np.max(vector):.6f}", 6)
    print_metadata_item("Mean", f"{np.mean(vector):.6f}", 6)
    print_metadata_item("Std Dev", f"{np.std(vector):.6f}", 6)
    
    # Show first and last values
    first_vals = ', '.join([f'{v:.4f}' for v in vector[:10]])
    last_vals = ', '.join([f'{v:.4f}' for v in vector[-10:]])
    print(f"\n{Colors.DIM}      First 10: [{first_vals}]{Colors.END}")
    print(f"{Colors.DIM}      Last 10:  [{last_vals}]{Colors.END}")

def main():
    """Main function to display vector embedding examples"""
    
    # Paths
    METADATA_PATH = "local_vector_db_enhanced/metadata.pkl"
    VECTOR_DB_PATH = "local_vector_db_enhanced/vdb_data"
    UUID_MAP_PATH = VECTOR_DB_PATH + '.map'
    DOCUMENT_SUMMARIES_PATH = "local_vector_db_enhanced/document_summaries.pkl"
    
    # Print title
    print_header("RAG SYSTEM - VECTOR EMBEDDING EXAMPLES", "═", 100)
    
    print(f"{Colors.BOLD}Generated:{Colors.END} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Colors.BOLD}Purpose:{Colors.END} Display vector embeddings as used during RAG queries\n")
    
    # Load metadata
    if not os.path.exists(METADATA_PATH):
        print(f"{Colors.RED}Error: Metadata file not found at {METADATA_PATH}{Colors.END}")
        sys.exit(1)
    
    with open(METADATA_PATH, 'rb') as f:
        chunks_metadata = pickle.load(f)
    
    # Load vector index
    index, uuid_map = display_vector_info(VECTOR_DB_PATH, UUID_MAP_PATH)
    has_vectors = index is not None
    
    # Database statistics
    print_section("📊 DATABASE STATISTICS", "")
    print_metadata_item("Total embeddings", format_number(len(chunks_metadata)))
    print_metadata_item("Vector dimension", "1 024 (per text chunk)")
    print_metadata_item("Similarity metric", "Cosine similarity (Annoy angular distance)")
    print_metadata_item("Vector index", "Available ✓" if has_vectors else "Not loaded")
    
    if has_vectors:
        print_metadata_item("Index items", format_number(index.get_n_items()))
    
    # Get 5 diverse examples spread across the database
    all_chunk_ids = list(chunks_metadata.keys())
    step = max(1, len(all_chunk_ids) // 5)
    chunk_ids = [all_chunk_ids[i * step] for i in range(5)]
    
    # Display examples
    print_header("VECTOR EMBEDDING EXAMPLES", "═", 100)
    
    for i, chunk_id in enumerate(chunk_ids, 1):
        chunk_data = chunks_metadata[chunk_id]
        chunk_text = chunk_data['text']
        metadata = chunk_data['metadata']
        
        # Main example header
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'─' * 100}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.YELLOW}  EXAMPLE {i}/5{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'─' * 100}{Colors.END}")
        
        # Chunk identifier
        print_section("🔑 CHUNK IDENTIFIER")
        print_metadata_item("UUID", chunk_id)
        print_metadata_item("Embedding Hash", chunk_data.get('embedding_hash', 'N/A'))
        
        # Metadata section
        print_section("📋 METADATA")
        print_metadata_item("Source Document", metadata.get('filename', 'N/A'))
        print_metadata_item("Chunk Index", str(metadata.get('chunk_index', 'N/A')))
        print_metadata_item("Estimated Tokens", f"{metadata.get('estimated_tokens', 0):.1f}")
        
        char_start = metadata.get('char_start', 0)
        char_end = metadata.get('char_end', 0)
        print_metadata_item("Character Range", 
                          f"{format_number(char_start)} → {format_number(char_end)}")
        print_metadata_item("Text Length", f"{format_number(len(chunk_text))} characters")
        
        # Text content
        print_section("📝 TEXT CONTENT")
        print_text_box(chunk_text)
        
        # Vector information
        if has_vectors and uuid_map:
            # Find the index ID for this UUID
            index_id = None
            for idx, uuid_val in uuid_map.items():
                if uuid_val == chunk_id:
                    index_id = idx
                    break
            
            if index_id is not None:
                try:
                    import numpy as np
                    vector = index.get_item_vector(index_id)
                    show_vector_stats(vector)
                except Exception as e:
                    print(f"\n   {Colors.RED}Could not retrieve vector: {e}{Colors.END}")
        
        # Usage information
        print(f"\n{Colors.BOLD}{Colors.GREEN}   💡 RAG USAGE:{Colors.END}")
        print(f"      • Text converted to 1 024-dimensional vector")
        print(f"      • Stored in Annoy index for fast similarity search")
        print(f"      • Retrieved when user queries match semantically")
        print(f"      • Similarity threshold: > 0.7 for high relevance")
    
    # Load and display document summaries
    if os.path.exists(DOCUMENT_SUMMARIES_PATH):
        with open(DOCUMENT_SUMMARIES_PATH, 'rb') as f:
            document_summaries = pickle.load(f)
        
        if document_summaries:
            print_header("DOCUMENT SUMMARIES", "═", 100)
            
            for idx, (filename, summary_data) in enumerate(list(document_summaries.items())[:3], 1):
                print(f"\n{Colors.BOLD}{Colors.CYAN}📄 Document {idx}: {filename}{Colors.END}")
                
                summary = summary_data.get('summary', 'N/A')
                if len(summary) > 400:
                    summary = summary[:400] + "..."
                print(f"\n   {Colors.BOLD}Summary:{Colors.END}")
                print(f"   {summary}")
                
                keywords = summary_data.get('keywords', [])
                if keywords:
                    keyword_str = ', '.join(keywords[:10])
                    print(f"\n   {Colors.BOLD}Keywords:{Colors.END} {Colors.YELLOW}{keyword_str}{Colors.END}")
    
    # How RAG uses these embeddings
    print_header("HOW THE RAG SYSTEM WORKS", "═", 100)
    
    steps = [
        ("1️⃣  USER QUERY", "User asks a question (e.g., 'What is the energy transition policy?')"),
        ("2️⃣  EMBEDDING", "Query text converted to 1 024-dimensional vector"),
        ("3️⃣  SEARCH", "Annoy index searches for similar vectors using cosine similarity"),
        ("4️⃣  RANKING", "Results sorted by similarity score (0.0 to 1.0)"),
        ("5️⃣  FILTERING", "Only chunks with similarity > 0.7 are used"),
        ("6️⃣  EXPANSION", "System loads surrounding context from source document"),
        ("7️⃣  FORMATTING", "Results formatted with metadata and source attribution"),
        ("8️⃣  INJECTION", "Top 3-5 chunks injected into LLM chat context"),
        ("9️⃣  RESPONSE", "LLM generates answer using the retrieved context"),
    ]
    
    for step_title, description in steps:
        print(f"\n{Colors.BOLD}{Colors.GREEN}{step_title}{Colors.END}")
        print(f"   {description}")
    
    # Footer
    print_header("END OF REPORT", "═", 100)
    print(f"\n{Colors.BOLD}Summary:{Colors.END}")
    print(f"  • Displayed {len(chunk_ids)} vector embedding examples")
    print(f"  • Total database size: {format_number(len(chunks_metadata))} chunks")
    print(f"  • Each chunk has text, metadata, and a 1 024-dim vector")
    print(f"  • Vectors enable semantic search for relevant context\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Interrupted by user{Colors.END}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


