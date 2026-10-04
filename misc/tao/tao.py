#!/usr/bin/env python3
"""
tao.py — Terminal reader for the Tao Te Ching with multiple translations.

Folder layout (keep everything in the same directory as tao.py):

    tao.py
    translations/
        01_legge.txt
        02_feng_english.txt
        03_le_guin.txt
        ...

Each .txt file is just the raw translation text — paste it in as-is.
The first lines of each file can optionally be:
    Name: James Legge
    Year: 1891

Then the rest is the translation.  Verses are detected automatically
from numbered headings in any of these formats:
    1.   1)   1:   [1]   Chapter 1   Verse 1   (or Roman numerals)

Usage:
    python tao.py             — random verse
    python tao.py 42          — open at verse 42
    python tao.py --list      — list loaded translations

Commands while reading:
    n / Enter   next translation
    p           previous translation
    r           random new verse
    1-81        jump to that verse
    q           quit
"""

import os
import random
import re
import sys

# ── Config ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TRANS_DIR  = os.path.join(SCRIPT_DIR, "translations")

# ── ANSI colours ──────────────────────────────────────────────────────────────
C      = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
RESET  = "\033[0m"  if C else ""
BOLD   = "\033[1m"  if C else ""
DIM    = "\033[2m"  if C else ""
CYAN   = "\033[96m" if C else ""
YELLOW = "\033[93m" if C else ""
GREY   = "\033[90m" if C else ""

try:
    TERM_WIDTH = min(os.get_terminal_size().columns, 82)
except OSError:
    TERM_WIDTH = 72

# ── Verse parsing ─────────────────────────────────────────────────────────────
VERSE_HEADER = re.compile(
    r"^\s*(?:"
    r"(?:chapter|verse|tao)\s+(\d+)"                           # Chapter 42
    r"|(\d+)\s*[.):\-]"                                        # 42. 42) 42: 42-
    r"|(\d+)\s*$"                                              # 42  (bare number alone on line)
    r"|\[(\d+)\]"                                              # [42]
    r"|(M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3}))[.)]"  # Roman
    r")",
    re.IGNORECASE,
)

def _roman_to_int(s: str) -> int | None:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    s = s.upper()
    total, prev = 0, 0
    for ch in reversed(s):
        v = vals.get(ch, 0)
        if v == 0:
            return None
        total += v if v >= prev else -v
        prev = v
    return total if total > 0 else None

def parse_translation(raw: str) -> dict:
    verses: dict = {}
    current = None

    for line in raw.splitlines():
        m = VERSE_HEADER.match(line)
        if m:
            num_str = m.group(1) or m.group(2) or m.group(3) or m.group(4)
            if num_str:
                current = int(num_str)
            else:
                roman = m.group(5) or ""
                current = _roman_to_int(roman)

            if current is not None:
                rest = line[m.end():].strip()
                verses.setdefault(current, [])
                if rest:
                    verses[current].append(rest)
        elif current is not None:
            verses[current].append(line)

    result = {}
    for num, lines in verses.items():
        text = "\n".join(lines).strip()
        if text:
            result[num] = text
    return result

# ── File loading ──────────────────────────────────────────────────────────────
def read_header(lines: list) -> tuple:
    """
    Read optional Name:/Year: metadata from the top of a file.
    Returns (name, year, body_start_line_index).
    """
    name, year = "", ""
    i = 0
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r"(?i)^name\s*:", s):
            name = re.sub(r"(?i)^name\s*:\s*", "", s).strip()
        elif re.match(r"(?i)^year\s*:", s):
            year = re.sub(r"(?i)^year\s*:\s*", "", s).strip()
        elif s == "" and i < 5:
            continue  # allow blank lines in header area
        else:
            break
    return name, year, i

def load_translations() -> list:
    if not os.path.isdir(TRANS_DIR):
        os.makedirs(TRANS_DIR)
        _write_samples()
        print(f"{YELLOW}Created translations/ folder with two sample files.{RESET}")
        print(f"Add your own .txt files to:  {TRANS_DIR}/")
        print("Then run tao.py again.\n")
        sys.exit(0)

    txt_files = sorted(f for f in os.listdir(TRANS_DIR) if f.endswith(".txt"))
    if not txt_files:
        print(f"{YELLOW}No .txt files found in translations/{RESET}")
        print(f"Add files like  01_legge.txt  to:  {TRANS_DIR}/")
        sys.exit(1)

    translations = []
    for fname in txt_files:
        path = os.path.join(TRANS_DIR, fname)
        lines = None
        for enc in ("utf-8", "mac_roman", "latin-1", "cp1252"):
            try:
                with open(path, encoding=enc) as f:
                    lines = f.readlines()
                break
            except UnicodeDecodeError:
                continue
        if lines is None:
            print(f"{YELLOW}Warning: could not decode {fname}, skipping.{RESET}")
            continue

        name, year, body_start = read_header(lines)
        body = "".join(lines[body_start:])

        if not name:
            base = os.path.splitext(fname)[0]
            base = re.sub(r"^\.+", "", base)          # strip leading dots
            base = re.sub(r"^\d+[_\-\s\.]*", "", base)  # strip leading numbers
            name = base.replace("_", " ").replace("-", " ").title() or fname

        verses = parse_translation(body)
        if not verses:
            print(f"{YELLOW}Warning: no verses parsed in {fname}{RESET}")

        translations.append({"name": name, "year": year, "verses": verses, "file": fname})

    return translations

