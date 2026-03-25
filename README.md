# SportyBet Virtual Sports RNG Study

**An empirical investigation into whether AI or algorithmic pattern recognition can detect exploitable structure in virtual sports HT/FT betting outcomes — with special focus on the Away/Home jackpot (100.00 odds).**

## Hypothesis

Virtual sports on platforms like SportyBet use certified CSPRNGs (Cryptographically Secure Pseudorandom Number Generators) to determine outcomes. If correctly implemented, no polynomial-time algorithm — including deep learning models — can predict future outcomes better than the base rate. The house edge, embedded in the odds, guarantees negative expected value on every bet regardless of strategy.

**This experiment tests that hypothesis with real data, focused on the HT/FT market.**

## Focus: HT/FT Market & The Jackpot

The Half-Time / Full-Time (HT/FT) market has 9 possible outcomes:

| Selection | Meaning | Odds |
|-----------|---------|------|
| Home/Home | Home leads at HT, Home wins FT | Low-mid |
| Home/Draw | Home leads at HT, Draw at FT | Mid-high |
| Home/Away | Home leads at HT, Away wins FT | High |
| Draw/Home | Draw at HT, Home wins FT | Mid |
| Draw/Draw | Draw at HT, Draw at FT | Mid |
| Draw/Away | Draw at HT, Away wins FT | Mid |
| **Away/Home** | **Away leads at HT, Home wins FT** | **100.00** |
| Away/Draw | Away leads at HT, Draw at FT | Mid-high |
| Away/Away | Away leads at HT, Away wins FT | Low-mid |

**Away/Home** is always priced at **100.00 odds** — the jackpot. At implied probability of 1%, we're investigating how often it actually hits and whether there are exploitable patterns.

## Data Collection Strategy

After each round, SportyBet displays ALL results from ALL 8 virtual leagues:
- **England, Spain, Germany, Champions, Italy, African Cup, Euros, Club World Cup**

This means every round gives us 40+ data points for free — no betting required. We scrape these results to build a large dataset rapidly.

## Project Structure

```
sportybet-rng-study/
├── README.md
├── PLAN.md                    # Full implementation plan
├── requirements.txt           # Python dependencies
├── src/
│   ├── __init__.py
│   ├── db.py                  # SQLite storage layer (HT/FT schema)
│   ├── bot.py                 # Playwright result scraper
│   ├── analyze.py             # HT/FT statistical analysis pipeline
│   └── strategies.py          # Jackpot betting strategy backtester
├── data/
│   └── sportybet.db           # SQLite database (gitignored)
└── reports/                   # Generated analysis reports & plots
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Option 1: Scrape results automatically via browser
python -m src.bot

# Option 2: Enter results manually (no browser needed)
python -m src.bot --manual

# Option 3: Inspect page DOM to fix selectors
python -m src.bot --inspect

# Run full HT/FT analysis
python -m src.analyze

# Jackpot-focused analysis only
python -m src.analyze --jackpot

# Backtest jackpot strategies
python -m src.strategies
```

## What We're Testing

| Test | What It Detects | If Found |
|------|----------------|----------|
| Chi-squared goodness-of-fit | Biased HT/FT distribution | Math model has uneven weights |
| Runs test | Non-random jackpot sequencing | Outcomes are not independent |
| Autocorrelation (lag 1-20) | Sequential dependency in jackpots | Past results influence future ones |
| Spectral analysis (FFT) | Periodic jackpot patterns | Cyclic structure exists |
| Transition matrix (9×9) | Outcome memory | Previous result affects next |
| Cross-category correlation | Shared RNG seed | Categories are not independent |
| Strategy backtesting | Exploitable edge | A betting strategy beats the margin |

## Expected Outcome

The jackpot (Away/Home) should occur at approximately 1% (implied by 100.00 odds), uniformly across categories and teams, with no sequential dependency. All betting strategies should converge to negative expected value.

**But we're scientists. We verify, not assume.**

## License

MIT — This is a research project, not a trading system.
