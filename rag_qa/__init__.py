"""
Q&A-based RAG system for precise factual retrieval.

This system generates question-answer pairs from documents and indexes them
for exact answer lookup. Complementary to the chunk-based rag_hq system.
"""
from .state import state, QAStats

__all__ = ['state', 'QAStats']

