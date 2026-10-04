#!/usr/bin/env python3
"""
Flōyél — Territory Launcher
────────────────────────────
Run from the territories/ folder:
  python3 launcher.py

Starts ngrok automatically, opens launcher.html in Chrome.
Stop: Ctrl+C
"""

import http.server, socketserver, os, sys, json, socket, subprocess, threading, webbrowser, urllib.request, time

PORT = 8000
os.chdir(os.path.dirname(os.path.abspath(__file__)))


def start_ngrok(port):
    try:
        subprocess.Popen(
            ["ngrok", "http", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(2.5)
        return get_ngrok_url()
    except FileNotFoundError:
        return "NOT_INSTALLED"
    except:
        return None


def get_ngrok_url():
    try:
        with urllib.request.urlopen("http://localhost:4040/api/tunnels", timeout=3) as r:
            data = json.loads(r.read())
            for t in data.get("tunnels", []):
                if t.get("proto") == "https":
                    return t["public_url"]
            tunnels = data.get("tunnels", [])
            if tunnels: return tunnels[0]["public_url"]
    except: pass
    return None


def print_qr(url):
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url); qr.make(fit=True)
        print(); qr.print_ascii(invert=True); print()
    except ImportError:
        print(f"\n  ┌{'─'*51}┐")
        print(f"  │  {url:<49} │")
        print(f"  └{'─'*51}┘\n")


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

    def translate_path(self, path):
        import unicodedata, urllib.parse
        decoded = urllib.parse.unquote(path, encoding='utf-8')
        for form in ('NFC', 'NFD'):
            normalized = unicodedata.normalize(form, decoded)
            parts = normalized.split('/')
            encoded = '/'.join(urllib.parse.quote(p, safe='') if i > 0 else p
                               for i, p in enumerate(parts))
            result = super().translate_path(encoded)
            if os.path.exists(result): return result
        normalized = unicodedata.normalize('NFC', decoded)
        parts = normalized.split('/')
        encoded = '/'.join(urllib.parse.quote(p, safe='') if i > 0 else p
                           for i, p in enumerate(parts))
        return super().translate_path(encoded)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):

        if self.path == "/api/territories":
            slugs = []
            for name in sorted(os.listdir(".")):
                path = os.path.join(".", name)
                if (os.path.isdir(path)
                        and not name.startswith(".")
                        and not name.startswith("_")
                        and os.path.exists(os.path.join(path, "webar-scene.html"))):
                    slugs.append(name)
            self._json(slugs); return

        if self.path == "/api/ngrok":
            url = get_ngrok_url()
            if url:
                self._json({"url": url.replace("http://", "https://")})
            else:
                self._json({"url": None})
            return

        if self.path == "/api/config":
            self._json({"server": True, "sharedSymbols": False}); return

        super().do_GET()

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def open_chrome(url):
    time.sleep(1.5)
    for path in [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]:
        if os.path.exists(path):
            subprocess.Popen([path, url]); return
    webbrowser.open(url)


def main():
    if not os.path.exists("launcher.html"):
        print("\n  ✗  launcher.html not found.")
        print("     Run from the territories/ folder.")
        input("  Press Enter to exit..."); sys.exit(1)

    territories = [
        n for n in sorted(os.listdir("."))
        if os.path.isdir(n)
        and not n.startswith(".")
        and not n.startswith("_")
        and os.path.exists(os.path.join(n, "webar-scene.html"))
    ]

    print("\n" + "═"*52)
    print("  Flōyél — Territory Launcher")
    print("═"*52)
    print(f"\n  Folder:      {os.getcwd()}")
    print(f"  Territories: {len(territories)} found")
    for t in territories: print(f"    · {t}")
    print()

    print("  Starting ngrok…")
    ngrok = start_ngrok(PORT)

    if ngrok == "NOT_INSTALLED":
        print("  ✗  ngrok not found — install from ngrok.com")
        print("     Launcher will still open but phone access won't work.")
    elif ngrok:
        ngrok_https = ngrok.replace("http://", "https://")
        print(f"  ★  ngrok active: {ngrok_https}")
        print_qr(ngrok_https + "/launcher.html")
    else:
        print("  ✗  ngrok failed to start — try running manually: ngrok http 8000")

    launcher_url = f"http://localhost:{PORT}/launcher.html"
    print(f"  Launcher: {launcher_url}")
    print("\n  Press Ctrl+C to stop.")
    print("═"*52 + "\n")

    threading.Thread(target=open_chrome, args=(launcher_url,), daemon=True).start()

    try:
        with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Launcher closed.")
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n  ✗  Port {PORT} in use. Stop other server or change PORT.")
            input("  Press Enter to exit...")
        else: raise


if __name__ == "__main__":
    main()
