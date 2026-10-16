const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, AlignmentType, LevelFormat, Footer, PageNumber,
} = require("docx");

const INK = "16212D", ACCENT = "C8501C", MUTED = "5B6878", RULE = "D5DBE2", WASH = "EEF1F4";
const FONT = "Calibri";

const p = (text, opts = {}) => new Paragraph({ spacing: { after: 120, line: 300 }, ...opts, children: runs(text) });
// **bold** support inside plain strings
function runs(text) {
  if (Array.isArray(text)) return text;
  return text.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map(t =>
    t.startsWith("**") ? new TextRun({ text: t.slice(2, -2), bold: true }) : new TextRun(t));
}
const h1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 320, after: 120 }, children: [new TextRun(t)] });
const h2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 80 }, children: [new TextRun(t)] });
const bullet = t => new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 60, line: 290 }, children: runs(t) });
const step = t => new Paragraph({ numbering: { reference: "steps", level: 0 }, spacing: { after: 60, line: 290 }, children: runs(t) });
const formula = t => new Paragraph({
  spacing: { before: 80, after: 160 }, indent: { left: 360 },
  shading: { type: ShadingType.CLEAR, color: "auto", fill: WASH },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 8 } },
  children: [new TextRun({ text: t, font: "Consolas", size: 20 })],
});

const W = 9360; // 6.5" content width
function table(widths, header, rows) {
  const border = { style: BorderStyle.SINGLE, size: 4, color: RULE };
  const borders = { top: border, bottom: border, left: border, right: border };
  const cell = (t, w, head, right) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders,
    shading: head ? { type: ShadingType.CLEAR, color: "auto", fill: INK } : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: [new Paragraph({ alignment: right ? AlignmentType.RIGHT : AlignmentType.LEFT,
      children: [new TextRun({ text: t, bold: head, color: head ? "FFFFFF" : INK, size: 20 })] })],
  });
  return new Table({
    width: { size: W, type: WidthType.DXA }, columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((t, i) => cell(t, widths[i], true, false)) }),
      ...rows.map(r => new TableRow({ children: r.map((t, i) => cell(t, widths[i], false, false)) })),
    ],
  });
}
const gap = () => new Paragraph({ spacing: { after: 120 }, children: [] });

