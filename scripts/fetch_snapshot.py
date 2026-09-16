"""
Fetch a complete Sleeper snapshot for the configured user and write
data/snapshot.json. Runs in the GitHub Action (GitHub's servers can call
Sleeper freely). The published file makes the current state of every league
readable by anything that can fetch a URL — including Claude, so weekly
waiver advice doesn't require screenshots.

No API key needed; Sleeper's API is public.
"""

import json
import sys
from datetime import datetime, timezone

import requests

USERNAME = "sapskull"
API = "https://api.sleeper.app/v1"
OUT_PATH = __file__.rsplit("/", 1)[0] + "/../data/snapshot.json"

PLAYER_FIELDS = ("full_name", "first_name", "last_name", "team", "position",
                 "injury_status", "injury_body_part", "status", "active",
                 "search_rank", "age", "years_exp")


def jget(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def trim_player(p):
    if not p:
        return None
    name = p.get("full_name") or f"{p.get('first_name','')} {p.get('last_name','')}".strip()
    return {
        "name": name,
        "team": p.get("team"),
        "pos": p.get("position"),
        "inj": p.get("injury_status"),
        "inj_part": p.get("injury_body_part"),
        "status": p.get("status"),
        "active": p.get("active"),
        "rank": p.get("search_rank"),
        "age": p.get("age"),
        "exp": p.get("years_exp"),
    }


def main() -> int:
    state = jget(f"{API}/state/nfl")
    user = jget(f"{API}/user/{USERNAME}")
    season = state.get("league_season") or state.get("season")
    week = max(1, int(state.get("week") or 1))

    leagues = jget(f"{API}/user/{user['user_id']}/leagues/nfl/{season}") or []
    if not leagues:
        leagues = jget(f"{API}/user/{user['user_id']}/leagues/nfl/{int(season) - 1}") or []

    referenced = set()
    out_leagues = []
    for lg in leagues:
        lid = lg["league_id"]
        rosters = jget(f"{API}/league/{lid}/rosters")
        users = jget(f"{API}/league/{lid}/users")
        matchups = []
        if lg.get("status") == "in_season":
            try:
                matchups = jget(f"{API}/league/{lid}/matchups/{week}")
            except Exception:  # noqa: BLE001
                matchups = []

        names = {u["user_id"]: (u.get("metadata") or {}).get("team_name") or u.get("display_name")
                 for u in users}
        slim_rosters = []
        for r in rosters:
            for pid in (r.get("players") or []) + (r.get("taxi") or []) + (r.get("reserve") or []):
                referenced.add(pid)
            slim_rosters.append({
                "roster_id": r["roster_id"],
                "owner": names.get(r.get("owner_id")),
                "is_me": r.get("owner_id") == user["user_id"] or
                         user["user_id"] in (r.get("co_owners") or []),
                "players": r.get("players"),
                "starters": r.get("starters"),
                "taxi": r.get("taxi"),
                "reserve": r.get("reserve"),
                "record": (r.get("settings") or {}),
            })

        out_leagues.append({
            "league_id": lid,
            "name": lg.get("name"),
            "status": lg.get("status"),
            "total_rosters": lg.get("total_rosters"),
            "roster_positions": lg.get("roster_positions"),
            "scoring_rec": (lg.get("scoring_settings") or {}).get("rec"),
            "settings_type": (lg.get("settings") or {}).get("type"),  # 0 redraft, 1 keeper, 2 dynasty
            "taxi_slots": (lg.get("settings") or {}).get("taxi_slots"),
            "waiver_budget": (lg.get("settings") or {}).get("waiver_budget"),
            "rosters": slim_rosters,
            "matchups": [
                {"roster_id": m.get("roster_id"), "matchup_id": m.get("matchup_id"),
                 "points": m.get("points"), "starters": m.get("starters"),
                 "players_points": m.get("players_points")}
                for m in matchups
            ],
        })

    trending = jget(f"{API}/players/nfl/trending/add?lookback_hours=24&limit=50")
    for t in trending:
        referenced.add(t["player_id"])

    all_players = jget(f"{API}/players/nfl")
    players = {pid: trim_player(all_players.get(pid)) for pid in referenced}
    # also include the best ~400 active ranked players so free agents are visible
    ranked = sorted(
        ((pid, p) for pid, p in all_players.items()
         if p.get("active") and p.get("status") == "Active"
         and isinstance(p.get("search_rank"), int) and p["search_rank"] < 400
         and p.get("team")),
        key=lambda kv: kv[1]["search_rank"])
    for pid, p in ranked:
        players.setdefault(pid, trim_player(p))

    snapshot = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "username": USERNAME,
        "season": season,
        "week": week,
        "season_type": state.get("season_type"),
        "leagues": out_leagues,
        "trending_adds": trending,
        "players": players,
    }
    with open(OUT_PATH, "w") as f:
        json.dump(snapshot, f, separators=(",", ":"))
    print(f"Wrote snapshot: {len(out_leagues)} leagues, {len(players)} players, week {week}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