# ── Display ───────────────────────────────────────────────────────────────────
def hr(char="─"):
    print(GREY + char * TERM_WIDTH + RESET)

def wrap(text: str) -> str:
    width = TERM_WIDTH - 4
    result = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            result.append("")
            continue
        words = paragraph.split()
        line, length = [], 0
        for w in words:
            if length + len(w) + bool(line) > width:
                result.append("  " + " ".join(line))
                line, length = [w], len(w)
            else:
                line.append(w)
                length += len(w) + bool(line)
        if line:
            result.append("  " + " ".join(line))
    return "\n".join(result)

def display_verse(translations: list, verse_num: int, trans_idx: int, clear: bool):
    """Print one translation block. Only clears screen on a new verse."""
    if clear:
        os.system("clear" if os.name != "nt" else "cls")
        hr("═")
        print(f"  {BOLD}{CYAN}TAO TE CHING  ·  Verse {verse_num}{RESET}")
        hr("═")
        print()

    t = translations[trans_idx]
    verse_text = t["verses"].get(
        verse_num,
        "(this translation does not include verse %d)" % verse_num
    )
    year = f"  {GREY}({t['year']}){RESET}" if t["year"] else ""
    print(f"  {BOLD}{t['name']}{RESET}{year}  "
          f"{DIM}[{trans_idx + 1} of {len(translations)}]{RESET}")
    hr()
    print()
    print(wrap(verse_text))
    print()

def print_prompt():
    hr("─")
    print(f"  {GREY}n/Enter  next · p  prev · r  random · [number]  jump · q  quit{RESET}")
    hr("═")

# ── Main loop ─────────────────────────────────────────────────────────────────
def run(translations: list, start_verse):
    all_verses = sorted(set(v for t in translations for v in t["verses"]))
    if not all_verses:
        sys.exit("No verses found across any translation file.")

    verse_num = start_verse if (start_verse and start_verse in all_verses) else random.choice(all_verses)
    trans_idx = next((i for i, t in enumerate(translations) if verse_num in t["verses"]), 0)
    new_verse = True  # first display always clears

    while True:
        display_verse(translations, verse_num, trans_idx, clear=new_verse)
        print_prompt()
        new_verse = False
        try:
            cmd = input("\n  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nFarewell.")
            break

        if cmd in ("q", "quit", "exit"):
            print("Farewell.")
            break
        elif cmd in ("n", "", "next"):
            trans_idx = (trans_idx + 1) % len(translations)
            # new_verse stays False — just append below
        elif cmd in ("p", "prev", "previous", "back"):
            trans_idx = (trans_idx - 1) % len(translations)
        elif cmd in ("r", "random"):
            verse_num = random.choice(all_verses)
            trans_idx = next((i for i, t in enumerate(translations) if verse_num in t["verses"]), 0)
            new_verse = True
        elif cmd.isdigit():
            n = int(cmd)
            if n in all_verses:
                verse_num = n
                trans_idx = next((i for i, t in enumerate(translations) if verse_num in t["verses"]), 0)
                new_verse = True
            else:
                print(f"  {YELLOW}Verse {n} not found.  "
                      f"Available: {all_verses[0]}–{all_verses[-1]}{RESET}")

# ── Sample files ──────────────────────────────────────────────────────────────
SAMPLE_1 = """\
Name: James Legge
Year: 1891

1.
The Tao that can be trodden is not the enduring and unchanging Tao.
The name that can be named is not the enduring and unchanging name.

Conceiving of the nameless: the beginning of heaven and earth.
Conceiving of the named: the mother of all things.

2.
When the people of the earth all know beauty as beauty,
there arises the recognition of ugliness.
When they all know the good as good,
there arises the recognition of evil.

Being and non-being inter-produce each other.
Difficulty and ease complete each other.
"""

SAMPLE_2 = """\
Name: Gia-Fu Feng & Jane English
Year: 1972

1.
The Tao that can be told is not the eternal Tao.
The name that can be named is not the eternal name.
The nameless is the beginning of heaven and earth.
The named is the mother of the ten thousand things.

2.
Under heaven all can see beauty as beauty
only because there is ugliness.
All can know good as good
only because there is evil.

Therefore having and not having arise together.
"""

def _write_samples():
    with open(os.path.join(TRANS_DIR, "01_legge.txt"), "w", encoding="utf-8") as f:
        f.write(SAMPLE_1)
    with open(os.path.join(TRANS_DIR, "02_feng_english.txt"), "w", encoding="utf-8") as f:
        f.write(SAMPLE_2)

# ── Entry ─────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]

    if "--list" in args:
        ts = load_translations()
        print(f"\n{BOLD}Loaded translations:{RESET}")
        for i, t in enumerate(ts, 1):
            yr = f"({t['year']}) " if t["year"] else ""
            print(f"  {i:2}. {t['name']} {GREY}{yr}— {len(t['verses'])} verses  [{t['file']}]{RESET}")
        print()
        return

    start = None
    for a in args:
        if a.isdigit():
            start = int(a)

    translations = load_translations()
    run(translations, start)

if __name__ == "__main__":
    main()