const body = [
  new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "NBA Matchmaker", bold: true, size: 52, color: INK })] }),
  new Paragraph({
    spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 6 } },
    children: [new TextRun({ text: "How it works", size: 28, color: MUTED })],
  }),

  h1("What the tool does"),
  p("The NBA Matchmaker pairs teams with players they can afford and measures how much each player would change the team's offensive and defensive rating. It has two modes, picked from the buttons at the top of the page:"),
  bullet("**Find players for a team.** Pick a team from the dropdown. The page lists every player on another team whose salary fits in that team's budget, ranked by how much he would improve the team."),
  bullet("**Find teams for a player.** Pick a player from the dropdown. The page ranks the other 29 teams by how much he would improve each one, with the teams that can afford him listed first."),
  bullet("**Trade machine.** Pick your team and the player you want, then choose which of your players and draft picks to send. The page checks whether both payrolls work, how both teams' ratings change, and whether the other team gets fair value back."),
  p("It covers all 30 teams and the 522 players under contract for the 2026-27 season."),

  h1("Step 1: The budget"),
  p("Every team has a payroll: the total of its players' 2026-27 salaries, plus any dead money (salary still owed to players it has waived). Salaries are held flat, so a player is assumed to earn the same amount next year as he does this year. That takes projected raises out of the comparison."),
  p("The budget is the room between the payroll and a spending line you choose. The default is the luxury tax line, since crossing it is the point where spending gets expensive for an owner. The four lines come from the NBA's official 2026-27 figures:"),
  table([4680, 4680], ["Line", "2026-27 amount"], [
    ["Salary cap", "$164.961M"],
    ["Luxury tax (default)", "$200.428M"],
    ["First apron", "$209.015M"],
    ["Second apron", "$221.686M"],
  ]),
  gap(),
  formula("Room = chosen line − team payroll"),
  p("A player is a candidate only if his salary is less than or equal to the room. A team already over the line has no room, so nobody fits. To make room, tick players on the roster to move them out. Their salary is added back to the budget and their minutes are handed to the rest of the roster."),
  p("Players on two-way or non-guaranteed deals have no cap figure for 2026-27, so they are left out of the candidate lists."),

  h1("Step 2: Each player's impact"),
  p("Every player has two impact numbers, both measured in points per 100 possessions:"),
  bullet("**Offensive impact:** how many points per 100 possessions his team scores above average while he is on the floor, after accounting for his teammates and opponents."),
  bullet("**Defensive impact:** how many points per 100 possessions he keeps the opponent below average. Positive means good defense."),
  p("The numbers come from last season (2025-26). Three cases are handled differently:"),
  bullet("**Injured or barely played.** If a player logged under 300 minutes last season, the tool uses his most recent season with 300 or more minutes from the last three years. Tyrese Haliburton, for example, is rated on 2024-25."),
  bullet("**No NBA minutes yet.** Rookies and players returning from overseas get the average impact of last season's first-year players (about −1.1 on offense and −0.3 on defense). The page marks them \"No NBA data\" and hides them from the candidate list unless you tick \"Include players with no NBA minutes.\""),
  bullet("**Projected minutes.** Each player is projected to play his minutes per game from that same season, capped at 36."),

  h1("Step 3: Weighting by minutes"),
  p("A player can only change a team's rating while he is on the floor. A game has 48 minutes, so a player who plays 24 minutes has half the effect of a player who plays all 48. The tool multiplies each impact by the share of the game he plays:"),
  formula("Effect on team rating = impact × minutes ÷ 48"),
  p("This works in both directions. A strong player who plays more moves the rating up by more, and a weak player who plays more drags it down by more."),

  h1("Step 4: Whose minutes he takes"),
  p("A team only has 240 player-minutes per game (5 players × 48 minutes). Adding someone means someone else plays less, so the tool compares the new player against the players he replaces, not against nothing."),
  step("**Current rotation.** The roster's minutes are filled up to 240 using each player's minutes per game, starting with the players who played the most. Players further down the bench get whatever is left, often zero."),
  step("**Same position first.** The new player's minutes come out of players in his position group (guard, forward or center), starting with the lowest-impact player."),
  step("**Then the rest of the rotation.** If his position group doesn't have enough minutes to give up, the remainder comes from the lowest-impact players elsewhere on the roster."),
  p("The change in each rating is then:"),
  formula("ORtg change = (his offense × his minutes − Σ replaced offense × minutes lost) ÷ 48"),
  formula("DRtg change = −(his defense × his minutes − Σ replaced defense × minutes lost) ÷ 48"),
  formula("Net change = ORtg change − DRtg change"),
  p("Defensive rating is points allowed, so lower is better. A negative DRtg change is an improvement, and the page shows it in green."),

  h2("Worked example: Victor Wembanyama to Detroit"),
  p("Detroit's payroll is $154.3M, leaving $46.1M under the tax line. Wembanyama earns $16.9M, so he fits. He is projected at 30.1 minutes, with an offensive impact of +3.66 and a defensive impact of +3.99."),
  p("Detroit's centers are all on the bench in the current rotation, so his 30.1 minutes come from the lowest-impact players in the rotation: 23.5 minutes from Taurean Prince (offense −1.65, defense −0.78) and 6.6 minutes from Elijah Harkless (offense −0.72, defense −0.02)."),
  table([2900, 3230, 3230], ["", "Offense", "Defense"], [
    ["Wembanyama adds", "3.66 × 30.1 = 110.2", "3.99 × 30.1 = 120.1"],
    ["Prince loses", "−1.65 × 23.5 = −38.8", "−0.78 × 23.5 = −18.3"],
    ["Harkless loses", "−0.72 × 6.6 = −4.8", "−0.02 × 6.6 = −0.1"],
    ["Change ÷ 48", "(110.2 + 38.8 + 4.8) ÷ 48 = +3.2", "(120.1 + 18.3 + 0.1) ÷ 48 = +2.9"],
  ]),
  gap(),
  p("Detroit's offensive rating rises by 3.2 (118.0 to 121.2) and its defensive rating falls by 2.9 (113.1 to 110.2). The net change is +6.1 points per 100 possessions, the best of any player Detroit can afford."),

  h1("Step 5: Team ratings"),
  p("The ratings shown for each team are projections built from the same numbers. Each team starts at last season's league-average offensive rating, 115.7, and adds up its players' minute-weighted impacts:"),
  formula("Team ORtg = 115.7 + Σ (offense × minutes) ÷ 48"),
  formula("Team DRtg = 115.7 − Σ (defense × minutes) ÷ 48"),
  p("When you click a candidate, the tiles at the top switch to the team's projected ratings with him added, and the small number beside each tile shows the change."),

  h1("Reading the page"),
  table([2200, 7160], ["Column", "Meaning"], [
    ["Salary", "His 2026-27 salary, held flat for next year"],
    ["Min", "Minutes per game he is projected to play for the new team"],
    ["ORtg", "Change in the team's offensive rating. Positive is better"],
    ["DRtg", "Change in the team's defensive rating. Negative is better"],
    ["Net", "Total improvement: ORtg change minus DRtg change"],
  ]),
  gap(),
  bullet("**Rank by** sorts the list by net change, offense only, defense only, or net change per $10M of salary (best value)."),
  bullet("**Position** narrows the list to guards, forwards or centers."),
  bullet("**Clicking a row** opens the detail: a slider to change his minutes, the team's ratings before and after, and exactly whose minutes he takes."),
  bullet("**Ticking a roster player** moves him out, which frees his salary and minutes and reruns every ranking."),

  h1("Trade machine"),
  p("The trade machine uses the same budget and rating math as the rest of the tool, and adds two things: a check that the money works for both teams, and a trade value for every player and pick so you can judge whether the other team would say yes."),
  h2("1. Does the money work?"),
  p("Each team's payroll after the trade is its payroll before, minus the salary it sends out, plus the salary it takes back. A team passes if it ends at or under your chosen line. A team that ends over the line still passes if it takes back no more than 110% of the salary it sends out, which mirrors the NBA's matching rule for teams above the apron."),
  formula("Payroll after = payroll before − salary sent + salary received"),
  h2("2. How do the ratings change?"),
  p("Each team's outgoing players are removed and their minutes are spread over the rest of the roster. The incoming players are then added one at a time, biggest-minutes player first, taking minutes from the lowest-impact players at their position just as in Step 4. The page shows your team's projected ORtg, DRtg and net rating after the trade, and the net change for the other team."),
  h2("3. Is it fair value?"),
  p("Every player and pick gets a trade value in today's dollars: the wins he is expected to produce, priced at what wins cost on the open market, minus what his team will pay him. The other team is likely to accept when the value you send is at least the value you get back."),
  h2("Player value"),
  p("For each remaining year of his contract (up to four), the tool projects his wins, prices them and subtracts his salary for that year:"),
  formula("Wins = 0.000614 × minutes × 70 games × (impact + 2.51)"),
  formula("Year value = 0.95^t × (wins × $6.67M × premium − (salary ÷ 1.07^t − $1.36M))"),
  formula("Trade value = sum of year values over the contract (max 4 years)"),
  bullet("**Wins.** The formula reproduces last season's wins above replacement almost exactly. Each future year, his impact moves along the league's aging curve, measured from 16 seasons of players who logged 500+ minutes in back-to-back years. A 21-year-old typically gains about +0.5 a year, a 25-year-old holds steady, and a 33-year-old loses about −0.3."),
  bullet("**Price of a win: $6.67M.** This is what teams paid per win last season to veterans past their rookie deals (salary above the minimum divided by wins), scaled up to this year's cap. Rookie contracts are left out because their pay is fixed by draft slot, not set by the market."),
  bullet("**Salary.** His real contract amount for each year, divided by 1.07 per year because the cap grows about 7% a year, which makes the same salary cheaper later. $1.36M, the minimum, is subtracted because a team pays that much even for a replacement-level player."),
  bullet("**Discount.** Each year out counts 5% less than the year before."),
  h2("Star premium and track record"),
  p("Every player is put in one tier. The tier decides whether his wins carry a premium and how many contract years count:"),
  table([1700, 3900, 1500, 2260], ["Tier", "Who", "Premium", "Contract years that count"], [
    ["Superstar", "6 or more All-Star selections in the last seven seasons (2020 to 2026)", "+50%", "All"],
    ["Star", "3 to 5 All-Star selections in the last seven seasons", "+25%", "All"],
    ["Proven", "Impact of +1.5 or better over 1,500+ minutes in 2 of the last 3 seasons (one such season is enough at 23 or under)", "None", "All"],
    ["Developing", "23 or under and not yet proven", "None", "Year 1 in full, later years at 25%"],
    ["Unproven", "24 or older and not proven", "None", "Year 1 only, using his stabilized impact"],
  ]),
  gap(),
  p("The premium multiplies the value of his wins. Real teams pay extra for a proven star, because his wins come in one roster spot and can't be bought on the open market. There are 8 superstars (Jokic, Giannis, LeBron, Donovan Mitchell, Luka, Tatum, Curry and Durant) and 18 stars, including Shai Gilgeous-Alexander, Booker, Brunson and Anthony Edwards."),
  p("The track-record rule keeps cheap long contracts for role players from inflating value. A team can find a similar role player next summer, so only his current year counts as surplus. His value also uses a stabilized impact instead of his last season alone: his last three seasons weighted 3:2:1 by minutes, pulled toward league average by the equivalent of 1,500 minutes. Overpaid years always count against a player in full, whatever his tier."),
  h2("Worked example: Cade Cunningham"),
  p("Cade's impact is +5.38 at 34.5 minutes a game, and he is 25 with four years left on his deal."),
  table([1500, 1700, 1900, 2260, 2000], ["Season", "Projected wins", "Wins × $6.67M", "Salary in today's $", "Year value"], [
    ["2026-27", "11.9", "$79.3M", "$50.1M", "+$30.6M"],
    ["2027-28", "12.0", "$79.8M", "$50.3M", "+$29.3M"],
    ["2028-29", "11.9", "$79.5M", "$50.2M", "+$27.6M"],
    ["2029-30", "11.8", "$78.6M", "$50.0M", "+$25.7M"],
  ]),
  gap(),
  p("His trade value is about $113M. The first version of the tool put him at $16.1M because it held his salary flat, priced a win at the league-wide average of $4.63M (dragged down by cheap rookie deals) and ignored cap growth. A max contract can't pay a player like Cade what his wins are worth on the market, so he is a big positive asset."),
  p("The same math makes some max-contract players negative: if a player's projected wins are worth less than his salary, taking on his contract costs the other team value, even with a star premium. Jaylen Brown and Trae Young are examples."),
  p("Neemias Queta shows the track-record rule at work. He had one strong season (+3.69 over 1,925 minutes) after two seasons as a little-used backup, so he is unproven. His stabilized impact is +1.79, and only this season of his five-year, $2.7M deal counts, so he is worth about $30M instead of $135M."),
  h2("Draft pick value"),
  p("Pick values come from real drafts. The tool rebuilds the first round of nine draft classes (players who debuted from 2015 to 2023) by ranking each year's young debuts by rookie salary, which the rookie scale pays in draft order. For each slot it measures the wins those players produced in their first eight seasons:"),
  bullet("**Years 1 to 4, the rookie deal:** all of the player's wins at $6.67M each, minus the 2026 rookie-scale salary for that slot."),
  bullet("**Years 5 to 8, after the rookie deal:** he is assumed to be paid what he's worth, so only a star's value beyond a max extension (25% of the cap) counts. This is where top picks earn most of their extra value."),
  table([3120, 3120, 3120], ["Slot", "Value if drafted today", "Example"], [
    ["#1", "$52.4M", "Top of the lottery"],
    ["#5", "$28.0M", "Late lottery"],
    ["#10", "$22.7M", "Fringe lottery"],
    ["#20", "$20.0M", "Mid first round"],
    ["#30", "$18.0M", "Last pick of the round"],
  ]),
  gap(),
  p("A future pick isn't tied to one slot. The tool projects where the team will pick from its projected net rating (the worst team picks first). It then averages the value of the slots the pick could land in, with the range widening by 3 slots for every year out. That average is discounted 5% for each year until the pick is made. A 2nd-round pick is worth about $1.4M, based on the median 2nd-round player."),
  p("Players drafted in 2026 who haven't played yet are valued as the pick they were. Players without NBA minutes from other leagues show no value."),
  h2("Suggest a package"),
  p("The Suggest a package button tries every combination of one, two or three of your players. For each one it adds the fewest draft picks (at most four) needed to close any value gap. It keeps only packages where the money works for both teams and the other team gets at least equal value. From those, it picks the one that improves your team's net rating the most, with a small penalty for each pick used."),
  h2("Worked example: Detroit trades for Derrick White"),
  p("Detroit projects to pick around #20. Suggest a package proposes Ebuka Okorie ($4.5M), Chaz Lanier ($2.2M) and Taurean Prince ($3.8M) plus Detroit's 2027, 2028, 2029 and 2032 1st-round picks."),
  table([3400, 2980, 2980], ["", "Detroit", "Boston"], [
    ["Salary sent", "$10.4M", "$30.3M"],
    ["Payroll after", "$174.2M (under the tax)", "$178.8M (under the tax)"],
    ["Value sent", "$102.3M (players $30.4M, picks $71.9M)", "$101.7M (White)"],
    ["Net rating change", "+5.0", "−4.7"],
  ]),
  gap(),
  p("The money works for both teams, Boston gets $0.6M more value than it gives up, and Detroit's net rating improves by 5.0 points per 100 possessions."),

  h1("Where the data comes from"),
  bullet("**Contracts and teams:** Spotrac salary data, as collected by the public github.com/gabriel1200/site_data repository. It was last updated on August 15, 2026, so any signing or trade after that date is missing."),
  bullet("**Impact numbers:** BBall Index's LEBRON metric (its offensive and defensive parts), from the same repository."),
  bullet("**League average and spending lines:** the same repository for the 115.7 league ORtg, and the NBA's June 30, 2026 release for the cap, tax and apron amounts."),

  h1("What it does not account for"),
  bullet("**Full trade rules.** The trade machine uses one simplified matching rule. It ignores roster limits, the second apron's ban on combining salaries, trade exceptions, pick protections and the rule against trading 1st-round picks in back-to-back years."),
  bullet("**Real pick ownership.** Every team is assumed to own all of its own picks from 2027 to 2033."),
  bullet("**Fit and chemistry.** Two strong ball-handlers may overlap in ways the impact numbers can't see."),
  bullet("**Change over time.** Ratings use last season's impact and minutes. Trade values apply the average aging curve, but no individual development or injury risk."),
  bullet("**Star status beyond All-Star votes.** The premium follows All-Star selections only. A player who is a star by impact but hasn't made three All-Star teams, like Cade Cunningham (two) or Victor Wembanyama (two), gets no premium yet."),

  h1("Refreshing the data"),
  p("The code and data live in the project's nba-matchmaking folder. Run these from that folder:"),
  formula("python3 build_data.py            # downloads fresh data, rebuilds the page"),
  formula("python3 matchmaking.py DET       # best fits for Detroit, as text"),
  formula("python3 matchmaking.py --player \"Ty Jerome\""),
];

const doc = new Document({
  creator: "NBA Matchmaker",
  title: "NBA Matchmaker: How It Works",
  styles: {
    default: { document: { run: { font: FONT, size: 22, color: INK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, color: INK, font: FONT }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, color: ACCENT, font: FONT }, paragraph: { outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: "NBA Matchmaker · page ", color: MUTED, size: 18 }), new TextRun({ children: [PageNumber.CURRENT], color: MUTED, size: 18 })] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then(b => {
  fs.writeFileSync(process.argv[2], b);
  console.log("wrote", process.argv[2]);
});
