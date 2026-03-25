# Steady Strategy — Complete Documentation

## Overview

The Steady Strategy is a low-variance, high-consistency betting approach for SportyBet Instant Virtual Soccer. It targets two markets with proven statistical edges:

1. **Draw/Draw (HT/FT)** in Italy and England categories
2. **Over 2.5 Goals (O/U)** in Germany and Champions categories

**Backtested performance (30,189 matches / 340 rounds):**
- ROI: **+22.3%**
- Win rate: **32.9%** (1 in 3 bets wins)
- Winning rounds: **74%** (profit in 3 out of 4 rounds)
- Max losing streak: **24 bets** (vs 280 for jackpot strategy)
- Max drawdown: **NGN 468** at NGN 10/bet (vs NGN 4,940 for jackpot)

---

## Why It Works

### Draw/Draw in Italy & England

The RNG produces significantly more draws in Italy (32.8% draw rate) and England (32.3%) compared to other categories. When both halves are draws (Draw/Draw = HT/FT outcome), the rate is:

| Category | Draw/Draw Rate | Typical Odds | Edge |
|----------|---------------|-------------|------|
| **Italy** | **25.8%** | ~5.0 | **+29.2%** |
| **England** | **24.4%** | ~5.0 | **+22.0%** |

These categories are "goal deserts" — average goals per match:
- Italy: 1.68 goals (lowest)
- England: 1.76 goals (second lowest)

This is exploitable because Draw/Draw odds (~5.0) imply a 20% probability, but the actual rate is 24-26%.

### Over 2.5 Goals in Germany & Champions

These are "goal-fest" categories with elevated scoring:

| Category | Over 2.5 Rate | Typical Odds | Edge |
|----------|--------------|-------------|------|
| **Germany** | **42.1%** | ~2.90 | **+22.0%** |
| **Champions** | **40.0%** | ~2.90 | **+15.9%** |

Average goals per match:
- Germany: 2.39 goals (highest)
- Champions: 2.28 goals

Over 2.5 odds (~2.90) imply a 34.5% probability, but actual rates are 40-42%.

### Statistical Significance

All edges are verified with Z-tests against 30,000+ matches:
- Germany Over 2.5: Z = +4.27 (p < 0.001)
- Italy Draw/Draw: Z = +4.85 (p < 0.001)
- England Draw/Draw: Z = +3.51 (p < 0.001)
- Champions Over 2.5: Z = +3.38 (p < 0.001)

---

## What To Bet On

### Per Category

| Category | Market | Selection | Expected Win Rate |
|----------|--------|-----------|------------------|
| **Italy** | HT/FT | **Draw/ Draw** | ~25.8% |
| **England** | HT/FT | **Draw/ Draw** | ~24.4% |
| **Germany** | O/U | **Over 2.5** | ~42.1% |
| **Champions** | O/U | **Over 2.5** | ~40.0% |

### What NOT To Bet On

- **Spain, African Cup, Euros, Club World Cup**: Not included in Steady (use jackpot strategy separately if desired)
- **Over 2.5 in Italy or England**: Negative edge (-25% to -30%)
- **Draw/Draw in Germany or Champions**: Lower rate, no edge
- Any market in Italy/England OTHER than Draw/Draw

---

## How The Bot Places Bets

### Flow Per Fixture

1. **Click category tab** (Italy/England/Germany/Champions) at the top of the betting screen
2. **Click fixture row** (e.g., "ROM vs JUV") → opens match detail page
3. **Navigate to the correct market section**:
   - For Italy/England: Scroll to **HT/FT** section, click **"Draw/ Draw"**
   - For Germany/Champions: Find **O/U** section, click **Over** on the **2.5** line
4. **Place Bet** → inline betslip appears automatically
5. **Confirm** → `#confirm-btn` button
6. **Go back** to betting list
7. Repeat for next fixture

### Flow Per Round

1. Scrape all 77 fixtures on betting screen
2. Filter to Italy (10), England (10), Germany (9), Champions (10) = 39 fixtures
3. Cap at 30 bets (SportyBet limit)
4. Place bets on each fixture using category-tab navigation
5. Click **Open Bets** (bottom left)
6. Click **Kick Off** (bottom right)
7. Click **Skip to Result**
8. Dismiss win splash (`#winngin-pop`) if present
9. Scrape all 89 match results
10. Click **Next Round**
11. Repeat

### CLI Command

```bash
# Start Steady strategy
python -m src bot --rounds 0 --steady

# With round limit
python -m src bot --rounds 100 --steady
```

---

## DOM Selectors

### O/U Market (Over 2.5)

```
div.market
  span[data-op="event_detail__market"].text → "O/U"
  div.market__content
    div.specifier-row (one per line: 0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
      div.specifier-column-title
        em → "2.5" (line number)
      div.iw-outcome[0] → Over odds (e.g., "2.91")
      div.iw-outcome[1] → Under odds (e.g., "1.42")
```

To select Over 2.5:
1. Find the `.specifier-row` where the title `em` contains "2.5"
2. Click the **first** `.iw-outcome` in that row (the Over side)

### HT/FT Market (Draw/Draw)

```
div.market
  span[data-op="event_detail__market"].text → "HT/FT"
  div.market__content
    div.m-table-row (×3, with 3 outcomes each)
      div.iw-outcome.m-outcome-odds-des
        em → "Draw/ Draw" (label)
        em → "4.13" (odds)
```

