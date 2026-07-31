# RSV Eintracht App 2.1 – finaler Release Candidate

Enthalten sind alle zuletzt abgestimmten UI-Funktionen: vier Mannschaften, Dark Mode, groessere Schriften, Countdown mit Sekunden unter 24 Stunden, Spielkarten-Accordion, Vereinslinks, Karten-Navigation, Ticket-Detailseiten, Wetterlinks und vier abonnierbare Kalender.

## Schutz vor unvollstaendigen Spielplaenen

Der Workflow veroeffentlicht U23 und U21 erst, wenn jeweils mindestens 30 Termine erkannt wurden. Ein auf zehn Eintraege gekuerzter FUSSBALL.DE-Abruf kann dadurch keine vollstaendigen Live-Daten mehr ersetzen. Die Pruefung erfolgt vor dem Upload zu Netlify Blobs.

## Datenquellen

- 1. Herren: DFB-Datencenter; Pokaltermine werden als zusaetzliche Wettbewerbe erhalten.
- U23, U21 und U19: vollstaendiger FUSSBALL.DE-Druckspielplan plus Mannschaftsseite als zweite Quelle.
- Tickets: Herren-Uebersicht und vorhandene Detailseiten; ohne Detailseite wird die Herren-Uebersicht geoeffnet.

## Logos

Vereinsnamen werden ueber `data/club-aliases.json` normalisiert. Die Anzeige nutzt die zentrale Datenbank `data/clubs.json`, die Netlify-Logo-Function und Initialen nur als letzte Rueckfallebene. Hallescher FC, Lok/Lokomotive Leipzig und Erzgebirge/FC Erzgebirge Aue sind eindeutig zugeordnet.
