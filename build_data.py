"""Build the NBA matchmaking dataset.

Pulls every player under contract for 2026-27 (salary, team, position) and every
player's offensive / defensive impact (O-LEBRON / D-LEBRON, points per 100
possessions) plus minutes from the public gabriel1200/site_data repository,
which scrapes Spotrac, NBA.com and BBall Index. Writes:

    data/players.csv            one row per player under contract
    data/teams.csv              one row per team with payroll and room under each line
    data/nba_matchmaking.json   everything the web page needs

Run:  python3 build_data.py            (downloads fresh copies of the source files)
      python3 build_data.py --offline  (reuses raw/ from the last run)
"""

import io
import json
import sys
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

import trade_values as tv

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
OUT = ROOT / "data"
SOURCE = "https://raw.githubusercontent.com/gabriel1200/site_data/master/"
SOURCE_FILES = ["nba_salaries.csv", "lebron.csv", "team_avg.csv", "year_salaries.csv"]

SALARY_SEASON = "2026-27"   # current contracts, held flat for next year
IMPACT_SEASON = "2025-26"   # last completed season of impact data
MIN_MINUTES = 300           # below this, fall back to an earlier season if one has more
MPG_CAP = 36.0              # nobody is projected above this many minutes
GAMES = 70                  # games a healthy player is projected to play, for trade value
MIN_SALARY = 1_360_000      # roughly the 2026-27 minimum salary
TEAM_MINUTES = 240.0        # 5 players x 48 minutes

# Official 2026-27 thresholds (NBA release, June 30, 2026), in dollars.
LINES = {
    "cap": 164_961_000,
    "tax": 200_428_000,
    "apron1": 209_015_000,
    "apron2": 221_686_000,
}

TEAMS = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat", "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks", "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors", "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}

POS_GROUP = {"PG": "G", "SG": "G", "G": "G", "SF": "F", "PF": "F", "F": "F", "C": "C"}


