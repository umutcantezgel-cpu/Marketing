#!/usr/bin/env python3
"""Tägliches Posten über Metricool: Tagesplan, fällige Aufträge, Bild-Links und Log.

Der Plan legt pro Firma jeden Tag einen Feed-Post fest (ein Karussell zählt als ein Post), dazu Stories.
Die Termine aus dem Posting-Plan im README der Firma (Mo/Mi/Fr, 10 Wochen) bleiben, die übrigen Tage füllen die
restlichen Posts im Wechsel der Kategorien. Saisonale Posts laufen nur in ihrem Zeitfenster (ZEITFENSTER).
Was schon in Metricool liegt (log.csv), behält seinen Tag. Posts, die auf eine Freigabe warten (Faktencheck, offene
Frage, zurueckhalten), kommen erst nach dem Vorlauf dran und rücken jeden Tag nach, bis ihre ID in geprueft.txt steht.
Mit einer Frist ("bis" in den Einstellungen der Firma) gehen alle freigegebenen Feed-Posts bis zu diesem Tag raus,
an so vielen Tagen wie nötig mehrere ("feed2", "feed3" mit den Uhrzeiten aus feed_zeit_extra).
Mit einem Monatslimit ("max_pro_monat", zum Beispiel 20 im kostenlosen Metricool-Plan) plant das Skript nur so viele
Feed-Posts pro Kalendermonat, wie Metricool veröffentlicht; jedes Netzwerk zählt einzeln. Die Posting-Tage liegen
gleichmäßig über den Monat verteilt, Saison-Posts kommen in ihrem Zeitfenster dran, Stories gibt es dann keine.
Log: der letzte Eintrag pro Schlüssel zählt. "kontrolle" listet, was laut Log veröffentlicht sein müsste. Feed-Posts,
die Metricool auf keinem Netzwerk veröffentlicht hat ("gescheitert", "fehlt"), plant der nächste "plan" neu ein, nach
einer Limit-Meldung erst im nächsten Monat; teilweise gescheiterte Posts und Stories nennt er unter "Nicht eingeplant".
Die geplante Aufgabe in Claude Code arbeitet posting/ANLEITUNG.md ab und ruft dieses Skript auf.

Aufruf:
  python3 tools/posting.py plan                  Plan ab morgen neu bauen: posting/plan.json und <Firma>/tagesplan.md
  python3 tools/posting.py vorrat                Reichweite des Plans und Posts, die auf eine Freigabe warten
  python3 tools/posting.py faellig --kurz        offene Aufträge der nächsten Tage als Übersicht
  python3 tools/posting.py faellig --datum D     fertige Metricool-Aufträge für einen Tag (JSON)
  python3 tools/posting.py bilder                Bilder der offenen Aufträge öffentlich bereitstellen und Links prüfen
                                                 (mit bild_url nur prüfen, sonst ins öffentliche Bilder-Repo kopieren)
  python3 tools/posting.py eintragen ZEILE ...   Ergebnisse ins Log; ZEILE = schluessel;status;metricool_id;bemerkung,
                                                 "-" liest die Zeilen von stdin
  python3 tools/posting.py kontrolle             Posts bis gestern, die laut Log in Metricool liegen, zum Abgleich (JSON):
                                                 eintragen mit Status veroeffentlicht oder gescheitert
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
from collections import Counter, defaultdict
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

DONE = {"geplant", "entwurf", "manuell", "freigabe", "veroeffentlicht"}  # liegt schon in Metricool, nicht neu anlegen
CHECKABLE = {"geplant", "manuell", "freigabe"}        # "kontrolle" prüft, ob Metricool sie veröffentlicht hat
CHECKED_STATUS = {"veroeffentlicht", "gescheitert", "fehlt"}  # Ergebnis der Kontrolle
FAILED = {"gescheitert", "fehlt"}                     # nicht veröffentlicht: der Post kommt wieder in den Plan
LIMIT_HIT = re.compile(r"account limit", re.I)         # Metricool: "You have reached your Metricool account limit."
MAX_ERRORS = 2                                        # danach lässt die Aufgabe den Auftrag liegen
STORY_GAP = 3                                         # Tage zwischen Stories, die nicht zu einem Feed-Post gehören
URGENT_DAYS = 10                                      # Saison-Posts gehen vor, wenn ihr Zeitfenster bald endet
MAX_PRO_TAG = 3                                       # mit Frist ("bis") höchstens so viele Feed-Posts pro Tag
FEED_ZEIT_EXTRA = {"werktags": ["17:30", "12:00"],    # Uhrzeiten für den 2. und 3. Feed-Post eines Tages
                   "wochenende": ["15:30", "14:00"]}  # (nicht 13:00: Story-Zeit von Bad & Energie und Tezgel)
STORY_NETWORKS = ("instagram", "facebook")
STICKER_NETWORKS = ("instagram",)                     # Sticker gibt es nur in Instagram-Stories
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
POST_ID = re.compile(r"\b[A-Z]{2}-\d{3}\b")
STICKER = re.compile(r"sticker|umfrage|quiz|countdown", re.I)
PHONE = re.compile(r"\b0\d{2,4}\s*[/-]?\s*\d[\d -]{3,}\d")
NO_GBP = re.compile(r"\bDMs?\b|kommentar|kommentier", re.I)  # Google-Profile haben weder Kommentare noch Chat

# Saisonale Posts: (frühestens, spätestens) für Tage außerhalb ihres README-Termins. Schlüssel: ID bzw. Karussell.
ZEITFENSTER = {
    "CD-076": ("2026-12-01", "2026-12-31"),  # PHP 8.2 nach Silvester: laut prompts.md vor dem 31.12. posten
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
    if s.get("bild_url"):  # Bilder direkt aus einem öffentlichen Repo verlinken, ohne Kopie ins Bilder-Repo
        return s["bild_url"].format(pfad=image_file(key, entry_id, story).relative_to(ROOT).as_posix())
    return f"https://raw.githubusercontent.com/{s['bild_repo']}/main/{image_target(key, entry_id, story)}"


def read_log():
    if not LOG.exists():
        return []
    with LOG.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def state(log):
    """Stand pro Schlüssel: der letzte Eintrag zählt (geplant → veroeffentlicht oder gescheitert → neu geplant)."""
    return {r["schluessel"]: r for r in log}


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


def skips_gmb(e):
    """Google lehnt Telefonnummern im Text ab; DMs und Kommentare gibt es dort nicht."""
    caption = (e["caption"] or e["headline"] or e["title"]).strip()
    return bool(PHONE.search(caption) or NO_GBP.search(caption))


def feed_networks(s, cfg, p, entries):
    """Netzwerke, auf denen ein Feed-Post wirklich erscheint (wie request()): jedes zählt fürs Monatslimit."""
    return [n for n in networks_for(s, cfg, {"art": "feed", "sticker": False})
            if n != "gmb" or not skips_gmb(entries[p["ids"][0]])]


def month_of(d):
    return d.strftime("%Y-%m")


def clock_for(cfg, art, when):
    """Uhrzeit eines Posts: story_zeit, feed_zeit (werktags/wochenende) oder feed_zeit_extra für feed2/feed3."""
    kind = "wochenende" if when.weekday() >= 5 else "werktags"
    if art == "story":
        return cfg["story_zeit"]
    slot = slot_of(art)
    return cfg["feed_zeit"][kind] if not slot else cfg.get("feed_zeit_extra", FEED_ZEIT_EXTRA)[kind][slot - 1]


def posting_days(year, month, n):
    """n Posting-Tage, gleichmäßig über den Kalendermonat verteilt: jeweils die Mitte eines n-tel des Monats.

    Hängt nur vom Monat ab, nicht vom Tag des Laufs; so bleiben die Tage von Lauf zu Lauf dieselben."""
    first = dt.date(year, month, 1)
    length = (dt.date(year + month // 12, month % 12 + 1, 1) - first).days
    return [first + dt.timedelta(days=int((i + 0.5) * length / n)) for i in range(n)]


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


def rotate(posts, recent=()):
    """Kategorien abwechseln, innerhalb einer Kategorie in ID-Reihenfolge.

    recent: Kategorien der schon eingeplanten Feed-Posts in Datumsfolge. Der Wechsel geht dort weiter, wo er
    aufgehört hat: zuerst Kategorien, die noch nicht dran waren, dann die am längsten nicht mehr benutzten.
    """
    groups = {}
    for p in posts:
        groups.setdefault(p["kategorie"], []).append(p)
    last = {c: i for i, c in enumerate(recent)}
    order = sorted(groups, key=lambda c: (c in last, last.get(c, 0)))
    out = []
    while any(groups.values()):
        for c in order:
            if groups[c]:
                out.append(groups[c].pop(0))
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


def pick(pool, when, allowed):
    """Post für einen Posting-Tag mit Monatslimit (wenige Tage im Monat): Saison-Posts gehen vor, sobald ihr Zeitfenster
    offen ist, nach dem frühesten Fensterende; so kommen sie zu ihrer Zeit und möglichst keiner verfällt. Sonst der
    nächste im Wechsel der Kategorien. Wählt nur aus, pool bleibt unverändert."""
    open_now = [p for p in pool if (not p["fenster"] or window(p)[0] <= when) and allowed(p)]
    seasonal = [p for p in open_now if p["fenster"]]
    if seasonal:
        return min(seasonal, key=lambda p: window(p)[1])
    return open_now[0] if open_now else None


def row(p, when, nr, source, held, art=None):
    return {"datum": when.isoformat(), "art": art or p["art"], "post": p["post"], "nr": nr, "typ": p["typ"],
            "ids": p["ids"], "titel": p["titel"], "sticker": p["sticker"], "quelle": source,
            "wartet": [i for i in p["ids"] if i in held]}


def is_feed(art):
    """Feed-Post des Tages ("feed") oder weiterer Feed-Post am selben Tag ("feed2", "feed3")."""
    return art.startswith("feed")


def feed_art(slot):
    return "feed" if slot == 0 else f"feed{slot + 1}"


def slot_of(art):
    return int(art[4:]) - 1 if art[4:] else 0


def extra_counts(days, cap, needed, scheduled, origin, deadline):
    """Zusatz-Posts (2. und 3. Feed-Post) pro Tag, gleichmäßig über die Spanne von origin bis zur Frist.

    scheduled Zusatz-Posts liegen schon in Metricool und zählen für das Muster mit; origin ist der Tag des ersten davon,
    sonst morgen. So bleibt das Muster von Tag zu Tag gleich, statt beim täglichen Neubau nach hinten zu rutschen.
    Was an Kapazitätsgrenzen (cap) hängen bleibt, wird möglichst früh nachgeholt."""
    out = {d: 0 for d in days}
    if needed <= 0 or not days:
        return out
    total, span, placed = scheduled + needed, (deadline - origin).days + 1, 0
    for d in days:
        want = -(-(total * ((d - origin).days + 1)) // span) - scheduled  # aufgerundet, kumulativ bis d
        k = max(0, min(want - placed, cap[d], needed - placed))
        out[d] += k
        placed += k
    for d in days:
        k = max(0, min(cap[d] - out[d], needed - placed))
        out[d] += k
        placed += k
    return out


def log_facts(key, log):
    """Stand pro Schlüssel einer Firma, Fehler beim Anlegen in Folge, Fehlschläge beim Veröffentlichen (ohne die am
    Monatslimit) und die Monate, in denen Metricool das Limit gemeldet hat."""
    current = {k: r for k, r in state(log).items() if k.split("|")[0] == key}
    streak, broken, limit_hit = Counter(), Counter(), set()
    for r in log:
        k = r["schluessel"]
        if k.split("|")[0] != key:
            continue
        streak[k] = streak[k] + 1 if r["status"] == "fehler" else 0
        if r["status"] in FAILED and LIMIT_HIT.search(r["bemerkung"] or ""):
            limit_hit.add(r["datum"][:7])
        elif r["status"] in FAILED:
            broken[k] += 1
    return current, streak, broken, limit_hit


def build_plan(key, s, today, log, held, previous=None, previous_today=None):
    feed, stories = posts_of(key)
    by_id = {e["id"]: e for e in entries_of(key)}
    start = max(day(s["start"]), today + dt.timedelta(days=1))
    horizon = today + dt.timedelta(days=s["vorlauf_tage"])
    soon = today + dt.timedelta(days=1)  # morgen: ist beim nächsten Lauf schon heute
    monday = day(s["readme_plan_ab"])  # Woche 1 im README-Plan; bleibt fest, auch wenn der Start sich verschiebt
    cfg = s["firmen"][key]
    budget = cfg.get("max_pro_monat")  # Veröffentlichungen pro Kalendermonat, jedes Netzwerk zählt
    no_stories = bool(budget) or cfg.get("stories", "an") == "aus"
    deadline = day(cfg["bis"]) if cfg.get("bis") and not budget else None  # alle Feed-Posts bis zu diesem Tag
    if deadline and deadline < start:
        deadline = None  # Frist vorbei: wieder ein Feed-Post pro Tag
    extra_times = cfg.get("feed_zeit_extra", FEED_ZEIT_EXTRA)
    most = min(cfg.get("max_pro_tag", MAX_PRO_TAG), 1 + min(len(t) for t in extra_times.values()))
    if deadline:
        for kind in ("werktags", "wochenende"):
            clocks = [cfg["feed_zeit"][kind], cfg["story_zeit"]] + extra_times[kind][:most - 1]
            if len(set(clocks)) < len(clocks):
                sys.exit(f"Fehler: {key}: Uhrzeiten in feed_zeit, story_zeit und feed_zeit_extra ({kind}) "
                         f"überschneiden sich: {clocks}. posting/einstellungen.json korrigieren.")

    def waits(p):
        return any(i in held for i in p["ids"])

    def allowed_on(when):
        # Wartende Posts nie in den Vorlauf legen, sonst bliebe der Tag leer
        return lambda p: when > horizon or not any(i in held for i in p["ids"])

    # Was schon in Metricool liegt, behält seinen Tag. Ganz gescheiterte Posts kommen wieder in den Wechsel; ist ein Post
    # auf einem Netzwerk gescheitert und auf einem anderen draußen, bleibt er (Hinweis unter "Nicht eingeplant")
    pinned, rows, feed_taken, story_taken, notes = {}, [], set(), set(), []
    spent = Counter()  # Veröffentlichungen je Monat, die schon in Metricool liegen oder veröffentlicht sind
    current, streak, broken, limit_hit = log_facts(key, log)
    nets_of = defaultdict(dict)
    for k, r in current.items():
        firma, art, post, nr, net = k.split("|")
        nets_of[(art, post, int(nr))][net] = r["status"]
        if r["status"] in DONE and r["datum"]:
            when = day(r["datum"])
            pinned[(art, post, int(nr))] = max(when, pinned.get((art, post, int(nr)), when))
            spent[r["datum"][:7]] += 1
    for (art, post, nr), nets in nets_of.items():
        failed, ok = sorted(n for n, st in nets.items() if st in FAILED), sorted(n for n, st in nets.items() if st in DONE)
        if failed and ok:
            p = (feed if is_feed(art) else stories).get(post)
            notes.append({"post": post, "titel": p["titel"] if p else post,
                          "grund": f"auf {', '.join(failed)} nicht veröffentlicht, auf {', '.join(ok)} schon: "
                                   "nicht neu eingeplant"})
    for (art, post, nr), when in sorted(pinned.items(), key=lambda kv: kv[1]):
        (feed_taken if is_feed(art) else story_taken).add(when)
        p = (feed if is_feed(art) else stories).get(post)
        if p:
            rows.append(row(p, when, nr, "metricool", held, art))
    pinned_feed = {(post, nr) for (art, post, nr) in pinned if is_feed(art)}

    # Termine aus dem README, soweit noch offen
    fixed, seen = {}, Counter()
    for (week, col), (pid, cell) in sorted(readme_plan(key).items()):
        when = monday + dt.timedelta(days=7 * (week - 1) + 2 * col)
        if pid is None:
            if when >= start:
                notes.append({"post": cell.split("]")[0].lstrip("["), "titel": cell.split(") ", 1)[-1],
                              "grund": "eigenes Foto nötig" if budget else
                              f"eigenes Foto nötig, Termin {when.isoformat()} ging an einen anderen Post"})
            continue
        if pid == "frei":
            if when >= start and when not in feed_taken:
                fixed[when] = None
            continue
        if pid not in feed or feed[pid]["sperre"]:
            continue
        seen[pid] += 1
        if (pid, seen[pid]) in pinned_feed or when < start or when in feed_taken \
                or not allowed_on(when)(feed[pid]):
            continue  # vorbei, belegt oder wartet: der Post kommt (falls noch offen) in den Rest
        if deadline and (waits(feed[pid]) or when > deadline):
            continue  # mit Frist: wartende Posts blockieren keinen Termin, späte Termine rücken vor die Frist
        fixed[when] = (pid, seen[pid])
    if budget:
        fixed = {}  # mit Monatslimit passt der Rhythmus aus dem README (Mo/Mi/Fr) nicht: eigene Posting-Tage

    first_done = {post for (post, nr) in pinned_feed if nr == 1}
    first_done |= {v[0] for v in fixed.values() if v and v[1] == 1}
    recent = [feed[post]["kategorie"] for (art, post, nr), when in sorted(pinned.items(), key=lambda kv: kv[1])
              if is_feed(art) and post in feed]
    pool = rotate([p for pid, p in feed.items() if not p["sperre"] and pid not in first_done], recent)
    for p in list(pool):
        # Lässt sich nicht anlegen (Fehler in Folge) oder wird nicht veröffentlicht (ohne Limit-Meldung): Platz für andere
        keys = [f"{key}|feed|{p['post']}|1|{n}" for n in feed_networks(s, cfg, p, by_id)]
        keys = [k for k in keys if not (k in current and current[k]["status"] in DONE)]
        if keys and all(streak[k] >= MAX_ERRORS or broken[k] >= MAX_ERRORS for k in keys):
            pool.remove(p)
            notes.append({"post": p["post"], "titel": p["titel"],
                          "grund": "zweimal gescheitert (beim Anlegen oder Veröffentlichen), nicht neu eingeplant"})
    lost = []
    if deadline:
        # Alle freigegebenen Posts bis zur Frist, notfalls mehrere am Tag; wartende und spätere danach wie üblich
        days = [start + dt.timedelta(days=k) for k in range((deadline - start).days + 1)]
        days = [d for d in days if not (d in fixed and fixed[d] is None)]  # Pausen aus dem README bleiben frei
        used = defaultdict(set)  # belegte Slots je Tag
        for r in rows:
            if is_feed(r["art"]):
                used[day(r["datum"])].add(slot_of(r["art"]))
        for d in [d for d in fixed if fixed[d] and start <= d <= deadline]:
            pid, nr = fixed.pop(d)
            rows.append(row(feed[pid], d, nr, "plan", held))
            used[d].add(0)
        # Was schon im Vorlauf stand, behält Tag und Slot: Sonst könnte ein angelegter, aber noch nicht eingetragener
        # Post beim nächsten Lauf an einem anderen Tag ein zweites Mal angelegt werden
        in_pool = {p["post"]: p for p in pool}
        for r in previous or []:
            d, p = day(r["datum"]), in_pool.get(r["post"])
            if p and is_feed(r["art"]) and start <= d <= min(horizon, deadline) and not waits(p) \
                    and slot_of(r["art"]) < most and slot_of(r["art"]) not in used[d] \
                    and (not p["fenster"] or window(p)[0] <= d <= window(p)[1]):
                rows.append(row(p, d, r["nr"], r["quelle"], held, r["art"]))
                used[d].add(slot_of(r["art"]))
                pool.remove(p)
                del in_pool[p["post"]]
        ready = [p for p in pool if not waits(p)]
        need = sum(1 for p in ready if not p["fenster"] or window(p)[0] <= deadline)
        # Zusatz-Posts frühestens übermorgen: Bräche ein Lauf nach dem Anlegen eines Posts für morgen ab, sähe der
        # nächste Lauf (dann ist morgen heute) ihn nicht mehr und legte ihn an einem anderen Tag noch einmal an
        cap = {d: 0 if d <= soon else most - max(len(used[d]), 1) for d in days}
        done = sorted(day(r["datum"]) for r in rows if is_feed(r["art"]) and slot_of(r["art"]) and day(r["datum"]) <= deadline)
        extras = extra_counts(days, cap, need - sum(1 for d in days if not used[d]), len(done),
                              done[0] if done else max(start, soon + dt.timedelta(days=1)), deadline)

        def put(p, d):
            slot = min(set(range(most)) - used[d])
            rows.append(row(p, d, 1, "auffueller", held, feed_art(slot)))
            used[d].add(slot)
            ready.remove(p)
            pool.remove(p)

        for d in days:
            for p in expire(ready, d):
                pool.remove(p)
                lost.append(p)
            for _ in range((0 if used[d] else 1) + extras[d]):
                pid = take(list(ready), d, lambda q: True)  # take() wählt aus einer Kopie, put() trägt aus
                if not pid:
                    break
                put(next(q for q in ready if q["post"] == pid), d)
        for p in [p for p in ready if p["fenster"] and window(p)[0] <= deadline]:
            # Spätes Zeitfenster, für das das Muster keinen Platz ließ: frühester Tag im Fenster mit freiem Slot
            d = next((d for d in days if window(p)[0] <= d <= window(p)[1] and len(used[d]) < most
                      and (d > soon or not used[d])), None)
            if d:
                put(p, d)
        feed_taken |= {d for d in days if used[d]}
    if budget:
        # Monatslimit: pro Monat so viele Posting-Tage, wie volle Posts (alle Netzwerke) ins Limit passen
        cost = {pid: len(feed_networks(s, cfg, p, by_id)) for pid, p in feed.items()}
        per_post = len(networks_for(s, cfg, {"art": "feed", "sticker": False}))
        for (art, post, nr), when in pinned.items():
            if is_feed(art) and post in feed and when >= start:
                # Netzwerke, die due() bei schon angelegten Posts noch ergänzt (zum Beispiel nach neuen "netzwerke")
                spent[month_of(when)] += sum(1 for n in feed_networks(s, cfg, feed[post], by_id)
                                             if current.get(f"{key}|{art}|{post}|{nr}|{n}", {}).get("status") not in DONE
                                             and streak[f"{key}|{art}|{post}|{nr}|{n}"] < MAX_ERRORS)
        for month in limit_hit:
            spent[month] = max(spent[month], budget)  # Metricool meldet das Limit: in diesem Monat nichts mehr anlegen
        # Was der letzte Lauf schon anlegen konnte, behält seinen Tag (wie mit Frist): Sonst könnte ein angelegter, aber
        # noch nicht eingetragener Post beim nächsten Lauf an einem anderen Tag ein zweites Mal angelegt werden.
        # Neue Posts frühestens übermorgen: Einen Post für morgen sähe der nächste Lauf nach einem Abbruch nicht mehr.
        reach = previous_today + dt.timedelta(days=s["vorlauf_tage"]) if previous_today else horizon
        before = {day(r["datum"]): r["post"] for r in previous or []
                  if r["art"] == "feed" and start <= day(r["datum"]) <= min(horizon, reach)}
        slots, (y, m) = [], (start.year, start.month)
        while per_post and budget // per_post and dt.date(y, m, 1) <= start + dt.timedelta(days=400):
            free = [d for d in posting_days(y, m, budget // per_post)
                    if d not in feed_taken and (d > soon or (d >= start and d in before))]
            slots += free[:max(0, budget - spent[f"{y:04d}-{m:02d}"]) // per_post]
            y, m = y + m // 12, m % 12 + 1
        for when in slots:
            lost += expire(pool, when)
            p = next((q for q in pool if q["post"] == before.get(when) and allowed_on(when)(q)
                      and (not q["fenster"] or window(q)[0] <= when)), None)
            if not p and when > soon:
                p = pick(pool, when, allowed_on(when))
            if p and spent[month_of(when)] + cost[p["post"]] <= budget:
                pool.remove(p)
                spent[month_of(when)] += cost[p["post"]]
                rows.append(row(p, when, 1, "auffueller", held))
        notes += [{"post": p["post"], "titel": p["titel"], "grund": "Monatslimit: im Planungszeitraum kein Posting-Tag frei"}
                  for p in pool]
    when, last = start, max(list(fixed) + [start])
    while not budget and (pool or when <= last) and when <= start + dt.timedelta(days=400):
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
    story_pool = []
    if no_stories:  # mit Monatslimit gehen alle Veröffentlichungen an Feed-Posts
        reason = "Stories aus" if cfg.get("stories") == "aus" else "Monatslimit: nur Feed-Posts"
        notes += [{"post": p["post"], "titel": p["titel"], "grund": reason} for p in stories.values()
                  if not p["sperre"] and ("story", p["post"], 1) not in pinned]
    else:
        first_day, post_of = {}, {i: p["post"] for p in feed.values() for i in p["ids"]}
        for r in sorted(rows, key=lambda r: r["datum"]):
            if is_feed(r["art"]):
                first_day.setdefault(r["post"], day(r["datum"]))
        kept = {}  # mit Frist: Stories aus dem Vorlauf behalten ihren Tag (wie die Feed-Posts, siehe oben)
        for r in previous or [] if deadline else []:
            p, d = stories.get(r["post"]), day(r["datum"])
            if p and r["art"] == "story" and ("story", p["post"], 1) not in pinned and p["post"] not in kept \
                    and start <= d <= horizon and d not in story_taken and not waits(p) and not p["sperre"] \
                    and not (p["sticker"] and s.get("sticker_stories", "manuell") == "aus") \
                    and (not p["fenster"] or window(p)[0] <= d <= window(p)[1]):
                kept[p["post"]] = d
                story_taken.add(d)
                rows.append(row(p, d, 1, r["quelle"], held))
        story_pool = []
        for p in stories.values():
            if p["sperre"] or ("story", p["post"], 1) in pinned or p["post"] in kept:
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
        feed_days = [day(r["datum"]) for r in rows if is_feed(r["art"])]
        end = max(feed_days + ([deadline] if deadline else [])) if feed_days or deadline else start
        # Der Abstand gilt auch zu Stories, die schon in Metricool liegen (außer Story-Versionen am Tag ihres Feed-Posts),
        # und zwar zur vorigen wie zur nächsten
        pinned_fill = {when for (art, post, nr), when in pinned.items() if art == "story" and post in stories
                       and first_day.get(post_of.get(stories[post]["eltern"])) != when}
        pinned_fill |= {d for post, d in kept.items() if first_day.get(post_of.get(stories[post]["eltern"])) != d}

        candidates = list(story_pool)

        def fill_stories(gap):
            trial, taken, placed, gone = list(candidates), set(story_taken), [], []
            # Mit Frist neue Auffüller-Stories frühestens übermorgen (wie bei den Zusatz-Posts, siehe oben)
            first = max(start, soon + dt.timedelta(days=1)) if deadline else start
            when, previous = first, max((d for d in pinned_fill if d < first), default=None)
            while trial and when <= end:
                gone += expire(trial, when)
                nxt = min((d for d in pinned_fill if d > when), default=None)
                if when in pinned_fill:
                    previous = when
                elif when not in taken and (previous is None or (when - previous).days >= gap) \
                        and (nxt is None or (nxt - when).days >= gap):
                    pid = take(trial, when, allowed_on(when))
                    if pid:
                        taken.add(when)
                        placed.append((when, pid))
                        previous = when
                when += dt.timedelta(days=1)
            return placed, trial, gone

        # Mit Frist rücken Stories enger zusammen, wenn sonst freigegebene Stories erst nach der Frist kämen
        must = {p["post"] for p in candidates if deadline and not waits(p)
                and (not p["fenster"] or window(p)[0] <= deadline and window(p)[1] >= start)}
        for gap in range(STORY_GAP, 0 if deadline else STORY_GAP - 1, -1):
            placed, story_pool, gone = fill_stories(gap)
            if not deadline or must <= {pid for d, pid in placed if d <= deadline}:
                break
        for when, pid in placed:
            story_taken.add(when)
            rows.append(row(stories[pid], when, 1, "auffueller", held))
        lost += gone

    # Wartende Posts, deren Zeitfenster noch offen ist, sind nicht verpasst: Eine Freigabe hilft noch
    still = [p for p in lost + story_pool if waits(p) and (not p["fenster"] or window(p)[1] >= start)]
    blocked = [{"post": p["post"], "titel": p["titel"], "grund": p["sperre"]}
               for p in list(feed.values()) + list(stories.values()) if p["sperre"]]
    lost = [{"post": p["post"], "titel": p["titel"], "grund": f"Zeitfenster bis {p['fenster'][1]} verpasst"}
            for p in lost if p not in still]
    left = [{"post": p["post"], "titel": p["titel"], "grund": "kein freier Story-Tag mehr"}
            for p in story_pool if p not in still]
    entries = sorted(rows, key=lambda r: (r["datum"], not is_feed(r["art"]), r["art"]))

    def belongs_before_deadline(r):
        p = feed[r["post"]] if is_feed(r["art"]) else stories[r["post"]]
        return not r["wartet"] and (not p["fenster"] or window(p)[0] <= deadline)

    late = [{"post": r["post"], "datum": r["datum"]} for r in entries
            if deadline and day(r["datum"]) > deadline and belongs_before_deadline(r)]
    return {"eintraege": entries, "nicht_eingeplant": blocked + notes + lost + left,
            "monatslimit": limit_info(key, s, entries, log, today),
            "wartet_ohne_termin": [{"post": p["post"], "titel": p["titel"], "ids": [i for i in p["ids"] if i in held],
                                    "bis": p["fenster"][1] if p["fenster"] else None} for p in still],
            "nach_frist": late}


def md_cell(text):
    return " ".join((text or "").split()).replace("|", "\\|")


def write_md(key, s, fp, today, held):
    c = bib.COMPANIES[key]
    entries = {e["id"]: e for e in entries_of(key)}
    days = {}
    for r in fp["eintraege"]:
        if day(r["datum"]) > today:
            slot = days.setdefault(r["datum"], {"feed": []})
            if is_feed(r["art"]):
                slot["feed"].append(r)
            else:
                slot[r["art"]] = r

    def link(i):
        return f"[{i}](prompts.md#{i.lower()})"

    def flags(r):
        return (" ⚠️" if r["wartet"] else "") + (" ✋" if r["sticker"] else "") + (" (Wiederholung)" if r["nr"] > 1 else "")

    cfg = s["firmen"][key]
    bis, budget = cfg.get("bis"), cfg.get("max_pro_monat")
    if budget:
        per_post = len(networks_for(s, cfg, {"art": "feed", "sticker": False})) or 1
        rhythm = (f"höchstens {budget} Veröffentlichungen pro Monat (Limit von Metricool, jedes Netzwerk zählt), "
                  f"also etwa {budget // per_post} Feed-Posts im Monat, gleichmäßig verteilt, ohne Stories")
    elif bis:
        rhythm = (f"pro Tag ein Feed-Post, bis {day(bis).strftime('%d.%m.%Y')} alle freigegebenen Posts und dafür an "
                  "manchen Tagen mehrere")
    else:
        rhythm = "ein Feed-Post pro Tag"
    if not budget:
        rhythm += ", ohne Stories" if cfg.get("stories", "an") == "aus" else ", dazu Stories"
    lines = [f"# Tagesplan {c['name']}", "",
             f"Stand {today.strftime('%d.%m.%Y')}: {rhythm}. Die geplante Aufgabe in Claude Code "
             "baut den Plan jeden Morgen neu und stellt die Posts eine Woche im Voraus in Metricool ein, siehe "
             "[posting/README.md](../posting/README.md).", "",
             "⚠️ Wartet auf Freigabe (Gründe unten): Der Termin ist vorläufig. Der Post geht erst raus, wenn seine ID in "
             "`posting/geprueft.txt` steht, und rückt bis dahin jeden Tag nach.  ",
             "✋ Story mit Sticker (Umfrage, Quiz, Link): Metricool erinnert in der App, der Sticker kommt von Hand dazu.", "",
             "| Datum | Feed-Post | Text | Story |", "| --- | --- | --- | --- |"]
    for d in sorted(days):
        feeds, st = sorted(days[d]["feed"], key=lambda r: r["art"]), days[d].get("story")
        for n, f in enumerate(feeds or [None]):
            label = f"{WEEKDAYS[day(d).weekday()]} {day(d).strftime('%d.%m.%Y')}" + (f" ({n + 1}. Post)" if n else "")
            feed_cell = text_cell = story_cell = ""
            if f:
                first = f["ids"][0]
                extra = f" (Karussell, {len(f['ids'])} Bilder)" if f["typ"] == "karussell" else ""
                feed_cell = (f'<img src="bilder/facebook-linkedin-4x5/{first}.jpg" width="90"><br>'
                             f"{link(first)} {md_cell(f['titel'])}{extra}{flags(f)}")
                text_cell = md_cell(entries[first]["caption"])
            if st and not n:
                story_cell = f"{link(st['ids'][0])} {md_cell(st['titel'])}{flags(st)}"
            lines.append(f"| {label} | {feed_cell} | {text_cell} | {story_cell} |")
    waiting = {i for r in fp["eintraege"] if day(r["datum"]) > today for i in r["wartet"]}
    no_date = {i: w for w in fp.get("wartet_ohne_termin", []) for i in w["ids"] if i in held}
    lines += ["", "## Wartet auf Freigabe", "", "Zum Freigeben die ID in `posting/geprueft.txt` eintragen.", "",
              "| ID | Grund |", "| --- | --- |"]
    lines += [f"| {link(i)} | {md_cell(' / '.join(held[i]))}" +
              (f" (noch ohne Termin{', Zeitfenster bis ' + no_date[i]['bis'] if no_date[i]['bis'] else ''})"
               if i in no_date and i not in waiting else "") + " |" for i in sorted(waiting | set(no_date))]
    if limit_text(fp.get("monatslimit")):
        lines += ["", "## Monatslimit", "", limit_text(fp["monatslimit"]) + "."]
    if fp.get("nach_frist"):
        lines += ["", "## Nach der Frist", "", f"Für diese freigegebenen Posts war bis {s['firmen'][key].get('bis')} "
                  "kein Platz mehr:", ""] + [f"- {x['post']} am {x['datum']}" for x in fp["nach_frist"]]
    lines += ["", "## Nicht eingeplant", "", "| Post | Titel | Grund |", "| --- | --- | --- |"]
    lines += [f"| {n['post']} | {md_cell(n['titel'])} | {md_cell(n['grund'])} |" for n in fp["nicht_eingeplant"]]
    (ROOT / c["folder"] / "tagesplan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def limit_info(key, s, rows, log, today):
    """Monatslimit ab dem laufenden Monat: veröffentlicht, in Metricool (noch nicht veröffentlicht) und noch nicht in
    Metricool (geplante Netzwerke ab morgen), jeweils Veröffentlichungen; dazu, ob Metricool das Limit gemeldet hat."""
    cfg = s["firmen"][key]
    if not cfg.get("max_pro_monat"):
        return {}
    current, streak, broken, limit_hit = log_facts(key, log)
    by_id = {e["id"]: e for e in entries_of(key)}
    feed = posts_of(key)[0]
    first = today.replace(day=1).isoformat()
    months = {}

    def slot(month):
        return months.setdefault(month, {"veroeffentlicht": 0, "in_metricool": 0, "neu": 0,
                                         "limit_gemeldet": month in limit_hit})
    for k, r in current.items():
        if r["datum"] >= first and r["status"] in DONE:
            slot(r["datum"][:7])["veroeffentlicht" if r["status"] == "veroeffentlicht" else "in_metricool"] += 1
    for r in rows:
        if is_feed(r["art"]) and day(r["datum"]) > today and r["post"] in feed:
            for n in feed_networks(s, cfg, feed[r["post"]], by_id):
                k = f"{key}|{r['art']}|{r['post']}|{r['nr']}|{n}"
                if current.get(k, {}).get("status") not in DONE and streak[k] < MAX_ERRORS:
                    slot(r["datum"][:7])["neu"] += 1
    return {"max": cfg["max_pro_monat"], "monate": dict(sorted(months.items()))}


def limit_text(lim):
    """Monatslimit in einer Zeile, mit Warnung, wenn mehr in Metricool liegt, als veröffentlicht werden kann."""
    parts = []
    for month, v in (lim or {}).get("monate", {}).items():
        total = v["veroeffentlicht"] + v["in_metricool"] + v["neu"]
        warn = []
        if v["limit_gemeldet"]:
            warn.append("Metricool meldet das Limit als erreicht, in diesem Monat geht nichts mehr raus")
        if total > lim["max"]:
            warn.append(f"{total - lim['max']} mehr als das Limit, die gehen nicht raus")
        parts.append(f"{month}: {v['veroeffentlicht']} veröffentlicht, {v['in_metricool']} in Metricool, {v['neu']} noch "
                     "nicht in Metricool" + (f" (Achtung: {'; '.join(warn)})" if warn else ""))
    return f"Monatslimit {lim['max']} Veröffentlichungen: " + "; ".join(parts) if parts else ""


def cmd_plan(s, today):
    log, held = read_log(), holds(s)
    old_plan = load_json(PLAN) if PLAN.exists() else {}
    old, old_today = old_plan.get("firmen", {}), old_plan.get("heute")
    plan = {"start": s["start"], "heute": today.isoformat(), "firmen": {}}
    for key in bib.COMPANIES:
        fp = plan["firmen"][key] = build_plan(key, s, today, log, held, old.get(key, {}).get("eintraege"),
                                              day(old_today) if old_today else None)
        write_md(key, s, fp, today, held)
        feed = [r for r in fp["eintraege"] if is_feed(r["art"]) and day(r["datum"]) > today]
        waiting = sum(1 for r in fp["eintraege"] if r["wartet"] and day(r["datum"]) > today)
        reasons = Counter(n["grund"].split(":")[0].split(",")[0] for n in fp["nicht_eingeplant"])
        span = f"von {feed[0]['datum']} bis {feed[-1]['datum']}" if feed else "keine"
        multi = len({r["datum"] for r in feed if r["art"] != "feed"})
        print(f"{key}: {len(feed)} Feed-Posts {span}" + (f" ({multi} Tage mit mehreren)" if multi else "") +
              f", davon {waiting} Posts mit Wartegrund; nicht eingeplant: {dict(reasons)}")
        if fp.get("nach_frist"):
            print(f"  Achtung, Frist {s['firmen'][key]['bis']} verpasst (zu wenig Platz): " +
                  ", ".join(f"{x['post']} am {x['datum']}" for x in fp["nach_frist"]))
        if limit_text(fp.get("monatslimit")):
            print(f"  {limit_text(fp['monatslimit'])}")
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
        if skips_gmb(e):
            return None
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
    clock = clock_for(cfg, r["art"], day(r["datum"]))
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
    current = state(log)
    done = {k for k, r in current.items() if r["status"] in DONE}
    errors = Counter()  # Fehler beim Anlegen seit dem letzten anderen Eintrag
    for r in log:
        errors[r["schluessel"]] = errors[r["schluessel"]] + 1 if r["status"] == "fehler" else 0
    # Monatslimit als zweite Sicherung neben dem Plan: nie mehr anlegen, als Metricool im Monat veröffentlicht
    spent = Counter((k.split("|")[0], r["datum"][:7]) for k, r in current.items() if r["status"] in DONE)
    for r in log:  # Metricool hat das Limit gemeldet: in diesem Monat nichts mehr anlegen
        if r["status"] in FAILED and LIMIT_HIT.search(r["bemerkung"] or ""):
            firma = r["schluessel"].split("|")[0]
            spent[(firma, r["datum"][:7])] = max(spent[(firma, r["datum"][:7])],
                                                 s["firmen"].get(firma, {}).get("max_pro_monat") or 0)
    tz = ZoneInfo(s["zeitzone"])
    first, last = today + dt.timedelta(days=1), today + dt.timedelta(days=s["vorlauf_tage"])
    out, given_up, waiting, over = [], [], [], []
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
                if req and cfg.get("max_pro_monat") and spent[(key, r["datum"][:7])] >= cfg["max_pro_monat"]:
                    over.append(k)
                elif req:
                    spent[(key, r["datum"][:7])] += 1
                    out.append({"schluessel": k, **req})
    return out, given_up, waiting, over


def cmd_faellig(s, today, args):
    reqs, given_up, waiting, over = due(s, today, day(args.datum) if args.datum else None)
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
    if over:
        print("Über dem Monatslimit (wird nicht angelegt): " + ", ".join(over))


def cmd_vorrat(s, today):
    """Reichweite, Wartende, Monatslimit (frisch aus dem Log) und was die Kontrolle in den letzten 24 Stunden als
    nicht veröffentlicht eingetragen hat, mit neuem Termin oder Grund."""
    plan, held, log = load_json(PLAN), holds(s), read_log()
    recent = (dt.datetime.now() - dt.timedelta(hours=24)).isoformat(timespec="seconds")
    for key, fp in plan["firmen"].items():
        rest = [r for r in fp["eintraege"] if day(r["datum"]) > today]
        feed = [r for r in rest if is_feed(r["art"])]
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
        for w in fp.get("wartet_ohne_termin", []):
            ids = [i for i in w["ids"] if i in held]
            if ids:
                print(f"  wartet: {w['post']} (noch ohne Termin" + (f", Zeitfenster bis {w['bis']}" if w["bis"] else "") +
                      "): " + " / ".join(held[ids[0]])[:240])
        if fp.get("nach_frist"):
            print(f"  Achtung, Frist {s['firmen'][key].get('bis')} verpasst (zu wenig Platz): " +
                  ", ".join(f"{x['post']} am {x['datum']}" for x in fp["nach_frist"]))
        lim = limit_info(key, s, fp["eintraege"], log, today)
        if limit_text(lim):
            print(f"  {limit_text(lim)}")
        failed = {}
        for k, r in state(log).items():
            if k.startswith(key + "|") and r["status"] in FAILED and r["zeit"] >= recent:
                f = failed.setdefault((k.split("|")[1], k.split("|")[2]), {"datum": r["datum"], "netze": [], "status": set()})
                f["netze"].append(k.split("|")[4])
                f["status"].add(r["status"])
        for (art, post), f in sorted(failed.items(), key=lambda kv: kv[1]["datum"]):
            new = [r["datum"] for r in fp["eintraege"] if r["post"] == post and is_feed(r["art"]) == is_feed(art)
                   and day(r["datum"]) > today and r["quelle"] != "metricool"]
            why = next((n["grund"] for n in fp["nicht_eingeplant"] if n["post"] == post), "")
            print(f"  {'/'.join(sorted(f['status']))}: {post} ({f['datum']}, {', '.join(sorted(f['netze']))}): " +
                  (f"neu eingeplant am {new[0]}" if new else f"nicht neu eingeplant{' (' + why + ')' if why else ''}"))


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
    direct = bool(s.get("bild_url"))  # Bilder liegen schon öffentlich: nur die Links prüfen, nichts kopieren
    repo = Path(os.path.expanduser(s["bild_repo_ordner"]))
    if not direct and not (repo / ".git").exists():
        sys.exit(f"Bilder-Repo fehlt: {repo}. Einrichtung siehe posting/README.md.")
    files = {}
    for r in due(s, today)[0]:
        for i in r["ids"]:
            story = r["art"] == "story"
            files[image_url(s, r["firma"], i, story)] = (image_file(r["firma"], i, story),
                                                         repo / image_target(r["firma"], i, story))
    copied = 0
    if not direct:
        git(repo, "pull", "-q", "--rebase")
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
    version = str(int(time.time())) if direct else git(repo, "rev-parse", "--short", "HEAD", capture=True)
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
    current = state(read_log())
    now = dt.datetime.now().isoformat(timespec="seconds")
    rows, bad, seen = [], [], set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("schluessel;"):
            continue
        k, status, mid, note = [x.strip() for x in (line.split(";", 3) + ["", "", ""])[:4]]
        before = current.get(k)
        if k in seen:
            bad.append(f"Schlüssel doppelt: {line}")
        elif status in CHECKED_STATUS:
            # Ergebnis der Kontrolle: nur für Posts, die laut Log in Metricool liegen, mit deren Tag und Post-ID
            if not before or before["status"] not in CHECKABLE:
                bad.append(f"laut Log nicht (mehr) zu prüfen: {line}")
            elif mid and before["metricool_id"] and mid != before["metricool_id"]:
                bad.append(f"Post-ID passt nicht zum Log ({before['metricool_id']}): {line}")
            else:
                rows.append([now, k, before["datum"], status, mid or before["metricool_id"], " ".join(note.split())])
        elif k not in dates:
            bad.append(f"unbekannter Schlüssel: {line}")
        elif status not in (DONE - CHECKED_STATUS) | {"fehler"}:
            bad.append(f"unbekannter Status: {line}")
        elif status != "fehler" and not mid:
            bad.append(f"Post-ID fehlt: {line}")
        else:
            rows.append([now, k, dates[k], status, mid, " ".join(note.split())])
        seen.add(k)
    if bad:
        sys.exit("Nichts eingetragen, bitte korrigieren:\n" + "\n".join(bad))
    new = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as fh:
        out = csv.writer(fh, delimiter=";")
        if new:
            out.writerow(LOG_FIELDS)
        out.writerows(rows)
    print(f"{len(rows)} Einträge ins Log geschrieben.")


def cmd_kontrolle(s, today):
    """Posts bis gestern, die laut Log in Metricool liegen: wurden sie wirklich veröffentlicht?"""
    tz = ZoneInfo(s["zeitzone"])
    posts = sorted(({"schluessel": k, "metricool_id": r["metricool_id"], "datum": r["datum"],
                     "uhrzeit": clock_for(s["firmen"][k.split("|")[0]], k.split("|")[1], day(r["datum"])),
                     "netzwerk": k.split("|")[4], "status_im_log": r["status"]}
                    for k, r in state(read_log()).items()
                    if r["status"] in CHECKABLE and r["datum"] and day(r["datum"]) < today
                    and k.split("|")[0] in s["firmen"]),
                   key=lambda p: (p["datum"], p["uhrzeit"], p["schluessel"]))
    brands = []
    for key in sorted({p["schluessel"].split("|")[0] for p in posts}):
        cfg = s["firmen"].get(key, {})
        dates = sorted({day(p["datum"]) for p in posts if p["schluessel"].startswith(key + "|")})
        while cfg.get("blogId") and dates:  # höchstens 7 Tage pro Abfrage, damit die Antwort handlich bleibt
            chunk = [d for d in dates if d < dates[0] + dt.timedelta(days=7)]
            dates = dates[len(chunk):]
            midnight = dt.datetime.combine(chunk[0], dt.time(0, 0), tzinfo=tz)
            end = dt.datetime.combine(chunk[-1], dt.time(23, 59, 59), tzinfo=tz)
            brands.append({"firma": key, "blogId": cfg["blogId"], "fromDate": midnight.isoformat(),
                           "toDate": end.isoformat(), "timezone": s["zeitzone"]})
    print(json.dumps({"bis": (today - dt.timedelta(days=1)).isoformat(), "marken_fuer_getScheduledPosts": brands,
                      "posts": posts}, ensure_ascii=False, indent=1))


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
    sub.add_parser("kontrolle")
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
    elif args.cmd == "kontrolle":
        cmd_kontrolle(s, today)


if __name__ == "__main__":
    main()
