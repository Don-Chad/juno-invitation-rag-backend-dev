"""
State management for Q&A RAG system.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


@dataclass
class QAStats:
    """Track Q&A generation statistics."""
    total_requests: int = 0
    total_tokens_sent: int = 0
    total_tokens_received: int = 0
    total_questions_generated: int = 0
    total_documents_processed: int = 0
    processing_time_ms: int = 0
    errors: List[str] = field(default_factory=list)
    
    def add_request(self, tokens_sent: int, tokens_received: int, questions_generated: int):
        """Add statistics from a single request."""
        self.total_requests += 1
        self.total_tokens_sent += tokens_sent
        self.total_tokens_received += tokens_received
        self.total_questions_generated += questions_generated
    
    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'total_requests': self.total_requests,
            'total_tokens_sent': self.total_tokens_sent,
            'total_tokens_received': self.total_tokens_received,
            'total_questions_generated': self.total_questions_generated,
            'total_documents_processed': self.total_documents_processed,
            'processing_time_ms': self.processing_time_ms,
            'errors': self.errors
        }
    
    def print_summary(self):
        """Print formatted statistics summary."""
        print("\n" + "="*60)
        print("Q&A GENERATION STATISTICS")
        print("="*60)
        print(f"Total Requests:       {self.total_requests:,}")
        print(f"Tokens Sent:          {self.total_tokens_sent:,}")
        print(f"Tokens Received:      {self.total_tokens_received:,}")
        print(f"Questions Generated:  {self.total_questions_generated:,}")
        print(f"Documents Processed:  {self.total_documents_processed}")
        print(f"Processing Time:      {self.processing_time_ms:,} ms")
        if self.errors:
            print(f"\nErrors ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
        print("="*60)


@dataclass
class QAState:
    """Global state for Q&A RAG system."""
    qa_enabled: bool = False
    annoy_index: Optional[object] = None
    qa_metadata: List[Dict] = field(default_factory=list)
    processed_files: Dict[str, str] = field(default_factory=dict)
    stats: QAStats = field(default_factory=QAStats)
    
    def reset_stats(self):
        """Reset statistics."""
        self.stats = QAStats()


# Global state instance
state = QAState()

