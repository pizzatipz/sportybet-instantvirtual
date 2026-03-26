# SportyBet Virtual Soccer RNG Study

An empirical investigation into whether exploitable patterns exist in SportyBet's Instant Virtual Soccer RNG.

## Final Conclusion

**The RNG is fair and the bookmaker's pricing is accurate. No exploitable edge exists.**

After 51,109 matches, 1,007 live bets, and 14,168 odds records:
- 13 statistical tests all confirm randomness and independence
- Bookmaker margin is exactly 5.0% across all categories and match types
- Bookmaker calibration error is < 1 percentage point
- Live betting ROI converged to -5.0% (exactly the house edge)
- Every strategy attempted (jackpot, category-level, pairing-level) converged to the house edge

## What Was Tested

| Test | Result |
|------|--------|
| Autocorrelation (lag 1-5) | No dependency (all < 0.035) |
| Runs test | Random sequence |
| Cross-category correlation | Independent (r < 0.08) |
| Streak analysis | No pattern after droughts |
| Poisson goal fit | Matches within 1.04pp |
| Home/Away independence | Correlation < 0.03 |
| Time-of-day patterns | None detected |
| Bookmaker calibration | Max error 0.9pp |
| Pairing-level edges | Regression to mean eliminated all |
| Live betting (1,007 bets) | -5.0% ROI |

## Project Structure

```
sportybet-rng-study/
├── README.md              # This file
├── ANALYSIS.md            # Complete final analysis (13 tests)
├── STEADY_STRATEGY.md     # Strategy documentation and post-mortem
├── PLAN.md                # Original research plan
├── requirements.txt       # Python dependencies
├── src/
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point
│   ├── bot.py             # Playwright browser automation
│   ├── db.py              # SQLite storage layer
│   ├── analyze.py         # Statistical analysis pipeline
│   └── strategies.py      # Betting strategy engine
├── data/                  # Database and odds (gitignored)
└── reports/               # Generated reports
```

## Data Collected

| Metric | Value |
|--------|-------|
| Matches | 51,109 |
| Rounds | 576 |
| Categories | 8 |
| Live bets | 1,007 |
| 1X2 odds records | 14,168 |
| Unique pairings | 3,296 |

## Documentation

- [ANALYSIS.md](ANALYSIS.md) — Complete statistical analysis with all 13 tests
- [STEADY_STRATEGY.md](STEADY_STRATEGY.md) — Strategy evolution, backtests, post-mortem
- [PLAN.md](PLAN.md) — Original implementation plan

## License

MIT — This is a research project.
