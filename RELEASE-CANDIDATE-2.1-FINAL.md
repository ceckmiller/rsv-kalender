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

## Letzte Layout-Korrekturen

- In „Alle Spieltermine“ sind Vereinsnamen bewusst keine externen Links mehr, damit die gesamte Karte zuverlässig das Accordion öffnet und schließt.
- Zukünftige Termine öffnen die vollständige Ansicht von „Nächstes Spiel“.
- Bereits absolvierte Termine öffnen die vollständige Ergebnisansicht von „Letztes Spiel“, einschließlich Halbzeitstand, Torfolge, Zuschauer, Schiedsrichter, OSTSPORT und Spielbericht, sofern diese Daten vorhanden sind.
- Stadionname und vollständige Adresse sind zentriert dargestellt; der Maps-Link bleibt erhalten.
- Das Schiedsrichter-Symbol wurde durch eine eindeutig erkennbare Outline-Pfeife ersetzt.

## Letzte Stabilisierung (v3)

- Die Dreispaltenansicht der Spielkarten besitzt auf Mobilgeräten mindestens 8 px und auf größeren Ansichten 12 px Spaltenabstand.
- Vollständige Online-Spielpläne ergänzen automatisch alle Ligateilnehmer in den Tabellen, auch wenn eine Tabellenquelle zunächst verkürzt ist.
- Von FUSSBALL.DE gelieferte Vereinswappen werden bevorzugt und beim Workflow lokal unter `docs/assets/clubs/` zwischengespeichert.
- Konfigurierte Logo-URLs werden ebenfalls lokal gespeichert, soweit die Quelle erreichbar ist.
- Bei einem nicht erreichbaren Logo erscheinen saubere Vereinsinitialen und niemals ein Fragezeichen.


## Final v6 – Spieltage und Pokalrunden
- Klick auf einen Liga-Spieltag öffnet die komplette Runde mit allen vorhandenen Paarungen und Ergebnissen/Anstoßzeiten.
- Klick auf eine Pokalrunde öffnet sämtliche vorhandenen Paarungen dieser Runde.
- Das RSV-Spiel wird innerhalb der Runde nicht automatisch doppelt als große Karte angezeigt. Erst ein Klick auf die RSV-Paarung öffnet die bekannte Detailkarte; erneuter Klick schließt sie.
- Pokalspiele bleiben Bestandteil der Mannschaftstermine und der jeweiligen ICS-Kalender.
- `data/rounds.json` ist als persistenter Speicher für vollständige offizielle Spieltags- und Pokalrunden-Paarungen ergänzt. Fehlen vollständige Rundendaten, zeigt die App nur die offiziell vorhandenen Paarungen und erfindet keine.
