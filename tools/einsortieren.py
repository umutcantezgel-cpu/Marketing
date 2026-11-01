#!/usr/bin/env python3
"""Sortiert heruntergeladene Bilder (Arena, ChatGPT ...) automatisch ins Repo ein.

Liest den Text im Bild per macOS-Texterkennung, sucht den passenden Prompt in
Coday/, Bad-und-Energie/ und Tezgel/ (prompts.json) und speichert das Bild als
<ID>.jpg nach <Firma>/bilder/original/. Danach entstehen die Posting-Formate
(Instagram 3:4, Facebook/LinkedIn 4:5, Story 9:16) und prompts.md zeigt die Bilder.

Die Downloads bleiben unverändert liegen (es wird kopiert, nicht verschoben).
Bilder ohne erkennbaren Text oder mit unsicherer Zuordnung landen in unsortiert/.

Aufruf (im Repo-Ordner):
  python3 tools/einsortieren.py                 ~/Downloads, Bilder ab 29.10.2026
  python3 tools/einsortieren.py --push          zusätzlich commit + push zu GitHub
  python3 tools/einsortieren.py --quelle ~/Desktop/arena --seit 2026-11-01
  python3 tools/einsortieren.py --probelauf     nur anzeigen, nichts kopieren
"""

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bibliothek as bib  # noqa: E402

ROOT = bib.ROOT
TOOLS = Path(__file__).resolve().parent
STATE = TOOLS / ".einsortiert.json"
UNSORTED = ROOT / "unsortiert"
EXTS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_SCORE = 0.6
MIN_MARGIN = 0.12


def norm(text):
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("ß", "ss")
    return re.sub(r"[^0-9a-zäöü]+", " ", text).split()


def score(expected, ocr_words):
    """Anteil der erwarteten Wörter, die (unscharf) im erkannten Text vorkommen."""
    words = norm(expected)
    if not words or not ocr_words:
        return 0.0
    hits = 0
    for w in words:
        if w in ocr_words or difflib.get_close_matches(w, ocr_words, n=1, cutoff=0.8):
            hits += 1
    return hits / len(words)


def ocr(paths):
    binary = TOOLS / ".bin" / "ocr"
    source = TOOLS / "ocr.swift"
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        binary.parent.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(source), "-o", str(binary)], check=True)
    out = subprocess.run([str(binary), *map(str, paths)], check=True, capture_output=True, text=True).stdout
    return {Path(o["path"]): o["text"] for o in map(json.loads, out.splitlines())}


def candidates():
    for key in bib.COMPANIES:
        if not (bib.company_dir(key) / "prompts.json").exists():
            continue
        for e in bib.load(key):
            text = " ".join([e.get("headline") or "", *[s["text"] for s in e.get("small_text") or []]])
            if text.strip():
                yield key, e, text


def sha1(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quelle", default=str(Path.home() / "Downloads"))
    ap.add_argument("--seit", default="2026-10-29", help="nur Bilder ab diesem Datum (JJJJ-MM-TT)")
    ap.add_argument("--push", action="store_true", help="danach git commit + push")
    ap.add_argument("--probelauf", action="store_true", help="nichts kopieren, nur anzeigen")
    args = ap.parse_args()

    since = dt.datetime.fromisoformat(args.seit).timestamp()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    files = [p for p in sorted(Path(args.quelle).expanduser().iterdir())
             if p.suffix.lower() in EXTS and p.stat().st_mtime >= since]
    files = [p for p in files if sha1(p) not in state]
    if not files:
        print("Keine neuen Bilder gefunden.")
        return
    print(f"{len(files)} neue Bilder, lese Text ...")
    texts = ocr(files)
    cands = list(candidates())
    touched, report = set(), []

    for path in files:
        words = norm(texts.get(path, ""))
        ranked = sorted(((score(t, words), k, e) for k, e, t in cands), key=lambda x: x[0], reverse=True)
        best = ranked[0] if ranked else (0, None, None)
        second = ranked[1][0] if len(ranked) > 1 else 0
        if best[0] >= MIN_SCORE and best[0] - second >= MIN_MARGIN:
            key, entry = best[1], best[2]
            target_dir = bib.company_dir(key) / "bilder" / "original"
            name = entry["id"]
            n = 1
            while list(target_dir.glob(f"{name}.*")):
                n += 1
                name = f"{entry['id']}_v{n}"
            target = target_dir / f"{name}.jpg"
            report.append(f"{path.name} -> {target.relative_to(ROOT)} ({best[0]:.0%})")
            if not args.probelauf:
                target_dir.mkdir(parents=True, exist_ok=True)
                # Originale als JPEG (Qualität 92): gleiche Auflösung, ein Bruchteil der PNG-Größe
                bib.sips("-s", "format", "jpeg", "-s", "formatOptions", "92", str(path), "--out", str(target))
                bib.export_image(key, target, entry["format"])
                touched.add(key)
        else:
            report.append(f"{path.name} -> unsortiert/ (Text: {' '.join(words)[:60]!r})")
            if not args.probelauf:
                UNSORTED.mkdir(exist_ok=True)
                shutil.copy2(path, UNSORTED / path.name)
        if not args.probelauf:
            state[sha1(path)] = path.name

    print("\n".join(report))
    if args.probelauf:
        return
    STATE.write_text(json.dumps(state, indent=1))
    for key in touched:
        bib.build(key)
    if args.push and touched:
        subprocess.run(["git", "-C", str(ROOT), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "commit", "-m", f"Bilder einsortiert ({len(files)} neu)"], check=True)
        subprocess.run(["git", "-C", str(ROOT), "push"], check=True)


if __name__ == "__main__":
    main()
