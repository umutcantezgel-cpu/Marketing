# Marketing-Bilder: Coday · Bad & Energie · Tezgel

Bildprompts, Captions und fertige Social-Media-Bilder für Instagram, Facebook und LinkedIn.
Modell: GPT Image 2.5, Variante Sunburst.

**Stand 01.11.2026:** 379 fertige Bilder, alle mit Caption und Hashtags.

| Firma | Prompts | Bilder | davon Feed (3:4, plus 4:5-Zuschnitt) | davon Stories (9:16) |
| --- | --- | --- | --- | --- |
| Coday | 127 | 127 | 109 | 18 |
| Bad & Energie | 126 | 126 | 107 | 19 |
| Tezgel | 126 | 126 | 109 | 17 |

| Ordner | Firma | Inhalt |
| --- | --- | --- |
| [Coday/](Coday/) | Coday, Webagentur Wetzlar | [Prompts](Coday/prompts.md) · [Captions (CSV)](Coday/captions.csv) · [Bilder](Coday/bilder/) |
| [Bad-und-Energie/](Bad-und-Energie/) | Bad & Energie GmbH Lahn-Dill | [Prompts](Bad-und-Energie/prompts.md) · [Captions (CSV)](Bad-und-Energie/captions.csv) · [Bilder](Bad-und-Energie/bilder/) |
| [Tezgel/](Tezgel/) | Fliesenverlegung Tezgel, Aßlar | [Prompts](Tezgel/prompts.md) · [Captions (CSV)](Tezgel/captions.csv) · [Bilder](Tezgel/bilder/) |

## So entsteht ein Bild

1. Prompt aus `<Firma>/prompts.md` kopieren. Jeder Prompt ist komplett: Brand-Block mit Farben und Format, Szene, Text im Bild.
2. In Arena (Direct Mode, `gpt-image-2.5-sunburst`) oder in ChatGPT einfügen und senden.
3. Text im Bild Wort für Wort prüfen. Bei Fehlern im selben Chat:
   `Edit: Change only the headline text to exactly "…". Keep everything else identical.`
4. Bild herunterladen (landet in `~/Downloads`).
5. Im Repo-Ordner einsortieren und hochladen:

   ```bash
   python3 tools/einsortieren.py --push
   ```

   Das Skript liest den Text im Bild (macOS-Texterkennung), findet den passenden Prompt, legt das Bild als
   `<ID>.jpg` ab, erzeugt alle Formate und lädt alles zu GitHub hoch. Bilder ohne Text oder mit unsicherer
   Zuordnung landen in `unsortiert/` (nicht im Repo).

Karussell-Slides ab Nr. 2: vorher die fertige Cover-Slide hochladen, dann den Prompt senden.

## Formate pro Firma

| Ordner | Größe | Wofür |
| --- | --- | --- |
| `bilder/original/` | volle Auflösung (Higgsfield 2K: 1744 × 2336), JPEG | Archiv, Anzeigen, spätere Bearbeitung |
| `bilder/instagram-3x4/` | 1080 × 1440 | Instagram-Feed (füllt Feed und Profilraster) |
| `bilder/facebook-linkedin-4x5/` | 1080 × 1350 | Facebook- und LinkedIn-Feed (Mitte des 3:4-Bildes, Text liegt im Sicherheitsrand) |
| `bilder/story-9x16/` | 1080 × 1920 | Instagram- und Facebook-Story |

`bilder/generiert.json` hält pro Bild fest, woher es stammt: Arena (von Hand) oder Higgsfield mit Modell,
Qualität, Auflösung und Job-ID. Fast alle Bilder stammen von GPT Image 2.5 Sunburst über Higgsfield
(Prompts aus den Dokumenten in 2K, neue Prompts in 1K).

## Markenfarben in den Prompts

Ausgelesen am 31.10.2026 von den Websites und Logos.

| Firma | Farben |
| --- | --- |
| Coday | Hintergrund Navy `#0B1220`, Off-White `#F5F5F2`, Akzent Türkis `#14B8A6` (Primärfarbe auf codayweb.de, Buttons `#147A7A`). Alternative wäre das Website-Amber `#F59E0B`. |
| Bad & Energie | Blau `#111D6D` und Rot `#D60000` (Website-Theme, passend zum Logo), Text `#222222` |
| Tezgel | Zinkgrau `#F4F4F5`, Anthrazit `#27272A`, Akzent Laser-Rot `#D82020` (tezgel.de) |

Firmenname und Logo stehen bewusst nicht in den Prompts, damit das Modell keinen falschen Schriftzug malt.
Die Ecke unten rechts bleibt frei: Dort kommt das echte Logo hin.

## Vor dem Posten

Die Checkliste mit allen offenen Fragen pro Firma steht in [offene-fragen.md](offene-fragen.md).

- **Nutzungsrechte Arena:** Laut Arena-Nutzungsbedingungen (Stand 23.02.2026) ist Output für Werbung ohne
  schriftliche Zustimmung untersagt (§ 3.5 G), ebenso die kommerzielle Verwertung (§ 5 i). Für Werbung also
  entweder eine schriftliche Freigabe von Arena einholen oder das Bild mit demselben Prompt in ChatGPT
  (oder bei einem bezahlten Bild-Dienst) neu erzeugen.
- **Fakten:** Einträge mit ⚠️ in `prompts.md` enthalten Zahlen, Fristen, Förderung oder Sicherheitsfakten.
  Vor dem Posten mit dem angegebenen Stand abgleichen.
- **KI-Kennzeichnung:** C2PA-Metadaten nicht entfernen. Bei fotorealistischen Motiven „Symbolbild“ bzw.
  „KI-generiertes Symbolbild“ in die Caption. Bei Anzeigen das KI-Label selbst setzen.
- **Freigaben:** Bad & Energie (Geschäftsführung) und Tezgel (Deniz Tezgel) geben Motive und Texte frei.
  Echte Kundenprojekte nur mit Zustimmung der Kunden zeigen.

## Werkzeuge

| Datei | Zweck |
| --- | --- |
| `tools/bibliothek.py` | Brand-Blocks, setzt die Prompts zusammen, baut `prompts.md` und `captions.csv`, exportiert Formate |
| `tools/einsortieren.py` | Downloads per Texterkennung zuordnen, Formate erzeugen, optional pushen |
| `tools/ocr.swift` | Texterkennung mit Apples Vision-Framework (wird beim ersten Lauf kompiliert) |

```bash
python3 tools/bibliothek.py build        # prompts.md und captions.csv neu bauen
python3 tools/bibliothek.py prompt TZ-002 # einen fertigen Prompt anzeigen
```
