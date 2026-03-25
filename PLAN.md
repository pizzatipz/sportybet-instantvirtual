# Implementation Plan: SportyBet Virtual Sports RNG Study

## 1. Overview

This document specifies the complete implementation plan for an automated data collection and statistical analysis system targeting SportyBet's Instant Virtual Soccer product.

**Goal**: Empirically determine whether the outcome sequence of SportyBet's instant virtual soccer exhibits any detectable statistical structure that could be exploited by AI/ML models or algorithmic betting strategies.

**Budget**: ₦5,000 (~$3 USD) — 500 bets at ₦10 minimum stake.

---

## 2. Architecture

### 2.1 System Components

```
┌──────────────────────────────────────────────────────┐
│                  User's Browser (Chromium)            │
│  ┌─────────────┐    ┌─────────────┐                  │
│  │  SportyBet   │◄──│  Playwright  │                  │
│  │  Website     │──►│  Controller  │                  │
│  └─────────────┘    └──────┬──────┘                  │
│                            │                          │
└────────────────────────────┼──────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   Data Logger   │
                    │   (Python)      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   SQLite DB     │
                    │   (local)       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Analysis      │
                    │   Pipeline      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Reports       │
                    │   (HTML/plots)  │
                    └─────────────────┘
```

### 2.2 Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Browser automation | Playwright (Python) | Reliable, supports persistent browser contexts |
| Data storage | SQLite | Zero setup, portable, sufficient for 500 rows |
| Analysis | pandas, scipy, numpy, statsmodels | Standard scientific Python |
| Visualization | matplotlib, seaborn | Publication-quality plots |
| CLI | argparse (stdlib) | No extra deps needed |

---

## 3. Data Model

### 3.1 Schema: `bets` Table

```sql
CREATE TABLE IF NOT EXISTS bets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        TEXT,               -- SportyBet's round identifier
    timestamp       TEXT NOT NULL,       -- ISO 8601 UTC timestamp
    league          TEXT,               -- Virtual league name
    home_team       TEXT NOT NULL,      -- Home team name
    away_team       TEXT NOT NULL,      -- Away team name
    market          TEXT NOT NULL,      -- e.g., '1X2', 'Over/Under 2.5'
    selection       TEXT NOT NULL,      -- What we bet on: '1', 'X', '2', 'Over', 'Under'
    odds            REAL NOT NULL,      -- Decimal odds at time of bet
    stake           REAL NOT NULL,      -- Stake in Naira
    result          TEXT,               -- Actual match result: e.g., '2-1'
    home_goals      INTEGER,           -- Home team goals
    away_goals      INTEGER,           -- Away team goals
    outcome         TEXT,               -- '1', 'X', or '2' (derived)
    won             INTEGER,           -- 1 = won, 0 = lost
    payout          REAL DEFAULT 0,    -- Amount returned (0 if lost)
    profit          REAL,              -- payout - stake
    cumulative_pnl  REAL,              -- Running total P&L
    bet_number      INTEGER            -- Sequential bet number (1, 2, 3...)
);
```

### 3.2 Schema: `rounds` Table (Optional Enrichment)

```sql
CREATE TABLE IF NOT EXISTS rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        TEXT UNIQUE,
    timestamp       TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    home_goals      INTEGER,
    away_goals      INTEGER,
    total_goals     INTEGER,
    outcome_1x2     TEXT,              -- '1', 'X', '2'
    home_odds       REAL,
    draw_odds       REAL,
    away_odds       REAL,
    over25_odds     REAL,
    under25_odds    REAL
);
```

---

## 4. Bot Implementation (src/bot.py)

### 4.1 Workflow

```
Phase 1: MANUAL LOGIN
  1. Launch Chromium with persistent profile (so login session persists)
  2. Navigate to SportyBet instant virtuals page
  3. Prompt user: "Please log in manually. Press Enter when ready..."
  4. Verify login by checking for account balance element

Phase 2: AUTOMATED BETTING LOOP (repeat N times)
  1. Wait for a new virtual match to appear
  2. Record: teams, odds for all 1X2 outcomes
  3. Select bet: always bet on a fixed selection (e.g., Home Win '1')
     OR rotate selections systematically for balanced data
  4. Enter stake: ₦10
  5. Place bet
  6. Wait for result to settle (instant virtuals settle in ~60-90 seconds)
  7. Record: final score, outcome, won/lost, payout
  8. Write record to SQLite
  9. Log progress (e.g., "Bet 47/500 | W | 2-1 | PnL: -₦230")
  10. Brief pause (2-5 seconds) before next round

Phase 3: COMPLETION
  1. Print summary stats
  2. Close browser
```