def fetch(offline: bool) -> None:
    RAW.mkdir(exist_ok=True)
    for name in SOURCE_FILES:
        dest = RAW / name
        if offline and dest.exists():
            continue
        with urllib.request.urlopen(SOURCE + name, timeout=60) as r:
            dest.write_bytes(r.read())
        print(f"downloaded {name} ({dest.stat().st_size:,} bytes)")


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = s.replace(".", "").replace("'", "").replace("-", " ")
    parts = [p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(parts)


def pick_impact_rows(lebron: pd.DataFrame) -> pd.DataFrame:
    """One impact row per player: the latest season with MIN_MINUTES+ minutes in the
    last three seasons, otherwise the latest season played."""
    seasons = sorted(lebron.Season.unique())
    recent = seasons[seasons.index(IMPACT_SEASON) - 2: seasons.index(IMPACT_SEASON) + 1]
    lb = lebron[lebron.Season.isin(recent)].copy()
    lb["key"] = lb["NBA ID"].fillna(-1).astype(int).astype(str) + "|" + lb.Player.map(norm_name)
    lb = lb.sort_values(["key", "Season"])
    rows = []
    for _, g in lb.groupby("key"):
        big = g[g.Minutes >= MIN_MINUTES]
        rows.append((big if len(big) else g).iloc[-1])
    return pd.DataFrame(rows)


def main() -> None:
    fetch(offline="--offline" in sys.argv)
    sal = pd.read_csv(RAW / "nba_salaries.csv")
    lebron = pd.read_csv(RAW / "lebron.csv")
    league_ortg = float(pd.read_csv(RAW / "team_avg.csv").set_index("Season").loc[IMPACT_SEASON, "ORtg"])

    # Rookie / no-data default: minutes-weighted average of last season's first-year players.
    cur = lebron[lebron.Season == IMPACT_SEASON]
    first = lebron.groupby("NBA ID").Season.min()
    rook = cur[cur["NBA ID"].map(first) == IMPACT_SEASON]
    w = rook.Minutes
    rookie = {
        "o": float((rook["O-LEBRON"] * w).sum() / w.sum()),
        "d": float((rook["D-LEBRON"] * w).sum() / w.sum()),
        "mpg": float((rook.Minutes / rook.Games).median()),
    }

    imp = pick_impact_rows(lebron)
    by_id = {int(r["NBA ID"]): r for _, r in imp.iterrows() if pd.notna(r["NBA ID"])}
    by_name = {}
    for _, r in imp.sort_values("Season").iterrows():
        by_name[norm_name(r.Player)] = r  # latest season wins

    players, dead = [], {t: 0 for t in TEAMS}
    for _, s in sal.iterrows():
        retired = pd.notna(s.nba_id) and not s.Age > 0 and s[SALARY_SEASON] < 1_000_000  # stretched or retired deals
        if "WAIVED" in str(s.Player).upper() or retired:  # dead money: counts on the cap, never plays
            dead[s.Team] += int(s[SALARY_SEASON])
            continue
        r = None
        if pd.notna(s.nba_id):
            r = by_id.get(int(s.nba_id))
        if r is None:
            r = by_name.get(norm_name(s.Player))
        pos = str(s.Pos)
        if pos not in POS_GROUP and r is not None:
            pos = str(r.Pos)
        if pos not in POS_GROUP:
            pos = "F"
        p = {
            "id": int(s.nba_id) if pd.notna(s.nba_id) else (int(r["NBA ID"]) if r is not None and pd.notna(r["NBA ID"]) else None),
            "name": s.Player,
            "team": s.Team,
            "pos": pos,
            "grp": POS_GROUP[pos],
            "age": int(s.Age) if s.Age and s.Age > 0 else (int(r.Age) + 1 if r is not None and pd.notna(r.Age) else None),
            "salary": int(s[SALARY_SEASON]),
            "years": int(sum(1 for c in ["2026-27", "2027-28", "2028-29", "2029-30", "2030-31", "2031-32", "2032-33"] if s.get(c, 0) and s[c] > 0)),
        }
        if r is not None:
            p.update({
                "o": round(float(r["O-LEBRON"]), 2),
                "d": round(float(r["D-LEBRON"]), 2),
                "mpg": round(float(r.Minutes) / max(float(r.Games), 1), 1),
                "gp": int(r.Games),
                "season": r.Season,
                "arch": r["Offensive Archetype"] if pd.notna(r["Offensive Archetype"]) else "",
                "role": r["Defensive Role"] if pd.notna(r["Defensive Role"]) else "",
                "est": False,
                "matched": r.Player,
            })
        else:
            p.update({"o": round(rookie["o"], 2), "d": round(rookie["d"], 2), "mpg": round(rookie["mpg"], 1),
                      "gp": 0, "season": "", "arch": "", "role": "", "est": True})
        players.append(p)

    # Trade value. LEBRON's wins above replacement are almost exactly
    # k * minutes * (LEBRON - replacement); fit that on last season, then project a
    # healthy season at each player's minutes. Dollars per win = what teams pay
    # above the minimum, divided by the wins it buys.
    fit = cur[cur.Minutes > 200]
    a = fit.Minutes * (fit["O-LEBRON"] + fit["D-LEBRON"])
    k, c = np.linalg.lstsq(np.c_[a, fit.Minutes], fit.WAR, rcond=None)[0]
    war_k, war_repl = float(k), float(c / k)  # WAR = k * min * (o + d + repl)
    for p in players:
        p["war"] = round(war_k * min(p["mpg"], MPG_CAP) * GAMES * (p["o"] + p["d"] + war_repl), 2)
    year_sal = pd.read_csv(RAW / "year_salaries.csv")
    aging = tv.aging_curve(lebron)
    price = tv.price_per_win(lebron, year_sal, LINES["cap"])
    pick1, pick2 = tv.pick_curve(tv.draft_history(lebron, year_sal), tv.rookie_scale(sal), price, MIN_SALARY, LINES["cap"])
    stars = tv.all_star_counts(pd.read_csv(ROOT / "all_stars.csv"))
    good, stable = tv.track_record(lebron)
    tv.player_values(players, sal, aging, price, MIN_SALARY, war_k, war_repl, GAMES, MPG_CAP, pick1, stars, good, stable)
    for p in players:
        p["allstar"] = stars.get(tv._norm(p["name"]), 0)

    # Baseline projected minutes: fill 240 by last season's MPG, best-used players first.
    for team in TEAMS:
        roster = sorted([p for p in players if p["team"] == team], key=lambda p: -p["mpg"])
        left = TEAM_MINUTES
        for p in roster:
            m = min(p["mpg"], MPG_CAP, left)
            p["proj"] = round(m, 1)
            left -= m
        if left > 0.5:  # short-handed roster: scale everyone up, respecting the cap
            used = sum(p["proj"] for p in roster)
            for p in roster:
                p["proj"] = round(min(MPG_CAP, p["proj"] * TEAM_MINUTES / used), 1) if used else 0

    teams = []
    for abbr, name in TEAMS.items():
        roster = [p for p in players if p["team"] == abbr]
        payroll = sum(p["salary"] for p in roster) + dead[abbr]
        o_imp = sum(p["o"] * p["proj"] for p in roster) / 48
        d_imp = sum(p["d"] * p["proj"] for p in roster) / 48
        teams.append({
            "abbr": abbr, "name": name, "payroll": payroll, "dead": dead[abbr], "players": len(roster),
            "ortg": round(league_ortg + o_imp, 1), "drtg": round(league_ortg - d_imp, 1),
            **{f"room_{k}": v - payroll for k, v in LINES.items()},
        })

    OUT.mkdir(exist_ok=True)
    pd.DataFrame(players).to_csv(OUT / "players.csv", index=False)
    pd.DataFrame(teams).to_csv(OUT / "teams.csv", index=False)
    meta = {
        "built": date.today().isoformat(),
        "salarySeason": SALARY_SEASON, "impactSeason": IMPACT_SEASON,
        "leagueORtg": league_ortg, "lines": LINES, "rookie": rookie,
        "mpgCap": MPG_CAP, "source": "github.com/gabriel1200/site_data",
        "war": {"k": war_k, "repl": war_repl, "games": GAMES}, "trade": {"pricePerWin": round(price), "pick1": [round(v) for v in pick1], "pick2": round(pick2),
                  "discount": tv.DISCOUNT, "aging": aging},
    }
    (OUT / "nba_matchmaking.json").write_text(json.dumps({"meta": meta, "teams": teams, "players": players}, separators=(",", ":")))

    template = ROOT / "page_template.html"
    if template.exists():
        page = template.read_text().replace("/*DATA*/null", json.dumps({"meta": meta, "teams": teams, "players": players}, separators=(",", ":")))
        (ROOT / "matchmaker.html").write_text(page)
        print("wrote matchmaker.html")

    est = sum(p["est"] for p in players)
    print(f"{len(players)} players, {len(teams)} teams, {est} without NBA impact data (rookie default used)")


if __name__ == "__main__":
    main()
