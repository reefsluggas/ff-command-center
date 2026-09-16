"""
Fetch FantasyPros Expert Consensus Rankings (ECR) and write data/rankings.json.

Runs inside the GitHub Action on a schedule. Requires the repo secret
FANTASYPROS_API_KEY (request a free key at fantasypros.com/apis).

If the key is missing or the API call fails, the script exits cleanly
without touching the existing data file, so the site keeps whatever
rankings it last had. The website works fine (minus suggestions) if this
file never gets populated.

Output shape (kept compact so the browser can load it fast):

{
  "updated": "2026-09-10T12:00:14Z",
  "season": 2026,
  "week": 1,
  "formats": {
    "ppr":  { "josh allen|QB": {"rank": 1, "posRank": 1, "team": "BUF"}, ... },
    "half": { ... },
    "std":  { ... }
  }
}

Player keys are lowercased "name|POS" with punctuation and suffixes
stripped; the website normalizes Sleeper names the same way to match.
Team defenses are keyed "TEAMABBREV|DEF".
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

API_KEY = os.environ.get("FANTASYPROS_API_KEY", "").strip()
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "rankings.json")

FP_BASE = "https://api.fantasypros.com/public/v2/json/nfl"
SLEEPER_STATE = "https://api.sleeper.app/v1/state/nfl"

SCORING = {"ppr": "PPR", "half": "HALF", "std": "STD"}

SUFFIXES = re.compile(r"\s+(jr|sr|ii|iii|iv|v)\.?$", re.I)
PUNCT = re.compile(r"[.'\-]")

# FantasyPros team names -> standard abbreviations for DST keys
TEAM_ABBREV = {
    "arizona cardinals": "ARI", "atlanta falcons": "ATL", "baltimore ravens": "BAL",
    "buffalo bills": "BUF", "carolina panthers": "CAR", "chicago bears": "CHI",
    "cincinnati bengals": "CIN", "cleveland browns": "CLE", "dallas cowboys": "DAL",
    "denver broncos": "DEN", "detroit lions": "DET", "green bay packers": "GB",
    "houston texans": "HOU", "indianapolis colts": "IND", "jacksonville jaguars": "JAX",
    "kansas city chiefs": "KC", "las vegas raiders": "LV", "los angeles chargers": "LAC",
    "los angeles rams": "LAR", "miami dolphins": "MIA", "minnesota vikings": "MIN",
    "new england patriots": "NE", "new orleans saints": "NO", "new york giants": "NYG",
    "new york jets": "NYJ", "philadelphia eagles": "PHI", "pittsburgh steelers": "PIT",
    "san francisco 49ers": "SF", "seattle seahawks": "SEA", "tampa bay buccaneers": "TB",
    "tennessee titans": "TEN", "washington commanders": "WAS",
}


def norm_name(name: str) -> str:
    n = name.strip().lower()
    n = PUNCT.sub("", n)
    n = SUFFIXES.sub("", n)
    n = re.sub(r"\s+", " ", n)
    return n


def player_key(name: str, pos: str) -> str:
    pos = pos.upper()
    if pos in ("DST", "DEF", "D/ST"):
        abbrev = TEAM_ABBREV.get(name.strip().lower())
        if abbrev:
            return f"{abbrev}|DEF"
        return f"{norm_name(name)}|DEF"
    return f"{norm_name(name)}|{pos}"


def fetch_format(season: int, week: int, scoring: str) -> dict:
    url = f"{FP_BASE}/{season}/consensus-rankings"
    params = {
        "type": "weekly",
        "scoring": scoring,
        "position": "ALL",
        "week": week,
    }
    r = requests.get(url, params=params, headers={"x-api-key": API_KEY}, timeout=30)
    r.raise_for_status()
    data = r.json()
    players = data.get("players", [])
    out = {}
    for p in players:
        name = p.get("player_name") or p.get("name")
        pos = (p.get("player_position_id") or p.get("position") or "").upper()
        rank = p.get("rank_ecr") or p.get("rank")
        pos_rank = p.get("pos_rank") or p.get("rank_pos")
        team = p.get("player_team_id") or p.get("team") or ""
        if not name or not pos or rank is None:
            continue
        out[player_key(name, pos)] = {
            "rank": int(rank),
            "posRank": str(pos_rank) if pos_rank else None,
            "team": team,
        }
    return out


def main() -> int:
    if not API_KEY:
        print("FANTASYPROS_API_KEY not set - skipping (site will run without ECR).")
        return 0

    state = requests.get(SLEEPER_STATE, timeout=15).json()
    season = int(state.get("league_season") or state.get("season"))
    week = max(1, int(state.get("week") or 1))

    formats = {}
    for key, scoring in SCORING.items():
        try:
            formats[key] = fetch_format(season, week, scoring)
            print(f"{scoring}: {len(formats[key])} players ranked")
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: {scoring} fetch failed: {exc}")

    if not formats:
        print("No formats fetched - leaving existing data file untouched.")
        return 0

    payload = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "season": season,
        "week": week,
        "formats": formats,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {OUT_PATH} for season {season}, week {week}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
