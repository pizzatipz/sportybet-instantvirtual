# Implementation Plan: SportyBet Virtual Sports RNG Study

## 1. Overview

This document specifies the complete implementation plan for an automated data collection and statistical analysis system targeting SportyBet's Instant Virtual Soccer product.

**Primary Focus**: The **Half-Time / Full-Time (HT/FT)** market, with special interest in the **Away/Home** outcome (always priced at **100.00 odds** — the jackpot).

**Goal**: Empirically determine whether the HT/FT outcome distribution of SportyBet's instant virtual soccer exhibits any detectable statistical structure, with particular focus on:
1. How often the Away/Home (100.00 odds) jackpot actually occurs
2. Which teams and categories produce it
3. Whether the RNG shows any exploitable patterns across all 9 HT/FT selections

**Data Collection Strategy**: Instead of placing bets to collect data (expensive), we exploit the fact that **after each round, SportyBet displays ALL results from ALL categories and ALL teams** — not just the ones we bet on. This means each round yields ~40+ data points across 8 categories, allowing rapid data accumulation at near-zero cost.

**Budget**: ₦5,000 (~$3 USD) — minimal bets to validate predictions, bulk data from observation.

---

## 2. HT/FT Market Structure

### 2.1 Selections (9 outcomes)

| Selection | Meaning | Typical Odds |
|-----------|---------|-------------|
| Home/Home | Home leads at HT, Home wins FT | Low-mid |
| Home/Draw | Home leads at HT, Draw at FT | Mid-high |
| Home/Away | Home leads at HT, Away wins FT | High |
| Draw/Home | Draw at HT, Home wins FT | Mid |
| Draw/Draw | Draw at HT, Draw at FT | Mid |
| Draw/Away | Draw at HT, Away wins FT | Mid |
| Away/Home | Away leads at HT, Home wins FT | **100.00** (jackpot) |
| Away/Draw | Away leads at HT, Draw at FT | Mid-high |
| Away/Away | Away leads at HT, Away wins FT | Low-mid |

### 2.2 Categories (8 virtual leagues)

| Category | Description |
|----------|-------------|
| England | English virtual league |
| Spain | Spanish virtual league |
| Germany | German virtual league |
| Champions | Champions League virtual |
| Italy | Italian virtual league |
| African Cup | African Cup virtual |
| Euros | European Championship virtual |
| Club World Cup | Club World Cup virtual |

Each category runs multiple fixtures per round. After a round completes, results for ALL fixtures across ALL 8 categories are displayed simultaneously.

---

## 3. Architecture

### 3.1 System Components

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
                    │  Result Scraper │
                    │   (Python)      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   SQLite DB     │
                    │   (local)       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  HT/FT Analysis │
                    │   Pipeline      │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   Reports       │
                    │   (HTML/plots)  │
                    └─────────────────┘
```

### 3.2 Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Browser automation | Playwright (Python) | Reliable, supports persistent browser contexts |
| Data storage | SQLite | Zero setup, portable, thousands of rows |
| Analysis | pandas, scipy, numpy, statsmodels | Standard scientific Python |
| Visualization | matplotlib, seaborn | Publication-quality plots |
| CLI | argparse (stdlib) | No extra deps needed |

---

## 4. Data Model

### 4.1 Schema: `rounds` Table

```sql
CREATE TABLE IF NOT EXISTS rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        TEXT NOT NULL UNIQUE,
    timestamp       TEXT NOT NULL,       -- ISO 8601 UTC
    scraped_at      TEXT NOT NULL        -- When we scraped this round
);
```

### 4.2 Schema: `matches` Table (core data — scraped from results screen)

```sql
CREATE TABLE IF NOT EXISTS matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        TEXT NOT NULL,
    category        TEXT NOT NULL,       -- England, Spain, Germany, Champions, Italy, African Cup, Euros, Club World Cup
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    ht_home_goals   INTEGER NOT NULL,    -- Half-time home goals
    ht_away_goals   INTEGER NOT NULL,    -- Half-time away goals
    ft_home_goals   INTEGER NOT NULL,    -- Full-time home goals
    ft_away_goals   INTEGER NOT NULL,    -- Full-time away goals
    ht_result       TEXT NOT NULL,       -- 'Home', 'Draw', 'Away'
    ft_result       TEXT NOT NULL,       -- 'Home', 'Draw', 'Away'
    htft_result     TEXT NOT NULL,       -- 'Home/Home', 'Away/Home', etc.
    is_jackpot      INTEGER DEFAULT 0,   -- 1 if Away/Home (the 100.00 odds outcome)
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);
```

### 4.3 Schema: `htft_odds` Table (odds snapshot if available)

```sql
CREATE TABLE IF NOT EXISTS htft_odds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        TEXT NOT NULL,
    category        TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    home_home       REAL,
    home_draw       REAL,
    home_away       REAL,
    draw_home       REAL,
    draw_draw       REAL,
    draw_away       REAL,
    away_home       REAL,               -- Always 100.00?
    away_draw       REAL,
    away_away       REAL,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);
