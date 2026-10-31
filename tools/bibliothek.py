#!/usr/bin/env python3
"""Prompt-Bibliothek fuer Coday, Bad & Energie und Tezgel.

Setzt aus prompts.json (Szene, Headline, Labels) die fertigen Bildprompts zusammen
(Brand-Block + Szene + Text) und erzeugt daraus pro Firma:
  prompts.md    Copy-Paste-Liste mit Caption, Hashtags und Hinweisen
  captions.csv  Tabelle fuer Planungstools (Metricool, Later, Excel ...)

Ausserdem bringt `export` fertige Bilder in die Posting-Formate (nur macOS, nutzt sips):
  instagram-3x4/             1080 x 1440  Instagram-Feed
  facebook-linkedin-4x5/     1080 x 1350  Facebook- und LinkedIn-Feed (Mitte des 3:4-Bildes)
  story-9x16/                1080 x 1920  Instagram- und Facebook-Story

Aufruf:
  python3 tools/bibliothek.py build              alle drei Firmen
  python3 tools/bibliothek.py build coday
  python3 tools/bibliothek.py export coday       Formate aus bilder/original neu erzeugen
  python3 tools/bibliothek.py prompt CD-001      einen fertigen Prompt anzeigen
"""

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FEED = "vertical 3:4 portrait format (1080x1440 proportions)"
STORY = "vertical 9:16 format (1080x1920 proportions); keep the top 14% and bottom 20% free of text"
STYLE_REF = ("Use the uploaded image as the exact style reference: same background, colours, "
             "typography and layout. Create the next slide of this carousel.")

COMPANIES = {
    "coday": {
        "folder": "Coday",
        "prefix": "CD",
        "name": "Coday",
        # Firmenname bewusst nicht im Block, damit das Modell keinen falschen Schriftzug malt.
        "brand": (
            "Brand style for a one-person web agency in Wetzlar, Germany. Premium, calm, technical-editorial look. "
            "Palette: deep near-black navy background (#0B1220), off-white (#F5F5F2), single accent colour teal (#14B8A6), "
            "thin grey hairlines. Typography: bold modern geometric sans-serif headline, left-aligned, generous whitespace, "
            "max two text sizes, high contrast. Imagery: clean minimal 3D objects or minimal photoreal scenes, soft studio "
            "light, subtle grain, no clutter. Layout: {FORMAT}; keep all text and key objects inside the centre with an 8% "
            "safe margin on every edge; keep the bottom-right corner (12% of width) empty and clean for a logo added later. "
            "Do not draw any logo. Text rules: render ONLY the German text given in quotes, exactly once, verbatim, with "
            "correct umlauts (ä, ö, ü, ß); no other words, no fake UI text, no watermarks, no third-party logos or brand "
            "names, no real or recognisable people."
        ),
    },
    "bad-energie": {
        "folder": "Bad-und-Energie",
        "prefix": "BE",
        "name": "Bad & Energie GmbH Lahn-Dill",
        "brand": (
            "Brand style for a long-established plumbing, heating and bathroom company in Germany. Look: bright, warm and "
            "trustworthy; realistic photographic style; clean German homes and tidy technical rooms; natural daylight; subtle "
            "depth of field. Palette: white and very light warm grey surfaces, brand blue (#111D6D) as the main colour, brand "
            "red (#D60000) only as a small accent, dark charcoal text (#222222). Typography: bold, friendly sans-serif "
            "headline, left-aligned, generous whitespace, at most two text sizes. People: only anonymous (hands, from behind "
            "or cropped at the shoulders), never a recognisable face. Layout: {FORMAT}; keep all text and key objects inside "
            "an 8% safe margin; keep the bottom-right corner (14% of the width) empty and calm for a logo added later. Do not "
            "draw any logo, manufacturer logo or label on devices, and no company name outside the quoted headline. Text "
            "rules: render ONLY the German text given in quotes, exactly once, verbatim, with correct umlauts (ä, ö, ü, ß); "
            "no other words, numbers or watermarks."
        ),
    },
    "tezgel": {
        "folder": "Tezgel",
        "prefix": "TZ",
        "name": "Fliesenverlegung Tezgel",
        "brand": (
            "Brand style for an owner-run tiling company in Germany known for precise large-format tiles, walk-in showers "
            "without a step, balconies and stairs. Look: calm architectural interior photography; razor-straight joints; "
            "perfectly level surfaces; soft natural side light that reveals texture; realistic materials (porcelain "
            "stoneware, mosaic, natural stone); no clutter, no tools lying around. Palette: light zinc grey (#F4F4F5), "
            "anthracite text (#27272A), warm stone and greige tones, one accent colour red (#D82020) used sparingly. "
            "Typography: clean modern sans-serif headline, left-aligned, generous whitespace, at most two text sizes. "
            "People: only hands or figures from behind, never a recognisable face. Layout: {FORMAT}; keep all text and key "
            "objects inside an 8% safe margin; keep the bottom-right corner (14% of the width) empty for a logo added later. "
            "Do not draw any logo, company name, brand name or watermark. Text rules: render ONLY the German text given in "
            "quotes, exactly once, verbatim, with correct umlauts (ä, ö, ü, ß); no other words or numbers."
        ),
    },
}

