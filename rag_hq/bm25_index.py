"""
BM25 keyword-based search for hybrid retrieval.
"""
import logging
import math
import re
from typing import List, Tuple, Dict
from collections import Counter

logger = logging.getLogger("rag-assistant-enhanced")


class BM25Index:
    """
    Simple BM25 implementation for keyword-based search.
    Uses standard BM25 parameters: k1=1.5, b=0.75
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents = {}  # uuid -> document text
        self.doc_lengths = {}  # uuid -> document length
        self.avg_doc_length = 0
        self.term_frequencies = {}  # uuid -> {term: frequency}
        self.doc_frequencies = {}  # term -> number of docs containing term
        self.num_docs = 0
        
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into terms."""
        # Lowercase and split on non-alphanumeric
        text = text.lower()
        tokens = re.findall(r'\b\w+\b', text)
        return tokens
    
    def add_document(self, uuid: str, text: str):
        """Add a document to the index."""
        tokens = self.tokenize(text)
        
        self.documents[uuid] = text
        self.doc_lengths[uuid] = len(tokens)
        self.term_frequencies[uuid] = Counter(tokens)
        
        # Update document frequencies
        unique_terms = set(tokens)
        for term in unique_terms:
            self.doc_frequencies[term] = self.doc_frequencies.get(term, 0) + 1
        
        self.num_docs += 1
        
        # Update average document length
        self.avg_doc_length = sum(self.doc_lengths.values()) / self.num_docs
    
    def compute_idf(self, term: str) -> float:
        """Compute inverse document frequency for a term."""
        df = self.doc_frequencies.get(term, 0)
        if df == 0:
            return 0.0
        
        # Standard BM25 IDF formula
        idf = math.log((self.num_docs - df + 0.5) / (df + 0.5) + 1.0)
        return idf
    
    def compute_score(self, query_terms: List[str], uuid: str) -> float:
        """Compute BM25 score for a document given query terms."""
        if uuid not in self.documents:
            return 0.0
        
        score = 0.0
        doc_length = self.doc_lengths[uuid]
        term_freqs = self.term_frequencies[uuid]
        
        for term in query_terms:
            if term not in term_freqs:
                continue
            
            idf = self.compute_idf(term)
            tf = term_freqs[term]
            
            # BM25 formula
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / self.avg_doc_length))
            
            score += idf * (numerator / denominator)
        
        return score
    
    def search(self, query: str, n: int = 10) -> List[Tuple[str, float]]:
        """
        Search for top-n documents matching the query.
        
        Returns:
            List of (uuid, score) tuples sorted by score descending
        """
        query_terms = self.tokenize(query)
        
        if not query_terms:
            return []
        
        # Score all documents
        scores = []
        for uuid in self.documents:
            score = self.compute_score(query_terms, uuid)
            if score > 0:
                scores.append((uuid, score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:n]
    
    def get_num_docs(self) -> int:
        """Return number of documents in index."""
        return self.num_docs
    
    def clear(self):
        """Clear the index."""
        self.documents = {}
        self.doc_lengths = {}
        self.term_frequencies = {}
        self.doc_frequencies = {}
        self.num_docs = 0
        self.avg_doc_length = 0


def merge_hybrid_results(
    semantic_results: List[Tuple[str, float]],
    bm25_results: List[Tuple[str, float]],
    semantic_weight: float = 0.7,
    bm25_weight: float = 0.3
) -> List[Tuple[str, float]]:
    """
    Merge semantic and BM25 results with configurable weights.
    
    Args:
        semantic_results: List of (uuid, cosine_similarity) tuples
        bm25_results: List of (uuid, bm25_score) tuples
        semantic_weight: Weight for semantic similarity (default 0.7)
        bm25_weight: Weight for BM25 score (default 0.3)
        
    Returns:
        Merged list of (uuid, combined_score) tuples sorted by score
    """
    # Normalize scores to [0, 1] range
    def normalize_scores(results):
        if not results:
            return {}
        scores = [score for _, score in results]
        min_score = min(scores)
        max_score = max(scores)
        if max_score == min_score:
            return {uuid: 1.0 for uuid, _ in results}
        return {
            uuid: (score - min_score) / (max_score - min_score)
            for uuid, score in results
        }
    
    semantic_scores = normalize_scores(semantic_results)
    bm25_scores = normalize_scores(bm25_results)
    
    # Combine scores
    all_uuids = set(semantic_scores.keys()) | set(bm25_scores.keys())
    combined = []
    
    for uuid in all_uuids:
        semantic_score = semantic_scores.get(uuid, 0.0)
        bm25_score = bm25_scores.get(uuid, 0.0)
        
        combined_score = (
            semantic_weight * semantic_score +
            bm25_weight * bm25_score
        )
        
        combined.append((uuid, combined_score))
    
    # Sort by combined score descending
    combined.sort(key=lambda x: x[1], reverse=True)
    
    return combined

