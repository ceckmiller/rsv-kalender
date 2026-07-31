#!/usr/bin/env python3
"""Decide whether the expensive live-data import should run.

Runs are due:
- once every 24 hours (the hourly scheduler invocation between 05:00 and 05:59 Europe/Berlin),
- around six hours before any known fixture,
- one hour after the estimated match end,
- two hours after the estimated match end.

Estimated match end is kickoff + 2 hours. The GitHub cron starts hourly at minute 17;
a +/- 35 minute window makes the event checks tolerant of GitHub scheduling delays.
"""
from __future__ import annotations
import json, os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Berlin")
WINDOW = timedelta(minutes=35)


def parse_kickoff(game: dict) -> datetime | None:
    date = game.get("date")
    time = game.get("time") or "00:00"
    if not date:
        return None
    try:
        return datetime.fromisoformat(f"{date}T{time}:00").replace(tzinfo=TZ)
    except ValueError:
        return None


def iter_fixtures(payload: dict):
    seen = set()
    for team in payload.get("teams", {}).values():
        for game in team.get("fixtures", []):
            ident = game.get("id") or (game.get("date"), game.get("time"), game.get("home"), game.get("away"))
            if ident in seen:
                continue
            seen.add(ident)
            yield game


def main() -> int:
    now = datetime.now(TZ)
    event_name = os.getenv("GITHUB_EVENT_NAME", "")
    reasons: list[str] = []

    if event_name == "workflow_dispatch":
        reasons.append("manueller Start")

    # Exactly one of the hourly checks becomes the daily run.
    if now.hour == 5:
        reasons.append("tägliche 24-Stunden-Prüfung")

    path = ROOT / "docs" / "site-data.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        reasons.append(f"Sicherheitslauf: Spielplandaten nicht lesbar ({exc})")
        payload = {}

    for game in iter_fixtures(payload):
        kickoff = parse_kickoff(game)
        if not kickoff:
            continue
        targets = (
            (kickoff - timedelta(hours=6), "6 Stunden vor Anstoß"),
            (kickoff + timedelta(hours=3), "1 Stunde nach erwartetem Spielende"),
            (kickoff + timedelta(hours=4), "2 Stunden nach erwartetem Spielende"),
        )
        for target, label in targets:
            if abs(now - target) <= WINDOW:
                fixture = f"{game.get('home', '?')} – {game.get('away', '?')} ({kickoff:%d.%m.%Y %H:%M})"
                reasons.append(f"{label}: {fixture}")

    should_run = bool(reasons)
    output = os.getenv("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"should_run={'true' if should_run else 'false'}\n")
            fh.write("reason<<EOF\n" + (" | ".join(reasons) if reasons else "kein fälliges Ereignis") + "\nEOF\n")

    print("Aktualisierung wird ausgeführt:" if should_run else "Aktualisierung wird übersprungen:")
    print(" | ".join(reasons) if reasons else "Kein täglicher oder spielbezogener Auslöser fällig.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
