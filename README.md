# SportyBet Virtual Sports RNG Study

An empirical investigation into pattern detection and value betting in SportyBet's Instant Virtual Soccer. Started as an academic study of RNG randomness; evolved into a working pairing-based value betting system.

## Key Findings (31,515 matches)

- The RNG produces **statistically significant biases** across categories (e.g., Italy avg 1.69 goals vs Germany avg 2.39)
- The bookmaker applies a **consistent 5.0% margin** across all markets
- The bookmaker's per-match pricing has **moderate accuracy** (correlation 0.53 with actual rates)
- **Specific team pairings consistently deviate** from bookmaker estimates, creating +EV opportunities
- A pairing-based strategy identifies +EV bets on **~44% of fixtures** with projected **+NGN 6,950/day** at NGN 10 stake

## Project Structure

```
sportybet-rng-study/
+-- README.md                  # This file
+-- PLAN.md                    # Original implementation plan
+-- ANALYSIS.md                # Complete analysis report
+-- STEADY_STRATEGY.md         # Strategy documentation
+-- requirements.txt           # Python dependencies
+-- src/
|   +-- __init__.py
|   +-- __main__.py            # CLI entry point
|   +-- bot.py                 # Playwright browser automation
|   +-- db.py                  # SQLite storage layer
|   +-- analyze.py             # Statistical analysis pipeline
|   +-- strategies.py          # Pairing-based value betting engine
+-- data/
|   +-- sportybet.db           # SQLite database (gitignored)
|   +-- scraped_odds.json      # Real odds data from SportyBet
|   +-- browser_profile/       # Persistent Chromium session
+-- reports/                   # Generated analysis reports
```

## Quick Start

```bash
# Install
pip install -r requirements.txt
playwright install chromium

# Collect data (observe mode - scrape results, no betting)
python -m src bot --rounds 100

# Scrape all market odds from fixtures
python -m src bot --scrape-odds --rounds 3

# Run Steady v2 strategy (pairing-based value betting)
python -m src bot --rounds 0 --steady

# Run statistical analysis
python -m src analyze
```

## Strategy Overview

### Steady v2: Pairing-Based Value Betting

The system evaluates each fixture by comparing the bookmaker's offered odds against the historical win rate for that specific team pairing:

1. **Pre-compute** outcome rates for every (category, home, away) pairing from 31,500+ matches
2. **For each fixture**, scrape O2.5, U2.5, and DD odds from the detail page
3. **Evaluate**: EV = historical_rate x offered_odds - 1
4. **Bet only when EV > 0** and pairing has 8+ matches of history
5. **Prioritize** by EV, cap at 30 bets per round

### Why It Works

The bookmaker prices each match based on perceived team strength, but the virtual soccer RNG doesn't differentiate as sharply as real football. Specific pairings produce outcomes at rates that consistently diverge from the bookmaker's model — and this divergence exceeds the 5% margin.

### Projected Returns

| Stake | Daily (60 rounds) | Monthly |
|-------|-------------------|---------|
| NGN 10 | NGN ~6,950 | NGN ~208,500 |
| NGN 50 | NGN ~34,750 | NGN ~1,042,500 |

## Data Summary

| Metric | Value |
|--------|-------|
| Matches collected | 31,515 |
| Rounds | 355 |
| Categories | 8 |
| Team pairings | 3,932 (2,113 with 8+ history) |
| Odds fixtures scraped | 231 |
| Bookmaker margin | 5.0% |
| Live bets placed | 41 |

## Documentation

- [ANALYSIS.md](ANALYSIS.md) — Complete statistical analysis with all findings
- [STEADY_STRATEGY.md](STEADY_STRATEGY.md) — Strategy documentation, backtest results, implementation details
- [PLAN.md](PLAN.md) — Original implementation plan

## License

MIT — This is a research project.
