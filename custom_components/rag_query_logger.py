"""
RAG Query Logger - Detailed logging of RAG search queries and results

This module provides formatted logging of RAG queries to help understand
what information is being retrieved and added to the conversation context.
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("rag-query-logger")
logger.setLevel(logging.ERROR) # Disabled INFO logs as requested


class RAGQueryLogger:
    """Handles formatted logging of RAG queries and results to file"""
    
    def __init__(self, log_file: str, enabled: bool = True):
        self.log_file = log_file
        self.enabled = enabled
        self.session_start = datetime.now()
        
        if self.enabled:
            self._write_session_header()
    
    def _write_session_header(self):
        """Write a session header when logger is initialized"""
        header = f"""
{'=' * 100}
{'=' * 100}
NEW SESSION STARTED
{'=' * 100}
Session Start Time: {self.session_start.strftime('%Y-%m-%d %H:%M:%S')}
{'=' * 100}
{'=' * 100}

"""
        self._append_to_file(header)
    
    def _append_to_file(self, content: str):
        """Append content to the log file"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            logger.error(f"Failed to write to RAG query log: {e}")
    
    def log_query(
        self,
        query: str,
        user_id: str,
        conversation_id: Optional[str] = None,
        search_time_ms: float = 0.0,
        results: Optional[List[Dict[str, Any]]] = None,
        context_added: Optional[str] = None,
        token_count: int = 0,
        num_documents: int = 0,
        error: Optional[str] = None,
        rag_mode: Optional[str] = None
    ):
        """
        Log a RAG query with all its details
        
        Args:
            query: The search query text
            user_id: User identifier
            conversation_id: Optional conversation/room identifier
            search_time_ms: Search execution time in milliseconds
            results: List of retrieved documents
            context_added: The actual context text added to conversation
            token_count: Estimated token count of added context
            num_documents: Number of documents retrieved
            error: Error message if query failed
        """
        if not self.enabled:
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        
        # Build the log entry
        log_entry = f"""
╔{'═' * 98}╗
║  RAG QUERY LOG ENTRY{' ' * 76}║
╚{'═' * 98}╝

┌─ QUERY INFORMATION {'─' * 77}┐
│
│  Timestamp:        {timestamp}
│  User ID:          {user_id}
│  Conversation ID:  {conversation_id or 'N/A'}
│  RAG Mode:         {rag_mode or 'Unknown'}
│  Search Time:      {search_time_ms:.2f} ms
│
└{'─' * 98}┘

┌─ USER QUERY PROCESSED {'─' * 76}┐
│
│  User Message: "{query}"
│
└{'─' * 98}┘

"""
        
        # Add error information if present
        if error:
            log_entry += f"""
┌─ ERROR {'─' * 89}┐
│
│  ⚠️  Query failed: {error}
│
└{'─' * 98}┘

"""
        
        # Add results information
        if results:
            log_entry += f"""
┌─ SEARCH RESULTS {'─' * 80}┐
│
│  Documents Retrieved: {num_documents}
│  Total Tokens:        {token_count:,}
│
"""
            
            for idx, doc in enumerate(results, 1):
                source = doc.get('source', 'Unknown')
                summary = doc.get('summary', '')
                similarity = doc.get('similarity', 0)
                page = doc.get('page', 'N/A')
                
                log_entry += f"""│
│  ╔═ Document {idx} {'═' * (85 - len(str(idx)))}╗
│  ║
│  ║  Source: {source}
│  ║  Page: {page}
│  ║  Similarity: {similarity:.4f}
│  ║
"""
                
                # Add summary if present
                if summary:
                    summary_lines = self._wrap_text(summary, 88)
                    log_entry += f"│  ║  Summary:\n"
                    for line in summary_lines:
                        log_entry += f"│  ║    {line}\n"
                    log_entry += f"│  ║\n"
                
                # Add all content/snippets - check for various possible keys
                content_keys = ['content', 'text', 'snippet_1', 'snippet_2', 'snippet_3']
                snippet_count = 0
                
                for key in content_keys:
                    if key in doc and doc[key]:
                        snippet_count += 1
                        snippet_text = doc[key]
                        snippet_lines = self._wrap_text(snippet_text, 86)
                        
                        content_label = "Content" if key in ['content', 'text'] else f"Fragment {snippet_count}"
                        log_entry += f"│  ║  {content_label}:\n"
                        for line in snippet_lines:
                            log_entry += f"│  ║    {line}\n"
                        log_entry += f"│  ║\n"
                
                log_entry += f"│  ╚{'═' * 94}╝\n"
            
            log_entry += f"│\n└{'─' * 98}┘\n"
        else:
            log_entry += f"""
┌─ SEARCH RESULTS {'─' * 80}┐
│
│  ⚠️  No results found or results not provided
│
└{'─' * 98}┘

"""
        
        # Add context information - FULL CONTEXT WITHOUT TRUNCATION
        if context_added:
            log_entry += f"""
┌─ FULL CONTEXT ADDED TO CONVERSATION {'─' * 58}┐
│
│  Length: {len(context_added)} characters, ~{token_count:,} tokens
│  NOTE: COMPLETE CONTEXT SHOWN BELOW (NO TRUNCATION)
│
"""
            
            # Show FULL context without any truncation
            context_lines = self._wrap_text(context_added, 95)
            
            for line in context_lines:
                log_entry += f"│  {line}\n"
            
            log_entry += f"│\n└{'─' * 98}┘\n"
        
        # Add footer
        log_entry += f"""

{'─' * 100}
END OF QUERY LOG ENTRY
{'─' * 100}


"""
        
        # Write to file
        self._append_to_file(log_entry)
        logger.info(f"📝 RAG query logged to {self.log_file}")
    
    def _wrap_text(self, text: str, width: int) -> List[str]:
        """Wrap text to specified width, respecting word boundaries"""
        if not text:
            return []
        
        words = text.split()
        lines = []
        current_line = ""
        
        for word in words:
            if len(current_line) + len(word) + 1 <= width:
                if current_line:
                    current_line += " " + word
                else:
                    current_line = word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word
        
        if current_line:
            lines.append(current_line)
        
        return lines if lines else [""]
    
    def log_session_summary(self, total_queries: int, total_documents: int, total_tokens: int):
        """Log a summary at the end of a session"""
        if not self.enabled:
            return
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        duration = datetime.now() - self.session_start
        
        summary = f"""
╔{'═' * 98}╗
║  SESSION SUMMARY{' ' * 82}║
╚{'═' * 98}╝

Session End Time:      {timestamp}
Session Duration:      {duration}
Total Queries:         {total_queries}
Total Documents:       {total_documents}
Total Tokens:          {total_tokens:,}

{'=' * 100}

"""
        self._append_to_file(summary)