### 4.2 Bet Selection Strategy for Data Collection

For maximum analytical value, we should **rotate selections systematically**:

```
Round 1: Bet Home (1)    — record all odds
Round 2: Bet Draw (X)    — record all odds
Round 3: Bet Away (2)    — record all odds
Round 4: Bet Home (1)    — record all odds
... (repeat)
```

This gives us ~167 observations per 1X2 outcome, enough for chi-squared tests on each.

**Alternative**: Always bet the same selection (e.g., Home). Simpler, and the analysis still works because we record the ACTUAL RESULT regardless of what we bet.

### 4.3 Error Handling

| Error | Recovery |
|-------|----------|
| Bet fails to place | Retry once, then skip and log error |
| Page navigation error | Refresh page, retry |
| Balance too low | Stop gracefully, save all data |
| Element not found | Wait with exponential backoff (max 30s) |
| Session expired | Pause, prompt user to re-login |
| Network error | Wait 10s, retry up to 3 times |

### 4.4 Safety Guardrails

- **Hard stop at N bets** (default 500, configurable)
- **Balance check before each bet** — abort if balance < stake + buffer
- **Rate limiting** — minimum 5-second gap between bets, respect natural round timing
- **Progress saves** — every bet is committed to DB immediately (no data loss on crash)
- **Dry-run mode** — `--dry-run` flag that does everything except actually clicking the "Place Bet" button

---

## 5. Analysis Pipeline (src/analyze.py)

### 5.1 Descriptive Statistics

```
- Total bets, wins, losses
- Win rate per selection (Home/Draw/Away)
- Total wagered, total returned, net P&L
- Actual margin vs theoretical margin
- Average odds per outcome
- Implied probabilities vs observed frequencies
```

### 5.2 Independence Tests

#### 5.2.1 Runs Test (Wald-Wolfowitz)
Tests whether the sequence of outcomes (W/L or 1/X/2) is random. If the number of "runs" (consecutive same-outcome streaks) is significantly different from expected, outcomes are not independent.

```python
from statsmodels.sandbox.stats.runs import runstest_1samp
```

#### 5.2.2 Autocorrelation Analysis
Compute autocorrelation at lags 1 through 20 for:
- Binary win/loss sequence
- Numeric outcome encoding (1=Home, 2=Draw, 3=Away)
- Total goals per round

If any lag shows significant autocorrelation (outside 95% CI), there's sequential dependency.

```python
from statsmodels.tsa.stattools import acf
```

#### 5.2.3 Chi-Squared Goodness-of-Fit
Test whether observed outcome frequencies match the implied probability distribution from the odds.

$$\chi^2 = \sum_{i} \frac{(O_i - E_i)^2}{E_i}$$

Where $O_i$ = observed count, $E_i$ = expected count from implied probabilities.

### 5.3 Pattern Detection

#### 5.3.1 Spectral Analysis (FFT)
Apply Fast Fourier Transform to the outcome sequence to detect periodic patterns (e.g., "Home wins every 7th round").

```python
from scipy.fft import fft
```

#### 5.3.2 Mutual Information
Non-linear dependency measure between consecutive outcomes. Unlike autocorrelation, this detects ANY dependency (not just linear).

```python
from sklearn.metrics import mutual_info_score
```

#### 5.3.3 Transition Matrix
Compute the transition probability matrix: P(outcome_t | outcome_{t-1}).

```
         Next: 1      X      2
Prev: 1  [0.45   0.25   0.30]
      X  [0.44   0.26   0.30]
      2  [0.46   0.24   0.30]
```

If rows are approximately equal, outcomes are memoryless (as expected from RNG).

### 5.4 Strategy Backtesting

Test common virtual sports "strategies" against collected data:

