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

## Lesbarkeit und Vereinslogos (letztes Update)

- Wichtige Schriftgrößen wurden auf Mobilgeräten und Desktop vergrößert.
- Mannschaftsnamen in Spielkarten, Terminlisten und Tabellen sind deutlich größer.
- Tabellen bleiben ohne horizontales Scrollen; Vereinsnamen dürfen innerhalb der Mannschaftsspalte umbrechen.
- Der Countdown verwendet größere Zahlen und Beschriftungen.
- Externe Vereinslogos werden über `/api/logo` von einer Netlify Function geladen und zwischengespeichert. Dadurch ist die Darstellung nicht mehr davon abhängig, ob der Browser externe Logo-Hosts direkt blockiert.
- Wenn eine Logoquelle dennoch nicht erreichbar ist, bleiben Vereinsinitialen als Rückfallebene erhalten.

## Release Candidate 1

- Spieltermine aller vier Mannschaften verwenden dieselbe Struktur.
- Wochentag und Datum bleiben in einer Zeile; die Uhrzeit steht darunter.
- Die Tabelle ist ohne horizontales Scrollen größer und besser lesbar.
- Schiedsrichter wird mit einer klaren Outline-Pfeife dargestellt.
- Tickets und Wetter erscheinen als zwei gleich große Chips.
- Stadionname und vollständige Adresse werden zweizeilig dargestellt und öffnen Google Maps.
- In „Alle Spieltermine“ lassen sich einzelne Spiele aufklappen; immer nur ein Termin ist geöffnet.
- Mannschaftsnamen in Termin- und Hauptkarten öffnen bei bekanntem Spielort die Navigation.
- Lok Leipzig/Lokomotive Leipzig und Erzgebirge Aue/FC Erzgebirge Aue werden über Aliase zusammengeführt.

## Spielbezogene Ticketlinks

Die App liest bei jedem regulären Datenlauf zusätzlich die Ticketübersicht der 1. Herren:

`https://rsv-eintracht.vereinsticket.de/herren/`

Für veröffentlichte Veranstaltungen wird die jeweilige Detailseite anhand von Gegner und Termin dem Heimspiel zugeordnet. Gibt es noch keine Detailseite, führt der Ticket-Chip auf die Herren-Übersichtsseite. Die zuletzt bekannten Detailseiten liegen zusätzlich in `data/tickets.json`, damit bei einem vorübergehenden Ausfall des Ticketshops keine bereits bekannte Zuordnung verloren geht.

Der Ticketshop wird damit im bestehenden Rhythmus geprüft:

- einmal innerhalb der täglichen Datenaktualisierung,
- sechs Stunden vor bekannten Spielen,
- eine Stunde nach dem errechneten Spielende,
- zwei Stunden nach dem errechneten Spielende,
- sowie bei jedem manuellen Workflow-Start.


## Vereins-Homepages

Mannschaftsnamen sind in Spielkarten, Ergebnislisten, vollständigen Spielterminen und Tabellen mit der jeweiligen Vereins-Homepage verknüpft. Die Links öffnen in einem neuen Tab und werden ohne sichtbare Unterstreichung dargestellt. Abweichende Schreibweisen werden über `data/club-aliases.json` auf den kanonischen Verein abgebildet. Die URLs werden in `data/clubs.json` gepflegt und beim Datenaufbau als `club_websites` sowie `club_aliases` in `site-data.json` veröffentlicht.
