# RSV-Kalender – stabiles System für Netlify

Dieses Projekt veröffentlicht zwei getrennte Kalender:

- `/rsv-regionalliga.ics` – 1. Herren
- `/rsv-u21.ics` – U21 / dritte Herrenmannschaft

## Grundprinzip

Die JSON-Dateien in `data/` sind die dauerhafte Datenbasis. Bei jedem Lauf versucht das Skript zusätzlich, die öffentlich sichtbaren offiziellen Seiten zu lesen. Neue Daten werden nur übernommen, wenn eine Plausibilitätsprüfung genügend Spiele erkennt. Bei einer Störung oder Layoutänderung bleiben die letzten gültigen Termine erhalten und die ICS-Dateien werden weiterhin erzeugt.

## Neuinstallation

1. Den Inhalt dieses Ordners direkt in die oberste Ebene eines neuen GitHub-Repositories laden. `.github` muss direkt im Repository liegen.
2. GitHub: `Settings → Actions → General → Workflow permissions → Read and write permissions` aktivieren.
3. `Actions → RSV-Kalender aktualisieren → Run workflow` starten.
4. Netlify: `Add new project → Import an existing project`, Repository auswählen.
5. Build command leer lassen; Publish directory: `docs`.
6. Deploy starten.

Danach lauten die URLs:

- `https://DEIN-NAME.netlify.app/rsv-regionalliga.ics`
- `https://DEIN-NAME.netlify.app/rsv-u21.ics`

## Manuelle Korrekturen

`data/overrides.json` ist für sichere Korrekturen vorgesehen. Beispiel:

```json
{
  "u21": {
    "u21-610480004": {
      "time": "15:00",
      "location": "Heinrich-Zille-Straße 32, 14532 Stahnsdorf"
    }
  }
}
```

Ein Eintrag mit `null` entfernt ein Spiel. Manuelle Overrides gewinnen immer gegen automatisch gelesene Daten.

## Test ohne Internet

```bash
pip install -r requirements.txt
python update_calendars.py --offline
```

Dabei werden beide ICS-Dateien ausschließlich aus den gespeicherten JSON-Daten erzeugt.

## Fehlerverhalten

Ein vorübergehender 404-, Timeout- oder Parserfehler beendet den Workflow nicht, solange gültige Basisdaten vorhanden sind. Im Action-Log steht dann `Online-Update übersprungen`, aber die vorhandenen Kalender bleiben verfügbar.