PREFIX_TO_KEY = {c["prefix"]: k for k, c in COMPANIES.items()}

FORMATS = {
    # Ordner: (Breite, Hoehe, fuer welche Formate)
    "instagram-3x4": (1080, 1440, "3:4"),
    "facebook-linkedin-4x5": (1080, 1350, "3:4"),
    "story-9x16": (1080, 1920, "9:16"),
}


def company_dir(key):
    return ROOT / COMPANIES[key]["folder"]


def load(key):
    return json.loads((company_dir(key) / "prompts.json").read_text(encoding="utf-8"))


def needs_style_ref(entry):
    s = entry.get("series")
    return bool(s) and int(s.get("slide", 1)) > 1


def full_prompt(key, entry, style_ref=None):
    """Fertiger Bildprompt: Brand-Block mit Format, Szene, Labels, Headline."""
    fmt = STORY if entry.get("format") == "9:16" else FEED
    parts = []
    if style_ref if style_ref is not None else needs_style_ref(entry):
        parts.append(STYLE_REF)
    parts.append(COMPANIES[key]["brand"].replace("{FORMAT}", fmt))
    scene = (entry.get("scene") or "").strip()
    if scene and scene[-1] not in ".!?":
        scene += "."
    parts.append(scene)
    labels = entry.get("small_text") or []
    if entry.get("headline"):
        parts.append(f'Headline: "{entry["headline"]}"' + ("." if labels else ""))
    for label in labels:
        parts.append(f'Small label ({label["where"]}): "{label["text"]}".')
    if not entry.get("headline") and not labels:
        parts.append("No text at all.")
    return " ".join(p for p in parts if p)


def image_paths(key, entry_id):
    """Vorhandene Bilddateien eines Eintrags, relativ zum Firmenordner."""
    base = company_dir(key) / "bilder"
    found = {}
    for sub in ["original", *FORMATS]:
        hits = sorted((base / sub).glob(f"{entry_id}*")) if (base / sub).is_dir() else []
        if hits:
            found[sub] = hits[0].relative_to(company_dir(key)).as_posix()
    return found


