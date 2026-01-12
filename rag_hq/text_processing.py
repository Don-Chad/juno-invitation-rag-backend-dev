"""
Text extraction and chunking functionality.
"""
import asyncio
import os
import re
import logging
import aiofiles
import PyPDF2
import docx
import spacy
from typing import List, Tuple, Dict
import numpy as np

from .config import (
    CHUNK_SIZE_TOKENS, CHUNK_OVERLAP_RATIO, MAX_CHUNK_SIZE_CHARS,
    SAFE_EMBEDDING_SIZE_CHARS
)
from .state import state
from .embeddings import create_embeddings, _embedding_cache_key

logger = logging.getLogger("rag-assistant-enhanced")


def clean_text_for_embedding(text: str) -> str:
    """
    Clean and validate text before sending to embedding server.
    Removes problematic content like TOC artifacts, excessive dots, etc.
    """
    if not text:
        return ""
    
    # Replace excessive dots (TOC artifacts like "...............")
    # Keep max 3 consecutive dots
    text = re.sub(r'\.{4,}', '...', text)
    
    # Replace excessive spaces/tabs
    text = re.sub(r'[ \t]{4,}', ' ', text)
    
    # Replace multiple newlines with max 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove standalone page numbers (lines with just 1-3 digits)
    text = re.sub(r'^\s*\d{1,3}\s*$', '', text, flags=re.MULTILINE)
    
    # Clean up Unicode issues
    # Replace non-breaking spaces
    text = text.replace('\u00a0', ' ')
    text = text.replace('\u202f', ' ')
    text = text.replace('\u2009', ' ')
    
    # Replace dashes with hyphens
    text = text.replace('\u2013', '-')  # en dash
    text = text.replace('\u2014', '-')  # em dash
    text = text.replace('\u2015', '-')  # horizontal bar
    
    # Replace ellipsis
    text = text.replace('\u2026', '...')
    
    # Remove soft hyphens
    text = text.replace('\u00ad', '')
    
    # Final cleanup
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return text


def is_valid_chunk(text: str) -> bool:
    """
    Validate that a chunk contains meaningful text content.
    Returns False for TOC artifacts, page numbers only, etc.
    """
    if not text or len(text.strip()) < 20:
        return False
    
    # Count actual words (letters)
    words = re.findall(r'\b[a-zA-Z]{2,}\b', text)
    word_count = len(words)
    
    # Count dots and numbers
    dot_count = text.count('.')
    digit_count = sum(c.isdigit() for c in text)
    
    # Reject if:
    # 1. Less than 5 real words
    if word_count < 5:
        return False
    
    # 2. More dots than words (TOC artifacts)
    if dot_count > word_count * 2:
        return False
    
    # 3. More than 30% digits (page numbers, indices)
    if digit_count > len(text) * 0.3:
        return False
    
    # 4. Very short average word length (just numbers/abbreviations)
    if words:
        avg_word_len = sum(len(w) for w in words) / len(words)
        if avg_word_len < 2.5:
            return False
    
    return True


async def initialize_spacy():
    """Initialize spaCy model for sentence segmentation asynchronously."""
    def _load_spacy():
        try:
            # Force spaCy to use CPU only (disable GPU)
            spacy.require_cpu()
            
            import importlib.util
            if importlib.util.find_spec("en_core_web_sm") is not None:
                nlp = spacy.load("en_core_web_sm")
                logger.info("spaCy model loaded successfully (CPU-only mode)")
                return nlp
            else:
                try:
                    nlp = spacy.load("en")
                    logger.info("spaCy model 'en' loaded successfully (CPU-only mode)")
                    return nlp
                except:
                    logger.warning("No spaCy model found, falling back to simple segmentation")
                    return None
        except:
            logger.warning("spaCy initialization failed, falling back to simple segmentation")
            return None
    
    loop = asyncio.get_running_loop()
    state.nlp = await loop.run_in_executor(state.executor, _load_spacy)


async def extract_text_from_pdf(file_path):
    """Extract text from a PDF file asynchronously."""
    logger.info(f"Extracting text from PDF: {file_path}")
    
    def _extract_pdf():
        text = ""
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text += f"\n[Page {i+1}]\n{page_text}\n\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}")
            return ""
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(state.executor, _extract_pdf)


