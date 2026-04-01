# SportyBet Virtual Soccer RNG Study

An empirical investigation into whether exploitable patterns exist in SportyBet's Instant Virtual Soccer RNG, specifically in the HT/FT Away/Home ("jackpot") market.

## Final Conclusion (April 1, 2026 — 130,741 matches)

**No exploitable edge exists. The RNG pricing is accurate.**

After 1,469 rounds, 130,741 matches, and 504,951 odds records:
- The primary hypothesis (55-75x bracket edge) failed: p=0.45, ROI=-0.7%
- No odds bracket survives Bonferroni correction for multiple comparisons
- Category differences are real but already priced into the odds
- The 50-55x range is confirmed as slightly -EV (p=0.017)
- The jackpot sequence is random (runs test p=0.66)
- Every "profitable" combination found is a statistical artifact of data snooping

The bookmaker's pricing is well-calibrated. High-AH categories (Club World Cup 1.81%, Germany 1.72%) get lower odds (~56-62x), while low-AH categories (Italy 1.04%, England 1.24%) get higher odds (~83-87x). The category effect is **priced in**.

## Data Summary

| Metric | Phase 1 (Local) | Phase 2 (Server) | Combined |
|--------|-----------------|-------------------|----------|
| Rounds | 576 | 1,469 | 2,045 |
| Matches | 51,109 | 130,741 | 181,850 |
| Market odds | 1,307,480 | 504,951 | 1,812,431 |

## Hypothesis Results

| # | Hypothesis | Result | p-value |
|---|---|---|---|
| H1 | 55-75x bracket has exploitable edge | **NOT SIGNIFICANT** | 0.4545 |
| H2 | Category matters for AH rate | **SIGNIFICANT** (but priced in) | <0.000001 |
| H3 | 50-55x is a dead zone | **SIGNIFICANT** | 0.017 |
| H4 | 100x odds are a trap | **NOT SIGNIFICANT** | 0.321 |
| H5 | AH rate is stable over time | **STABLE** (runs test p=0.66) | — |
| H6 | Edge is in odds not categories | **Category effect is priced in** | — |

## Deployment (CONCLUDED)

The data collection bot ran on a Hetzner server from March 31 to April 1, 2026. Both services (`sportybot`, `sportybot-api`) are now stopped and disabled. The database is archived at `/opt/probodds/sportybet/data/sportybet.db` on the server.

## Project Structure

```
sportybet-instantvirtual/
├── README.md              # This file
├── RESEARCH_PLAN.md       # Full research plan, hypotheses, and deployment guide
├── ANALYSIS.md            # Phase 1 statistical analysis (13 tests)
├── STEADY_STRATEGY.md     # Strategy documentation and post-mortem
├── PLAN.md                # Original implementation plan
├── .env.example           # Credentials template
├── requirements.txt       # Python dependencies
├── src/
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point
│   ├── bot.py             # Playwright browser automation (auto-login, odds scraping)
│   ├── db.py              # SQLite storage layer
│   ├── analyze.py         # Statistical analysis pipeline
│   └── strategies.py      # Betting strategy engine
├── status.py              # CLI status dashboard
├── api.py                 # JSON status API (port 8007)
├── verify_data.py         # Data verification script
├── watchdog.sh            # Process watchdog (kills if hung >10 min)
├── data/                  # Database and browser profile (gitignored)
└── reports/               # Generated reports
```

## Documentation

- [RESEARCH_PLAN.md](RESEARCH_PLAN.md) — Full research plan, hypotheses, data collection plan, and deployment guide
- [ANALYSIS.md](ANALYSIS.md) — Phase 1 statistical analysis with all 13 tests
- [STEADY_STRATEGY.md](STEADY_STRATEGY.md) — Strategy evolution, backtests, post-mortem
- [PLAN.md](PLAN.md) — Original implementation plan

## License

MIT — This is a research project.
