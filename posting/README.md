# Tägliches Posten über Metricool

Claude Code plant jeden Morgen die Posts der nächsten 7 Tage in Metricool ein: pro Firma und Tag ein Feed-Post auf allen
verbundenen Netzwerken, dazu Stories. Metricool veröffentlicht sie zur geplanten Zeit.

| Datei | Inhalt |
| --- | --- |
| [einstellungen.json](einstellungen.json) | Start, Uhrzeiten, Netzwerke, Links, Modus und Metricool-Marke pro Firma, zurückgehaltene Posts |
| [plan.json](plan.json) | Tagesplan aller Firmen |
| Tagesplan pro Firma | [Coday](../Coday/tagesplan.md) · [Bad & Energie](../Bad-und-Energie/tagesplan.md) · [Tezgel](../Tezgel/tagesplan.md): Bild und Text pro Tag, dazu alle Posts, die auf eine Freigabe warten |
| [geprueft.txt](geprueft.txt) | freigegebene Posts |
| [log.csv](log.csv) | was schon in Metricool liegt (schreibt die Aufgabe) |
| [ANLEITUNG.md](ANLEITUNG.md) | Ablauf der täglichen Aufgabe |

## Was die Automation macht

- **Termine:** Die Termine aus dem Posting-Plan im README jeder Firma bleiben (Mo/Mi/Fr ab 2.11.2026). Die übrigen Tage
  füllen die restlichen Posts im Wechsel der Themen. Saisonale Posts (Advent, Weihnachten, Jahreswechsel, Förderfristen)
  laufen nur in ihrem Zeitfenster. Am 25.12. pausieren Bad & Energie und Tezgel, wie im Plan vorgesehen.
- **Täglich neu geplant:** Die Aufgabe baut den Plan jeden Morgen neu. Was schon in Metricool liegt, behält seinen Tag;
  Posts von Tagen, an denen nichts rausging (zum Beispiel weil die Netzwerke noch nicht verbunden waren), rücken nach.
- **Freigaben:** Posts mit Faktencheck (⚠️ in `prompts.md`), mit einer offenen Frage in [offene-fragen.md](../offene-fragen.md)
  oder in `zurueckhalten` gehen erst raus, wenn ihre ID in `geprueft.txt` steht. Bis dahin rücken sie nach, und andere
  Posts füllen die Tage. Was zu prüfen ist, steht im Tagesplan unter „Wartet auf Freigabe“.
- **Texte pro Netzwerk:** Instagram mit allen Hashtags und „Link in Bio“. Facebook, LinkedIn und Threads mit dem Link
  selbst, inklusive UTM-Parametern, damit die Website-Statistik zeigt, woher Besucher kommen. Google-Unternehmensprofil
  ohne Hashtags; Posts mit Telefonnummer, DM- oder Kommentar-Aufruf lässt es aus. X und Bluesky: Headline, ein Satz, Link.
- **KI-Kennzeichnung:** Instagram-Posts tragen das KI-Label (`ki_kennzeichnung`).
- **Stories mit Sticker** (Umfrage, Quiz, Link): nur Instagram, weil sich Sticker nicht automatisch setzen lassen.
  Metricool erinnert zur geplanten Zeit in der App; Sticker und „KI-Info“ kommen von Hand dazu. Mit
  `"sticker_stories": "aus"` fallen sie weg.
- **Gesperrt:** CD-001 bis CD-016 und die Coday-Karussells K1 und K2, deren Cover aus Arena stammt. Arena erlaubt
  Werbung nur mit schriftlicher Zustimmung.