def build(key):
    c = COMPANIES[key]
    entries = load(key)
    out_dir = company_dir(key)
    for e in entries:
        e["prompt"] = full_prompt(key, e)
    (out_dir / "prompts.json").write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    feed = sum(1 for e in entries if e["format"] == "3:4")
    story = len(entries) - feed
    with_img = 0
    lines = [
        f"# {c['name']}: Prompt-Bibliothek ({len(entries)} Bildprompts)",
        "",
        f"Modell: GPT Image 2.5, Variante Sunburst · {feed} Feed-Posts (3:4, 1080 × 1440) · {story} Stories (9:16, 1080 × 1920)",
        "",
        "Jeder Prompt unten ist komplett: Brand-Block, Szene und der Text im Bild. In Arena oder ChatGPT einfach "
        "den Codeblock kopieren und senden. Karussell-Slides ab Nr. 2: vorher die fertige Cover-Slide hochladen. "
        "Danach Text im Bild Wort für Wort prüfen und das echte Logo unten rechts einsetzen.",
        "",
        "⚠️ = vor dem Posten Fakten prüfen (Stand steht in den Hinweisen).",
        "",
        "## Übersicht",
        "",
        "| ID | Titel | Kategorie | Format | Text im Bild | Bild |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for e in entries:
        imgs = image_paths(key, e["id"])
        shown = imgs.get("instagram-3x4") or imgs.get("story-9x16") or imgs.get("original")
        with_img += bool(shown)
        flag = " ⚠️" if e.get("fact_check") else ""
        series = f" ({e['series']['id']} {e['series']['slide']}/{e['series']['of']})" if e.get("series") else ""
        cell = f"[ansehen]({shown})" if shown else "–"
        headline = (e.get("headline") or "(ohne Text)").replace("|", "/")
        lines.append(f"| [{e['id']}](#{e['id'].lower()}){flag} | {e['title']}{series} | {e['category']} | "
                     f"{e['format']} | {headline} | {cell} |")
    lines.append("")
    for e in entries:
        imgs = image_paths(key, e["id"])
        lines += [f'<a id="{e["id"].lower()}"></a>', f"## {e['id']} · {e['title']}", ""]
        meta = [e["category"], e["format"]]
        if e.get("series"):
            s = e["series"]
            meta.append(f"Karussell {s['id']} „{s.get('title', '')}“, Slide {s['slide']} von {s['of']}")
        if e.get("doc_ref"):
            meta.append(f"Dokument Nr. {e['doc_ref']}")
        lines += [" · ".join(meta), ""]
        if needs_style_ref(e):
            lines += ["Vorher die Cover-Slide dieser Serie hochladen (Stilreferenz).", ""]
        lines += ["```text", e["prompt"], "```", ""]
        if e.get("headline"):
            lines.append(f"**Text im Bild:** „{e['headline']}“  ")
        for label in e.get("small_text") or []:
            lines.append(f"**Label:** „{label['text']}“ ({label['where']})  ")
        lines.append(f"**Caption:** {e['caption']}  ")
        lines.append(f"**Hashtags:** {e['hashtags']}  ")
        if e.get("notes") or e.get("fact_check"):
            lines.append(f"**Hinweise:** {'⚠️ Fakten prüfen. ' if e.get('fact_check') else ''}{e.get('notes', '')}  ")
        if imgs:
            lines.append("**Bilder:** " + " · ".join(f"[{k}]({v})" for k, v in imgs.items()))
            shown = imgs.get("instagram-3x4") or imgs.get("story-9x16") or imgs.get("original")
            lines += ["", f'<img src="{shown}" width="270">']
        lines.append("")
    (out_dir / "prompts.md").write_text("\n".join(lines), encoding="utf-8")

    with open(out_dir / "captions.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "titel", "kategorie", "format", "text_im_bild", "caption", "hashtags", "hinweise",
                    "fakten_pruefen", "bild_instagram_3x4", "bild_facebook_linkedin_4x5", "bild_story_9x16"])
        for e in entries:
            imgs = image_paths(key, e["id"])
            w.writerow([e["id"], e["title"], e["category"], e["format"], e.get("headline", ""), e["caption"],
                        e["hashtags"], e.get("notes", ""), "ja" if e.get("fact_check") else "nein",
                        imgs.get("instagram-3x4", ""), imgs.get("facebook-linkedin-4x5", ""),
                        imgs.get("story-9x16", "")])
    uploads_file = out_dir / "needs_upload.json"
    if uploads_file.exists():
        uploads = json.loads(uploads_file.read_text(encoding="utf-8"))
        up = [f"# {c['name']}: Edit-Prompts mit eigenen Dateien ({len(uploads)})", "",
              "Diese Prompts brauchen eigene Uploads (Screenshots, Logo, echte Projektfotos). Nur Dateien ohne "
              "Personen, Hausnummern oder Kundendaten hochladen und nur mit Zustimmung der Kunden.", ""]
        for u in uploads:
            up += [f"## {u['id']} · {u['title']}", "", f"Dokument Nr. {u.get('doc_ref', '')} · "
                   f"**Hochladen:** {u.get('upload', '')}", "", "```text", u["prompt"], "```", ""]
            if u.get("caption"):
                up.append(f"**Caption:** {u['caption']}  ")
            if u.get("hashtags"):
                up.append(f"**Hashtags:** {u['hashtags']}  ")
            if u.get("notes"):
                up.append(f"**Hinweise:** {u['notes']}  ")
            up.append("")
        (out_dir / "uploads-noetig.md").write_text("\n".join(up), encoding="utf-8")
    print(f"{c['folder']}: {len(entries)} Prompts, {with_img} mit Bild")


KEYS = {"id": str, "source": str, "title": str, "category": str, "format": str, "scene": str, "headline": str,
        "small_text": list, "caption": str, "hashtags": str, "notes": str, "fact_check": bool}
# (Muster, geprüfte Felder) je Firma; "all" gilt überall
FORBIDDEN = {
    "all": [(r"\bunhackbar\b|100\s?%\s?sicher", ("scene", "headline", "caption")),
            (r"\[(ACCENT|AKZENT|BLAU|ROT|BRAND|BE|TZ)\]", ("scene",)),
            (r"\\?\[\d+\\?\]", ("caption",))],
    "coday": [(r"\b(hack|attack|exploit|shell)\b", ("scene", "headline"))],
    "tezgel": [(r"garantie", ("headline", "caption"))],
    "bad-energie": [(r"\bGEG\b|heizungsgesetz", ("headline", "caption"))],
}


