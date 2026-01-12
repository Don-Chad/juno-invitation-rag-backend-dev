"""
Document splitting utilities for large documents.

Splits documents >30k tokens into smaller chunks with overlap for better Q&A generation.
"""
import re
from typing import List, Tuple
from .qa_generator import count_tokens


def split_by_semantic_boundaries(text: str, page_texts: dict = None) -> List[Tuple[str, str]]:
    """
    Split text by semantic boundaries (pages, sections, paragraphs).
    
    Returns:
        List of (section_text, section_label) tuples
    """
    sections = []
    
    # If we have page information, use it
    if page_texts:
        for page_num, page_text in page_texts.items():
            sections.append((page_text, f"Page {page_num}"))
        return sections
    
    # Otherwise split by double newlines (paragraphs)
    paragraphs = text.split('\n\n')
    for i, para in enumerate(paragraphs, 1):
        if para.strip():
            sections.append((para.strip(), f"Section {i}"))
    
    return sections


def create_chunks_with_overlap(text: str, chunk_size_tokens: int = 10000, 
                               overlap_tokens: int = 500, page_texts: dict = None) -> List[dict]:
    """
    Split document into chunks with overlap.
    
    Args:
        text: Full document text
        chunk_size_tokens: Target tokens per chunk (default 10k)
        overlap_tokens: Overlap between chunks (default 500)
        page_texts: Optional dict of page_num -> text for semantic splitting
    
    Returns:
        List of chunk dicts with: {text, start_page, end_page, chunk_num, total_chunks}
    """
    
    # Get semantic sections
    sections = split_by_semantic_boundaries(text, page_texts)
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    current_pages = []
    
    for section_text, section_label in sections:
        section_tokens = count_tokens(section_text)
        
        # Extract page number from label if available
        page_match = re.search(r'Page (\d+)', section_label)
        page_num = int(page_match.group(1)) if page_match else None
        
        # If adding this section would exceed chunk size
        if current_tokens + section_tokens > chunk_size_tokens and current_chunk:
            # Save current chunk
            chunks.append({
                'text': '\n\n'.join(current_chunk),
                'tokens': current_tokens,
                'start_page': min(current_pages) if current_pages else None,
                'end_page': max(current_pages) if current_pages else None,
                'chunk_num': len(chunks) + 1,
            })
            
            # Start new chunk with overlap
            # Keep last few sections for context overlap
            overlap_sections = []
            overlap_tokens_count = 0
            
            for i in range(len(current_chunk) - 1, -1, -1):
                section_overlap_tokens = count_tokens(current_chunk[i])
                if overlap_tokens_count + section_overlap_tokens <= overlap_tokens:
                    overlap_sections.insert(0, current_chunk[i])
                    overlap_tokens_count += section_overlap_tokens
                else:
                    break
            
            current_chunk = overlap_sections
            current_tokens = overlap_tokens_count
            current_pages = [p for p in current_pages[-2:] if p] if current_pages else []
        
        # Add section to current chunk
        current_chunk.append(section_text)
        current_tokens += section_tokens
        if page_num:
            current_pages.append(page_num)
    
    # Add final chunk
    if current_chunk:
        chunks.append({
            'text': '\n\n'.join(current_chunk),
            'tokens': current_tokens,
            'start_page': min(current_pages) if current_pages else None,
            'end_page': max(current_pages) if current_pages else None,
            'chunk_num': len(chunks) + 1,
        })
    
    # Add total_chunks to all
    total_chunks = len(chunks)
    for chunk in chunks:
        chunk['total_chunks'] = total_chunks
    
    return chunks


def get_chunk_title(base_title: str, chunk: dict) -> str:
    """Generate title for a document chunk."""
    if chunk['total_chunks'] == 1:
        return base_title
    
    page_info = ""
    if chunk['start_page'] and chunk['end_page']:
        if chunk['start_page'] == chunk['end_page']:
            page_info = f", Pagina {chunk['start_page']}"
        else:
            page_info = f", Pagina's {chunk['start_page']}-{chunk['end_page']}"
    
    return f"{base_title} (Deel {chunk['chunk_num']}/{chunk['total_chunks']}{page_info})"

