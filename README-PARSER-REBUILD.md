# RSV Eintracht App 2.1 – FUSSBALL.DE-Parser neu aufgebaut

## Änderung

Der Import von U23, U21 und U19 wertet jetzt die vollständige tabellarische
Struktur der offiziellen FUSSBALL.DE-Druck- und AJAX-Seiten aus. Pro Spiel werden
folgende Felder aus den Tabellenzellen gelesen:

- Datum und Anstoßzeit
- Wettbewerb
- Heim- und Auswärtsmannschaft
- Ergebnis, wenn im Klartext vorhanden
- Spiel-ID und Detailseite
- Vereinslogos aus `data-responsive-image`
- ausdrücklich angegebener Spielort

Die offiziellen Druckseiten verschleiern Datum, Uhrzeit und Ergebnis mit
Einweg-Webfonts (`data-obfuscation`). Der Parser lädt diese Schriften, mappt die
Private-Use-Glyphen zurück auf Klartext und liest danach die komplette Tabelle.
Sobald die Druckseite den erwarteten Ligaspielplan liefert, wird die kürzere
Mannschaftsseite übersprungen.

Die alte flache Textauswertung bleibt nur als Rückfallebene erhalten.

## Diagnose im Workflow

Der Lauf schreibt jetzt je Quelle beispielsweise:

    FUSSBALL.DE Parser RSV Eintracht 1949 U23: Tabellenstruktur=30, Text-Fallback=0, zusammen=30

So ist sofort erkennbar, ob die vollständige Tabelle oder nur ein Fallback
gelesen wurde.

## Schutz

Die adaptive Vollständigkeitsprüfung bleibt aktiv. Ein verkürzter Abruf ersetzt
keine bereits vollständigen Live-Daten.

## Installation

Den gesamten Paketinhalt in das GitHub-Repository laden, vorhandene Dateien
ersetzen und committen. Danach unter **Actions → RSV-Livedaten aktualisieren →
Run workflow** einmal manuell starten.
