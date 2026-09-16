"""
Fetch the user's Yahoo Fantasy football league(s) and write data/yahoo.json.

Runs in the GitHub Action. Requires three repo secrets (see
yahoo_auth_helper.py for the one-time setup):
    YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_REFRESH_TOKEN

Exits cleanly (code 0) when the secrets aren't configured, so the rest of
the pipeline keeps working without Yahoo.

Yahoo's JSON is deeply nested with numeric-string keys ("0", "1", ...,
"count"); the helpers below flatten that into something sane. Output:

{
  "generated": "...", "week": 2,
  "leagues": [{
    "name": ..., "league_key": ..., "num_teams": ..., "scoring_type": ...,
    "my_team": {"name": ..., "team_key": ...,
      "roster": [{"name","pos","team","status","selected_position"}]},
    "standings": [{"name","rank","wins","losses","ties","points_for"}],
    "my_matchup": {"opponent": ..., "my_points": ..., "opp_points": ...},
    "free_agents": [{"name","pos","team","status","percent_owned"}]
  }]
}
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

CID = os.environ.get("YAHOO_CLIENT_ID", "").strip()
CSEC = os.environ.get("YAHOO_CLIENT_SECRET", "").strip()
RTOK = os.environ.get("YAHOO_REFRESH_TOKEN", "").strip()

TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
BASE = "https://fantasysports.yahooapis.com/fantasy/v2"
OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "yahoo.json")

SESSION = requests.Session()


def get_access_token() -> str:
    r = requests.post(TOKEN_URL, data={
        "client_id": CID,
        "client_secret": CSEC,
        "redirect_uri": "oob",
        "refresh_token": RTOK,
        "grant_type": "refresh_token",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def yget(path: str) -> dict:
    r = SESSION.get(f"{BASE}/{path}", params={"format": "json"}, timeout=30)
    r.raise_for_status()
    return r.json()


def unroll(node):
    """Flatten Yahoo's {'0': {...}, '1': {...}, 'count': n} dicts to lists."""
    if isinstance(node, dict) and "count" in node:
        return [node[str(i)] for i in range(node["count"]) if str(i) in node]
    return node


def merge_fragments(fragments):
    """A Yahoo object is often a list of single-key dicts (plus stray lists);
    merge them into one dict."""
    out = {}
    stack = [fragments]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
        elif isinstance(item, dict):
            out.update(item)
    return out


def parse_player(p):
    d = merge_fragments(p.get("player", p))
    name = (d.get("name") or {}).get("full")
    sel = d.get("selected_position")
    sel_pos = None
    if sel:
        sel_pos = merge_fragments(sel).get("position")
    own = d.get("percent_owned")
    pct = merge_fragments(own).get("value") if own else None
    return {
        "name": name,
        "pos": d.get("display_position"),
        "team": d.get("editorial_team_abbr"),
        "status": d.get("status"),           # e.g. Q, O, IR — absent when healthy
        "selected_position": sel_pos,        # QB/RB/WR/BN/IR... when from a roster
        "percent_owned": pct,
    }


def main() -> int:
    if not (CID and CSEC and RTOK):
        print("Yahoo secrets not configured - skipping Yahoo fetch.")
        return 0

    SESSION.headers["Authorization"] = f"Bearer {get_access_token()}"

    # current NFL game + my leagues in it
    data = yget("users;use_login=1/games;game_keys=nfl/leagues")
    user = merge_fragments(unroll(data["fantasy_content"]["users"])[0]["user"])
    games = unroll(user.get("games") or {})
    out_leagues = []

    for g in games:
        game = merge_fragments(g.get("game", g))
        leagues = unroll(game.get("leagues") or {})
        for lg_wrap in leagues:
            lg = merge_fragments(lg_wrap.get("league", lg_wrap))
            lkey = lg.get("league_key")
            if not lkey:
                continue
            week = int(lg.get("current_week") or 1)

            # teams + standings
            st = yget(f"league/{lkey}/standings")
            st_league = merge_fragments(unroll(st["fantasy_content"]["league"]))
            teams = unroll(merge_fragments(st_league.get("standings") or {}).get("teams") or {})
            standings, my_team_key, my_team_name = [], None, None
            for t_wrap in teams:
                t = merge_fragments(t_wrap.get("team", t_wrap))
                ts = merge_fragments(t.get("team_standings") or {})
                rec = merge_fragments(ts.get("outcome_totals") or {})
                is_me = False
                mgrs = t.get("managers")
                if mgrs:
                    for m in unroll(mgrs) if isinstance(mgrs, dict) else mgrs:
                        mm = merge_fragments(m.get("manager", m))
                        if str(mm.get("is_current_login")) == "1":
                            is_me = True
                if is_me:
                    my_team_key, my_team_name = t.get("team_key"), t.get("name")
                standings.append({
                    "name": t.get("name"),
                    "rank": ts.get("rank"),
                    "wins": rec.get("wins"), "losses": rec.get("losses"),
                    "ties": rec.get("ties"),
                    "points_for": ts.get("points_for"),
                    "is_me": is_me,
                })

            my_team = None
            my_matchup = None
            if my_team_key:
                ro = yget(f"team/{my_team_key}/roster/players")
                ro_team = merge_fragments(unroll(ro["fantasy_content"]["team"]))
                roster_players = unroll(merge_fragments(ro_team.get("roster") or {}).get("players") or {})
                my_team = {
                    "name": my_team_name,
                    "team_key": my_team_key,
                    "roster": [parse_player(p) for p in roster_players],
                }

                try:
                    mu = yget(f"team/{my_team_key}/matchups;weeks={week}")
                    mu_team = merge_fragments(unroll(mu["fantasy_content"]["team"]))
                    matchups = unroll(merge_fragments(mu_team.get("matchups") or {}))
                    if matchups:
                        m0 = merge_fragments(matchups[0].get("matchup", matchups[0]))
                        mteams = unroll(merge_fragments(m0).get("teams") or {})
                        pts = []
                        for mt in mteams:
                            td = merge_fragments(mt.get("team", mt))
                            tp = merge_fragments(td.get("team_points") or {})
                            pts.append({"name": td.get("name"),
                                        "key": td.get("team_key"),
                                        "points": tp.get("total")})
                        me = next((x for x in pts if x["key"] == my_team_key), None)
                        opp = next((x for x in pts if x["key"] != my_team_key), None)
                        if me and opp:
                            my_matchup = {"opponent": opp["name"],
                                          "my_points": me["points"],
                                          "opp_points": opp["points"]}
                except Exception as exc:  # noqa: BLE001
                    print(f"matchup fetch skipped: {exc}")

            # top free agents by ownership
            fa = yget(f"league/{lkey}/players;status=FA;sort=OR;count=25")
            fa_league = merge_fragments(unroll(fa["fantasy_content"]["league"]))
            fa_players = unroll(fa_league.get("players") or {})
            free_agents = [parse_player(p) for p in fa_players]

            out_leagues.append({
                "name": lg.get("name"),
                "league_key": lkey,
                "num_teams": lg.get("num_teams"),
                "scoring_type": lg.get("scoring_type"),
                "current_week": week,
                "my_team": my_team,
                "standings": standings,
                "my_matchup": my_matchup,
                "free_agents": free_agents,
            })

    payload = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "leagues": out_leagues,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {OUT_PATH}: {len(out_leagues)} Yahoo league(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
