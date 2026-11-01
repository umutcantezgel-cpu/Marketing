#!/usr/bin/env python3
"""Tägliches Posten über Metricool: Tagesplan, fällige Aufträge, Bild-Links und Log.

Der Plan legt pro Firma jeden Tag einen Feed-Post fest (ein Karussell zählt als ein Post), dazu Stories.
Die Termine aus dem Posting-Plan im README der Firma (Mo/Mi/Fr, 10 Wochen) bleiben, die übrigen Tage füllen die
restlichen Posts im Wechsel der Kategorien. Saisonale Posts laufen nur in ihrem Zeitfenster (ZEITFENSTER).
Was schon in Metricool liegt (log.csv), behält seinen Tag. Posts, die auf eine Freigabe warten (Faktencheck, offene
Frage, zurueckhalten), kommen erst nach dem Vorlauf dran und rücken jeden Tag nach, bis ihre ID in geprueft.txt steht.
Die geplante Aufgabe in Claude Code arbeitet posting/ANLEITUNG.md ab und ruft dieses Skript auf.

Aufruf:
  python3 tools/posting.py plan                  Plan ab morgen neu bauen: posting/plan.json und <Firma>/tagesplan.md
  python3 tools/posting.py vorrat                Reichweite des Plans und Posts, die auf eine Freigabe warten
  python3 tools/posting.py faellig --kurz        offene Aufträge der nächsten Tage als Übersicht
  python3 tools/posting.py faellig --datum D     fertige Metricool-Aufträge für einen Tag (JSON)
  python3 tools/posting.py bilder                Bilder der offenen Aufträge ins öffentliche Bilder-Repo
  python3 tools/posting.py eintragen ZEILE ...   Ergebnisse ins Log; ZEILE = schluessel;status;metricool_id;bemerkung,
                                                 "-" liest die Zeilen von stdin
"""

import argparse
import csv
import datetime as dt
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bibliothek as bib  # noqa: E402

ROOT = bib.ROOT
POSTING = ROOT / "posting"
SETTINGS = POSTING / "einstellungen.json"
PLAN = POSTING / "plan.json"
LOG = POSTING / "log.csv"
CHECKED = POSTING / "geprueft.txt"
QUESTIONS = ROOT / "offene-fragen.md"
LOG_FIELDS = ["zeit", "schluessel", "datum", "status", "metricool_id", "bemerkung"]

DONE = {"geplant", "entwurf", "manuell", "freigabe"}  # liegt schon in Metricool, nicht noch einmal anlegen
MAX_ERRORS = 2                                        # danach lässt die Aufgabe den Auftrag liegen
STORY_GAP = 3                                         # Tage zwischen Stories, die nicht zu einem Feed-Post gehören
URGENT_DAYS = 10                                      # Saison-Posts gehen vor, wenn ihr Zeitfenster bald endet
STORY_NETWORKS = ("instagram", "facebook")
STICKER_NETWORKS = ("instagram",)                     # Sticker gibt es nur in Instagram-Stories
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
POST_ID = re.compile(r"\b[A-Z]{2}-\d{3}\b")
STICKER = re.compile(r"sticker|umfrage|quiz|countdown", re.I)
PHONE = re.compile(r"\b0\d{2,4}\s*[/-]?\s*\d[\d -]{3,}\d")
NO_GBP = re.compile(r"\bDMs?\b|kommentar|kommentier", re.I)  # Google-Profile haben weder Kommentare noch Chat

