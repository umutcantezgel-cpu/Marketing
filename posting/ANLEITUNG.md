# Tägliche Aufgabe: Posts in Metricool einplanen

Die geplante Aufgabe „Social Media: Posts einplanen“ arbeitet diese Anleitung jeden Morgen in Claude Code ab.
Ziel: Metricool hat für jede Firma die nächsten 7 Tage eingeplant, auf allen verbundenen Netzwerken: pro Tag ein
Feed-Post, dazu Stories, mit Monatslimit (`max_pro_monat`, Coday) nur so viele Feed-Posts, wie Metricool im Monat
veröffentlicht. Und was laut Log draußen sein müsste, ist wirklich veröffentlicht. Das Skript liefert jeden Auftrag
fertig; du rufst Metricool auf und trägst sofort ins Log ein.

## Regeln

- Ohne Rückfrage erlaubt: die Befehle dieser Anleitung, `git pull`, `commit` und `push` in `~/Marketing` und
  `~/Marketing-Bilder`, in Metricool `getBrandSettings`, `getScheduledPosts`, `createScheduledPost` und
  `createScheduledPostForReview`.
- Verboten: Posts in Metricool ändern, löschen, zur Freigabe schicken oder bewerben (`boost`); Texte oder Bilder ändern;
  `git reset`, `git checkout` oder `git restore` auf `posting/`, `git stash drop`, Force-Push.
- Nie nachfragen. Fehlt etwas oder schlägt etwas fehl: den betroffenen Teil auslassen und im Bericht melden.
- Pfade immer absolut (`git -C ~/Marketing …`, `python3 ~/Marketing/tools/posting.py …`), vor git-Befehlen
  `GIT_TERMINAL_PROMPT=0`.
- Zeilen mit einer Meldung (Metricool-Texte enthalten oft Apostrophe) nie in einfache Anführungszeichen setzen, sondern
  über stdin eintragen, eine Zeile pro Post, die Meldung ohne Zeilenumbruch:

  ```bash
  python3 ~/Marketing/tools/posting.py eintragen - <<'EOF'
  SCHLUESSEL;STATUS;POST-ID;MELDUNG
  EOF
  ```

## Ablauf

1. Aktualisieren: `GIT_TERMINAL_PROMPT=0 git -C ~/Marketing pull --rebase --autostash`. Schlägt das fehl: aufhören,
   Bericht.
2. Kontrolle: `python3 ~/Marketing/tools/posting.py kontrolle` listet unter `posts` die Posts bis gestern, die laut Log
   in Metricool liegen. Sind `posts` und `verwaist` leer: weiter mit Schritt 3. Sonst für jeden Eintrag aus
   `marken_fuer_getScheduledPosts` einmal `getScheduledPosts` mit brandId (= blogId), fromDate, toDate und timezone von
   dort aufrufen und jeden Post aus `posts` über seine `metricool_id` suchen (bei Metricool `id`). Findet sich die ID
   nicht, gilt ein Post mit demselben Netzwerk, demselben Datum und derselben Uhrzeit (`uhrzeit`,
   `publicationDate.dateTime`); dann die POST-ID in der Zeile leer lassen. Je nach Status des Netzwerks
   (`providers[].status`):
   - `PUBLISHED`: `SCHLUESSEL;veroeffentlicht;POST-ID;`
   - `ERROR`: `SCHLUESSEL;gescheitert;POST-ID;MELDUNG`, MELDUNG wörtlich aus `detailedStatus`
   - gar nicht gefunden, obwohl die Abfrage für dieses Datum ohne Fehler zurückkam (zum Beispiel in Metricool gelöscht):
     `SCHLUESSEL;fehlt;POST-ID;in Metricool nicht gefunden`
   - anderer Status (zum Beispiel noch `PENDING`): nichts eintragen, im Bericht melden; morgen wird wieder geprüft

   Dazu `verwaist`: Posts aus dem Plan des vorigen Laufs bis heute, die nicht im Log stehen (ein Lauf brach vielleicht
   zwischen Anlegen und Eintragen ab). Hat Metricool einen Post mit demselben Netzwerk, Datum und derselben Uhrzeit:
   `SCHLUESSEL;STATUS;POST-ID;` mit STATUS aus `status_bei_fund`; sonst nichts eintragen. Verwaiste Posts nie anlegen.

   Alle Zeilen in einem Aufruf über stdin eintragen (siehe Regeln). Ganz gescheiterte oder fehlende Feed-Posts plant
   Schritt 3 neu ein, mit Meldung „account limit“ erst im nächsten Monat. Schlägt `getScheduledPosts` fehl: Kontrolle
   auslassen und melden.
