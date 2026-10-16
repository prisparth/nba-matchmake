# NBA Matchmaker

Pick a team and see which players it can afford and how much each would move its offensive and defensive rating. Or pick a player and see which teams he fits best. The Trade machine lets you send players and draft picks for a target player and checks salary, ratings and trade value for both teams.

## Files

| File | What it is |
| --- | --- |
| `build_data.py` | Downloads salaries and player impact, builds `data/` and `matchmaker.html` |
| `trade_values.py` | Player and draft-pick trade values: aging curve, market price of a win, pick values from past drafts, All-Star tiers |
| `all_stars.csv` | All-Star selections 2020-2026 (Basketball-Reference and Wikipedia rosters, injury replacements included) |
| `matchmaking.py` | Same matchmaking logic as the page, as a Python CLI/module |
| `page_template.html` | The web page; `build_data.py` inlines the data into it |
| `index.html` | The built page, served by GitHub Pages |
| `data/players.csv` | 522 players under contract for 2026-27: salary, position, O/D impact, minutes |
| `data/teams.csv` | 30 teams: payroll (dead money included), room under each line, projected ratings |
| `data/nba_matchmaking.json` | Everything the page uses |
| `NBA_Matchmaker_How_It_Works.docx` | Plain-language guide to the model, including the trade machine |
| `make_doc.js` | Builds the Word guide (`node make_doc.js NBA_Matchmaker_How_It_Works.docx`) |

## Rebuild

```
python3 build_data.py              # fresh download, rebuilds data/ and matchmaker.html (copy it to index.html for GitHub Pages)
python3 matchmaking.py DET         # best fits for Detroit under the tax line
python3 matchmaking.py BOS --line apron1
python3 matchmaking.py --player "Ty Jerome"
```

## Model

- **Salary**: 2026-27 contract amount, held flat for next year.
- **Impact**: O-LEBRON and D-LEBRON (points per 100 possessions) from 2025-26. If a player had under 300 minutes, his most recent season with 300+ minutes in the last three is used (covers injured players such as Tyrese Haliburton). Players with no NBA minutes get the minutes-weighted average of last season's first-year players.
- **Minutes weighting**: a team rating moves by impact x minutes / 48. A new player gets last season's MPG (capped at 36). His minutes come out of the roster: same position group (guard / forward / center) first, lowest-impact players first, then the rest of the rotation.
- **Budget**: room = line - payroll. Default line is the luxury tax ($200.428M). Lines from the NBA's June 30, 2026 release: cap $164.961M, tax $200.428M, first apron $209.015M, second apron $221.686M.

## Sources

The cloud machine this was built on can't reach stats.nba.com, Basketball-Reference or Spotrac, so the data comes from the public repository github.com/gabriel1200/site_data, which scrapes Spotrac (contracts) and BBall Index (LEBRON). Its last update was August 15, 2026, so moves after that date are missing. Two-way deals carry no cap figure and are left out of the candidate lists.