```

### 4.4 Schema: `bets` Table (for any validation bets we place)

```sql
CREATE TABLE IF NOT EXISTS bets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    round_id        TEXT,
    timestamp       TEXT NOT NULL,
    category        TEXT,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    market          TEXT DEFAULT 'HT/FT',
    selection       TEXT NOT NULL,       -- e.g., 'Away/Home'
    odds            REAL NOT NULL,
    stake           REAL NOT NULL,
    htft_result     TEXT,               -- Actual HT/FT result
    won             INTEGER,
    payout          REAL DEFAULT 0,
    profit          REAL,
    FOREIGN KEY (round_id) REFERENCES rounds(round_id)
);
```

---

## 5. Bot Implementation (src/bot.py)

### 5.1 Workflow — Result Scraping Mode (Primary)

```
Phase 1: MANUAL LOGIN
  1. Launch Chromium with persistent profile
  2. Navigate to SportyBet instant virtuals page
  3. Prompt user: "Please log in and navigate to virtual soccer. Press Enter when ready..."

Phase 2: AUTOMATED RESULT SCRAPING LOOP
  1. Wait for current round to complete
  2. When results screen appears (shows ALL categories, ALL teams):
     a. Scrape every match result from every category
     b. For each match, extract: category, home team, away team, HT score, FT score
     c. Derive: ht_result, ft_result, htft_result, is_jackpot
     d. Write all records to SQLite
     e. Log: "Round {id} | {n} matches scraped | {j} jackpots found"
  3. Wait for next round to complete
  4. Repeat

Phase 3: COMPLETION
  1. Print summary: total rounds, total matches, jackpot count
  2. Close browser
```

### 5.2 Workflow — Observation + Betting Mode (Secondary)

Same as above, but also places occasional bets on Away/Home to validate findings.

### 5.3 Error Handling

| Error | Recovery |
|-------|----------|
| Results page not loading | Wait with exponential backoff (max 30s) |
| Partial results scraped | Log warning, save what we have, retry |
| Page navigation error | Refresh page, retry |
| Session expired | Pause, prompt user to re-login |
| Network error | Wait 10s, retry up to 3 times |
| Duplicate round detected | Skip (idempotent writes) |

### 5.4 Safety Guardrails

- **Hard stop at N rounds** (configurable)
- **Progress saves** — every match committed to DB immediately
- **Duplicate detection** — skip already-scraped rounds
- **Rate limiting** — respect natural round timing, no aggressive polling

---

## 6. Analysis Pipeline (src/analyze.py)

### 6.1 Descriptive Statistics — HT/FT Focus

```
Overall:
- Total rounds scraped, total matches recorded
- HT/FT outcome distribution across all matches (9-way breakdown)
- Away/Home (jackpot) frequency: observed vs implied (1/100 = 1%)
- Jackpot frequency by category
- Jackpot frequency by team pairing
- Teams most frequently involved in jackpots

Per Category:
- HT/FT distribution for each of the 8 categories
- Category-specific jackpot rates
- Most common HT/FT outcomes per category

Per Team:
- Which teams produce Away/Home results most often (both as home and away)
- Team-specific HT/FT tendencies
```

### 6.2 Jackpot Deep Dive

```
- Total jackpots observed vs expected (at 1% implied probability)
- Time between jackpots (inter-arrival distribution)
- Jackpot clustering: do they bunch up or spread evenly?
- Which category-team combinations have produced the most jackpots?
- Conditional probabilities: P(jackpot | category), P(jackpot | team), P(jackpot | previous round had jackpot)
- Score patterns in jackpots: what are the typical HT and FT scores?
```

### 6.3 Independence Tests

#### 6.3.1 Chi-Squared Goodness-of-Fit
Test whether observed HT/FT frequencies match implied probabilities from odds.

$$\chi^2 = \sum_{i=1}^{9} \frac{(O_i - E_i)^2}{E_i}$$

Applied per-category and across all categories combined.

#### 6.3.2 Runs Test (Wald-Wolfowitz)
Tests whether the sequence of jackpot/non-jackpot outcomes is random within each category.

#### 6.3.3 Autocorrelation Analysis
Compute autocorrelation at lags 1-20 for:
- Binary jackpot/non-jackpot sequence (per category)
- HT/FT outcome encoding (per category)
- Cross-category: does a jackpot in one category predict jackpots in others?

### 6.4 Pattern Detection

#### 6.4.1 Spectral Analysis (FFT)
Detect periodic patterns in jackpot occurrences. E.g., "jackpot every N rounds."

#### 6.4.2 Transition Matrix (9x9)
P(htft_outcome_t | htft_outcome_{t-1}) for each category. If rows differ, outcomes are not memoryless.

#### 6.4.3 Cross-Category Correlation
Do categories share the same RNG seed? Test whether jackpots in different categories are correlated within the same round.

#### 6.4.4 Mutual Information
Non-linear dependency between consecutive HT/FT outcomes.

### 6.5 Strategy Backtesting (src/strategies.py)

Test strategies specifically for the Away/Home jackpot bet:

1. **Flat bet every round** — Bet Away/Home on every match (baseline)
2. **Category-specific** — Only bet in the category with highest observed jackpot rate
3. **Team-specific** — Only bet when specific teams play (if patterns found)
4. **After-drought** — Bet after N consecutive non-jackpot rounds in a category
5. **Cross-category signal** — Bet when another category just had a jackpot
6. **Martingale on jackpot** — Double stake after each loss, reset on jackpot
7. **Kelly criterion** — Size bets based on estimated edge (if any)

For each strategy, compute:
- Final P&L, ROI (%)
- Hit rate (jackpots caught / total bets)
- Max drawdown, longest losing streak
- Expected value per bet

### 6.6 ML Model Test

```python
# Features per match:
#   - Category (one-hot)
#   - Home/away team embeddings (or one-hot)
#   - Previous N outcomes in same category
#   - Round number within session
#   - Cross-category outcomes from same round
# Target: is_jackpot (binary)
# Model: LightGBM, logistic regression
# Test: can it beat the 1% base rate?
```

---

## 7. Reporting (reports/)

### 7.1 Generated Outputs

```
reports/
├── summary.txt                  # Overall statistics
├── htft_distribution.png        # 9-way HT/FT outcome frequencies (all data)
├── htft_by_category.png         # HT/FT distribution per category (8 subplots)
├── jackpot_frequency.png        # Jackpot rate by category
├── jackpot_teams.png            # Teams most involved in Away/Home results
├── jackpot_interarrival.png     # Time between jackpots histogram
├── jackpot_scores.png           # Common HT→FT score lines for jackpots
├── autocorrelation.png          # ACF plot for jackpot sequence
├── spectral.png                 # FFT power spectrum
├── transition_matrix.png        # 9x9 HT/FT transition heatmap
├── cross_category.png           # Cross-category jackpot correlation
├── strategy_comparison.png      # Strategy P&L comparison
└── full_report.html             # Combined HTML report with all findings
```

---

## 8. CLI Interface

```bash
# Phase 1: Scrape results (primary data collection — no betting required)
python -m src.bot --rounds 100                # Scrape 100 rounds of results
python -m src.bot --rounds 0                  # Run indefinitely until stopped