1. **Flat bet Home** — Always bet Home at ₦10
2. **Flat bet Draw** — Always bet Draw at ₦10  
3. **Flat bet Away** — Always bet Away at ₦10
4. **Martingale** — Double stake after loss, reset after win
5. **Anti-streak** — Bet against whatever won last round
6. **Follow-streak** — Bet whatever won last round
7. **Random** — Random selection each round

For each strategy, compute:
- Final P&L
- ROI (%)
- Max drawdown
- Longest losing streak
- Sharpe-like ratio (mean return / std dev)

### 5.5 ML Model Test

Train a simple model on the first 400 outcomes, predict the last 100:

```python
# Features: last N outcomes, lag features, running averages
# Target: next outcome (1/X/2)
# Model: LightGBM classifier
# Metric: accuracy vs base rate, log-loss vs uniform
```

If the model cannot beat the base rate (predicting the most frequent outcome every time), that's strong evidence of CSPRNG-quality randomness.

---

## 6. Reporting (reports/)

### 6.1 Generated Outputs

```
reports/
├── summary.txt              # Plain-text summary statistics
├── outcome_distribution.png # Bar chart: observed vs expected
├── autocorrelation.png      # ACF plot with confidence bands
├── spectral.png             # FFT power spectrum
├── pnl_curve.png            # Cumulative P&L over time
├── transition_matrix.png    # Heatmap of outcome transitions
├── strategy_comparison.png  # Bar chart of strategy ROIs
└── full_report.html         # Combined HTML report
```

---

## 7. CLI Interface

```bash
# Phase 1: Collect data
python -m src.bot --bets 500 --stake 10 --selection rotate
python -m src.bot --bets 100 --stake 10 --selection home --dry-run

# Phase 2: Analyze
python -m src.analyze                    # Full analysis
python -m src.analyze --test independence  # Specific test
python -m src.analyze --export csv       # Export data

# Phase 3: Backtest strategies
python -m src.strategies                 # All strategies
python -m src.strategies --strategy martingale
```

---

## 8. Implementation Order

### Sprint 1: Foundation
- [ ] Project structure, dependencies, gitignore
- [ ] SQLite database layer (`src/db.py`)
- [ ] Basic CLI skeleton

### Sprint 2: Bot
- [ ] Playwright setup with persistent browser context
- [ ] Manual login flow
- [ ] Page navigation to instant virtuals
- [ ] Fixture/odds scraping
- [ ] Bet placement automation
- [ ] Result settlement detection
- [ ] Full betting loop with error handling

### Sprint 3: Analysis
- [ ] Descriptive statistics
- [ ] Chi-squared test
- [ ] Runs test
- [ ] Autocorrelation analysis
- [ ] Spectral analysis (FFT)
- [ ] Transition matrix
- [ ] Mutual information

### Sprint 4: Strategy & Reporting
- [ ] Strategy backtester framework
- [ ] All 7 strategies implemented
- [ ] ML model baseline test
- [ ] Plot generation
- [ ] HTML report generation

---

## 9. Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Minimum stake | ₦10 | Lowest possible cost per observation |
| Number of bets | 500 | Sufficient for chi-squared (>5 per cell), autocorrelation, and spectral analysis |
| Market | 1X2 (Match Result) | Simplest market, 3 outcomes, easiest to analyze |
| Browser | Chromium via Playwright | Best automation support, persistent sessions |
| Database | SQLite | Zero infrastructure, portable, ACID compliant |
| Selection strategy | Rotate (1→X→2→1→...) | Balanced observations per outcome |

---

## 10. What Success Looks Like

### If the RNG is proper (expected):
- Chi-squared p-value > 0.05 (cannot reject uniform distribution)
- All autocorrelation values within 95% CI of zero
- No significant peaks in FFT spectrum
- Transition matrix rows are approximately equal
- All strategies converge to ~-12% ROI
- ML model accuracy ≈ base rate (33-45%)
- **Conclusion: The math was right. House always wins.**

### If the RNG has detectable structure (unexpected but possible):
- Significant autocorrelation at specific lags
- FFT shows periodic peaks
- Transition matrix rows significantly differ
- One or more strategies show positive ROI over 500 bets
- ML model beats base rate significantly (p < 0.01)
- **Conclusion: Further investigation warranted. Collect more data.**

---

*Document version: 1.0 | Created: 2026-03-25*
