# Workflow-Hotfix

Behoben:

- fehlender Python-Import `mimetypes` bei der lokalen Logo-Ablage
- kaputte Google-Favicon-URLs erzeugen keine Warnungsflut mehr
- FUSSBALL.DE-Spielpläne werden zusätzlich aus der kompakten Spielplan-Darstellung gelesen (`So, 30.08.26 | 14:00 ...`)
- vollständige Druckspielpläne für U23/U21/U19 können damit über mehr als die zunächst sichtbaren Spiele hinaus erkannt werden

Nach dem Upload den Workflow einmal manuell starten. Im Protokoll sollten U23 und U21 mindestens 30 Termine melden. Falls eine offizielle Quelle temporär weniger liefert, bleibt die Schutzprüfung aktiv und verhindert die Veröffentlichung eines gekürzten Spielplans.
