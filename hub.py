#!/usr/bin/env python3
"""
Flōyél Hub
──────────
Boots the hub: serves the whole floyel-symbols/ folder locally, opens the
terminal+taskbar shell as the main window, and exposes a small JS API so
the shell (and other apps, like the library's symbol viewer) can open or
focus windows without ever touching the OS's real browser.

Run:  python3 hub.py
Stop: Ctrl+C (or close the last window)
"""

import http.server
import socketserver
import threading
import os
import sys
import subprocess
import time
import json
import re
import platform
import zipfile
import shutil
import webbrowser
import urllib.request
import importlib.util
import webview
from pathlib import Path

PORT = 5050
LIBRARY_PORT = 5000       # the library's own Flask server, imported and run separately —
                           # it needs real API routes (/api/symbols, /api/rpc) that a plain
                           # static file server can't provide
TERRITORIES_PORT = 8000   # the territories launcher's own server, same reasoning —
                           # it needs /api/territories and /api/ngrok, which a plain
                           # static server can't provide either
ROOT = os.path.dirname(os.path.abspath(__file__))
SHELL_PATH = "shell/hub-shell.html"   # the terminal+taskbar page built in the design pass

# ── Symbols, for the terminal's direct-access commands ────────────────────
# Ported from the old standalone terminal tool (run.py): each symbol is a
# folder under symbols/ named "<id> - <name>" (e.g. "0001 - inni"),
# containing a viewer.html and/or a manifest.json and/or raw media
# (*.gif / *.mp3). symbols/ is already served by the hub's own static
# server alongside shell/, library/, etc. — no separate route needed.
SYMBOLS_DIR = os.path.join(ROOT, "symbols")
MISC_DIR = os.path.join(ROOT, "misc")   # the Start menu's "Misc" panel lists whatever's dropped in here


def _find_symbol_folder(symbol_id):
    """Same lookup rule as the old terminal tool: the first folder in
    symbols/ whose name CONTAINS the given id."""
    if not os.path.isdir(SYMBOLS_DIR):
        return None
    for name in sorted(os.listdir(SYMBOLS_DIR)):
        if symbol_id in name and os.path.isdir(os.path.join(SYMBOLS_DIR, name)):
            return name
    return None


def _first_file_match(folder_name, patterns):
    """Returns the first file in a symbol's folder matching any of the
    given glob patterns, checked in order (e.g. try *.gif before *.mp3)."""
    folder_path = Path(SYMBOLS_DIR) / folder_name
    for pattern in patterns:
        matches = sorted(folder_path.glob(pattern))
        if matches:
            return matches[0]
    return None


def _url_path_for_symbol_file(file_path):
    """Converts an absolute path under ROOT into the relative, forward-slash
    path open_window()/url_for() expect."""
    return os.path.relpath(str(file_path), ROOT).replace(os.sep, "/")

# ── Static file server for the whole floyel-symbols/ folder ──────────────
# Everything (shell, symbols/, library/, territories/, arg-map/) is served
# from one place so relative paths like ../symbols/ resolve the same way
# they do when files are opened directly.

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)
    def log_message(self, format, *args):
        pass
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

def start_server():
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        httpd.serve_forever()

def url_for(relative_path):
    return f"http://127.0.0.1:{PORT}/{relative_path.lstrip('/')}"


