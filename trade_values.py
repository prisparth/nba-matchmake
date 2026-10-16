"""Trade values for players and draft picks, in 2026-27 dollars.

A trade value is the surplus a team expects to get: the wins a player (or pick) will
produce, priced at what wins cost on the market, minus what the team will pay him.

Player:  sum over his remaining contract years (max 4) of
         0.95^t * (wins_t * price_per_win - (salary_t / 1.07^t - minimum salary))
         wins_t   = projected wins above replacement in year t, with his impact moved
                    along the league's aging curve
         salary_t = his actual contract amount for that year; dividing by 1.07^t puts it
                    in today's cap dollars, since the cap grows about 7% a year
Pick:    the same sum for the average player taken at that draft slot, using what nine
         real draft classes (2015-2023 debuts) produced in their first eight seasons:
         rookie-scale years count in full, and years 5-8 count only the part of a star's
         value his max contract can't capture.
"""

import unicodedata

import numpy as np
import pandas as pd

DISCOUNT = 0.95        # a win next year is worth 95% of a win now
STAR_PREMIUM = 1.25        # 3-5 All-Star selections in the last seven seasons
SUPERSTAR_PREMIUM = 1.5    # 6+ All-Star selections in the last seven seasons
LATER_YEARS = {"developing": 0.25, "unproven": 0.0}  # weight on years 2-4 of a cheap contract
CAP_GROWTH = 1.07      # salary cap growth per year, used to deflate future salaries
CAP_2025_26 = 154_647_000
YEARS = ["2026-27", "2027-28", "2028-29", "2029-30"]


def aging_curve(lebron: pd.DataFrame) -> dict:
    """Average change in impact (O + D) from age a to a+1, for players with 500+ minutes
    in both seasons, smoothed with a weighted cubic fit."""
    l = lebron[lebron["NBA ID"].notna()].copy()
    l["nid"] = l["NBA ID"].astype(int)
    l["net"] = l["O-LEBRON"] + l["D-LEBRON"]
    a = l[["nid", "year", "Age", "net", "Minutes"]]
    b = a.assign(year=a.year - 1)
    m = a.merge(b, on=["nid", "year"], suffixes=("", "_n"))
    m = m[(m.Minutes >= 500) & (m.Minutes_n >= 500) & m.Age.between(19, 38)]
    m["d"] = m.net_n - m.net
    m["w"] = np.minimum(m.Minutes, m.Minutes_n)
    g = m.groupby("Age").apply(lambda x: pd.Series({"d": np.average(x.d, weights=x.w), "n": len(x)}), include_groups=False)
    coef = np.polyfit(g.index, g.d, 3, w=np.sqrt(g.n))
    return {int(age): round(float(np.polyval(coef, age)), 3) for age in range(18, 44)}


def price_per_win(lebron: pd.DataFrame, year_sal: pd.DataFrame, cap_2026_27: float) -> float:
    """What teams paid per win above replacement in 2025-26, scaled to the 2026-27 cap.
    Only veterans past their rookie deal (5th season or later) count: rookie-scale pay is
    set by draft slot, not by the market, and would make wins look cheaper than they are."""
    l = lebron[lebron["NBA ID"].notna()].copy()
    l["nid"] = l["NBA ID"].astype(int)
    debut = l.groupby("nid").year.min()
    cur = l[l.year == 2026].merge(year_sal[year_sal.year == 2026][["nba_id", "salary"]], left_on="nid", right_on="nba_id")
    cur = cur[cur.salary > 0]
    floor = cur.salary.quantile(0.05)
    cur = cur[2026 - cur.nid.map(debut) >= 4]
    dpw = (cur.salary - floor).clip(lower=0).sum() / cur.WAR.clip(lower=0).sum()
    return float(dpw * cap_2026_27 / CAP_2025_26)


def draft_history(lebron: pd.DataFrame, year_sal: pd.DataFrame) -> pd.DataFrame:
    """First-round classes rebuilt from rookie contracts: within each debut season,
    players 23 or younger ranked by first-year salary (the rookie scale pays by pick
    order). Returns slot and wins in each of the first eight seasons."""
    l = lebron[lebron["NBA ID"].notna()].copy()
    l["nid"] = l["NBA ID"].astype(int)
    first = l.sort_values("year").groupby("nid").agg(deb=("year", "first"), age=("Age", "first"))
    y = year_sal.merge(first, left_on="nba_id", right_index=True)
    y = y[(y.year == y.deb) & y.salary.notna() & (y.age <= 23) & y.deb.between(2015, 2023)].copy()
    y["slot"] = y.groupby("deb").salary.rank(ascending=False, method="first").astype(int)
    wins = l.groupby(["nid", "year"]).WAR.sum()
    for t in range(8):
        y[f"w{t}"] = [wins.get((n, d + t), 0.0) if d + t <= 2026 else np.nan for n, d in zip(y.nba_id, y.deb)]
    return y


def rookie_scale(salaries: pd.DataFrame) -> np.ndarray:
    """2026 first-round rookie scale by slot (rows 1-30) for its four years, fitted
    log-linearly on this year's first-round rookies."""
    r = salaries[(salaries.nba_id.isna()) & salaries.Age.between(18, 22)]
    r = r[(r[YEARS] > 0).all(axis=1) & (r["2026-27"] >= 2_500_000)].sort_values("2026-27", ascending=False)
    slots = np.arange(1, len(r) + 1)
    out = np.zeros((30, 4))
    for t, col in enumerate(YEARS):
        b, a = np.polyfit(slots, np.log(r[col].values), 1)
        out[:, t] = np.exp(a + b * np.arange(1, 31))
    return out


