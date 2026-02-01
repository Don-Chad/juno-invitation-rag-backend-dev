#!/usr/bin/env python3
"""
Production-ready HTTP server for LiveKit embed iframe
Runs on port 3002 with security hardening
"""

import http.server
import socketserver
import os
import sys
from urllib.parse import urlparse, unquote
from pathlib import Path

PORT = 3002
DIRECTORY = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = "test_embed.html"

# Whitelist of allowed files to serve (security measure)
ALLOWED_FILES = {
    '/',
    '/test_embed.html',
    '/favicon.ico',  # Allow favicon requests
}

class SecureHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    # Disable directory listing
    def list_directory(self, path):
        self.send_error(403, "Directory listing forbidden")
        return None
    
    def do_GET(self):
        # Parse and sanitize the path
        parsed_path = urlparse(self.path)
        clean_path = unquote(parsed_path.path)
        
        # Normalize path to prevent directory traversal
        clean_path = os.path.normpath(clean_path)
        
        # Block directory traversal attempts
        if '..' in clean_path or clean_path.startswith('/..'):
            self.send_error(403, "Access forbidden")
            return
        
        # Only serve whitelisted files
        if clean_path not in ALLOWED_FILES:
            # Serve root for any unknown path
            if clean_path == '/' or clean_path == '':
                clean_path = '/' + HTML_FILE
            else:
                self.send_error(404, "File not found")
                return
        
        # Serve the HTML file for root path
        if clean_path == '/' or clean_path == '':
            clean_path = '/' + HTML_FILE
        
        # Update path and serve
        self.path = clean_path
        
        # Check if file exists
        file_path = os.path.join(DIRECTORY, clean_path.lstrip('/'))
        if not os.path.exists(file_path) and clean_path != '/favicon.ico':
            self.send_error(404, "File not found")
            return
        
        return super().do_GET()
    
    def do_HEAD(self):
        # Same security checks for HEAD requests
        return self.do_GET()
    
    def do_POST(self):
        # Block POST requests
        self.send_error(405, "Method not allowed")
        return
    
    def end_headers(self):
        # Security headers
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        self.send_header('X-XSS-Protection', '1; mode=block')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy', 
                        "default-src 'self'; "
                        "frame-src http://178.156.186.166:3001 https://178.156.186.166:3001; "
                        "style-src 'unsafe-inline' 'self'; "
                        "script-src 'self';")
        
        # CORS headers (only if needed)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        
        # Cache control
        self.send_header('Cache-Control', 'public, max-age=3600')
        
        super().end_headers()
    
    def log_message(self, format, *args):
        # Custom logging with more info
        sys.stderr.write("%s - - [%s] %s\n" %
                        (self.address_string(),
                         self.log_date_time_string(),
                         format%args))

class ReuseAddrTCPServer(socketserver.TCPServer):
    # Allow reusing the address to avoid "Address already in use" errors
    allow_reuse_address = True

if __name__ == "__main__":
    # Verify HTML file exists
    html_path = os.path.join(DIRECTORY, HTML_FILE)
    if not os.path.exists(html_path):
        print(f"ERROR: {HTML_FILE} not found in {DIRECTORY}")
        sys.exit(1)
    
    try:
        with ReuseAddrTCPServer(("", PORT), SecureHTTPRequestHandler) as httpd:
            print(f"")
            print(f"=" * 60)
            print(f"🔒 Production Embed Server Running (Secured)")
            print(f"=" * 60)
            print(f"")
            print(f"  🌐 Server URL: http://localhost:{PORT}")
            print(f"  📄 Serving:    {HTML_FILE}")
            print(f"")
            print(f"  Security features enabled:")
            print(f"    ✓ Directory traversal protection")
            print(f"    ✓ File whitelist enforcement")
            print(f"    ✓ Security headers (CSP, X-Frame-Options, etc.)")
            print(f"    ✓ Directory listing disabled")
            print(f"    ✓ POST requests blocked")
            print(f"")
            print(f"  LiveKit embed source:")
            print(f"    http://178.156.186.166:3001")
            print(f"")
            print(f"  Press Ctrl+C to stop the server")
            print(f"")
            print(f"=" * 60)
            print(f"")
            
            httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n\n✓ Server stopped gracefully.")
    except OSError as e:
        if e.errno == 98:  # Address already in use
            print(f"\nERROR: Port {PORT} is already in use.")
            print(f"Kill the existing process or choose a different port.")
        else:
            print(f"\nERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