To select Draw/Draw:
1. Find the HT/FT market by header text
2. Find the `.iw-outcome` where the first `em` text is "Draw/ Draw"
3. Click it

### Common Elements

- **Place Bet**: `span[data-cms-key="place_bet"]` (click with `force=True`)
- **Confirm**: `#confirm-btn` (click with `force=True`)
- **Open Bets**: `.nav-bottom-left .action-button-sub-container` (click with `force=True`)
- **Kick Off**: `.nav-bottom-right` with text "Kick Off"
- **Skip to Result**: Element with text containing "Skip" + "Result"
- **Win splash**: `#winngin-pop` — hide with `display:none`
- **Category tabs**: `li.sport-type-item` (click to switch categories)
- **Back button**: `[data-op='iv-header-back-icon']` or `.m-left-icon`

---

## Staking & Bankroll

### Recommended Starting Configuration

| Parameter | Value |
|-----------|-------|
| Starting stake | NGN 10 per bet |
| Starting bankroll | NGN 1,500 (conservative) |
| Bets per round | ~30 (capped) |
| Rounds per day | ~60 (at 50s/round) |

### Profit Projections

| Stake | Bankroll | Daily Profit | Monthly Profit | Max Drawdown |
|-------|---------|-------------|----------------|-------------|
| NGN 10 | NGN 1,170 | NGN 5,194 | NGN 155,816 | NGN 468 |
| NGN 20 | NGN 2,340 | NGN 10,388 | NGN 311,633 | NGN 936 |
| NGN 50 | NGN 5,850 | NGN 25,969 | NGN 779,082 | NGN 2,340 |
| NGN 100 | NGN 11,700 | NGN 51,939 | NGN 1,558,165 | NGN 4,680 |

### Scaling Rules

1. Start at NGN 10/bet
2. After bankroll grows 2x → increase stake 50%
3. Never increase stake after a loss
4. If drawdown exceeds 2x historical max → pause and re-analyze

---

## Adaptive Learning

The bot's learning system monitors:
- Draw/Draw rate per category (every 10 rounds)
- Over 2.5 rate per category (every 10 rounds)
- Recent trend vs all-time average

### Edge Decay Detection

If any of these thresholds are breached, the strategy should be paused:
- Italy Draw/Draw drops below 22% (currently 25.8%)
- England Draw/Draw drops below 20% (currently 24.4%)
- Germany Over 2.5 drops below 38% (currently 42.1%)
- Champions Over 2.5 drops below 36% (currently 40.0%)

### RNG Change Response

SportyBet could change their RNG at any time. Signs to watch for:
- Sudden shift in category rates (>3% in 50 rounds)
- New categories added or existing ones restructured
- Odds structure changes (e.g., Draw/Draw odds drop from 5.0 to 3.5)

The bot collects data continuously — any change will show up in the stats within 20-30 rounds.

---

## Comparison: Steady vs Jackpot Strategy

| Metric | Steady | Jackpot (--bet) |
|--------|--------|----------------|
| Market | DD + O2.5 | HT/FT Away/Home |
| Win rate | 32.9% | 1.7% |
| Max losing streak | 24 bets | 280 bets |
| Max drawdown (NGN 10) | NGN 468 | NGN 4,940 |
| Daily profit (NGN 10) | NGN 5,194 | NGN 6,792 |
| Winning rounds | 74% | 47% |
| Bankroll needed | NGN 1,170 | NGN 12,350 |
| Psychological difficulty | Easy | Very Hard |
| Risk of ruin | Very Low | Moderate |

**Steady wins on consistency.** Jackpot wins on maximum daily profit but requires 10x more bankroll and tolerance for long losing streaks.

**Optimal approach**: Run both simultaneously on the same account — Steady bets provide the reliable base income, while jackpot bets provide occasional big spikes.

---

## Key Functions (src/bot.py)

| Function | Purpose |
|----------|---------|
| `select_over_under(page, line, over)` | Click Over or Under for any O/U line |
| `select_htft_outcome(page, selection)` | Click any HT/FT outcome (e.g., "Draw/ Draw") |
| `place_steady_bet(page, cat, home, away)` | Full bet flow for one fixture |
| `place_strategic_bets(page, fixtures)` | Multi-fixture jackpot betting |
| `click_place_bet(page)` | Click Place Bet button |
| `click_confirm(page)` | Click Confirm (#confirm-btn) |
| `click_kick_off(page)` | Click Kick Off |
| `click_skip_to_result(page)` | Click Skip to Result |
| `dismiss_win_splash(page)` | Hide #winngin-pop overlay |
| `learn_from_data(conn)` | Re-analyze DB and update strategy targets |
| `fixture_matches_strategy(fixture)` | Check if fixture qualifies for jackpot strategy |

---

## Files

| File | Purpose |
|------|---------|
| `src/bot.py` | Main bot — all betting logic, DOM interaction, strategies |
| `src/db.py` | SQLite storage — matches, rounds, odds, bets |
| `src/analyze.py` | Statistical analysis pipeline |
| `src/strategies.py` | Strategy backtesting framework |
| `full_strategy.py` | Comprehensive strategy analysis (run for latest numbers) |
| `deep_alpha.py` | Cross-market alpha search (found DD + O2.5 edges) |
| `multi_strategy.py` | Multi-market strategy simulation |
| `ANALYSIS.md` | Full research report (14 sections) |
| `STEADY_STRATEGY.md` | This document |

---

*Document created March 25, 2026. Based on 30,189 matches across 340 rounds. All statistics verified from SQLite database.*
