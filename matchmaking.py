"""Matchmaking engine (the web page runs the same logic in JavaScript).

How a player's effect on a team is measured
-------------------------------------------
Each player has an offensive and a defensive impact (O-LEBRON / D-LEBRON): points
per 100 possessions he adds to his team's offense, or takes off the opponent's,
while on the floor. A team's rating moves by impact x (minutes / 48), so the
more a player plays, the bigger his effect, good or bad.

Adding a player gives him his projected minutes (last season's MPG, capped at 36).
Those minutes come out of the current roster: first from players at his position
group (guard / forward / center), lowest-impact first, then from the rest of the
roster if needed. The change in team ratings is

    dORtg = (o_new * m - sum(o_j * m_j taken)) / 48
    dDRtg = -(d_new * m - sum(d_j * m_j taken)) / 48     (negative = better defense)

Budget: a player fits if his 2026-27 salary (held flat for next year) fits in the
room between the team's payroll and the chosen line (luxury tax by default).

Usage:
    python3 matchmaking.py BOS                 best fits for Boston under the tax line
    python3 matchmaking.py BOS --line apron1   ...under the first apron
    python3 matchmaking.py --player "Ty Jerome"  which teams he fits best
"""

import argparse
import json
from pathlib import Path

DATA = json.loads((Path(__file__).resolve().parent / "data" / "nba_matchmaking.json").read_text())
META, TEAMS, PLAYERS = DATA["meta"], {t["abbr"]: t for t in DATA["teams"]}, DATA["players"]
TEAM_MINUTES = 240.0


def allocate(roster):
    """Projected minutes: fill 240 by last season's MPG, best-used players first."""
    out, left = {}, TEAM_MINUTES
    for p in sorted(roster, key=lambda p: -p["mpg"]):
        m = min(p["mpg"], META["mpgCap"], left)
        out[p["name"]] = m
        left -= m
    used = sum(out.values())
    if left > 0.5 and used:
        out = {k: min(META["mpgCap"], v * TEAM_MINUTES / used) for k, v in out.items()}
    return out


def team_ratings(roster, minutes):
    o = sum(p["o"] * minutes[p["name"]] for p in roster) / 48
    d = sum(p["d"] * minutes[p["name"]] for p in roster) / 48
    return META["leagueORtg"] + o, META["leagueORtg"] - d


def evaluate(roster, minutes, cand, m=None):
    """Effect of adding cand to a roster with the given minute allocation."""
    m = min(cand["mpg"], META["mpgCap"]) if m is None else m
    net = lambda p: p["o"] + p["d"]
    same = sorted([p for p in roster if p["grp"] == cand["grp"]], key=net)
    rest = sorted([p for p in roster if p["grp"] != cand["grp"]], key=net)
    need, taken = m, []
    for p in same + rest:
        if need <= 0:
            break
        t = min(minutes[p["name"]], need)
        if t > 0:
            taken.append((p, t))
            need -= t
    d_o = (cand["o"] * m - sum(p["o"] * t for p, t in taken)) / 48
    d_d = (cand["d"] * m - sum(p["d"] * t for p, t in taken)) / 48
    return {"minutes": m, "dORtg": d_o, "dDRtg": -d_d, "net": d_o + d_d, "taken": taken}


def team_fits(abbr, line="tax", outgoing=()):
    roster = [p for p in PLAYERS if p["team"] == abbr and p["name"] not in outgoing]
    freed = sum(p["salary"] for p in PLAYERS if p["team"] == abbr and p["name"] in outgoing)
    room = META["lines"][line] - TEAMS[abbr]["payroll"] + freed
    minutes = allocate(roster)
    rows = []
    for c in PLAYERS:
        if c["team"] == abbr or c["salary"] <= 0 or c["salary"] > room:
            continue
        rows.append({**c, **evaluate(roster, minutes, c)})
    return room, sorted(rows, key=lambda r: -r["net"])


def player_fits(name, line="tax"):
    cand = next(p for p in PLAYERS if p["name"].lower() == name.lower())
    rows = []
    for abbr, t in TEAMS.items():
        if abbr == cand["team"]:
            continue
        roster = [p for p in PLAYERS if p["team"] == abbr]
        room = META["lines"][line] - t["payroll"]
        rows.append({"team": abbr, "room": room, "fits": cand["salary"] <= room,
                     **evaluate(roster, allocate(roster), cand)})
    return cand, sorted(rows, key=lambda r: (not r["fits"], -r["net"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("team", nargs="?")
    ap.add_argument("--player")
    ap.add_argument("--line", default="tax", choices=list(META["lines"]))
    ap.add_argument("-n", type=int, default=15)
    a = ap.parse_args()
    if a.player:
        cand, rows = player_fits(a.player, a.line)
        print(f"{cand['name']} ({cand['team']}, ${cand['salary']/1e6:.1f}M, O {cand['o']:+.1f} D {cand['d']:+.1f})")
        for r in rows[: a.n]:
            tag = "fits" if r["fits"] else f"needs ${(cand['salary']-r['room'])/1e6:.1f}M more room"
            print(f"  {r['team']}  ORtg {r['dORtg']:+.2f}  DRtg {r['dDRtg']:+.2f}  net {r['net']:+.2f}  {tag}")
    else:
        room, rows = team_fits(a.team.upper(), a.line)
        print(f"{a.team.upper()}: ${room/1e6:.1f}M of room under the {a.line} line")
        for r in rows[: a.n]:
            print(f"  {r['name']:<26}{r['team']}  {r['pos']:<3}${r['salary']/1e6:5.1f}M  {r['minutes']:4.1f} min"
                  f"  ORtg {r['dORtg']:+.2f}  DRtg {r['dDRtg']:+.2f}  net {r['net']:+.2f}")


if __name__ == "__main__":
    main()
