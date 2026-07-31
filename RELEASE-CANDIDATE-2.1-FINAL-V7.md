# Release Candidate 2.1 Final v7

## Automatische Spielortdatenbank

- Offizielle Spielortangaben aus den FUSSBALL.DE-Druckspielplänen (`show-venues/true`) werden pro Spiel gespeichert.
- Bereits bekannte Spielorte werden in `venue-cache.json` in Netlify Blobs dauerhaft erhalten und vor jedem Lauf wieder geladen.
- Leere oder vorübergehend fehlende Angaben überschreiben keinen bekannten Spielort.
- Änderungen offizieller Ansetzungen aktualisieren den gespeicherten Spielort beim nächsten erfolgreichen Lauf.
- Jugend- und Reservemannschaften übernehmen keinen Spielort der ersten Herren.

## Schutz vor unvollständigen Spielplänen

Der Workflow veröffentlicht nur, wenn mindestens folgende Terminanzahl erkannt wurde:

- 1. Herren: 30
- U23: 30
- U21: 30
- U19: 30

Ein fehlgeschlagener oder unvollständiger Abruf beendet den Workflow vor der Veröffentlichung. Die zuletzt vollständigen Daten in Netlify Blobs bleiben dann online.

## Erster manueller Lauf

Ein manueller Lauf umgeht die Zeitfensterprüfung. Er lädt die offiziellen Quellen, erzeugt die Kalender und veröffentlicht nur bei erfolgreicher Vollständigkeitsprüfung.
