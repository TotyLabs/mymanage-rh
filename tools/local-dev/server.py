#!/usr/bin/env python3
"""
Simple HTTP server with correct MIME types for JS module loading.
Fixes: Failed to load module script - Expected JavaScript-or-Wasm module
"""

import http.server
import socketserver
import os
from pathlib import Path

class JSMimeTypeHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that serves .js files with correct MIME type"""
    
    def end_headers(self):
        # Set correct MIME type for JavaScript modules
        if self.path.endswith('.js'):
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
        elif self.path.endswith('.mjs'):
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
        super().end_headers()

def main():
    PORT = 8001
    # Ensure we're serving from the ui directory
    ui_dir = Path(__file__).parent.absolute()
    os.chdir(ui_dir)
    
    handler = JSMimeTypeHandler
    with socketserver.TCPServer(("", PORT), handler) as httpd:
        url = f"http://127.0.0.1:{PORT}"
        print(f"âœ“ Server started at {url}")
        print(f"âœ“ Serving from: {ui_dir}")
        print(f"âœ“ Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nâœ“ Server stopped")

if __name__ == "__main__":
    main()
