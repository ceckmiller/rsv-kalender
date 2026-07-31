# RSV Eintracht App – Version 2.0

Diese Version bündelt Spieltage, Tabellen und Kalender-Abonnements in einer installierbaren Web-App.

## Neu in diesem Paket

- luftiges App-Design mit sauber ausgerichteter Ergebnisachse
- Tagmodus als Standard und Schwarz/Gold-Nachtmodus
- ausschließlich zwei feste Navigationspunkte am unteren Rand
- scrollbarerer RSV-Abbinder bleibt auch nachts blau
- nächstes und letztes Spiel als kompakte Karten
- Torverlauf direkt unter dem Ergebnis, letztes Tor oben
- Minute und Torschütze immer auf der Seite der erfolgreichen Mannschaft
- kompaktere absolvierte Spiele sowie vollständige Terminlisten
- Liga-, Pokal- und Freundschaftsspiele werden getrennt bezeichnet
- U21-/U23-Nulltabellen werden bis zur offiziellen Tabelle alphabetisch aufgebaut
- robustere FUSSBALL.DE-Quellen mit mehreren Quellen und Mindestmengenprüfung
- stündliche Open-Meteo-Prognose zur Anstoßzeit
- feste Stadionkoordinaten plus mehrstufiges Geocoding und sichtbare Workflow-Warnungen
- Vereinslogo-Fallbacks und automatische Nachladeversuche

## Deployment

Den gesamten Ordnerinhalt in das GitHub-Repository übernehmen und vorhandene Dateien ersetzen. Danach den Workflow `Update calendars` ausführen. Netlify veröffentlicht anschließend den Inhalt des Ordners `docs`.

Hinweis: Wetterdaten werden während des Online-Workflows geladen. Beim lokalen Offline-Build bleiben sie erwartungsgemäß leer.