- **Bilder:** Metricool lädt Bilder nur über öffentliche Links und speichert sie beim Einplanen bei sich. Zurzeit
  verlinkt die Aufgabe die Bilder direkt aus diesem Repo, das dafür öffentlich ist (`bild_url`); damit sind auch
  Prompts und Notizen öffentlich. Soll es wieder privat sein: das öffentliche Repo
  [Marketing-Bilder](https://github.com/umutcantezgel-cpu/Marketing-Bilder) anlegen und `bild_url` löschen. Dann kopiert
  die Aufgabe jeweils die Bilder der nächsten 7 Tage dorthin, und alles andere bleibt privat.

## Einstellungen

- `modus` pro Firma: `direkt` (Standard), `entwurf` (alles nur als Entwurf) oder `freigabe` (Freigabe in Metricool, braucht
  einen Plan mit Team-Funktion; dazu `freigabe_mails` und `freigabe_art`: `optional` = geht raus, wenn niemand
  widerspricht, `any` = braucht eine Zustimmung).
- `netzwerke`: wohin gepostet wird, sofern das Netzwerk in Metricool verbunden ist. Pro Firma überschreibbar.
- `zurueckhalten`: weitere Posts, die erst nach einer Freigabe rausgehen, mit Grund.
- `bis` pro Firma (optional): Frist, bis zu der alle freigegebenen Feed-Posts draußen sein sollen. Reichen die Tage nicht,
  bekommen so viele Tage wie nötig einen zweiten oder dritten Feed-Post, gleichmäßig verteilt; die Uhrzeiten dafür stehen
  in `feed_zeit_extra`, höchstens `max_pro_tag` (Standard 3) Feed-Posts pro Tag. Wartende Posts belegen dabei keinen Tag:
  Gibt man sie frei, verdichtet der nächste Lauf den Plan. Posts, deren Zeitfenster erst nach der Frist beginnt (zum
  Beispiel Januar-Posts), kommen danach. Zurzeit bei Coday: `2026-12-31`.
- `bild_url` (optional): Bilder direkt aus einem öffentlichen Repo verlinken, statt sie nach Marketing-Bilder zu
  kopieren; `{pfad}` ist der Pfad der Bilddatei in diesem Repo, zum Beispiel `Coday/bilder/story-9x16/CD-028.jpg`.
  Zurzeit zeigt es auf das öffentliche Repo Marketing. Wird Marketing wieder privat: `bild_url` löschen, dann gilt
  wieder Marketing-Bilder (`bild_repo`, `bild_repo_ordner`).
- Neue Posts im Repo nimmt die Aufgabe beim nächsten Lauf von selbst in den Plan auf.

## Einrichtung

Voraussetzung: In Metricool hat jede Firma eine eigene Marke mit verbundenen Netzwerken (Instagram, Facebook usw.),
benannt wie `metricool_marke`: „Coday“, „Bad & Energie“ und „Tezgel“. Dann findet die tägliche Aufgabe die Marken auch
selbst, falls sie erst nach der Einrichtung verbunden werden. Keine Marke ohne Netzwerk stehen lassen: Für so eine Marke
meldet Metricool einen Fehler, und bei einem Fehler lässt die Aufgabe den Tag aus.

Dann eine neue Claude-Code-Sitzung starten:

- **Ordner:** den Benutzerordner (`~`), nicht „ohne Ordner“. Die geplante Aufgabe läuft später in dem Ordner, in dem sie
  angelegt wurde. Ohne Ordner legt die App einen an, der nur zu dieser Sitzung gehört und mit ihr gelöscht wird. Im
  Benutzerordner liegen außerdem beide Repos (`~/Marketing` und `~/Marketing-Bilder`).
- **Modus:** Auto, damit die tägliche Aufgabe ohne Rückfragen läuft. Der Metricool-Connector muss eingeschaltet sein.

Diesen Prompt einfügen:

```text
Richte das tägliche Social-Media-Posting für Coday, Bad & Energie und Tezgel ein. Arbeite selbstständig und frag nur, wenn du ohne meine Antwort nicht weiterkommst.

1. Repo: Klone https://github.com/umutcantezgel-cpu/Marketing nach ~/Marketing (liegt es schon dort: git pull --rebase --autostash). Fehlen danach posting/ANLEITUNG.md oder tools/posting.py: abbrechen und Bescheid sagen. Lies posting/README.md und posting/ANLEITUNG.md.
2. Bilder-Repo: Metricool lädt Bilder nur über öffentliche Links. Lege deshalb mit gh das öffentliche Repo umutcantezgel-cpu/Marketing-Bilder an, falls es noch fehlt, mit einer README „Bilder für geplante Social-Media-Posts von Coday, Bad & Energie und Tezgel“. Klone es nach ~/Marketing-Bilder.
3. Metricool: Rufe getBrandSettings auf. Schlag mir vor, welche Marke zu welcher Firma gehört, und trag blogId und metricool_marke erst nach meinem OK in posting/einstellungen.json ein. Jede Marke gehört zu höchstens einer Firma. Meldet Metricool einen Fehler oder fehlen Marken oder Netzwerke, sag mir genau, was ich in Metricool verbinden muss, und mach mit den übrigen Schritten weiter.
4. Probelauf: python3 ~/Marketing/tools/posting.py plan, danach vorrat und faellig --kurz. Zeig mir kurz, was in den nächsten 7 Tagen rausgeht und welche Posts auf eine Freigabe warten.
5. Geplante Aufgabe: Lege mit create_scheduled_task die Aufgabe „social-media-tagesposting“ an, Titel „Social Media: Posts einplanen“, täglich um 6:30 Uhr (cronExpression „30 6 * * *“), mit diesem Prompt:
   „Tägliche Aufgabe für Coday, Bad & Energie und Tezgel: die Posts der nächsten 7 Tage in Metricool einplanen. Du darfst ohne Rückfrage die Befehle aus ~/Marketing/posting/ANLEITUNG.md ausführen, in ~/Marketing und ~/Marketing-Bilder committen und pushen und im Metricool-Connector getBrandSettings, getScheduledPosts, createScheduledPost und createScheduledPostForReview aufrufen. Verboten: Metricool-Posts ändern, löschen, zur Freigabe schicken oder bewerben; Texte oder Bilder ändern; git reset, checkout oder Force-Push. Frag nie nach: Fehlt etwas, lass den Teil aus und melde ihn. Führe GIT_TERMINAL_PROMPT=0 git -C ~/Marketing pull --rebase --autostash aus, arbeite dann ~/Marketing/posting/ANLEITUNG.md Schritt für Schritt ab und schreib am Ende den Bericht aus der Anleitung.“
   Prüf im Ergebnis, ob die Aufgabe ohne Rückfragen laufen darf (Auto-Modus), und sag mir Bescheid, falls nicht.
6. Arbeite posting/ANLEITUNG.md jetzt einmal komplett ab und zeig mir den Bericht.
```

Danach in derselben Sitzung schreiben: „Starte die Aufgabe jetzt einmal zum Test und sag mir, ob sie durchläuft.“ Der
Testlauf läuft wie die Läufe am Morgen, mit denselben Rechten. So zeigt sich sofort, ob die Aufgabe Metricool erreicht
und ohne Rückfragen durchkommt. Die Sitzung danach behalten: Nach jedem Lauf meldet sich die Aufgabe dort.

Geplante Aufgaben laufen, solange die Claude-App geöffnet ist. War sie zur geplanten Zeit zu, läuft die Aufgabe beim
nächsten Start nach. Weil Metricool immer eine Woche im Voraus gefüllt ist, fällt ein ausgelassener Tag nicht auf.