# Phase 2: Analyze collected data
python -m src.analyze                         # Full analysis
python -m src.analyze --jackpot               # Jackpot-focused analysis only
python -m src.analyze --category England      # Single category analysis
python -m src.analyze --export csv            # Export data to CSV

# Phase 3: Backtest strategies
python -m src.strategies                      # All strategies
python -m src.strategies --strategy drought   # Specific strategy
```

---

## 9. Implementation Order

### Sprint 1: Foundation
- [x] Project structure, dependencies, gitignore
- [ ] SQLite database layer (`src/db.py`)
- [ ] Basic CLI skeleton

### Sprint 2: Result Scraper
- [ ] Playwright setup with persistent browser context
- [ ] Manual login flow
- [ ] Navigate to instant virtuals results
- [ ] Scrape all match results from all categories after each round
- [ ] Parse HT and FT scores, derive HT/FT outcome
- [ ] Store results in SQLite
- [ ] Full scraping loop with error handling

### Sprint 3: HT/FT Analysis
- [ ] Descriptive statistics (9-way distribution, jackpot frequency)
- [ ] Jackpot deep dive (by category, by team, inter-arrival)
- [ ] Chi-squared test
- [ ] Runs test
- [ ] Autocorrelation analysis
- [ ] Spectral analysis (FFT)
- [ ] Transition matrix (9x9)
- [ ] Cross-category correlation

### Sprint 4: Strategy & Reporting
- [ ] Strategy backtester framework
- [ ] All 7 jackpot strategies implemented
- [ ] ML model baseline test
- [ ] Plot generation
- [ ] HTML report generation

---

## 10. Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Primary market | HT/FT (9 outcomes) | Away/Home jackpot at 100x is the focus |
| Data collection | Scrape results, not bet | Get 40+ data points per round for free |
| Categories | All 8 | More data, cross-category analysis possible |
| Database | SQLite | Zero infrastructure, ACID compliant |
| Browser | Chromium via Playwright | Persistent sessions, reliable automation |
| Jackpot definition | Away/Home at 100.00 odds | Always priced the same, easy to track |

---

## 11. What Success Looks Like

### If the RNG is proper (expected):
- Jackpot occurs at ~1% rate (matching 100.00 odds implied probability)
- No significant autocorrelation in jackpot sequence
- No periodic patterns in FFT spectrum
- Jackpot rate is consistent across categories and teams
- No strategy produces positive expected value
- **Conclusion: The math is right. 100.00 odds means ~1% probability. House edge makes it -EV.**

### If the RNG has detectable structure (unexpected but interesting):
- Jackpot rate differs significantly from 1% in certain categories or teams
- Autocorrelation shows sequential dependency
- Jackpots cluster in time or show periodic patterns
- Cross-category correlation (same RNG seed producing correlated outcomes)
- A strategy shows positive ROI over sufficient sample
- **Conclusion: Potential exploitable structure. Collect more data to confirm.**

---

*Document version: 2.0 | Updated: 2026-03-25 | Focus: HT/FT Market & Away/Home Jackpot*