async def extract_text_from_docx(file_path):
    """Extract text from a DOCX file asynchronously."""
    logger.info(f"Extracting text from DOCX: {file_path}")
    
    def _extract_docx():
        text = ""
        try:
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text + "\n\n"
            return text
        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path}: {e}")
            return ""
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(state.executor, _extract_docx)


async def extract_text_from_txt(file_path):
    """Extract text from a TXT file asynchronously."""
    logger.info(f"Extracting text from TXT: {file_path}")
    try:
        async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return await file.read()
    except Exception as e:
        logger.error(f"Error extracting text from TXT {file_path}: {e}")
        return ""


async def extract_text(file_path):
    """Extract text from a document based on its file extension."""
    file_ext = os.path.splitext(file_path)[1].lower()
    
    if file_ext == '.pdf':
        return await extract_text_from_pdf(file_path)
    elif file_ext in ['.docx', '.doc']:
        return await extract_text_from_docx(file_path)
    elif file_ext in ['.txt', '.md', '.csv', '.json']:
        return await extract_text_from_txt(file_path)
    else:
        logger.warning(f"Unsupported file format: {file_ext} for file {file_path}")
        return ""


async def smart_chunk_text(text: str, filename: str) -> List[Tuple[str, Dict]]:
    """Enhanced text chunking with character-based sizing and metadata."""
    if not text or not text.strip():
        return []
    
    def _chunk_text():
        chunks_with_metadata = []
        
        # Use spaCy for sentence segmentation if available
        if state.nlp:
            doc = state.nlp(text)
            sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        else:
            sentences = re.split(r'(?<=[.!?])\s+', text)
            sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return []
        
        # Use configured chunk size (now supports up to 1250 tokens with 2048 context)
        from .config import CHUNK_SIZE_TOKENS
        adjusted_chunk_size_tokens = CHUNK_SIZE_TOKENS
        
        current_chunk = []
        current_chars = 0
        estimated_tokens = 0
        chunk_index = 0
        
        chars_per_token = 4
        target_tokens = adjusted_chunk_size_tokens
        target_chars = target_tokens * chars_per_token
        
        # Track character positions for context expansion
        char_position = 0
        sentence_positions = []
        
        for sentence in sentences:
            start_pos = text.find(sentence, char_position)
            if start_pos != -1:
                sentence_positions.append((start_pos, start_pos + len(sentence)))
                char_position = start_pos + len(sentence)
            else:
                sentence_positions.append((char_position, char_position + len(sentence)))
                char_position += len(sentence)
        
        for i, sentence in enumerate(sentences):
            sentence_chars = len(sentence)
            sentence_tokens = sentence_chars / chars_per_token
            
            if estimated_tokens + sentence_tokens > target_tokens and current_chunk:
                chunk_text = ' '.join(current_chunk)
                
                # Enforce hard character limit (normal behavior when breaking at sentence boundaries)
                if len(chunk_text) > MAX_CHUNK_SIZE_CHARS:
                    logger.debug(f"Chunk exceeds MAX_CHUNK_SIZE_CHARS ({len(chunk_text)} > {MAX_CHUNK_SIZE_CHARS}), truncating")
                    chunk_text = chunk_text[:MAX_CHUNK_SIZE_CHARS]
                
                chunk_start_idx = i - len(current_chunk)
                chunk_end_idx = i - 1
                
                if chunk_start_idx >= 0 and chunk_end_idx < len(sentence_positions):
                    char_start = sentence_positions[chunk_start_idx][0]
                    char_end = sentence_positions[chunk_end_idx][1]
                else:
                    char_start = 0
                    char_end = len(chunk_text)
                
                metadata = {
                    'filename': filename,
                    'chunk_index': chunk_index,
                    'start_sentence': chunk_index * (1 - CHUNK_OVERLAP_RATIO),
                    'estimated_tokens': estimated_tokens,
                    'char_start': char_start,
                    'char_end': char_end
                }
                chunks_with_metadata.append((chunk_text, metadata))
                
                # Start new chunk with overlap
                overlap_sentences = int(len(current_chunk) * CHUNK_OVERLAP_RATIO)
                current_chunk = current_chunk[-overlap_sentences:] if overlap_sentences > 0 else []
                current_chars = sum(len(s) for s in current_chunk)
                estimated_tokens = current_chars / chars_per_token
                chunk_index += 1
            
            current_chunk.append(sentence)
            current_chars += sentence_chars
            estimated_tokens = current_chars / chars_per_token
        
        # Add the last chunk
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            
            # Enforce hard character limit (normal behavior when breaking at sentence boundaries)
            if len(chunk_text) > MAX_CHUNK_SIZE_CHARS:
                logger.debug(f"Chunk exceeds MAX_CHUNK_SIZE_CHARS ({len(chunk_text)} > {MAX_CHUNK_SIZE_CHARS}), truncating")
                chunk_text = chunk_text[:MAX_CHUNK_SIZE_CHARS]
            
            chunk_start_idx = len(sentences) - len(current_chunk)
            chunk_end_idx = len(sentences) - 1
            
            if chunk_start_idx >= 0 and chunk_end_idx < len(sentence_positions):
                char_start = sentence_positions[chunk_start_idx][0]
                char_end = sentence_positions[chunk_end_idx][1]
            else:
                char_start = 0
                char_end = len(chunk_text)
            
            metadata = {
                'filename': filename,
                'chunk_index': chunk_index,
                'start_sentence': chunk_index * (1 - CHUNK_OVERLAP_RATIO),
                'estimated_tokens': estimated_tokens,
                'char_start': char_start,
                'char_end': char_end
            }
            chunks_with_metadata.append((chunk_text, metadata))
        
        # Filter out invalid chunks (TOC, page numbers, etc.)
        valid_chunks = []
        for chunk_text, metadata in chunks_with_metadata:
            if is_valid_chunk(chunk_text):
                valid_chunks.append((chunk_text, metadata))
            else:
                logger.debug(f"Skipping invalid chunk {metadata['chunk_index']} from {filename}: {chunk_text[:100]}...")
        
        if len(valid_chunks) < len(chunks_with_metadata):
            logger.info(f"Filtered out {len(chunks_with_metadata) - len(valid_chunks)} invalid chunks from {filename}")
        
        return valid_chunks
    
    loop = asyncio.get_running_loop()
    chunks_with_metadata = await loop.run_in_executor(state.executor, _chunk_text)
    
    # Deduplicate nearly identical chunks
    deduplicated_chunks = await deduplicate_chunks(chunks_with_metadata)
    
    return deduplicated_chunks


