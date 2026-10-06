"""
build_symbols_json.py
─────────────────────
Generates symbols.json for the static/GitHub Pages version of the library.
Run from the same folder as server.py:
    python build_symbols_json.py

Output: symbols.json (commit this to your GitHub repo alongside library.html)
Regenerate whenever manifests change.
"""

import os
import json

SYMBOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "symbols")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "symbols.json")


def get_symbols():
    symbols = []
    if not os.path.isdir(SYMBOLS_DIR):
        print(f"ERROR: symbols/ not found at {SYMBOLS_DIR}")
        return symbols

    for folder_name in sorted(os.listdir(SYMBOLS_DIR)):
        folder_path = os.path.join(SYMBOLS_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue

        manifest_path = os.path.join(folder_path, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"  SKIP  {folder_name}  (manifest error: {e})")
            continue

        gif_file = next((
            f for f in sorted(os.listdir(folder_path))
            if f.lower().endswith(".gif") and not f.startswith("._")
        ), None)

        has_audio  = any(f.lower().endswith(".mp3") for f in os.listdir(folder_path))
        has_viewer = os.path.isfile(os.path.join(folder_path, "viewer.html"))

        symbols.append({
            "folder":     folder_name,
            "manifest":   manifest,
            "gif":        gif_file,
            "has_audio":  has_audio,
            "has_viewer": has_viewer,
        })

    return symbols


def main():
    print(f"\n  build_symbols_json.py")
    print(f"  Symbols dir : {SYMBOLS_DIR}")
    print(f"  Output      : {OUTPUT_FILE}\n")

    symbols = get_symbols()
    if not symbols:
        print("No symbols found.")
        return

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(symbols, f, ensure_ascii=False, indent=2)

    print(f"  Written {len(symbols)} symbols to symbols.json")
    print(f"  Commit this file to your GitHub repo.\n")


if __name__ == "__main__":
    main()
