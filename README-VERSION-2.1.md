# RSV Eintracht App – Version 2.1

## Enthalten

- Luftiges App-Design mit Tagmodus und Schwarz-Gold-Nachtmodus.
- Die untere Navigation wechselt im Nachtmodus ebenfalls auf Schwarz/Gold.
- Der blaue RSV-Abbinder am Seitenende bleibt in beiden Modi blau.
- Nächstes Spiel mit kleinem Countdown direkt in der Kopfzeile:
  - über 7 Tage: Tage,
  - 1 bis 7 Tage: Tage, Stunden und Minuten,
  - unter 24 Stunden: Stunden, Minuten und Sekunden.
- Geschützte mittlere Datum-/Uhrzeitspalte, damit lange Vereinsnamen nicht hineinlaufen.
- Letztes Spiel mit vier Kacheln: Zuschauer, Schiedsrichter, OSTSPORT und Spielbericht.
- Torfolge mit gemeinsamer Ergebnisachse; spätestes Tor oben, Minute und Torschütze auf der jeweiligen Mannschaftsseite.
- Smartphone-Tabelle ohne Differenz und ohne horizontales Scrollen: Platz, Mannschaft, Spiele, Tore, Punkte.
- Vereinslogo und Vereinsname stehen in der Tabelle enger zusammen.
- Wetter wird nur verlinkt und verursacht keine regelmäßigen Datenänderungen.
- Livedaten und ICS-Dateien werden über Netlify Blobs und Functions ausgeliefert.
- SHA-256-Vergleich: Unveränderte Dateien werden nicht erneut veröffentlicht.

## Intelligenter Aktualisierungsplan

Der kleine GitHub-Scheduler startet stündlich, der eigentliche Datenabruf aber nur:

- einmal täglich zwischen 05:00 und 05:59 Uhr (Europe/Berlin),
- etwa 6 Stunden vor einem bekannten Spiel,
- 1 Stunde nach dem errechneten Spielende,
- 2 Stunden nach dem errechneten Spielende,
- bei einem manuellen Workflow-Start.

Als errechnetes Spielende gilt Anstoß plus 2 Stunden. GitHub-Zeitpläne können sich verzögern; deshalb nutzt die Prüfung ein tolerantes Zeitfenster. Wenn keine Prüfung fällig ist, werden weder Quellen abgerufen noch Daten veröffentlicht. Wenn Daten identisch sind, wird ebenfalls nichts geschrieben.

## Einmalige Einrichtung nach dem Deployment

1. Den kompletten Inhalt dieses Pakets in das GitHub-Repository übernehmen und vorhandene Dateien ersetzen.
2. Committen und pushen. Netlify muss Version 2.1 einmal regulär deployen, damit Functions und Redirects verfügbar sind.
3. In Netlify die Project/Site ID kopieren.
4. In Netlify einen persönlichen Zugriffstoken erzeugen.
5. In GitHub unter **Settings → Secrets and variables → Actions** anlegen:
   - `NETLIFY_SITE_ID`
   - `NETLIFY_AUTH_TOKEN`
6. Unter **Actions** den Workflow **RSV-Livedaten aktualisieren** einmal manuell starten.
7. Danach kontrollieren, ob im Lauf `site-data.json` und die drei ICS-Dateien in Netlify Blobs veröffentlicht wurden.

Die bisherigen öffentlichen ICS-Adressen bleiben bestehen.


## Ergänzung: U19 als vierte Mannschaft

- U19-Ansicht und U19-Tabelle
- alle von FUSSBALL.DE veröffentlichten Liga-, Pokal- und Freundschaftstermine
- eigener abonnierbarer Kalender `rsv-u19.ics`
- U19-Spiele sind in den intelligenten Vor- und Nachspiel-Prüfungen enthalten

## U19 und Vereinslogos

- U19 vollständig als vierte Mannschaft integriert (30 veröffentlichte Termine: Liga, Pokal und Freundschaftsspiele).
- Vereinsnamen werden über `data/club-aliases.json` normalisiert.
- Beispiele: `1. FC Lokomotive Leipzig` und `1. FC Lok Leipzig` nutzen dasselbe Logo; ebenso `FC Erzgebirge Aue` und `Erzgebirge Aue`.
- Für alle aktuell im Datenbestand vorkommenden Mannschaften ist eine Logo-Zuordnung vorhanden.
- Fehlt später ein neuer Verein, bleibt das Initialen-Ersatzlogo als letzte Rückfallebene aktiv.
