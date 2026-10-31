# Coday: Social-Media-Bilder

Coday, Webagentur in Wetzlar. Captions in Du-Form, Haupt-CTA: kostenloser Website-Check.

- [prompts.md](prompts.md): 80 Bildprompts zum Kopieren (80 aus dem Prompt-Arsenal, 0 neu), davon 75 Feed-Posts (3:4) und 5 Stories (9:16)
- [captions.csv](captions.csv): Caption, Hashtags und Hinweise je Bild (Semikolon-getrennt, öffnet in Excel und Numbers)
- [uploads-noetig.md](uploads-noetig.md): 5 Edit-Prompts für eigene Fotos, Screenshots oder das Logo
- [bilder/](bilder/): fertige Bilder in allen Formaten

## Brand-Block

Steht in jedem Prompt schon drin. Für eigene neue Prompts: Block + Szene + `Headline: "…"`.

```text
Brand style for a one-person web agency in Wetzlar, Germany. Premium, calm, technical-editorial look. Palette: deep near-black navy background (#0B1220), off-white (#F5F5F2), single accent colour teal (#14B8A6), thin grey hairlines. Typography: bold modern geometric sans-serif headline, left-aligned, generous whitespace, max two text sizes, high contrast. Imagery: clean minimal 3D objects or minimal photoreal scenes, soft studio light, subtle grain, no clutter. Layout: vertical 3:4 portrait format (1080x1440 proportions); keep all text and key objects inside the centre with an 8% safe margin on every edge; keep the bottom-right corner (12% of width) empty and clean for a logo added later. Do not draw any logo. Text rules: render ONLY the German text given in quotes, exactly once, verbatim, with correct umlauts (ä, ö, ü, ß); no other words, no fake UI text, no watermarks, no third-party logos or brand names, no real or recognisable people.
```

Story-Variante: statt `vertical 3:4 portrait format (1080x1440 proportions)` steht `vertical 9:16 format (1080x1920 proportions); keep the top 14% and bottom 20% free of text`.

## Hashtag-Sets

| Set | Hashtags |
| --- | --- |
| L lokal | #wetzlar #mittelhessen #lahndill #giessen #webdesignwetzlar |
| S Security | #websitesicherheit #phpsicherheit #wordpresssicherheit #itsicherheit #kmu |
| G GEO/SEO | #geo #kisichtbarkeit #lokaleseo #googleranking #chatgpt |
| W Webdesign | #webdesign #nextjs #webentwicklung #websiterelaunch #selbststaendig |

## Posting-Plan: 10 Wochen ab 2.11.2026

3 Feed-Posts pro Woche (Mo/Mi/Fr, 7:30 oder 18:00 Uhr) plus 3–5 Stories. Jede Woche ein Karussell. Mix: etwa 35 % Security-Funnel, 20 % Leistungen/GEO, 20 % Branchen, 15 % Wissen, 10 % Lokal/BTS/Humor.

| Woche | Mo | Mi | Fr |
| --- | --- | --- | --- |
| 1 | [CD-001](prompts.md#cd-001) PHP-Lücke: sachlicher Aufhänger | K1 PHP-Version prüfen (CD-005 + CD-029–033) | [CD-003](prompts.md#cd-003) Kostenloser Website-Check (Haupt-CTA) |
| 2 | [CD-002](prompts.md#cd-002) WordPress-Update reicht nicht | [CD-014](prompts.md#cd-014) Ein Ansprechpartner | [CD-016](prompts.md#cd-016) Gastro |
| 3 | [CD-004](prompts.md#cd-004) PHP 8.2 Support-Ende | K2 GEO in 5 Slides (CD-011 + CD-034–038) | [CD-018](prompts.md#cd-018) Schlüsseldienst |
| 4 | [CD-008](prompts.md#cd-008) Migration WordPress → Next.js | [CD-026](prompts.md#cd-026) Meme: Plugin-Update | [CD-017](prompts.md#cd-017) Handwerk |
| 5 | [CD-009](prompts.md#cd-009) Wartung | K3 5 Website-Mythen (CD-024 + CD-039–043) | [CD-022](prompts.md#cd-022) Lokal |
| 6 | [CD-013](prompts.md#cd-013) Festpreis | [CD-U01](uploads-noetig.md) Edit: Laptop-Mockup mit eigenem Screenshot (eigenes Foto) | [CD-019](prompts.md#cd-019) Friseur |
| 7 | [CD-010](prompts.md#cd-010) GEO-Hook | [CD-023](prompts.md#cd-023) Vorher/Nachher (Konzept) | [CD-021](prompts.md#cd-021) Kanzlei/Praxis |
| 8 | [CD-007](prompts.md#cd-007) Ich prüfe. Du entscheidest. | [CD-025](prompts.md#cd-025) 3D begehbar | [CD-020](prompts.md#cd-020) Boutique |
| 9 | [CD-012](prompts.md#cd-012) Ladezeit | [CD-027](prompts.md#cd-027) Behind the Scenes | [CD-U02](uploads-noetig.md) Edit: Smartphone-Mockup Referenz (eigenes Foto) |
| 10 | [CD-004](prompts.md#cd-004) PHP 8.2 Support-Ende | [CD-015](prompts.md#cd-015) Quellcode-Übergabe | [CD-003](prompts.md#cd-003) Kostenloser Website-Check (Haupt-CTA) |

Vor jedem Post mit ⚠️ (siehe prompts.md) Fakten und Stand prüfen. Läuft ein Post deutlich besser, zwei Varianten davon erzeugen und in die nächsten Wochen setzen.
