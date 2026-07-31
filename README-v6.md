# RSV-Kalender v6 – 1. Herren Plus

## Neu für die 1. Herren

- Nach einem abgeschlossenen Regionalliga-Spiel erscheint ein Link zum passenden OSTSPORT.TV-Beitrag.
  - Ist `youtube_url` im Spiel hinterlegt, wird der direkte Beitrag verlinkt.
  - Sonst wird automatisch eine passende YouTube-Suche nach Paarung + OSTSPORT.TV erzeugt.
- Jeder Termin mit bekanntem Stadion erhält einen Google-Maps-Link.
- Zukünftige Spiele erhalten:
  - eine Wetterprognose, sobald der Spieltag höchstens 16 Tage entfernt ist;
  - dauerhaft einen Link zum Öffnen der Wetteransicht.
- Beide Vereinszeichen werden als Bildanhänge und zusätzlich als Links in den Termindetails hinterlegt.

## Wichtiger Hinweis zu Logos

ICS kann Bilder als Anhang anbieten. Ob sie direkt sichtbar dargestellt werden, entscheidet die jeweilige Kalender-App. Google Kalender zeigt externe ICS-Bilder nicht in jeder Ansicht. Die Logo-Links in der Beschreibung funktionieren unabhängig davon.

Die gegnerischen Vereinszeichen werden zunächst über die Website-Icons der offiziellen Vereinsdomains bezogen. Echte, selbst gehostete Logo-Dateien können später in `data/clubs.json` eingetragen werden.

## Installation

Im bestehenden GitHub-Repository ersetzen bzw. ergänzen:

1. `update_calendars.py`
2. `data/clubs.json`
3. `data/regionalliga.json`
4. `data/u21.json`
5. `docs/assets/rsv-logo.png`

Danach unter **Actions → RSV-Kalender aktualisieren → Run workflow** starten.

Netlify veröffentlicht die neuen ICS-Dateien automatisch. Bereits abonnierte Kalender müssen nicht erneut hinzugefügt werden; Google kann die Aktualisierung allerdings verzögert anzeigen.

## Direkten OSTSPORT-Link nachtragen

Sobald der konkrete Beitrag bekannt ist, in `data/overrides.json` ergänzen:

```json
{
  "regionalliga": {
    "rl-02": {
      "youtube_url": "https://www.youtube.com/watch?v=BEISPIEL"
    }
  },
  "u21": {}
}
```

## Beispiel: zukünftiges Spiel

```text
2. Spieltag
Regionalliga Nordost
RSV Eintracht 1949 – FSV 63 Luckenwalde
Anstoß: 14:00 Uhr

🏟️ Spielort: Preußenstadion, vollständige Adresse
🗺️ Google Maps: …
🌦️ Wetterprognose: …
🛡️ Vereinslogos: …
```

## Beispiel: abgeschlossenes Spiel

```text
1. Spieltag
Regionalliga Nordost
BFC Preussen 1894 – RSV Eintracht 1949
Endstand: 1:1

🏅 Punkte: 1
🏟️ Spielort: …
🗺️ Google Maps: …
▶️ OSTSPORT.TV-Beitrag: …
🛡️ Vereinslogos: …
```
