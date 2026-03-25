# SportyBet Virtual Sports RNG Study

**An empirical investigation into whether AI or algorithmic pattern recognition can detect exploitable structure in virtual sports betting outcomes.**

## Hypothesis

Virtual sports on platforms like SportyBet use certified CSPRNGs (Cryptographically Secure Pseudorandom Number Generators) to determine outcomes. If correctly implemented, no polynomial-time algorithm — including deep learning models — can predict future outcomes better than the base rate. The house edge, embedded in the odds, guarantees negative expected value on every bet regardless of strategy.

**This experiment tests that hypothesis with real data.**

## Method

1. **Automated Data Collection** — A Playwright-driven browser bot logs into SportyBet, places minimum-stake (₦10) bets on Instant Virtual Soccer, and records every outcome.
2. **500+ Observations** — Sufficient sample size for meaningful statistical analysis.
3. **Rigorous Statistical Analysis** — Independence tests, distribution analysis, autocorrelation, spectral analysis, and strategy backtesting.
4. **Total Cost** — ~₦5,000 ($3 USD). Science on a budget.

## What We're Testing

| Test | What It Detects | If Found |
|------|----------------|----------|
| Chi-squared goodness-of-fit | Biased outcome distribution | Math model has uneven weights |
| Runs test | Non-random sequencing | Outcomes are not independent |
| Autocorrelation (lag 1-20) | Sequential dependency | Past results influence future ones |
| Spectral analysis (FFT) | Periodic patterns | Cyclic structure in outcomes |
| Mutual information | Any nonlinear dependency | Hidden structure exists |
| Strategy backtesting | Exploitable edge | A betting strategy beats the margin |

## Project Structure

```
sportybet-rng-study/
├── README.md
├── PLAN.md                    # Full implementation plan
├── requirements.txt           # Python dependencies
├── src/
│   ├── __init__.py
│   ├── db.py                  # SQLite storage layer
│   ├── bot.py                 # Playwright browser automation
│   ├── analyze.py             # Statistical analysis pipeline
│   └── strategies.py          # Betting strategy backtester
├── data/
│   └── .gitkeep               # SQLite DB stored here (gitignored)
├── reports/                   # Generated analysis reports
│   └── .gitkeep
└── .gitignore
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run the bot (you log in manually once, then it takes over)
python -m src.bot --bets 500 --stake 10

# Run analysis on collected data
python -m src.analyze

# Backtest strategies against collected data
python -m src.strategies
```

## Expected Outcome

Based on the mathematical analysis: outcomes will be IID (independent and identically distributed), no test will find significant sequential dependency, and the cumulative P&L will converge to approximately -12% of total wagered (the house margin). No strategy will produce positive expected value.

**But we're scientists. We verify, not assume.**

## License

MIT — This is a research project, not a trading system.