# Saisonale Posts: (frühestens, spätestens) für Tage außerhalb ihres README-Termins. Schlüssel: ID bzw. Karussell.
ZEITFENSTER = {
    "CD-076": ("2027-01-01", "2027-01-31"),  # PHP 8.2 nach Silvester
    "CD-087": ("2027-01-01", "2027-02-28"),  # PHP 8.2 ausgelaufen
    "CD-K4": ("2026-11-23", "2026-12-18"),   # Karussell: Vor den Feiertagen
    "CD-100": ("2026-11-02", "2026-12-04"),  # Gastro: Weihnachtsfeier-Anfragen
    "CD-101": ("2026-11-02", "2026-11-30"),  # Kfz-Werkstatt: Reifenwechsel im Herbst
    "CD-102": ("2026-11-02", "2026-11-27"),  # Blumenladen: Adventskranz vorbestellen
    "CD-103": ("2026-11-02", "2027-01-31"),  # Winterdienst
    "CD-105": ("2026-11-02", "2026-12-18"),  # Pension: vor den Feiertagen buchen
    "CD-106": ("2026-12-27", "2027-01-20"),  # Verein: neue Mitglieder im Januar
    "CD-113": ("2026-12-24", "2026-12-24"),  # Weihnachtsgruß
    "CD-114": ("2027-01-02", "2027-01-31"),  # Footer im neuen Jahr
    "CD-120": ("2026-12-28", "2027-01-15"),  # Story: Website-Vorsatz fürs neue Jahr
    "CD-121": ("2026-11-02", "2026-11-30"),  # Story: PHP-Lücke vom Oktober
    "CD-123": ("2026-11-02", "2026-12-31"),  # Story: PHP 8.2 Support-Ende
    "BE-001": ("2026-11-02", "2026-12-31"),  # Jubiläum
    "BE-002": ("2026-11-02", "2026-12-31"),
    "BE-K1": ("2026-11-02", "2026-12-31"),
    "BE-120": ("2026-11-02", "2026-12-31"),
    "BE-068": ("2026-11-02", "2026-12-31"),
    "BE-108": ("2026-11-02", "2026-12-31"),
    "BE-111": ("2026-11-02", "2026-12-31"),
    "BE-003": ("2026-11-02", "2027-01-31"),  # Förderung bis zum Bonus-Stichtag 1.2.2027
    "BE-004": ("2026-11-02", "2027-01-31"),
    "BE-K2": ("2026-11-02", "2027-01-31"),
    "BE-K5": ("2026-11-02", "2027-01-31"),
    "BE-121": ("2026-11-02", "2027-01-31"),
    "BE-122": ("2026-11-02", "2027-01-31"),
    "BE-083": ("2026-11-02", "2027-01-25"),
    "BE-084": ("2026-11-02", "2027-01-25"),
    "BE-090": ("2027-01-11", "2027-01-30"),  # Story-Countdown zum Bonus-Stichtag
    "BE-048": ("2026-11-02", "2027-02-28"),  # Heizsaison
    "BE-085": ("2026-11-02", "2027-02-28"),
    "BE-087": ("2026-11-02", "2027-02-28"),
    "BE-088": ("2026-11-16", "2027-02-28"),
    "BE-091": ("2026-11-02", "2027-02-28"),
    "BE-094": ("2026-11-16", "2027-02-28"),
    "BE-115": ("2026-11-16", "2027-02-28"),
    "BE-062": ("2026-11-02", "2026-12-31"),  # Bereit für den Winter?
    "BE-116": ("2026-11-29", "2026-11-29"),  # Erster Advent
    "BE-117": ("2026-11-02", "2026-12-11"),  # Außenwasserhahn winterfest machen
    "BE-118": ("2026-12-14", "2026-12-22"),  # Heizung bei Abwesenheit über die Feiertage
    "BE-063": ("2026-12-20", "2026-12-26"),  # Frohe Weihnachten
    "BE-114": ("2026-12-21", "2026-12-30"),  # Feiertage: Schlange vorm Bad
    "BE-064": ("2026-12-31", "2027-01-06"),  # Gutes neues Jahr
    "BE-107": ("2026-12-27", "2027-01-08"),  # Jahresrückblick Jubiläumsjahr
    "BE-104": ("2026-12-28", "2027-01-15"),  # Trinkwasser nach dem Urlaub
    "BE-119": ("2026-12-28", "2027-01-10"),  # Story: Vorsatz fürs neue Jahr
    "TZ-018": ("2026-11-02", "2026-12-12"),  # Handwerkerbonus nur bis Mitte Dezember
    "TZ-119": ("2026-11-02", "2026-12-12"),
    "TZ-095": ("2026-11-16", "2027-02-15"),  # Balkon im Winter planen
    "TZ-110": ("2026-11-29", "2026-11-29"),  # Erster Advent
    "TZ-064": ("2026-12-20", "2026-12-26"),  # Frohe Weihnachten
    "TZ-120": ("2026-12-27", "2027-01-12"),  # Story: Neues Bad im neuen Jahr
    "TZ-109": ("2026-12-30", "2027-01-15"),  # Guter Vorsatz
    "TZ-111": ("2027-01-01", "2027-01-03"),  # Gutes neues Jahr
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def day(text):
    return dt.date.fromisoformat(text)


def entries_of(key):
    return load_json(ROOT / bib.COMPANIES[key]["folder"] / "prompts.json")


def image_file(key, entry_id, story=False):
    sub = "story-9x16" if story else "facebook-linkedin-4x5"
    return ROOT / bib.COMPANIES[key]["folder"] / "bilder" / sub / f"{entry_id}.jpg"


def image_target(key, entry_id, story=False):
    """Pfad im öffentlichen Bilder-Repo, gleich für Datei und Link."""
    return f"{bib.COMPANIES[key]['folder']}/{'story/' if story else ''}{entry_id}.jpg"


def image_url(s, key, entry_id, story=False):
    return f"https://raw.githubusercontent.com/{s['bild_repo']}/main/{image_target(key, entry_id, story)}"


def read_log():
    if not LOG.exists():
        return []
    with LOG.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def read_checked():
    if not CHECKED.exists():
        return set()
    return set(POST_ID.findall(re.sub(r"#.*", "", CHECKED.read_text(encoding="utf-8"))))


def holds(s):
    """Warum ein Post noch nicht raus darf, pro ID. IDs in geprueft.txt sind freigegeben."""
    reasons = {}
    for key in bib.COMPANIES:
        for e in entries_of(key):
            if e.get("fact_check"):
                note = " ".join((e["notes"] or "siehe prompts.md").split())
                reasons.setdefault(e["id"], []).append(f"Fakten prüfen: {note[:220]}")
    for i, text in s.get("zurueckhalten", {}).items():
        reasons.setdefault(i, []).append(text)
    if QUESTIONS.exists():
        items, current = [], None
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines():
            if re.match(r"\s*- \[[ xX]\]", line):
                current = [line.strip()]
                items.append(current)
            elif current is not None and line.strip() and not line.lstrip().startswith(("-", "#")):
                current.append(line.strip())
            else:
                current = None
        for item in items:
            text = " ".join(item)
            if text.startswith("- [ ]"):
                for i in set(POST_ID.findall(text)):
                    reasons.setdefault(i, []).append(f"Offene Frage: {text[6:][:220]}")
    checked = read_checked()
    return {i: r for i, r in reasons.items() if i not in checked}


def networks_for(s, cfg, r):
    networks = cfg.get("netzwerke", s["netzwerke"])
    if r["art"] == "story":
        allowed = STICKER_NETWORKS if r["sticker"] else STORY_NETWORKS
        networks = [n for n in networks if n in allowed]
    return networks


def check_brands(s):
    """Zwei Firmen auf derselben Metricool-Marke würden sich gegenseitig die Kanäle füllen."""
    firms = s["firmen"].values()
    ids = [str(c["blogId"]) for c in firms if c.get("blogId")]
    names = [c["metricool_marke"] for c in firms]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        sys.exit("Fehler: Mehrere Firmen teilen sich eine Metricool-Marke (blogId oder metricool_marke). "
                 "posting/einstellungen.json korrigieren, bis dahin nichts einplanen.")


# ---------------------------------------------------------------- Plan

def posts_of(key):
    """Feed-Posts (Einzelbild oder Karussell) und Stories einer Firma, jeweils mit Sperrgrund."""
    c = bib.COMPANIES[key]
    origin = load_json(ROOT / c["folder"] / "bilder" / "generiert.json")

    def lock(es, story):
        for e in es:
            if origin.get(e["id"], {}).get("quelle", "").startswith("Arena"):
                return "Arena-Bild: ohne schriftliche Freigabe von Arena nicht für Werbung nutzen"
            if not image_file(key, e["id"], story).exists():
                return "Bild fehlt"
        return None

    def post(pid, art, typ, es):
        cover = es[0]
        return {"post": pid, "art": art, "typ": typ, "ids": [e["id"] for e in es],
                "titel": cover["series"]["title"] if typ == "karussell" else cover["title"],
                "kategorie": cover["category"],
                "sticker": art == "story" and bool(STICKER.search(f"{cover['title']} {cover['notes'] or ''}")),
                "eltern": cover["doc_ref"] if cover["source"] == "story" else None,
                "sperre": lock(es, art == "story"), "fenster": ZEITFENSTER.get(pid)}

    feed, stories, slides = {}, {}, {}
    for e in entries_of(key):
        if e["format"] == "9:16":
            stories[e["id"]] = post(e["id"], "story", "story", [e])
        elif e.get("series"):
            slides.setdefault(f"{c['prefix']}-{e['series']['id']}", []).append(e)
        else:
            feed[e["id"]] = post(e["id"], "feed", "bild", [e])
    for pid, es in slides.items():
        feed[pid] = post(pid, "feed", "karussell", sorted(es, key=lambda e: e["series"]["slide"]))
    return feed, stories


def readme_plan(key):
    """Termine aus dem Posting-Plan im README: {(woche, spalte): (post, zelle)}; post "frei" oder None (eigenes Foto)."""
    c = bib.COMPANIES[key]
    text = (ROOT / c["folder"] / "README.md").read_text(encoding="utf-8")
    section = text.split("## Posting-Plan", 1)[1].split("\n## ", 1)[0]
    slots = {}
    for line in section.splitlines():
        row = re.match(r"\|\s*(\d+)\s*\|(.*)\|\s*$", line)
        if not row:
            continue
        for col, cell in enumerate(row.group(2).split("|")):
            cell = cell.strip()
            if cell in ("", "-", "–"):
                pid = "frei"
            elif re.match(r"K\d+\b", cell):
                pid = f"{c['prefix']}-{cell.split()[0]}"
            elif re.match(r"\[[A-Z]{2}-\d{3}\]", cell):
                pid = cell[1:7]
            else:
                pid = None
            slots[(int(row.group(1)), col)] = (pid, cell)
    return slots


def rotate(posts):
    """Kategorien abwechseln, innerhalb einer Kategorie in ID-Reihenfolge."""
    groups = {}
    for p in posts:
        groups.setdefault(p["kategorie"], []).append(p)
    out = []
    while any(groups.values()):
        for g in groups.values():
            if g:
                out.append(g.pop(0))
    return out


def window(p):
    return (day(p["fenster"][0]), day(p["fenster"][1])) if p["fenster"] else None


def expire(pool, when):
    gone = [p for p in pool if p["fenster"] and window(p)[1] < when]
    for p in gone:
        pool.remove(p)
    return gone


def take(pool, when, allowed):
    """Post für einen freien Tag: ein Saison-Post, dessen Zeitfenster bald endet, sonst der nächste im Wechsel."""
    open_now = [p for p in pool if (not p["fenster"] or window(p)[0] <= when) and allowed(p)]
    urgent = [p for p in open_now if p["fenster"] and (window(p)[1] - when).days < URGENT_DAYS]
    p = min(urgent, key=lambda p: window(p)[1]) if urgent else (open_now[0] if open_now else None)
    if p:
        pool.remove(p)
    return p["post"] if p else None


def row(p, when, nr, source, held):
    return {"datum": when.isoformat(), "art": p["art"], "post": p["post"], "nr": nr, "typ": p["typ"],
            "ids": p["ids"], "titel": p["titel"], "sticker": p["sticker"], "quelle": source,
            "wartet": [i for i in p["ids"] if i in held]}


def build_plan(key, s, today, log, held):
    feed, stories = posts_of(key)
    start = max(day(s["start"]), today + dt.timedelta(days=1))
    horizon = today + dt.timedelta(days=s["vorlauf_tage"])
    monday = day(s["readme_plan_ab"])  # Woche 1 im README-Plan; bleibt fest, auch wenn der Start sich verschiebt

    def allowed_on(when):
        # Wartende Posts nie in den Vorlauf legen, sonst bliebe der Tag leer
        return lambda p: when > horizon or not any(i in held for i in p["ids"])

    # Was schon in Metricool liegt, behält seinen Tag
    pinned, rows, feed_taken, story_taken = {}, [], set(), set()
    for r in log:
        firma, art, post, nr, _ = r["schluessel"].split("|")
        if firma == key and r["status"] in DONE and r["datum"]:
            pinned[(art, post, int(nr))] = day(r["datum"])
    for (art, post, nr), when in sorted(pinned.items(), key=lambda kv: kv[1]):
        (feed_taken if art == "feed" else story_taken).add(when)
        p = (feed if art == "feed" else stories).get(post)
        if p:
            rows.append(row(p, when, nr, "metricool", held))

    # Termine aus dem README, soweit noch offen
    fixed, notes, seen = {}, [], Counter()
    for (week, col), (pid, cell) in sorted(readme_plan(key).items()):
        when = monday + dt.timedelta(days=7 * (week - 1) + 2 * col)
        if pid is None:
            if when >= start:
                notes.append({"post": cell.split("]")[0].lstrip("["), "titel": cell.split(") ", 1)[-1],
                              "grund": f"eigenes Foto nötig, Termin {when.isoformat()} ging an einen anderen Post"})
            continue
        if pid == "frei":
            if when >= start and when not in feed_taken:
                fixed[when] = None
            continue
        if pid not in feed or feed[pid]["sperre"]:
            continue
        seen[pid] += 1
        if ("feed", pid, seen[pid]) in pinned or when < start or when in feed_taken \
                or not allowed_on(when)(feed[pid]):
            continue  # vorbei, belegt oder wartet: der Post kommt (falls noch offen) in den Rest
        fixed[when] = (pid, seen[pid])

    first_done = {post for (art, post, nr) in pinned if art == "feed" and nr == 1}
    first_done |= {v[0] for v in fixed.values() if v and v[1] == 1}
    pool = rotate([p for pid, p in feed.items() if not p["sperre"] and pid not in first_done])
    lost = []
    when, last = start, max(list(fixed) + [start])
    while (pool or when <= last) and when <= start + dt.timedelta(days=400):
        lost += expire(pool, when)
        if when in feed_taken:
            pass
        elif when in fixed:
            if fixed[when]:
                rows.append(row(feed[fixed[when][0]], when, fixed[when][1], "plan", held))
        else:
            pid = take(pool, when, allowed_on(when))
            if pid:
                rows.append(row(feed[pid], when, 1, "auffueller", held))
        when += dt.timedelta(days=1)

    # Stories: Story-Versionen am Tag ihres Feed-Posts, die übrigen mit Abstand an Tagen ohne Story
    first_day, post_of = {}, {i: p["post"] for p in feed.values() for i in p["ids"]}
    for r in sorted(rows, key=lambda r: r["datum"]):
        if r["art"] == "feed":
            first_day.setdefault(r["post"], day(r["datum"]))
    story_pool = []
    for p in stories.values():
        if p["sperre"] or ("story", p["post"], 1) in pinned:
            continue
        if p["sticker"] and s.get("sticker_stories", "manuell") == "aus":
            notes.append({"post": p["post"], "titel": p["titel"], "grund": "Story mit Sticker, sticker_stories ist aus"})
            continue
        when = first_day.get(post_of.get(p["eltern"]))
        if when and when >= start and when not in story_taken and allowed_on(when)(p):
            story_taken.add(when)
            rows.append(row(p, when, 1, f"zu {post_of[p['eltern']]}", held))
        else:
            story_pool.append(p)
    feed_days = [day(r["datum"]) for r in rows if r["art"] == "feed"]
    end = max(feed_days) if feed_days else start
    when, previous = start, None
    while story_pool and when <= end:
        lost += expire(story_pool, when)
        if when not in story_taken and (previous is None or (when - previous).days >= STORY_GAP):
            pid = take(story_pool, when, allowed_on(when))
            if pid:
                story_taken.add(when)
                rows.append(row(stories[pid], when, 1, "auffueller", held))
                previous = when
        when += dt.timedelta(days=1)

    blocked = [{"post": p["post"], "titel": p["titel"], "grund": p["sperre"]}
               for p in list(feed.values()) + list(stories.values()) if p["sperre"]]
    lost = [{"post": p["post"], "titel": p["titel"], "grund": f"Zeitfenster bis {p['fenster'][1]} verpasst"}
            for p in lost]
    left = [{"post": p["post"], "titel": p["titel"], "grund": "kein freier Story-Tag mehr"} for p in story_pool]
    entries = sorted(rows, key=lambda r: (r["datum"], r["art"] != "feed"))
    return {"eintraege": entries, "nicht_eingeplant": blocked + notes + lost + left}


def md_cell(text):
    return " ".join((text or "").split()).replace("|", "\\|")


def write_md(key, s, fp, today, held):
    c = bib.COMPANIES[key]
    entries = {e["id"]: e for e in entries_of(key)}
    days = {}
    for r in fp["eintraege"]:
        if day(r["datum"]) > today:
            days.setdefault(r["datum"], {})[r["art"]] = r

    def link(i):
        return f"[{i}](prompts.md#{i.lower()})"

    def flags(r):
        return (" ⚠️" if r["wartet"] else "") + (" ✋" if r["sticker"] else "") + (" (Wiederholung)" if r["nr"] > 1 else "")

    lines = [f"# Tagesplan {c['name']}", "",
             f"Stand {today.strftime('%d.%m.%Y')}: ein Feed-Post pro Tag, dazu Stories. Die geplante Aufgabe in Claude Code "
             "baut den Plan jeden Morgen neu und stellt die Posts eine Woche im Voraus in Metricool ein, siehe "
             "[posting/README.md](../posting/README.md).", "",
             "⚠️ Wartet auf Freigabe (Gründe unten): Der Termin ist vorläufig. Der Post geht erst raus, wenn seine ID in "
             "`posting/geprueft.txt` steht, und rückt bis dahin jeden Tag nach.  ",
             "✋ Story mit Sticker (Umfrage, Quiz, Link): Metricool erinnert in der App, der Sticker kommt von Hand dazu.", "",
             "| Datum | Feed-Post | Text | Story |", "| --- | --- | --- | --- |"]
    for d in sorted(days):
        f, st = days[d].get("feed"), days[d].get("story")
        label = f"{WEEKDAYS[day(d).weekday()]} {day(d).strftime('%d.%m.%Y')}"
        feed_cell = text_cell = story_cell = ""
        if f:
            first = f["ids"][0]
            extra = f" (Karussell, {len(f['ids'])} Bilder)" if f["typ"] == "karussell" else ""
            feed_cell = (f'<img src="bilder/facebook-linkedin-4x5/{first}.jpg" width="90"><br>'
                         f"{link(first)} {md_cell(f['titel'])}{extra}{flags(f)}")
            text_cell = md_cell(entries[first]["caption"])
        if st:
            story_cell = f"{link(st['ids'][0])} {md_cell(st['titel'])}{flags(st)}"
        lines.append(f"| {label} | {feed_cell} | {text_cell} | {story_cell} |")
    waiting = sorted({i for r in fp["eintraege"] if day(r["datum"]) > today for i in r["wartet"]})
    lines += ["", "## Wartet auf Freigabe", "", "Zum Freigeben die ID in `posting/geprueft.txt` eintragen.", "",
              "| ID | Grund |", "| --- | --- |"]
    lines += [f"| {link(i)} | {md_cell(' / '.join(held[i]))} |" for i in waiting]
    lines += ["", "## Nicht eingeplant", "", "| Post | Titel | Grund |", "| --- | --- | --- |"]
    lines += [f"| {n['post']} | {md_cell(n['titel'])} | {md_cell(n['grund'])} |" for n in fp["nicht_eingeplant"]]
    (ROOT / c["folder"] / "tagesplan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_plan(s, today):
    log, held = read_log(), holds(s)
    plan = {"start": s["start"], "firmen": {}}
    for key in bib.COMPANIES:
        fp = plan["firmen"][key] = build_plan(key, s, today, log, held)
        write_md(key, s, fp, today, held)
        feed = [r for r in fp["eintraege"] if r["art"] == "feed" and day(r["datum"]) > today]
        waiting = sum(1 for r in fp["eintraege"] if r["wartet"] and day(r["datum"]) > today)
        reasons = Counter(n["grund"].split(":")[0].split(",")[0] for n in fp["nicht_eingeplant"])
        span = f"von {feed[0]['datum']} bis {feed[-1]['datum']}" if feed else "keine"
        print(f"{key}: {len(feed)} Feed-Posts {span}, davon {waiting} Posts mit Wartegrund; "
              f"nicht eingeplant: {dict(reasons)}")
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- Aufträge für Metricool

def utm(link, network, post):
    sep = "&" if "?" in link else "?"
    return f"{link}{sep}utm_source={network}&utm_medium=social&utm_campaign=tagespost&utm_content={post.lower()}"


def with_link(caption, url):
    """„Link in Bio“ gibt es nur auf Instagram; anderswo steht der Link selbst im Text."""
    if "Link in Bio" in caption:
        return re.sub(r"Link in Bio\.?", url, caption, count=1)
    return f"{caption}\n\n{url}"


def short(e, url, limit):
    """Headline, ein Satz und Link für X und Bluesky (und Threads, falls der ganze Text zu lang ist)."""
    caption = e["caption"] or ""
    plain = re.sub(r"\s*\((?:KI-generiertes )?Symbolbild(?:er)?\)", "", caption)
    sentences = [x for x in re.split(r"(?<=[.!?])\s+", plain) if x and "Symbolbild" not in x and "Link in Bio" not in x]
    label = ("(KI-generiertes Symbolbild)" if "KI-generiertes Symbolbild" in caption
             else "(Symbolbild)" if "Symbolbild" in caption else "")
    head = (e["headline"] or e["title"]).strip()
    for parts in ([head, sentences[0] if sentences else "", label], [head, label], [head], [e["title"]]):
        text = "\n".join(p for p in parts if p)
        if len(text) + 1 + len(url) <= limit:
            return f"{text}\n{url}"
    return url


def request(key, cfg, s, r, network, entries, tz):
    """Fertiger Auftrag für einen Post auf einem Netzwerk, oder None, wenn das Netzwerk den Post auslässt."""
    e = entries[r["ids"][0]]
    story = r["art"] == "story"
    caption = (e["caption"] or e["headline"] or e["title"]).strip()
    hashtags = (e["hashtags"] or "").split()
    link = cfg["link_recruiting"] if e["category"] == "Recruiting" and cfg.get("link_recruiting") else cfg["link"]
    media = [image_url(s, key, i, story) for i in r["ids"]]
    alt = [f"{entries[i]['title']}. Text im Bild: {entries[i]['headline']}" if entries[i]["headline"]
           else entries[i]["title"] for i in r["ids"]]
    ki = bool(s.get("ki_kennzeichnung", True))

    if story:
        text, data = "", ({"instagramData": {"type": "STORY", "isAiGenerated": ki}} if network == "instagram"
                          else {"facebookData": {"type": "STORY"}})
    elif network == "instagram":
        text = caption + ("\n\n" + " ".join(hashtags) if hashtags else "")
        data = {"instagramData": {"type": "POST", "isAiGenerated": ki}}
    elif network in ("facebook", "linkedin"):
        text = with_link(caption, utm(link, network, r["post"])) + ("\n\n" + " ".join(hashtags[:3]) if hashtags else "")
        data = {"facebookData": {"type": "POST"}} if network == "facebook" else {"linkedinData": {"type": "post"}}
    elif network == "gmb":
        if PHONE.search(caption) or NO_GBP.search(caption):
            return None  # Google lehnt Telefonnummern im Text ab; DMs und Kommentare gibt es dort nicht
        text, data, media, alt = with_link(caption, link), {"gmbData": {"type": "publication"}}, media[:1], alt[:1]
    elif network == "threads":
        text = with_link(caption, utm(link, network, r["post"]))
        if len(text) > 500:
            text = short(e, utm(link, network, r["post"]), 500)
        data = {"threadsData": {}}
    elif network in ("bluesky", "twitter"):
        limit = 300 if network == "bluesky" else 280
        text = short(e, utm(link, "x" if network == "twitter" else network, r["post"]), limit)
        data = {"blueskyData": {"postLanguages": ["de"]}} if network == "bluesky" else {"twitterData": {"tags": []}}
        media, alt = media[:1], alt[:1]
    else:
        return None

    mode = cfg.get("modus", "direkt")
    if mode == "freigabe" and not cfg.get("freigabe_mails"):
        mode = "entwurf"
    status = {"freigabe": "freigabe", "entwurf": "entwurf"}.get(mode, "manuell" if r["sticker"] else "geplant")
    clock = cfg["story_zeit"] if story else cfg["feed_zeit"]["wochenende" if day(r["datum"]).weekday() >= 5 else "werktags"]
    when = dt.datetime.combine(day(r["datum"]), dt.time.fromisoformat(clock), tzinfo=tz)
    info = {"autoPublish": not r["sticker"],  # Sticker setzt Instagram nicht automatisch: Metricool erinnert in der App
            "draft": mode == "entwurf", "descendants": [], "firstCommentText": "", "hasNotReadNotes": False,
            "media": media, "mediaAltText": alt, "providers": [{"network": network}],
            "publicationDate": {"dateTime": when.strftime("%Y-%m-%dT%H:%M:%S"), "timezone": s["zeitzone"]},
            "shortener": False, "smartLinkData": {"ids": []}, "text": text, **data}
    out = {"datum": r["datum"], "firma": key, "blogId": cfg.get("blogId"), "netzwerk": network, "art": r["art"],
           "post": r["post"], "ids": r["ids"],
           "werkzeug": "createScheduledPostForReview" if mode == "freigabe" else "createScheduledPost",
           "date": when.isoformat(), "info": info, "status_bei_erfolg": status}
    if mode == "freigabe":
        out["reviewers"] = cfg["freigabe_mails"]
        out["approvalSystem"] = cfg.get("freigabe_art", "optional")
    return out


def due(s, today, only=None):
    """Offene Aufträge für morgen bis in vorlauf_tage Tagen: freigegeben und noch nicht im Log."""
    check_brands(s)
    plan, log, held = load_json(PLAN), read_log(), holds(s)
    done = {r["schluessel"] for r in log if r["status"] in DONE}
    errors = Counter(r["schluessel"] for r in log if r["status"] == "fehler")
    tz = ZoneInfo(s["zeitzone"])
    first, last = today + dt.timedelta(days=1), today + dt.timedelta(days=s["vorlauf_tage"])
    out, given_up, waiting = [], [], []
    for key, fp in plan["firmen"].items():
        cfg = s["firmen"][key]
        entries = {e["id"]: e for e in entries_of(key)}
        for r in fp["eintraege"]:
            when = day(r["datum"])
            if not first <= when <= last or (only and when != only):
                continue
            if any(i in held for i in r["ids"]):
                waiting.append(f"{key}|{r['art']}|{r['post']}")
                continue
            for network in networks_for(s, cfg, r):
                k = f"{key}|{r['art']}|{r['post']}|{r['nr']}|{network}"
                if k in done:
                    continue
                if errors[k] >= MAX_ERRORS:
                    given_up.append(k)
                    continue
                req = request(key, cfg, s, r, network, entries, tz)
                if req:
                    out.append({"schluessel": k, **req})
    return out, given_up, waiting


def cmd_faellig(s, today, args):
    reqs, given_up, waiting = due(s, today, day(args.datum) if args.datum else None)
    if args.datum:
        tz = ZoneInfo(s["zeitzone"])
        midnight = dt.datetime.combine(day(args.datum), dt.time(0, 0), tzinfo=tz)
        brands = [{"firma": k, "blogId": c["blogId"], "fromDate": midnight.isoformat(),
                   "toDate": (midnight + dt.timedelta(hours=23, minutes=59, seconds=59)).isoformat(),
                   "timezone": s["zeitzone"]}
                  for k, c in s["firmen"].items() if c.get("blogId")]
        missing = sorted({r["firma"] for r in reqs if not r["blogId"]})
        print(json.dumps({"datum": args.datum, "marken_fuer_getScheduledPosts": brands, "ohne_blogId": missing,
                          "auftraege": [r for r in reqs if r["blogId"]]}, ensure_ascii=False, indent=1))
        return
    for r in reqs:
        print(f"{r['datum']}  {r['firma']:<12} {r['netzwerk']:<10} {r['art']:<5} {r['post']:<7} "
              f"{r['status_bei_erfolg']:<9} {r['schluessel']}{'' if r['blogId'] else '  (blogId fehlt)'}")
    by_day = Counter(r["datum"] for r in reqs)
    print(f"{len(reqs)} offene Aufträge an {len(by_day)} Tagen: " + ", ".join(f"{d} ({n})" for d, n in sorted(by_day.items())))
    if given_up:
        print("Nach zwei Fehlern aufgegeben: " + ", ".join(given_up))
    if waiting:
        print("Im Vorlauf, aber noch ohne Freigabe (wird nicht angelegt): " + ", ".join(waiting))


def cmd_vorrat(s, today):
    plan, held = load_json(PLAN), holds(s)
    for key, fp in plan["firmen"].items():
        rest = [r for r in fp["eintraege"] if day(r["datum"]) > today]
        feed = [r for r in rest if r["art"] == "feed"]
        if not feed:
            print(f"{key}: Plan aufgebraucht, neue Posts nötig")
            continue
        print(f"{key}: {len(feed)} Feed-Posts bis {feed[-1]['datum']} (noch {(day(feed[-1]['datum']) - today).days} Tage), "
              f"{len(rest) - len(feed)} Stories")
        waiting = [r for r in rest if any(i in held for i in r["ids"])]
        for r in waiting[:12]:
            ids = [i for i in r["ids"] if i in held]
            print(f"  wartet: {r['post']} (vorläufig {r['datum']}): " + " / ".join(held[ids[0]])[:240])
        if len(waiting) > 12:
            print(f"  … und {len(waiting) - 12} weitere, siehe {bib.COMPANIES[key]['folder']}/tagesplan.md")


# ---------------------------------------------------------------- Bilder und Log

def git(repo, *args, capture=False):
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=capture,
                            env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    return result.stdout.strip() if capture else None


def reachable(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as resp:
            return resp.status == 200
    except OSError:
        return False


def cmd_bilder(s, today):
    repo = Path(os.path.expanduser(s["bild_repo_ordner"]))
    if not (repo / ".git").exists():
        sys.exit(f"Bilder-Repo fehlt: {repo}. Einrichtung siehe posting/README.md.")
    files = {}
    for r in due(s, today)[0]:
        for i in r["ids"]:
            story = r["art"] == "story"
            files[image_url(s, r["firma"], i, story)] = (image_file(r["firma"], i, story),
                                                         repo / image_target(r["firma"], i, story))
    git(repo, "pull", "-q", "--rebase")
    copied = 0
    for src, dst in files.values():
        if not dst.exists() or not filecmp.cmp(src, dst, shallow=False):
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    if copied:
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", f"Bilder für die Posts bis {today + dt.timedelta(days=s['vorlauf_tage'])}")
    if git(repo, "rev-list", "--count", "@{u}..HEAD", capture=True) != "0":
        git(repo, "push", "-q")
    # Prüfen mit eigenem Parameter, damit GitHub für den echten Link keine 404 zwischenspeichert
    version = git(repo, "rev-parse", "--short", "HEAD", capture=True)
    missing = [u for u in files if not reachable(f"{u}?v={version}")]
    for _ in range(8):  # frisch gepushte Dateien brauchen bei GitHub manchmal ein paar Minuten
        if not missing:
            break
        time.sleep(30)
        missing = [u for u in missing if not reachable(f"{u}?v={version}")]
    print(f"{len(files)} Bilder gebraucht, {copied} neu hochgeladen, {len(files) - len(missing)} Links erreichbar.")
    if missing:
        print("Nicht erreichbar (Aufträge mit diesen Bildern heute auslassen):\n" + "\n".join(missing))
        sys.exit(1)


def cmd_eintragen(s, lines):
    """Alle Zeilen prüfen und erst dann schreiben: ein Tippfehler im Schlüssel hieße morgen ein doppelter Post."""
    plan = load_json(PLAN)
    dates = {}
    for key, fp in plan["firmen"].items():
        for r in fp["eintraege"]:
            for network in networks_for(s, s["firmen"][key], r):
                dates[f"{key}|{r['art']}|{r['post']}|{r['nr']}|{network}"] = r["datum"]
    now = dt.datetime.now().isoformat(timespec="seconds")
    rows, bad = [], []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("schluessel;"):
            continue
        k, status, mid, note = [x.strip() for x in (line.split(";", 3) + ["", "", ""])[:4]]
        if k not in dates:
            bad.append(f"unbekannter Schlüssel: {line}")
        elif status not in DONE | {"fehler"}:
            bad.append(f"unbekannter Status: {line}")
        else:
            rows.append([now, k, dates[k], status, mid, " ".join(note.split())])
    if bad:
        sys.exit("Nichts eingetragen, bitte korrigieren:\n" + "\n".join(bad))
    new = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, delimiter=";")
        if new:
            out.writerow(LOG_FIELDS)
        out.writerows(rows)
    print(f"{len(rows)} Einträge ins Log geschrieben.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--heute", help="Datum für Tests (JJJJ-MM-TT), sonst heute")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("vorrat")
    f = sub.add_parser("faellig")
    f.add_argument("--datum", help="nur dieser Tag, als JSON mit allen Feldern")
    f.add_argument("--kurz", action="store_true", help="Übersicht (Standard)")
    sub.add_parser("bilder")
    e = sub.add_parser("eintragen")
    e.add_argument("zeilen", nargs="+", help="Zeilen schluessel;status;metricool_id;bemerkung oder - für stdin")
    args = ap.parse_args()

    s = load_json(SETTINGS)
    today = day(args.heute) if args.heute else dt.date.today()
    if args.cmd == "plan":
        cmd_plan(s, today)
    elif args.cmd == "vorrat":
        cmd_vorrat(s, today)
    elif args.cmd == "faellig":
        cmd_faellig(s, today, args)
    elif args.cmd == "bilder":
        cmd_bilder(s, today)
    elif args.cmd == "eintragen":
        cmd_eintragen(s, sys.stdin if args.zeilen == ["-"] else args.zeilen)


if __name__ == "__main__":
    main()
