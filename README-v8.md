# RSV Kalender Version 8

## Enthalten

- 1. Herren – Regionalliga Nordost
- 2. Herren (U23) – Kreisoberliga Havelland
- 3. Herren (U21) – Kreisliga
- drei separat abonnierbare ICS-Kalender
- mobile Startseite mit den Bereichen **Kalender** und **Spieltage & Tabellen**
- absolvierte Ligaspiele chronologisch ab dem 1. Spieltag
- kompakte Ergebniszeile mit aufklappbaren Details
- Torfolge, Spielort, Zuschauer, Schiedsrichter, OSTSPORT und Spielbericht, sofern in den Daten vorhanden
- eigene Tabelle je Mannschaft, sobald offizielle Tabellenzeilen in `data/tables.json` vorliegen

## Installation

Den gesamten Inhalt dieses ZIPs in das Stammverzeichnis des GitHub-Repositories hochladen und vorhandene Dateien ersetzen. Danach committen und unter **Actions → RSV-Kalender aktualisieren → Run workflow** starten. Netlify veröffentlicht weiterhin den Ordner `docs`.

## URLs

- Startseite: `https://rsv-kalender.netlify.app/`
- 1. Herren: `https://rsv-kalender.netlify.app/rsv-regionalliga.ics`
- U23: `https://rsv-kalender.netlify.app/rsv-u23.ics`
- U21: `https://rsv-kalender.netlify.app/rsv-u21.ics`

## Datenhinweis

Die U23-Konfiguration ist separat angelegt. Da noch keine belastbare Mannschaftsspielplan-URL im Projekt vorlag, enthält `data/u23.json` bewusst keine erfundenen Termine. Sobald eine offizielle FUSSBALL.DE-Mannschafts-URL oder ein vollständiger Spielplan eingetragen wird, erzeugt das System daraus den U23-Kalender. Tabellen werden ebenfalls nur aus hinterlegten offiziellen Daten angezeigt; leere Tabellen werden transparent als noch nicht verbunden gekennzeichnet.
