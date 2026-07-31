# RSV-Kalender Update v5

## Darstellung

Zukünftiges Spiel:

```
2. Spieltag
Regionalliga Nordost
RSV Eintracht 1949 – FSV 63 Luckenwalde
Anstoß: 14:00 Uhr
```

Abgeschlossenes Spiel:

```
2. Spieltag
Regionalliga Nordost
RSV Eintracht 1949 – FSV 63 Luckenwalde
Endstand: 2:1
```

Nach einem Ergebnis berechnet das Skript die bis dahin erreichten RSV-Punkte automatisch. Ein Tabellenplatz wird angezeigt, sobald beim Spiel `table_position` vorhanden ist. Dieser Wert kann über `data/overrides.json` gesetzt oder später von einer zuverlässigen Tabellenquelle geliefert werden.

Optional unterstützte Felder je Spiel:

- `table_position`
- `points` (überschreibt die automatische Berechnung)
- `scorers` (Liste oder Text)
- `referee`
- `attendance`
- `report_url`

## Installation

Im bestehenden GitHub-Repository nur `update_calendars.py` ersetzen. Danach den Workflow **RSV-Kalender aktualisieren** manuell starten.

Hinweis: Kalenderprogramme können Zeilenumbrüche im kompakten Titel teilweise zu einer Zeile zusammenziehen. In der geöffneten Terminansicht stehen dieselben Informationen zusätzlich strukturiert in der Beschreibung.
