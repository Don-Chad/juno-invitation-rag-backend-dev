#!/usr/bin/env python3
"""
RAG Database Inspector
Beautifully displays all components of the RAG vector database.
"""
import pickle
import numpy as np
import json
import os
from pathlib import Path
from collections import Counter
from datetime import datetime

# Optional import
try:
    from annoy import AnnoyIndex
    ANNOY_AVAILABLE = True
except ImportError:
    ANNOY_AVAILABLE = False

# Configuration
DB_FOLDER = "local_vector_db_enhanced"
VECTOR_DIM = 768  # EmbeddingGemma-300M dimensions

# ANSI colors for pretty output
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

def header(text):
    """Print a fancy header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'=' * 80}{Colors.END}\n")

def subheader(text):
    """Print a subheader"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}┌─ {text} {'─' * (70 - len(text))}┐{Colors.END}")

def info(label, value, indent=0):
    """Print labeled information"""
    spaces = "  " * indent
    print(f"{spaces}{Colors.GREEN}▸ {label}:{Colors.END} {Colors.BOLD}{value}{Colors.END}")

def warning(text):
    """Print a warning"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")

def error(text):
    """Print an error"""
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def success(text):
    """Print a success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def format_size(bytes_size):
    """Format bytes into human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

def format_number(num):
    """Format number with thousands separators"""
    return f"{num:,}".replace(',', ' ')

def inspect_metadata(show_chunks=0):
    """Inspect the chunks metadata"""
    subheader("CHUNKS METADATA")
    
    metadata_path = os.path.join(DB_FOLDER, "metadata.pkl")
    if not os.path.exists(metadata_path):
        error(f"Metadata file not found: {metadata_path}")
        return None
    
    with open(metadata_path, 'rb') as f:
        metadata = pickle.load(f)
    
    info("Total chunks", format_number(len(metadata)))
    info("Data structure", type(metadata).__name__)
    
    if len(metadata) > 0:
        # Analyze metadata
        sample_key = list(metadata.keys())[0]
        sample_value = metadata[sample_key]
        
        print(f"\n{Colors.BOLD}Sample chunk structure:{Colors.END}")
        print(f"  {Colors.CYAN}UUID:{Colors.END} {sample_key[:40]}...")
        
        if isinstance(sample_value, dict):
            for key, val in sample_value.items():
                if key == 'text':
                    continue  # Skip text in structure overview
                if isinstance(val, str) and len(val) > 100:
                    val = val[:100] + "..."
                info(key, val, indent=1)
        
        # Count chunks per document
        docs = {}
        for chunk_meta in metadata.values():
            if isinstance(chunk_meta, dict):
                doc = chunk_meta.get('filename', chunk_meta.get('source', 'Unknown'))
                docs[doc] = docs.get(doc, 0) + 1
        
        print(f"\n{Colors.BOLD}Chunks per document:{Colors.END}")
        for doc, count in sorted(docs.items(), key=lambda x: x[1], reverse=True):
            print(f"  {Colors.CYAN}•{Colors.END} {doc[:60]:<60} {Colors.GREEN}{format_number(count):>8}{Colors.END} chunks")
        
        # Show actual chunk texts if requested
        if show_chunks > 0:
            print(f"\n{Colors.BOLD}Sample chunk texts (first {show_chunks}):{Colors.END}")
            print(f"{Colors.CYAN}{'─' * 80}{Colors.END}")
            
            for i, (uuid, chunk_data) in enumerate(list(metadata.items())[:show_chunks]):
                if isinstance(chunk_data, dict):
                    text = chunk_data.get('text', '')
                    meta = chunk_data.get('metadata', {})
                    filename = meta.get('filename', 'Unknown')
                    chunk_idx = meta.get('chunk_index', '?')
                    tokens = meta.get('estimated_tokens', 0)
                    
                    print(f"\n{Colors.YELLOW}Chunk #{i+1}:{Colors.END}")
                    print(f"  {Colors.CYAN}File:{Colors.END} {filename}")
                    print(f"  {Colors.CYAN}Index:{Colors.END} {chunk_idx} | {Colors.CYAN}Tokens:{Colors.END} {tokens:.0f} | {Colors.CYAN}UUID:{Colors.END} {uuid[:20]}...")
                    print(f"  {Colors.CYAN}Text:{Colors.END}")
                    
                    # Print text with line wrapping and indentation
                    text_lines = text.split('\n')
                    for line in text_lines[:15]:  # Show first 15 lines max per chunk
                        if line.strip():
                            # Wrap long lines
                            if len(line) > 76:
                                print(f"    {line[:76]}")
                                print(f"    {line[76:152]}")
                            else:
                                print(f"    {line}")
                    
                    if len(text_lines) > 15:
                        print(f"    {Colors.YELLOW}... ({len(text_lines) - 15} more lines){Colors.END}")
                    
                    print(f"{Colors.CYAN}{'─' * 80}{Colors.END}")
    
    return metadata

def inspect_embeddings_cache():
    """Inspect the embeddings cache"""
    subheader("EMBEDDINGS CACHE")
    
    # Try both possible filenames
    cache_paths = [
        os.path.join(DB_FOLDER, "embeddings_cache.npy.npy"),
        os.path.join(DB_FOLDER, "embeddings_cache.npy"),
    ]
    
    cache_path = None
    for path in cache_paths:
        if os.path.exists(path):
            cache_path = path
            break
    
    if not cache_path:
        error("Embeddings cache not found")
        return None
    
    try:
        cache = np.load(cache_path, allow_pickle=True).item()
        
        info("Cache file", os.path.basename(cache_path))
        info("Cached embeddings", format_number(len(cache)))
        info("File size", format_size(os.path.getsize(cache_path)))
        
        if len(cache) > 0:
            # Get sample embedding
            sample_key = list(cache.keys())[0]
            sample_embedding = cache[sample_key]
            
            try:
                if hasattr(sample_embedding, '__len__'):
                    info("Embedding dimension", len(sample_embedding))
                if hasattr(sample_embedding, 'dtype'):
                    info("Embedding dtype", str(sample_embedding.dtype))
                if hasattr(sample_embedding, 'nbytes'):
                    info("Memory per embedding", format_size(sample_embedding.nbytes))
                    info("Total memory", format_size(sum(e.nbytes for e in cache.values() if hasattr(e, 'nbytes'))))
            except Exception as e:
                warning(f"Could not analyze embeddings: {e}")
            
            # Show sample text keys
            print(f"\n{Colors.BOLD}Sample cached texts:{Colors.END}")
            for i, key in enumerate(list(cache.keys())[:5]):
                text_preview = key[:80] + "..." if len(key) > 80 else key
                print(f"  {Colors.CYAN}{i+1}.{Colors.END} {text_preview}")
        
        return cache
    
    except Exception as e:
        error(f"Error loading cache: {e}")
        return None

def inspect_bm25_index():
    """Inspect the BM25 index"""
    subheader("BM25 KEYWORD INDEX")
    
    bm25_path = os.path.join(DB_FOLDER, "bm25_index.pkl")
    if not os.path.exists(bm25_path):
        warning("BM25 index not found (hybrid search may be disabled)")
        return None
    
    try:
        with open(bm25_path, 'rb') as f:
            bm25_data = pickle.load(f)
    except Exception as e:
        error(f"Error loading BM25 index: {e}")
        info("File size", format_size(os.path.getsize(bm25_path)))
        return None
    
    info("File size", format_size(os.path.getsize(bm25_path)))
    info("Data structure", type(bm25_data).__name__)
    
    if isinstance(bm25_data, dict):
        for key, value in bm25_data.items():
            if isinstance(value, list):
                info(key, f"{format_number(len(value))} items")
            elif isinstance(value, dict):
                info(key, f"{format_number(len(value))} entries")
            else:
                info(key, type(value).__name__)
    
    return bm25_data

def inspect_annoy_index():
    """Inspect the Annoy vector index"""
    subheader("ANNOY VECTOR INDEX")
    
    index_path = os.path.join(DB_FOLDER, "vdb_data")
    map_path = os.path.join(DB_FOLDER, "vdb_data.map")
    
    if not os.path.exists(index_path):
        error(f"Annoy index not found: {index_path}")
        return None
    
    if not ANNOY_AVAILABLE:
        warning("Annoy module not available - showing limited info")
        info("Index file size", format_size(os.path.getsize(index_path)))
        info("Vector dimension", VECTOR_DIM)
        
        # Try to load UUID map
        if os.path.exists(map_path):
            with open(map_path, 'rb') as f:
                uuid_map = pickle.load(f)
            info("UUID mappings", format_number(len(uuid_map)))
            
            if len(uuid_map) > 0:
                print(f"\n{Colors.BOLD}Sample UUID mappings:{Colors.END}")
                for i, (idx, uuid) in enumerate(list(uuid_map.items())[:5]):
                    print(f"  {Colors.CYAN}Index {idx}:{Colors.END} {uuid[:50]}...")
        return None
    
    # Load index
    index = AnnoyIndex(VECTOR_DIM, 'angular')
    index.load(index_path)
    
    # Load UUID map
    uuid_map = {}
    if os.path.exists(map_path):
        with open(map_path, 'rb') as f:
            uuid_map = pickle.load(f)
    
    info("Index file size", format_size(os.path.getsize(index_path)))
    info("Vector dimension", VECTOR_DIM)
    info("Distance metric", "Angular (Cosine Similarity)")
    info("Total vectors", format_number(index.get_n_items()))
    info("UUID mappings", format_number(len(uuid_map)))
    
    if len(uuid_map) > 0:
        print(f"\n{Colors.BOLD}Sample UUID mappings:{Colors.END}")
        for i, (idx, uuid) in enumerate(list(uuid_map.items())[:5]):
            print(f"  {Colors.CYAN}Index {idx}:{Colors.END} {uuid[:50]}...")
    
    # Test query performance
    if index.get_n_items() > 0:
        print(f"\n{Colors.BOLD}Query performance test:{Colors.END}")
        
        # Create a random query vector
        query_vector = np.random.rand(VECTOR_DIM).astype(np.float32)
        query_vector = query_vector / np.linalg.norm(query_vector)
        
        import time
        
        # Test different K values
        for k in [1, 5, 10, 20]:
            start = time.perf_counter()
            results = index.get_nns_by_vector(query_vector, k, include_distances=True)
            elapsed_ms = (time.perf_counter() - start) * 1000
            
            print(f"  {Colors.CYAN}K={k:>2}:{Colors.END} {elapsed_ms:>6.2f} ms")
    
    return index, uuid_map

def inspect_document_summaries():
    """Inspect document summaries"""
    subheader("DOCUMENT SUMMARIES")
    
    summary_path = os.path.join(DB_FOLDER, "document_summaries.pkl")
    if not os.path.exists(summary_path):
        warning("Document summaries not found")
        return None
    
    with open(summary_path, 'rb') as f:
        summaries = pickle.load(f)
    
    info("Total documents", format_number(len(summaries)))
    info("File size", format_size(os.path.getsize(summary_path)))
    
    print(f"\n{Colors.BOLD}Documents with summaries:{Colors.END}")
    for i, (filename, data) in enumerate(summaries.items(), 1):
        print(f"\n  {Colors.YELLOW}{i}. {filename}{Colors.END}")
        
        if isinstance(data, dict):
            if 'summary' in data:
                summary = data['summary']
                summary_preview = summary[:150] + "..." if len(summary) > 150 else summary
                print(f"     {Colors.CYAN}Summary:{Colors.END} {summary_preview}")
            
            if 'keywords' in data:
                keywords = data['keywords'][:10]  # First 10 keywords
                print(f"     {Colors.CYAN}Keywords:{Colors.END} {', '.join(keywords)}")
            
            if 'generated_at' in data:
                timestamp = datetime.fromtimestamp(data['generated_at'])
                print(f"     {Colors.CYAN}Generated:{Colors.END} {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    
    return summaries

def inspect_file_history():
    """Inspect file processing history"""
    subheader("FILE PROCESSING HISTORY")
    
    history_path = os.path.join(DB_FOLDER, "file_history.pkl")
    if not os.path.exists(history_path):
        warning("File history not found")
        return None
    
    with open(history_path, 'rb') as f:
        history = pickle.load(f)
    
    info("Files processed", format_number(len(history)))
    info("File size", format_size(os.path.getsize(history_path)))
    
    print(f"\n{Colors.BOLD}Processing history:{Colors.END}")
    for i, (file_hash, file_info) in enumerate(list(history.items())[:10], 1):
        if isinstance(file_info, dict):
            filename = file_info.get('filename', 'Unknown')
            timestamp = file_info.get('timestamp', 0)
            dt = datetime.fromtimestamp(timestamp) if timestamp else 'Unknown'
            
            print(f"  {Colors.CYAN}{i}.{Colors.END} {filename[:60]}")
            if timestamp:
                print(f"     {Colors.GREEN}Processed:{Colors.END} {dt}")
    
    return history

def inspect_document_texts():
    """Inspect document texts directory"""
    subheader("DOCUMENT TEXTS")
    
    texts_dir = os.path.join(DB_FOLDER, "document_texts")
    if not os.path.exists(texts_dir):
        warning("Document texts directory not found")
        return None
    
    # List all text files
    text_files = list(Path(texts_dir).glob("*.txt"))
    
    info("Text files", format_number(len(text_files)))
    
    total_size = sum(f.stat().st_size for f in text_files)
    info("Total size", format_size(total_size))
    
    if text_files:
        print(f"\n{Colors.BOLD}Document text files:{Colors.END}")
        for i, file_path in enumerate(sorted(text_files, key=lambda f: f.stat().st_size, reverse=True)[:10], 1):
            size = file_path.stat().st_size
            print(f"  {Colors.CYAN}{i}.{Colors.END} {file_path.name[:60]:<60} {Colors.GREEN}{format_size(size):>10}{Colors.END}")
    
    return text_files

def inspect_ingestion_report():
    """Inspect ingestion report"""
    subheader("INGESTION REPORT")
    
    report_path = os.path.join(DB_FOLDER, ".ingestionrapport.json")
    if not os.path.exists(report_path):
        warning("Ingestion report not found")
        return None
    
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    info("Report file size", format_size(os.path.getsize(report_path)))
    
    if isinstance(report, dict):
        print(f"\n{Colors.BOLD}Latest ingestion:{Colors.END}")
        
        for key, value in report.items():
            if key == 'files_processed' and isinstance(value, list):
                info(key, f"{len(value)} files")
                for file_info in value[:5]:
                    if isinstance(file_info, dict):
                        fname = file_info.get('filename', 'Unknown')
                        chunks = file_info.get('chunks', 0)
                        print(f"    {Colors.CYAN}•{Colors.END} {fname[:50]:<50} {chunks:>4} chunks")
            elif key == 'timestamp':
                dt = datetime.fromtimestamp(value)
                info(key, dt.strftime('%Y-%m-%d %H:%M:%S'))
            elif isinstance(value, (int, float)):
                info(key, format_number(value))
            elif isinstance(value, str) and len(value) < 100:
                info(key, value)
    
    return report

def main(show_chunks=0):
    """Main inspection function"""
    header("🔍 RAG DATABASE INSPECTOR")
    
    print(f"{Colors.BOLD}Database location:{Colors.END} {os.path.abspath(DB_FOLDER)}\n")
    
    if not os.path.exists(DB_FOLDER):
        error(f"Database folder not found: {DB_FOLDER}")
        return
    
    # Get folder size
    total_size = sum(f.stat().st_size for f in Path(DB_FOLDER).rglob('*') if f.is_file())
    success(f"Database size: {format_size(total_size)}")
    
    # Inspect all components
    metadata = inspect_metadata(show_chunks=show_chunks)
    cache = inspect_embeddings_cache()
    bm25 = inspect_bm25_index()
    index_data = inspect_annoy_index()
    summaries = inspect_document_summaries()
    history = inspect_file_history()
    texts = inspect_document_texts()
    report = inspect_ingestion_report()
    
    # Summary
    header("📊 SUMMARY")
    
    if metadata:
        success(f"✓ Metadata: {format_number(len(metadata))} chunks")
    if cache:
        success(f"✓ Cache: {format_number(len(cache))} embeddings")
    if bm25:
        success(f"✓ BM25: Keyword index loaded")
    if index_data:
        if isinstance(index_data, tuple):
            index, uuid_map = index_data
            success(f"✓ Annoy: {format_number(index.get_n_items())} vectors")
        else:
            success(f"✓ Annoy: Index file exists (module not available)")
    if summaries:
        success(f"✓ Summaries: {format_number(len(summaries))} documents")
    if history:
        success(f"✓ History: {format_number(len(history))} files processed")
    if texts:
        success(f"✓ Texts: {format_number(len(texts))} document files")
    
    # Calculations
    if metadata and index_data and isinstance(index_data, tuple):
        index, uuid_map = index_data
        num_docs = len(summaries) if summaries else 0
        num_chunks = len(metadata)
        num_vectors = index.get_n_items()
        
        if num_docs > 0:
            avg_chunks = num_chunks / num_docs
            print(f"\n{Colors.BOLD}Averages:{Colors.END}")
            info("Chunks per document", f"{avg_chunks:.1f}")
            info("Vectors per document", f"{num_vectors / num_docs:.1f}")
        
        # Capacity estimate
        print(f"\n{Colors.BOLD}Capacity estimate (100ms SLA):{Colors.END}")
        
        # Based on 30ms Annoy budget
        vectors_per_doc = num_vectors / num_docs if num_docs > 0 else 62.5
        
        capacity_estimates = {
            "Conservative (3K docs)": int(3000),
            "Acceptable (4K docs)": int(4000),
            "Stretch (5K docs)": int(5000),
        }
        
        for label, doc_count in capacity_estimates.items():
            vector_count = int(doc_count * vectors_per_doc)
            print(f"  {Colors.CYAN}▸ {label:25}{Colors.END} → {Colors.GREEN}{format_number(vector_count):>12}{Colors.END} vectors")
    
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'=' * 80}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'Inspection complete!'.center(80)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'=' * 80}{Colors.END}\n")

if __name__ == "__main__":
    import sys
    
    # Parse command line arguments
    show_chunks = 0
    if len(sys.argv) > 1:
        try:
            show_chunks = int(sys.argv[1])
        except ValueError:
            print(f"{Colors.RED}Error: Argument must be a number{Colors.END}")
            print(f"{Colors.BOLD}Usage:{Colors.END} python3 inspect_rag_db.py [number_of_chunks_to_show]")
            print(f"  Example: python3 inspect_rag_db.py 10")
            sys.exit(1)
    
    main(show_chunks=show_chunks)