async def deduplicate_chunks(chunks_with_metadata: List[Tuple[str, Dict]], 
                      similarity_threshold: float = 0.95) -> List[Tuple[str, Dict]]:
    """Remove nearly identical chunks based on cosine similarity."""
    if len(chunks_with_metadata) <= 1:
        return chunks_with_metadata
    
    # Create embeddings for all chunks
    chunk_embeddings = []
    for i, (chunk_text, metadata) in enumerate(chunks_with_metadata):
        # Clean text before embedding
        chunk_text_cleaned = clean_text_for_embedding(chunk_text)
        
        chunk_size = len(chunk_text_cleaned)
        if chunk_size > SAFE_EMBEDDING_SIZE_CHARS:
            logger.warning(f"Chunk {i} too large ({chunk_size} chars), truncating to {SAFE_EMBEDDING_SIZE_CHARS}")
            chunk_text_for_embedding = chunk_text_cleaned[:SAFE_EMBEDDING_SIZE_CHARS]
        else:
            chunk_text_for_embedding = chunk_text_cleaned
        
        logger.debug(f"Chunk {i}: {len(chunk_text_for_embedding)} chars (original: {chunk_size})")
        embedding = await create_embeddings(chunk_text_for_embedding)
        chunk_embeddings.append(embedding)
    
    # Find duplicates
    unique_indices = []
    for i in range(len(chunks_with_metadata)):
        is_duplicate = False
        for j in unique_indices:
            sim = np.dot(chunk_embeddings[i], chunk_embeddings[j])
            if sim > similarity_threshold:
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_indices.append(i)
    
    return [chunks_with_metadata[i] for i in unique_indices]
