# SportyBet Virtual Soccer RNG Study

An empirical investigation into whether exploitable patterns exist in SportyBet's Instant Virtual Soccer RNG, specifically in the HT/FT Away/Home ("jackpot") market.

## Status: Phase 2 — Extended Data Collection (In Progress)

The bot is deployed on a Hetzner server collecting data 24/7. Live status: [probodds.com/sportybot/](https://probodds.com/sportybot/)

### Phase 1 Conclusion (51K matches, March 2026)

The initial study with 51,109 matches found the RNG appears fair and bookmaker pricing accurate across broad categories. 13 statistical tests confirmed randomness and independence. However, a potential edge was identified in the **55-75x odds bracket** for the Away/Home jackpot that was NOT statistically significant with the sample size available. Phase 2 extends data collection to 1,500+ rounds to test this hypothesis with 80% statistical power.

### Phase 2 Goal (Target: 1,500 rounds / ~133K matches)

Test whether the Away/Home hit rate in the 55-75x odds bracket significantly exceeds the implied probability. Current data suggests ~1.74% actual vs ~1.56% implied, which would represent a ~10.6% EV edge — but sample sizes are too small to confirm. Need 30,443 fixtures in the target bracket at 80% power.

## Current Data (Live — updating continuously)

| Metric | Value |
|--------|-------|
| Rounds | 130+ |
| Matches | 11,570+ |
| Jackpots (Away/Home) | 180 (1.56%) |
| HT/FT odds records | 52,119 |
| Away/Home odds records | 5,791 |
| Market odds (all types) | 156,841 |
| Target rounds | 1,500 |
| Est. completion | ~5 days |

## Deployment

The bot runs as a systemd service on the Hetzner server with:
- **Auto-login:** Credentials from `.env` (SPORTYBET_PHONE / SPORTYBET_PASSWORD)
- **HT/FT odds scraping:** Opens each fixture detail page to collect Away/Home odds per round
- **Watchdog:** Kills and restarts if the process hangs for >10 minutes
- **Auto-restart:** systemd `Restart=on-failure` with 30s delay
- **Monitoring:** Live dashboard at [probodds.com/sportybot/](https://probodds.com/sportybot/), JSON API at `/api/sportybot/status`

```bash
# Check status
ssh root@188.34.136.239 "cd /opt/probodds/sportybet && .venv/bin/python status.py"

# Live logs
ssh root@188.34.136.239 "journalctl -u sportybot -f"

# Service control
ssh root@188.34.136.239 "systemctl status|restart|stop sportybot"
```

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