def check(key, entries=None):
    """Formale Prüfung einer Bibliothek; gibt eine Liste von Warnungen zurück."""
    entries = entries if entries is not None else load(key)
    warn = []
    prefix = COMPANIES[key]["prefix"]
    for i, e in enumerate(entries, 1):
        eid = e.get("id", f"#{i}")
        for k, typ in KEYS.items():
            if not isinstance(e.get(k), typ):
                warn.append(f"{eid}: Feld {k} fehlt oder hat falschen Typ")
        if eid != f"{prefix}-{i:03d}":
            warn.append(f"{eid}: erwartet {prefix}-{i:03d}")
        if e.get("format") not in ("3:4", "9:16"):
            warn.append(f"{eid}: Format {e.get('format')!r}")
        words = len((e.get("headline") or "").split())
        if words > 7 and e.get("source") == "new":
            warn.append(f"{eid}: Headline hat {words} Wörter")
        if len((e.get("scene") or "").split()) > 60:
            warn.append(f"{eid}: Szene länger als 60 Wörter")
        tags = (e.get("hashtags") or "").split()
        if any(not t.startswith("#") or re.fullmatch(r"#?[A-Z]\d?", t) for t in tags):
            warn.append(f"{eid}: Hashtags nicht aufgelöst: {e.get('hashtags')}")
        s = e.get("series")
        if s and not (1 <= int(s.get("slide", 0)) <= int(s.get("of", 0))):
            warn.append(f"{eid}: Serie inkonsistent {s}")
        for pat, fields in FORBIDDEN["all"] + FORBIDDEN.get(key, []):
            text = " ".join(str(e.get(k) or "") for k in fields)
            if re.search(pat, text, re.IGNORECASE):
                warn.append(f"{eid}: verbotenes Muster {pat} in {'/'.join(fields)}")
    heads = {}
    for e in entries:
        h = (e.get("headline") or "").strip().lower()
        if h:
            heads.setdefault(h, []).append(e.get("id"))
    warn += [f"doppelte Headline {ids}: {h!r}" for h, ids in heads.items() if len(ids) > 1]
    return warn


def sips(*args):
    subprocess.run(["sips", *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def size(path):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
                         check=True, capture_output=True, text=True).stdout
    vals = dict(line.strip().split(": ") for line in out.splitlines()[1:] if ": " in line)
    return int(vals["pixelWidth"]), int(vals["pixelHeight"])


def export_image(key, original, entry_format):
    """Original -> Posting-Formate als JPEG. Schneidet mittig zu, staucht nie."""
    base = company_dir(key) / "bilder"
    stem = Path(original).stem
    w, h = size(original)
    for sub, (tw, th, src_fmt) in FORMATS.items():
        if src_fmt != entry_format:
            continue
        (base / sub).mkdir(parents=True, exist_ok=True)
        target = base / sub / f"{stem}.jpg"
        # erst so skalieren, dass das Ziel komplett bedeckt ist, dann mittig beschneiden
        scale = max(tw / w, th / h)
        sw, sh = round(w * scale), round(h * scale)
        sips("-s", "format", "jpeg", "-s", "formatOptions", "90", "-z", str(sh), str(sw), str(original),
             "--out", str(target))
        sips("-c", str(th), str(tw), str(target), "--out", str(target))


def export(key):
    entries = {e["id"]: e for e in load(key)}
    originals = sorted((company_dir(key) / "bilder" / "original").glob("*.*"))
    for o in originals:
        entry = entries.get(o.stem.split("_")[0])
        export_image(key, o, entry["format"] if entry else "3:4")
    print(f"{COMPANIES[key]['folder']}: {len(originals)} Originale exportiert")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {"build", "export", "prompt", "check"}:
        print(__doc__)
        sys.exit(1)
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "prompt":
        for entry_id in rest:
            key = PREFIX_TO_KEY[entry_id.split("-")[0]]
            entry = next(e for e in load(key) if e["id"] == entry_id)
            print(full_prompt(key, entry), "\n")
        return
    for key in rest or list(COMPANIES):
        if cmd == "check":
            warnings = check(key)
            print(f"{COMPANIES[key]['folder']}: {len(warnings)} Warnungen")
            print("\n".join(f"  {w}" for w in warnings))
        elif cmd == "build":
            build(key)
        else:
            export(key)


if __name__ == "__main__":
    main()
