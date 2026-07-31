RSV-Kalender Version 8.7

Diese Version enthält zusätzlich zu Version 8.6:

- Hauptmenü heißt jetzt „Kalender abonnieren“.
- RSV-Logo als Browser-Favicon.
- RSV-Logo als App-Symbol für iPhone, iPad und Android.
- Web-App-Manifest und Service Worker für die Installation auf dem Startbildschirm.
- Browser-Titel: „RSV Eintracht 1949 – Spieltage, Tabellen & Kalender“.
- Begegnungen werden überall zweizeilig dargestellt:
  Heimmannschaft –
  Auswärtsmannschaft
  Dadurch bleiben die Vereinslogos links in einer Flucht.
- Vorhandene Spieldetails, Tabellen, Spielberichte, Torfolgen und Kalenderdateien bleiben erhalten.

Installation:
Den kompletten Inhalt dieses Ordners in das GitHub-Repository übernehmen und vorhandene Dateien ersetzen. Danach committen, den GitHub-Workflow ausführen und den Netlify-Deploy abwarten.

Hinweis zu Favicons/App-Symbolen:
Browser und Smartphones speichern Symbole oft lange im Cache. Nach dem Deploy die Seite einmal vollständig neu laden. Ein bereits angelegtes Startbildschirm-Symbol gegebenenfalls löschen und anschließend neu hinzufügen.