def pick_curve(hist: pd.DataFrame, scale: np.ndarray, D: float, min_salary: float, cap: float) -> tuple:
    """Value of a 1st-round pick at each slot (drafted today), and of a 2nd-round pick."""
    first = hist[hist.slot <= 30]
    max_ext = 0.25 * cap  # a rookie max extension
    slots = np.arange(1, 31)
    value = np.zeros(30)
    for t in range(8):
        d = first[first[f"w{t}"].notna()]
        if t < 4:
            # rookie-scale years: all of his wins, minus his rookie salary
            b, a = np.polyfit(np.log(d.slot), d[f"w{t}"], 1)
            wins = a + b * np.log(slots)
            value += DISCOUNT ** t * (wins * D - (scale[:, t] / CAP_GROWTH ** t - min_salary))
        else:
            # after the rookie deal he is paid market value, so only a star's value beyond
            # a max contract is surplus; average that per slot band, then fit by log(slot)
            star = np.maximum(0, d[f"w{t}"] * D - max_ext)
            b, a = np.polyfit(np.log(d.slot), star, 1)
            value += DISCOUNT ** t * np.maximum(0, a + b * np.log(slots))
    value = np.minimum.accumulate(value)  # an earlier pick is never worth less than a later one
    second = hist[(hist.slot > 30) & (hist.slot <= 60)]
    # Undrafted players who made a roster sneak into this group, so use the median, not the mean.
    w2 = sum(DISCOUNT ** t * second[f"w{t}"].median() for t in range(2))
    return value, float(max(0.0, w2 * D))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = s.replace(".", "").replace("'", "").replace("-", " ")
    return " ".join(p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"})


def all_star_counts(all_stars: pd.DataFrame) -> dict:
    """All-Star selections per player over the last seven games (2020-2026)."""
    recent = all_stars[all_stars.year >= 2020]
    return recent.player.map(_norm).value_counts().to_dict()


def track_record(lebron: pd.DataFrame) -> tuple:
    """For each NBA ID over the last three seasons: how many seasons he was a clearly
    good player (impact +1.5 or better over 1,500+ minutes), and a stabilized impact:
    a recency-weighted average (3:2:1 by minutes) pulled toward league average by
    the equivalent of 1,500 minutes of last season."""
    l = lebron[lebron.Season.isin(["2023-24", "2024-25", "2025-26"]) & lebron["NBA ID"].notna()].copy()
    l["nid"] = l["NBA ID"].astype(int)
    l["net"] = l["O-LEBRON"] + l["D-LEBRON"]
    l["w"] = l.Season.map({"2023-24": 1, "2024-25": 2, "2025-26": 3}) * l.Minutes
    good = l[(l.net >= 1.5) & (l.Minutes >= 1500)].groupby("nid").size().to_dict()
    stable = l.groupby("nid").apply(lambda d: (d.net * d.w).sum() / (d.w.sum() + 3 * 1500), include_groups=False).to_dict()
    return good, stable


def tier(p: dict, stars: dict, good: dict) -> str:
    n = stars.get(_norm(p["name"]), 0)
    if n >= 6:
        return "superstar"
    if n >= 3:
        return "star"
    young = (p["age"] or 99) <= 23
    if good.get(p["id"], 0) >= 2 or (young and p["o"] + p["d"] >= 1.5 and not p["est"]):
        return "proven"
    return "developing" if young else "unproven"


def player_values(players: list, salaries: pd.DataFrame, aging: dict, D: float, min_salary: float,
                  war_k: float, war_repl: float, games: int, mpg_cap: float, pick1: np.ndarray,
                  stars: dict, good: dict, stable: dict) -> None:
    """Adds 'tv' (trade value, dollars) and 'tier' to every player in place.

    superstar / star: wins are priced 50% / 25% higher.
    proven (2 of the last 3 seasons at +1.5 or better, or one such season at 23 or under): as is.
    developing (23 or under, not yet proven): later years of a cheap contract count a quarter.
    unproven (24 or older): valued on his stabilized impact instead of one season, and only
    the first year of a cheap contract counts, since a team can find a similar player next
    summer. Overpaid years still count against any player in full."""
    by_name = salaries.set_index("Player")
    rookies = salaries[(salaries.nba_id.isna()) & salaries.Age.between(18, 22)]
    rookies = rookies[(rookies[YEARS] > 0).all(axis=1) & (rookies["2026-27"] >= 2_500_000)].sort_values("2026-27", ascending=False)
    rookie_slot = {n: i + 1 for i, n in enumerate(rookies.Player)}
    for p in players:
        p["tier"] = tier(p, stars, good)
        if p["est"]:
            slot = rookie_slot.get(p["name"])
            p["tv"] = round(float(pick1[min(slot, 30) - 1])) if slot else 0
            continue
        premium = {"superstar": SUPERSTAR_PREMIUM, "star": STAR_PREMIUM}.get(p["tier"], 1.0)
        unproven = p["tier"] == "unproven"
        later = LATER_YEARS.get(p["tier"], 1.0)
        row = by_name.loc[p["name"]]
        if isinstance(row, pd.DataFrame):
            row = row[row.Team == p["team"]].iloc[0]
        age_last = (p["age"] or 27) - 1
        impact = stable.get(p["id"], p["o"] + p["d"]) if unproven else p["o"] + p["d"]
        value = 0.0
        for t, col in enumerate(YEARS):
            salary = float(row.get(col, 0) or 0)
            if salary <= 0:
                break
            impact += aging.get(int(age_last + t), 0.0)
            wins = war_k * min(p["mpg"], mpg_cap) * games * (impact + war_repl)
            year = DISCOUNT ** t * (wins * D * premium - (salary / CAP_GROWTH ** t - min_salary))
            if t > 0 and year > 0:
                year *= later
            value += year
        p["tv"] = round(value)
