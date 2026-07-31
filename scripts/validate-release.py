#!/usr/bin/env python3
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
failed=[]
for key in ("regionalliga","u23","u21","u19"):
    data=json.loads((ROOT/"data"/f"{key}.json").read_text(encoding="utf-8"))
    games=data.get("games",[])
    expected=int(data.get("expected_league_games") or 0)
    league=[g for g in games if not any(x in str(g.get("competition","")).lower() for x in ("pokal","freundschaft","testspiel"))]
    extras=len(games)-len(league)
    print(f"{key}: {len(league)} Ligaspiele / erwartet {expected}; {extras} zusätzliche Pokal-/Freundschaftsspiele")
    if expected and len(league)<expected:
        failed.append(f"{key}: nur {len(league)}/{expected} Ligaspiele")
rl=json.loads((ROOT/"data"/"regionalliga.json").read_text(encoding="utf-8"))
print("Pokal-Termine 1. Herren:", sum("pokal" in str(g.get("competition","")).lower() for g in rl.get("games",[])))
if failed:
    print("Release-Prüfung fehlgeschlagen: "+"; ".join(failed), file=sys.stderr)
    sys.exit(1)
