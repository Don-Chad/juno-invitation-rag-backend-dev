"""
Simple Document Server for RAG Sources

Serves PDF/document files with direct download links.
Runs on a separate port from the main application.
"""
import os
import logging
from pathlib import Path
from flask import Flask, send_file, jsonify, abort
from werkzeug.utils import secure_filename

# Configuration
DOCUMENT_FOLDER = "./docs"
SERVER_PORT = 8888
SERVER_HOST = "0.0.0.0"

app = Flask(__name__)
logger = logging.getLogger(__name__)


def get_safe_filename(filename):
    """Convert filename to URL-safe format."""
    return secure_filename(filename)


def get_document_path(filename):
    """Get full path to document, ensuring it exists and is within docs folder."""
    # Security: Ensure filename is safe
    safe_filename = secure_filename(filename)
    doc_path = Path(DOCUMENT_FOLDER) / safe_filename
    
    # Security: Ensure path is within DOCUMENT_FOLDER (prevent directory traversal)
    doc_path = doc_path.resolve()
    base_path = Path(DOCUMENT_FOLDER).resolve()
    
    if not str(doc_path).startswith(str(base_path)):
        raise ValueError("Invalid document path")
    
    if not doc_path.exists():
        raise FileNotFoundError(f"Document not found: {filename}")
    
    return doc_path


@app.route('/')
def index():
    """List all available documents."""
    try:
        docs_path = Path(DOCUMENT_FOLDER)
        if not docs_path.exists():
            return jsonify({"error": "Document folder not found"}), 404
        
        # List all PDF and common document files
        extensions = ['.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls']
        documents = []
        
        for file_path in docs_path.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in extensions:
                documents.append({
                    'filename': file_path.name,
                    'url': f"/download/{get_safe_filename(file_path.name)}",
                    'size_mb': file_path.stat().st_size / (1024 * 1024)
                })
        
        return jsonify({
            'status': 'ok',
            'document_count': len(documents),
            'documents': sorted(documents, key=lambda x: x['filename'])
        })
    
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/download/<filename>')
def download_document(filename):
    """Download a specific document."""
    try:
        doc_path = get_document_path(filename)
        
        # Send file with proper content disposition for download
        return send_file(
            doc_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    
    except FileNotFoundError:
        logger.warning(f"Document not found: {filename}")
        abort(404, description=f"Document '{filename}' not found")
    
    except ValueError as e:
        logger.warning(f"Invalid document request: {filename}")
        abort(403, description="Invalid document path")
    
    except Exception as e:
        logger.error(f"Error serving document {filename}: {e}")
        abort(500, description="Internal server error")


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'document-server'})


def generate_document_url(filename, base_url=None):
    """Generate download URL for a document.
    
    Args:
        filename: Name of the document file
        base_url: Base URL of the server (default: http://64.23.171.50:8888)
    
    Returns:
        Full download URL
    """
    if base_url is None:
        # Use your server IP from the rules
        base_url = f"http://64.23.171.50:{SERVER_PORT}"
    
    safe_filename = get_safe_filename(filename)
    return f"{base_url}/download/{safe_filename}"


def start_server(host=SERVER_HOST, port=SERVER_PORT, debug=False):
    """Start the document server."""
    logger.info(f"=" * 60)
    logger.info(f"Starting Document Server")
    logger.info(f"=" * 60)
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    logger.info(f"Document folder: {DOCUMENT_FOLDER}")
    logger.info(f"=" * 60)
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Ensure document folder exists
    os.makedirs(DOCUMENT_FOLDER, exist_ok=True)
    
    # Start server
    start_server(debug=False)

