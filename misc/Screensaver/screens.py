#!/usr/bin/env python3
"""
Screensaver launcher — serves on port 8765 and opens the browser automatically.
Run with:  python3 launch.py
Or pick a different port:  python3 launch.py 8766
"""

import sys
import os
import threading
import webbrowser
import http.server
import socketserver

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765

# serve from the directory this script lives in
os.chdir(os.path.dirname(os.path.abspath(__file__)))

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # silence request logs — cleaner terminal

def open_browser():
    webbrowser.open(f"http://localhost:{PORT}/screensaver.html")

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"  ✦  Screensaver running at http://localhost:{PORT}/screensaver.html")
    print(f"     Press Ctrl+C to stop.\n")
    threading.Timer(0.8, open_browser).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