def start_library_server():
    """Imports library/server.py directly (not as a subprocess) and runs its
    Flask app in this thread. Importing rather than running the file avoids
    triggering its `if __name__ == "__main__":` block, so its own
    webbrowser.open() call never fires — the library's real API routes
    (/api/symbols, /api/rpc, chain_data.json fallback) become available
    without ever popping a real browser window."""
    server_path = os.path.join(ROOT, "library", "server.py")
    if not os.path.isfile(server_path):
        print("  (library/server.py not found yet — Library won't work until it's added)")
        return
    spec = importlib.util.spec_from_file_location("library_server", server_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.app.run(port=LIBRARY_PORT, debug=False, use_reloader=False, threaded=True)


_territories_module = None  # cached once imported, so start_ngrok can reuse it

def start_territories_server():
    """Imports territories/launcher.py directly (not as a subprocess) and runs
    its own server (with the /api/territories and /api/ngrok routes the real
    launcher.html depends on) in this thread. Same importing trick as the
    library: because main() — including its own eager ngrok start and its
    open_chrome() call — only runs under `if __name__ == "__main__":`,
    importing it never pops a real browser window or starts ngrok on its own;
    the hub controls both explicitly instead."""
    global _territories_module
    launcher_path = os.path.join(ROOT, "territories", "launcher.py")
    if not os.path.isfile(launcher_path):
        print("  (territories/launcher.py not found yet — Territories won't work until it's added)")
        return
    spec = importlib.util.spec_from_file_location("territories_launcher", launcher_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # runs its top-level os.chdir(territories/) — expected
    _territories_module = module
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", TERRITORIES_PORT), module.Handler) as httpd:
        httpd.serve_forever()


# ── Window sizing: windowed, not fullscreen ───────────────────────────────
def windowed_geometry(scale=0.85):
    """Returns (width, height, x, y) sized to a fraction of the primary
    screen and centered, instead of guessing a fixed resolution."""
    try:
        screen = webview.screens[0]
        sw, sh = screen.width, screen.height
    except Exception:
        sw, sh = 1440, 900  # fallback if screen info isn't available yet
    w, h = int(sw * scale), int(sh * scale)
    x, y = (sw - w) // 2, (sh - h) // 2
    return w, h, x, y


def fixed_geometry(width, height):
    """Returns (width, height, x, y) for a window that must stay a FIXED
    size regardless of screen size — e.g. the library's symbol viewer,
    which is designed around a specific layout, not a scaled one. Still
    centers it on screen; just doesn't scale the dimensions themselves."""
    try:
        screen = webview.screens[0]
        sw, sh = screen.width, screen.height
    except Exception:
        sw, sh = 1440, 900
    x, y = max((sw - width) // 2, 0), max((sh - height) // 2, 0)
    return width, height, x, y


def parse_window_meta(url):
    """Reads <meta name="window-width/height/x/y"> tags from a page's <head>,
    if present, so a page can declare its own preferred window geometry
    instead of the hub guessing a generic size for every app. Values can be
    plain pixel numbers or vh/vw viewport units (e.g. '92vh')."""
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            head = r.read(4096).decode("utf-8", errors="ignore")
    except Exception:
        return {}
    found = {}
    for key in ("window-width", "window-height", "window-x", "window-y"):
        m = re.search(rf'<meta\s+name=["\']{key}["\']\s+content=["\']([^"\']+)["\']', head)
        if m:
            found[key] = m.group(1).strip()
    return found


def resolve_dimension(value, screen_dim):
    """Converts a meta tag value like '520' or '92vh' into an int pixel size."""
    if value is None:
        return None
    if value.endswith("vh") or value.endswith("vw"):
        try:
            return int(screen_dim * (float(value[:-2]) / 100))
        except ValueError:
            return None
    try:
        return int(float(value))
    except ValueError:
        return None


def geometry_for_url(url, default_scale=0.85):
    """Sizes a window from the page's own meta tags if it declares them,
    falling back to the generic scaled/centered size otherwise."""
    try:
        screen = webview.screens[0]
        sw, sh = screen.width, screen.height
    except Exception:
        sw, sh = 1440, 900
    meta = parse_window_meta(url)
    w = resolve_dimension(meta.get("window-width"), sw) or int(sw * default_scale)
    h = resolve_dimension(meta.get("window-height"), sh) or int(sh * default_scale)
    x = resolve_dimension(meta.get("window-x"), sw)
    y = resolve_dimension(meta.get("window-y"), sh)
    if x is None: x = (sw - w) // 2
    if y is None: y = (sh - h) // 2
    return w, h, x, y


def _bind_resize_reflow(win):
    """Some pywebview backends — WKWebView on macOS in particular — don't
    reliably reflow their content when the native window is resized: the
    page's own layout stays exactly as it was at the last paint, so a
    shrunk window can visually lose grid cards that are still there, just
    outside the stale layout, rather than wrapping/scrolling to fit like
    it does when the CSS reflows normally in a browser. Nudging a resize
    event plus a 1px scroll after every native resize forces WebKit to
    recompute the page's actual layout against the window's real size."""
    def _on_resized(*_args):
        try:
            win.evaluate_js(
                "window.dispatchEvent(new Event('resize'));"
                "window.scrollBy(0,1); window.scrollBy(0,-1);"
            )
        except Exception:
            pass
    try:
        win.events.resized += _on_resized
    except Exception:
        pass


def get_local_ngrok_url(retries=10, delay=0.3):
    """Polls ngrok's local API for the public URL of the tunnel it just
    started. Same technique the territories chat's launch.py already uses."""
    for _ in range(retries):
        try:
            with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as r:
                data = json.loads(r.read())
                for t in data.get("tunnels", []):
                    if t.get("proto") == "https":
                        return t["public_url"]
                if data.get("tunnels"):
                    return data["tunnels"][0]["public_url"]
        except Exception:
            time.sleep(delay)
    return None


SETTINGS_PATH = os.path.join(ROOT, "hub_settings.json")

def load_settings():
    try:
        with open(SETTINGS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w") as f:
            json.dump(settings, f)
    except Exception as e:
        print(f"  (couldn't save settings: {e})")


BROWSER_PATHS = {
    "Darwin": {
        "Safari": "/Applications/Safari.app",
        "Google Chrome": "/Applications/Google Chrome.app",
        "Firefox": "/Applications/Firefox.app",
        "Brave Browser": "/Applications/Brave Browser.app",
        "Microsoft Edge": "/Applications/Microsoft Edge.app",
        "Arc": "/Applications/Arc.app",
    },
    "Windows": {
        "Google Chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "Firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "Microsoft Edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "Brave": r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    },
    "Linux": {
        "Google Chrome": "google-chrome",
        "Firefox": "firefox",
        "Brave": "brave-browser",
        "Chromium": "chromium-browser",
    },
}

def list_available_browsers():
    """Only offers browsers actually found on this machine — no manual list
    to keep in sync, no guessing what's installed."""
    system = platform.system()
    candidates = BROWSER_PATHS.get(system, {})
    found = []
    for name, path in candidates.items():
        exists = shutil.which(path) if system == "Linux" else os.path.exists(path)
        if exists:
            found.append(name)
    return found

def open_specific_browser(name, url):
    system = platform.system()
    path = BROWSER_PATHS.get(system, {}).get(name)
    if not path:
        webbrowser.open(url)  # unknown choice — fall back rather than fail silently
        return
    try:
        if system == "Darwin":
            # macOS apps expect to be launched via `open -a`, not by running
            # their binary directly with a URL argument — Chrome happens to
            # tolerate that, Safari does not (this was the cause of Safari
            # opening and then closing the whole thing).
            subprocess.Popen(["open", "-a", name, url])
        else:
            subprocess.Popen([path, url])
    except Exception:
        webbrowser.open(url)


def _open_file_cross_platform(path):
    """Opens a file with the OS's default application for it — the same
    technique the old terminal tool used for gif/mp3 files, reused here
    for plain files (e.g. hub_settings.json, misc/ items) that aren't
    meant to be rendered inside a hub window."""
    try:
        system = platform.system()
        if system == "Darwin":
            subprocess.Popen(["open", path])
        elif system == "Windows":
            os.startfile(path)  # Windows-only API, only reached on Windows
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"  (couldn't open {path}: {e})")
        return False


def ensure_ngrok():
    """Checks whether ngrok is already reachable; if not, downloads the
    right build for this OS/chip straight from ngrok's own official
    distribution URLs into a local bin/ folder inside this project —
    no admin/sudo, nothing touches system-wide install locations. Returns
    True if ngrok is available (already installed or freshly downloaded)."""
    if shutil.which("ngrok"):
        return True

    bin_dir = os.path.join(ROOT, "bin")
    exe_name = "ngrok.exe" if platform.system() == "Windows" else "ngrok"
    local_ngrok = os.path.join(bin_dir, exe_name)
    if os.path.isfile(local_ngrok):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        return True

    system = platform.system()
    machine = platform.machine().lower()
    if system == "Darwin":
        platform_key = "darwin-arm64" if machine in ("arm64", "aarch64") else "darwin-amd64"
    elif system == "Windows":
        platform_key = "windows-amd64"
    elif system == "Linux":
        platform_key = "linux-arm64" if machine in ("arm64", "aarch64") else "linux-amd64"
    else:
        print(f"  (ngrok: unrecognized OS '{system}' — install it manually from ngrok.com)")
        return False

    url = f"https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-{platform_key}.zip"
    try:
        print(f"  Downloading ngrok for {platform_key}...")
        os.makedirs(bin_dir, exist_ok=True)
        zip_path = os.path.join(bin_dir, "ngrok.zip")
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(bin_dir)
        os.remove(zip_path)
        if platform.system() != "Windows":
            os.chmod(local_ngrok, 0o755)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        print("  ngrok installed.")
        return True
    except Exception as e:
        print(f"  (ngrok download failed: {e} — install it manually from ngrok.com)")
        return False


# ── Window registry: spawn-or-focus, one entry per named app ─────────────
class HubAPI:
    def __init__(self):
        self.windows = {}       # app_name -> webview.Window, for taskbar entries
        self._child_count = 0   # for anonymous windows (e.g. symbol viewers)
        self._territories_ngrok_started = False

    def spawn_or_focus(self, app_name, relative_path):
        """Called by the taskbar. Opens a tracked app window, or brings it
        forward if it's already open, instead of creating a duplicate."""
        win = self.windows.get(app_name)
        if win is not None:
            try:
                win.show()
                return "focused"
            except Exception:
                pass  # window was closed elsewhere; fall through and recreate

        url = relative_path if relative_path.startswith("http") else url_for(relative_path)

        if app_name == "territories" and not self._territories_ngrok_started:
            # launcher.html expects ngrok to already be running by the time
            # someone clicks Launch — start it now, in the background, the
            # first time Territories is opened, rather than blocking here.
            self._territories_ngrok_started = True
            threading.Thread(
                target=lambda: ensure_ngrok() and _territories_module and _territories_module.start_ngrok(TERRITORIES_PORT),
                daemon=True
            ).start()

        library_mode = load_settings().get("library_mode", "webview")
        if app_name == "library" and library_mode != "webview":
            # Library needs a real browser for wallet extensions (MetaMask etc.)
            # to work at all — no webview has an extension system.
            if library_mode == "system_default":
                webbrowser.open(url)
            else:
                open_specific_browser(library_mode, url)
            return "opened-in-browser"

        w, h, x, y = geometry_for_url(url)
        new_win = webview.create_window(
            app_name, url,
            width=w, height=h, x=x, y=y,
            js_api=self,
            resizable=True, min_size=(400, 300)
        )
        _bind_resize_reflow(new_win)
        new_win.events.closed += lambda: self.windows.pop(app_name, None)
        self.windows[app_name] = new_win
        return "opened"

    def open_window(self, relative_or_absolute_url, width=620, height=760, x=None, y=None):
        """Called from inside an app (e.g. the library's symbol viewer /
        chain card, or the mint page's pack-reveal popups) to open an
        untracked child window at a FIXED size — not scaled to the screen.
        Defaults match the library's actual viewer/chain card size (620x760).
        Pass explicit x/y (e.g. from a reveal-pattern layout) to position the
        window exactly rather than centering it — used by the mint page's
        scattered pack reveal, where each popup needs its own computed spot."""
        self._child_count += 1
        url = relative_or_absolute_url
        if not url.startswith("http"):
            url = url_for(url)
        if x is None or y is None:
            w, h, x, y = fixed_geometry(width, height)
        else:
            w, h = width, height
        win = webview.create_window(f"viewer-{self._child_count}", url, width=w, height=h, x=int(x), y=int(y), js_api=self)
        try:
            win.show()  # explicit show, in case a same-size/fullscreen window underneath is stealing focus
        except Exception:
            pass

    def open_or_navigate(self, name, relative_or_absolute_url, width=360, height=540):
        """Like spawn_or_focus, but for a single reusable NAMED window that
        navigates to a new URL each time instead of staying put — e.g. the
        manifest panel, which shows a different symbol's info in the same
        window rather than stacking up a new popup per click."""
        url = relative_or_absolute_url if relative_or_absolute_url.startswith("http") else url_for(relative_or_absolute_url)
        win = self.windows.get(name)
        if win is not None:
            try:
                win.load_url(url)
                win.show()
                return "navigated"
            except Exception:
                pass  # window was closed elsewhere; fall through and recreate
        w, h, x, y = fixed_geometry(width, height)
        new_win = webview.create_window(name, url, width=w, height=h, x=x, y=y, js_api=self)
        new_win.events.closed += lambda: self.windows.pop(name, None)
        self.windows[name] = new_win
        return "opened"

    def open_window_full(self, relative_or_absolute_url):
        """Opens a window at full screen size — used for the mint page,
        which is deliberately full-screen unlike every other fixed-size
        window."""
        self._child_count += 1
        url = relative_or_absolute_url
        if not url.startswith("http"):
            url = url_for(url)
        try:
            screen = webview.screens[0]
            sw, sh = screen.width, screen.height
        except Exception:
            sw, sh = 1440, 900
        win = webview.create_window("Simulated Mint", url, width=sw, height=sh, x=0, y=0, js_api=self)
        try:
            win.show()  # explicit show — a same-size/fullscreen window (the
            # library window this is opened from) underneath will otherwise
            # steal focus and the new window never surfaces, silently.
        except Exception as e:
            print(f"  (couldn't show mint window: {e})")

    def get_library_mode(self):
        """Read by the Settings panel to show the current choice when it opens."""
        return load_settings().get("library_mode", "webview")

    def set_library_mode(self, mode):
        """mode is 'webview' (built-in), 'system_default', or a specific
        browser name from list_available_browsers(). Only affects the NEXT
        time Library is opened, not an already-open one."""
        settings = load_settings()
        settings["library_mode"] = mode
        save_settings(settings)
        return mode

    def get_wallet_address(self):
        return load_settings().get("wallet_address", "")

    def set_wallet_address(self, address):
        settings = load_settings()
        settings["wallet_address"] = address
        save_settings(settings)
        return address

    def get_explorer_name(self):
        return load_settings().get("explorer_name", "")

    def set_explorer_name(self, name):
        settings = load_settings()
        settings["explorer_name"] = name
        save_settings(settings)
        return name

    def get_avatar(self):
        """Returns the saved avatar as a data: URL (already resized/encoded
        client-side before it ever reaches here — see the avatarFile
        handler in hub-shell.html), or '' if none is saved."""
        return load_settings().get("avatar_data_url", "")

    def set_avatar(self, data_url):
        settings = load_settings()
        settings["avatar_data_url"] = data_url
        save_settings(settings)
        return True

    def list_available_browsers(self):
        return list_available_browsers()

    def list_map_files(self):
        """Scans maps/maps/ for any .html file — each one is a self-contained
        map (e.g. arg-map-v4.html). No registration needed; a new map just
        needs to be dropped in the folder."""
        maps_dir = os.path.join(ROOT, "maps", "maps")
        found = []
        if os.path.isdir(maps_dir):
            for name in sorted(os.listdir(maps_dir)):
                if name.lower().endswith(".html") and name.lower() != "picker.html":
                    display_name = os.path.splitext(name)[0].replace("-", " ").replace("_", " ").title()
                    found.append({"filename": name, "name": display_name, "path": f"maps/maps/{name}"})
        return found

    # ── Terminal direct-access commands ───────────────────────────────
    # Called by the command parser in hub-shell.html. Ported from the old
    # standalone terminal tool's open_symbol/view_symbol/unfold_symbol,
    # adapted to open real hub windows instead of shelling out to the OS's
    # default app. All three reuse _find_symbol_folder's lookup rule and
    # open_window's existing window-creation logic — no new machinery.

    def list_symbols(self):
        """Terminal 'list'. Scans symbols/ the same way maps are scanned
        by list_map_files — each folder is named '<id> - <name>' (e.g.
        '0001 - inni'), split on the first '-' like the old terminal tool
        did."""
        found = []
        if os.path.isdir(SYMBOLS_DIR):
            for folder_name in sorted(os.listdir(SYMBOLS_DIR)):
                if not os.path.isdir(os.path.join(SYMBOLS_DIR, folder_name)):
                    continue
                parts = folder_name.split("-", 1)
                if len(parts) != 2:
                    continue
                found.append({
                    "id": parts[0].strip(),
                    "name": parts[1].strip(),
                    "folder": folder_name,
                })
        return found

    def get_symbol_manifest(self, symbol_id):
        """Terminal 'read <id>' (renamed from the old tool's 'view <id>')
        — reads manifest.json straight from the symbol's folder and hands
        it back for the terminal to print inline, instead of opening a
        window for it."""
        folder_name = _find_symbol_folder(symbol_id)
        if not folder_name:
            return {"error": f"No symbol folder matching '{symbol_id}'."}
        manifest_path = os.path.join(SYMBOLS_DIR, folder_name, "manifest.json")
        if not os.path.isfile(manifest_path):
            return {"error": f"'{folder_name}' has no manifest.json."}
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["_folder"] = folder_name
            return data
        except Exception as e:
            return {"error": f"Couldn't read manifest for '{folder_name}': {e}"}

    def open_symbol_viewer(self, symbol_id):
        """Terminal 'open <id>'. Prefers viewer.html; if the symbol
        doesn't have one, falls back to its raw media (gif, then mp3) —
        some symbols are just a media file with no separate viewer page.
        Reuses open_window exactly like the library's own viewer/chain-card
        popups (untracked, fixed at the 620x760 default)."""
        folder_name = _find_symbol_folder(symbol_id)
        if not folder_name:
            return {"error": f"No symbol folder matching '{symbol_id}'."}
        viewer_path = Path(SYMBOLS_DIR) / folder_name / "viewer.html"
        target = viewer_path if viewer_path.is_file() else _first_file_match(folder_name, ["*.gif", "*.mp3"])
        if not target:
            return {"error": f"'{folder_name}' has no viewer.html, .gif, or .mp3."}
        self.open_window(_url_path_for_symbol_file(target))
        return {"opened": folder_name}

    def unfold_symbol(self, symbol_id):
        """Terminal 'unfold <id>' — like the old terminal tool's unfold,
        opens the symbol's raw media file (gif, then mp3) directly, even
        if it also has a viewer.html."""
        folder_name = _find_symbol_folder(symbol_id)
        if not folder_name:
            return {"error": f"No symbol folder matching '{symbol_id}'."}
        target = _first_file_match(folder_name, ["*.gif", "*.mp3"])
        if not target:
            return {"error": f"'{folder_name}' has no .gif or .mp3 to unfold."}
        self.open_window(_url_path_for_symbol_file(target))
        return {"opened": folder_name}

    # ── Settings panel: Data & sync / Network rows ────────────────────

    def open_settings_file(self):
        """Settings 'Data & sync' — opens hub_settings.json directly in
        whatever app the OS has associated with .json files, instead of
        building a JSON editor into the hub."""
        if not os.path.isfile(SETTINGS_PATH):
            save_settings({})  # create it so there's something to open
        return {"opened": _open_file_cross_platform(SETTINGS_PATH)}

    def is_ngrok_running(self):
        """Settings 'Network' row — a single quick check, not the retry
        loop get_local_ngrok_url uses while WAITING for ngrok to start."""
        return get_local_ngrok_url(retries=1, delay=0) is not None

    def quit_app(self):
        """Wired to the dot in the terminal's title bar — closes every open
        window (the hub itself, library, territories, viewers, mint, all of
        it) and ends the whole running program, not just whatever window
        the click happened to originate in.

        Destroying windows synchronously, from inside this very call (which
        one of those windows' own JS just triggered over the bridge), tore
        things down before the call could finish returning — that's what
        crashed it originally. Deferring the actual destroying by a moment
        fixed the crash, but relying on webview.start() to return on its
        own once every window is destroyed turned out to only reliably
        close the one window the call came from, leaving the process (and
        any other still-open windows) running. os._exit() is the blunt but
        certain fix: it ends the process outright, regardless of any
        window/thread/event-loop state — nothing is left running."""
        def _destroy_all():
            for win in list(webview.windows):
                try:
                    win.destroy()
                except Exception:
                    pass
            os._exit(0)
        threading.Timer(0.15, _destroy_all).start()

    # ── Start menu: Misc panel ─────────────────────────────────────────

    def list_misc_files(self):
        """Lists whatever's dropped in misc/ — same no-registration-needed
        pattern as list_map_files. Top-level files of any kind are listed
        as-is; anything nested inside a subfolder (a program kept alongside
        the assets it needs) only surfaces if it's a .py file, so the list
        doesn't get cluttered with everything else sitting next to it."""
        found = []
        if not os.path.isdir(MISC_DIR):
            return found
        for name in sorted(os.listdir(MISC_DIR)):
            full = os.path.join(MISC_DIR, name)
            if os.path.isfile(full):
                found.append({"filename": name, "ext": os.path.splitext(name)[1].lower()})
        for dirpath, dirnames, filenames in os.walk(MISC_DIR):
            dirnames.sort()
            if os.path.abspath(dirpath) == os.path.abspath(MISC_DIR):
                continue  # top level already handled above
            for name in sorted(filenames):
                if name.lower().endswith(".py"):
                    rel = os.path.relpath(os.path.join(dirpath, name), MISC_DIR).replace(os.sep, "/")
                    found.append({"filename": rel, "ext": ".py"})
        return found

    def open_misc_item(self, filename):
        """Runs .py files in place (fire-and-forget subprocess — no output
        streaming back into the terminal yet, that's a bigger feature),
        opens .html files in a hub window, and falls back to the OS's
        default app for anything else. filename may be a nested relative
        path (e.g. "toolname/main.py") — runs with its own folder as the
        working directory so it can still find whatever sits alongside it."""
        full = os.path.normpath(os.path.join(MISC_DIR, *filename.split("/")))
        misc_abs = os.path.abspath(MISC_DIR)
        if not os.path.isfile(full) or os.path.commonpath([os.path.abspath(full), misc_abs]) != misc_abs:
            return {"error": f"'{filename}' not found in misc/."}
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".py":
            try:
                subprocess.Popen([sys.executable, full], cwd=os.path.dirname(full))
                return {"ran": filename}
            except Exception as e:
                return {"error": f"Couldn't run '{filename}': {e}"}
        if ext == ".html":
            self.open_window(f"misc/{filename}")
            return {"opened": filename}
        return {"opened": filename} if _open_file_cross_platform(full) else {"error": f"Couldn't open '{filename}'."}

    # ── Profile panel: Favourites ───────────────────────────────────────
    # Added via the terminal's 'fav'/'favourites' command, not from the UI
    # directly — the Profile panel only displays and removes them.

    def get_favourites(self):
        return load_settings().get("favourites", [])

    def add_favourite(self, symbol_id):
        folder_name = _find_symbol_folder(symbol_id)
        if not folder_name:
            return {"error": f"No symbol folder matching '{symbol_id}'."}
        parts = folder_name.split("-", 1)
        canonical_id = parts[0].strip() if len(parts) == 2 else symbol_id
        name = parts[1].strip() if len(parts) == 2 else folder_name
        settings = load_settings()
        favs = settings.get("favourites", [])
        if not any(f["id"] == canonical_id for f in favs):
            favs.append({"id": canonical_id, "name": name})
            settings["favourites"] = favs
            save_settings(settings)
        return favs

    def remove_favourite(self, symbol_id):
        settings = load_settings()
        favs = [f for f in settings.get("favourites", []) if f["id"] != symbol_id]
        settings["favourites"] = favs
        save_settings(settings)
        return favs

    # ── Profile panel: Terminal themes (renamed from "Saved themes") ───
    # Was previously a purely decorative mock (no real values persisted).
    # Now actually captures/replays the CSS custom properties Customize
    # sets, stored in hub_settings.json like everything else here.

    def get_theme_presets(self):
        return load_settings().get("theme_presets", [])

    def save_theme_preset(self, name, values):
        settings = load_settings()
        presets = [p for p in settings.get("theme_presets", []) if p.get("name") != name]
        presets.append({"name": name, "values": values})
        settings["theme_presets"] = presets
        save_settings(settings)
        return presets

    def delete_theme_preset(self, name):
        settings = load_settings()
        presets = [p for p in settings.get("theme_presets", []) if p.get("name") != name]
        settings["theme_presets"] = presets
        save_settings(settings)
        return presets

    # ── Customize panel: currently-active theme ─────────────────────────
    # Distinct from theme_presets above (named, explicitly-saved snapshots)
    # — this is just "whatever the live Customize values were last set to",
    # persisted so the hub reopens looking the way it was left instead of
    # always booting back into the hardcoded default.

    def get_current_theme(self):
        return load_settings().get("current_theme")

    def set_current_theme(self, values):
        settings = load_settings()
        settings["current_theme"] = values
        save_settings(settings)
        return values


def main():
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    library_thread = threading.Thread(target=start_library_server, daemon=True)
    library_thread.start()

    territories_thread = threading.Thread(target=start_territories_server, daemon=True)
    territories_thread.start()

    api = HubAPI()
    # The hub shell (terminal + taskbar) is small by design — roughly 520px
    # wide plus the taskbar strip. Sizing the window to 85% of the screen
    # (like the big app windows get) left it floating in a mostly-empty
    # window. This is its own fixed, small size instead.
    w, h, x, y = fixed_geometry(640, 480)
    main_win = webview.create_window(
        "Symbol by Flōyél", url_for(SHELL_PATH),
        width=w, height=h, x=x, y=y,
        js_api=api,
        frameless=True, easy_drag=False, resizable=True,
        text_select=True
        # frameless + easy_drag=False: no native title bar, and dragging only
        # works from elements marked class="pywebview-drag-region" in the
        # HTML (the shell's own title bar) — not the whole window surface,
        # so clicking the terminal input or taskbar doesn't drag it around.
        # text_select=True: pywebview disables text selection by default —
        # without this, scrollback text in the terminal can't be
        # highlighted/copied at all.
    )
    api.windows["hub"] = main_win  # the shell itself counts as a taskbar-trackable window

    # private_mode=False + a real storage_path: without this, every window
    # runs in a throwaway incognito-style profile — localStorage, "don't show
    # this again" checkboxes, etc. never survive a restart. This gives the
    # webview engine a real, persistent data folder inside this project.
    storage_path = os.path.join(ROOT, ".webview_data")
    webview.start(private_mode=False, storage_path=storage_path)


if __name__ == "__main__":
    main()
