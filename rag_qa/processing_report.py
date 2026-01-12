"""
Processing report generation for Q&A document ingestion.
"""
import json
import time
from pathlib import Path
from typing import List, Dict
from . import config


class ProcessingReport:
    """Track and report Q&A processing results."""
    
    def __init__(self):
        self.documents = []
        self.start_time = time.time()
        self.report_path = Path(config.QA_DB_FOLDER) / "processing_report.json"
    
    def add_document(self, doc_result: Dict):
        """Add a document processing result."""
        self.documents.append({
            **doc_result,
            'processed_at': time.strftime('%Y-%m-%d %H:%M:%S')
        })
    
    def get_summary(self) -> Dict:
        """Get processing summary statistics."""
        total_docs = len(self.documents)
        successful = sum(1 for d in self.documents if d.get('success', False))
        failed = total_docs - successful
        
        total_qas = sum(d.get('qa_count', 0) for d in self.documents if d.get('success'))
        total_tokens_sent = sum(d.get('tokens_sent', 0) for d in self.documents)
        total_tokens_received = sum(d.get('tokens_received', 0) for d in self.documents)
        total_chunks = sum(d.get('chunks_processed', 0) for d in self.documents)
        
        elapsed = time.time() - self.start_time
        
        return {
            'total_documents': total_docs,
            'successful': successful,
            'failed': failed,
            'total_qa_pairs': total_qas,
            'total_chunks_processed': total_chunks,
            'total_tokens_sent': total_tokens_sent,
            'total_tokens_received': total_tokens_received,
            'processing_time_seconds': int(elapsed),
            'failed_documents': [
                {
                    'filename': d['filename'],
                    'error': d.get('error', 'Unknown error')
                }
                for d in self.documents if not d.get('success', False)
            ]
        }
    
    def save(self):
        """Save report to JSON file (append mode)."""
        # Load existing report if it exists
        existing_data = []
        if self.report_path.exists():
            try:
                with open(self.report_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = [existing_data]
            except:
                existing_data = []
        
        # Create new report entry
        report_entry = {
            'report_date': time.strftime('%Y-%m-%d %H:%M:%S'),
            'summary': self.get_summary(),
            'documents': self.documents
        }
        
        # Append to existing reports
        existing_data.append(report_entry)
        
        # Save
        with open(self.report_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 Processing report saved to: {self.report_path}")
    
    def print_summary(self):
        """Print formatted summary to console."""
        summary = self.get_summary()
        
        print("\n" + "="*80)
        print("📊 PROCESSING SUMMARY")
        print("="*80)
        print(f"Total documents:    {summary['total_documents']}")
        print(f"✓ Successful:       {summary['successful']}")
        print(f"✗ Failed:           {summary['failed']}")
        print(f"Total Q&A pairs:    {summary['total_qa_pairs']:,}")
        print(f"Total chunks:       {summary['total_chunks_processed']}")
        print(f"Tokens sent:        {summary['total_tokens_sent']:,}")
        print(f"Tokens received:    {summary['total_tokens_received']:,}")
        print(f"Processing time:    {summary['processing_time_seconds']} seconds")
        
        if summary['failed_documents']:
            print(f"\n⚠️  FAILED DOCUMENTS:")
            for failed in summary['failed_documents']:
                print(f"  - {failed['filename']}")
                print(f"    Error: {failed['error'][:100]}")
        
        print("="*80)