3. Plan auffrischen: `python3 ~/Marketing/tools/posting.py plan`. Was schon in Metricool liegt, behält seinen Tag.
4. Marken: Metricool `getBrandSettings`.
   - Kommt ein Fehler zurück (zum Beispiel „keine Netzwerke verbunden“): Fehlermeldung und die Ausgabe von
     `python3 ~/Marketing/tools/posting.py vorrat` berichten, mit Schritt 8 speichern, fertig.
   - Für jede Firma die Marke suchen, deren Name genau `metricool_marke` in `~/Marketing/posting/einstellungen.json`
     entspricht. Fehlt dort die `blogId` und passt genau eine Marke, ihre blogId eintragen. Eine blogId nie aus einer
     Fehlermeldung übernehmen, nie zwei Firmen dieselbe Marke geben, `metricool_marke` nie ändern. Passt keine Marke:
     die Firma heute auslassen und melden.
   - Die verbundenen Netzwerke jeder Marke notieren.
5. Überblick: `python3 ~/Marketing/tools/posting.py faellig --kurz`. Sind keine Aufträge offen: weiter mit Schritt 8.
   Aufträge „über dem Monatslimit“ legt das Skript nicht an; sie gehören in den Bericht.
6. Bilder: `python3 ~/Marketing/tools/posting.py bilder`. Meldet es nicht erreichbare Links, die Aufträge mit diesen
   Bildern heute auslassen.
7. Einplanen, höchstens die ersten drei Daten mit offenen Aufträgen, die sich heute anlegen lassen (Firma mit blogId,
   Netzwerk bei der Marke verbunden; der Rest folgt morgen), ein Datum nach dem anderen:
   1. `python3 ~/Marketing/tools/posting.py faellig --datum JJJJ-MM-TT` liefert `marken_fuer_getScheduledPosts` und
      `auftraege`.
   2. Für jede Marke aus `marken_fuer_getScheduledPosts` einmal `getScheduledPosts` mit brandId (= blogId), fromDate,
      toDate und timezone von dort. Hat Metricool schon einen Post mit demselben Netzwerk und derselben Uhrzeit
      (`info.publicationDate.dateTime`) wie ein Auftrag: nicht neu anlegen, sondern mit der ID von dort als `geplant`
      eintragen (wie in Schritt 4 dieser Liste).
   3. Für jeden übrigen Auftrag, dessen Netzwerk bei der Marke verbunden ist, das Werkzeug aus `werkzeug` aufrufen:
      `blogId`, `date` und `info` aus dem Auftrag, `info` unverändert als JSON-Text; bei `createScheduledPostForReview`
      zusätzlich `reviewers` und `approvalSystem`.
   4. Gleich danach eintragen, einzeln: `python3 ~/Marketing/tools/posting.py eintragen 'SCHLUESSEL;STATUS;POST-ID;'`
      mit dem Schlüssel aus dem Auftrag und STATUS aus `status_bei_erfolg`.
   5. Bei einem Fehler: erst mit `getScheduledPosts` prüfen, ob der Post doch angelegt wurde (dann wie in 2.), sonst
      einmal wiederholen. Scheitert der Post selbst (zum Beispiel Text zu lang, Bild abgelehnt): die Zeile
      `SCHLUESSEL;fehler;;kurze Meldung` über stdin eintragen (siehe Regeln). Trifft derselbe Fehler mehrere Aufträge nacheinander oder alle
      Aufträge einer Marke oder eines Netzwerks (Verbindung abgelaufen, Limit, Störung): dort aufhören, nichts als
      `fehler` eintragen, einmal melden.
   6. Nach jedem Datum speichern (Schritt 8).
8. Speichern: `git -C ~/Marketing add posting Coday/tagesplan.md Bad-und-Energie/tagesplan.md Tezgel/tagesplan.md`,
   committen mit „Posting: Stand JJJJ-MM-TT“, falls sich etwas geändert hat, und pushen. Wird der Push abgelehnt:
   `pull --rebase --autostash`, dann erneut pushen.
9. Bericht auf Deutsch, kurz:
   - veröffentlicht laut Kontrolle: Datum, Firma, Post-ID, Netzwerke
   - nicht veröffentlicht laut Kontrolle: die Zeilen „gescheitert“ und „fehlt“ aus
     `python3 ~/Marketing/tools/posting.py vorrat` (mit neuem Termin oder dem Grund, warum nicht), dazu die Meldung von
     Metricool und Posts mit anderem Status
   - neu eingeplant: Datum, Firma, Post-ID, Netzwerke
   - Stories zum Fertigstellen in der Metricool-App (Status `manuell`): Sticker setzen und in Instagram „KI-Info“
     einschalten
   - wartet auf Freigabe: die Zeilen „wartet“ aus `python3 ~/Marketing/tools/posting.py vorrat`, mit dem Hinweis, dass
     die ID zum Freigeben in `posting/geprueft.txt` gehört
   - übersprungene Marken oder Netzwerke, aufgegebene Aufträge und alle Fehler
   - Vorrat pro Firma; Warnung, wenn er unter 14 Tagen liegt
   - Monatslimit: die Zeile „Monatslimit“ aus `vorrat`; steht darin „Achtung“, das deutlich melden
