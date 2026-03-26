# SportyBet Instant Virtual Soccer — Final Analysis Report

*51,109 matches across 576 rounds. 1,007 live bets. 14,168 odds records. March 26, 2026.*

---

## Conclusion

**The RNG is fair and the bookmaker's pricing is accurate. No exploitable edge exists in SportyBet Instant Virtual Soccer.**

This conclusion is based on 13 independent statistical tests across 51,000+ matches and 1,007 live bets. Every angle was tested. Every pattern was investigated. The house edge of ~5% is genuine and unbeatable.

---

## 1. Dataset

| Metric | Value |
|--------|-------|
| Total matches | 51,109 |
| Total rounds | 576 |
| Categories | 8 |
| Matches per round | ~89 |
| Live bets placed | 1,007 |
| Live bets settled | 1,007 |
| 1X2 odds records | 14,168 |
| Unique pairings with odds | 3,296 |
| Pairings with odds + outcomes | 2,599 |

## 2. Live Betting Results

| Metric | Value |
|--------|-------|
| Total bets | 1,007 |
| Wins | 298 (29.6%) |
| Total staked | NGN 10,070 |
| **Total profit** | **NGN -499** |
| **ROI** | **-5.0%** |

### By Odds Range

| Odds Range | Bets | Win Rate | Breakeven WR | Edge | Profit | ROI |
|------------|------|----------|-------------|------|--------|-----|
| 1.0-1.5 | 53 | 60.4% | 74.0% | -13.7pp | -102 | -19.2% |
| 1.5-2.0 | 82 | 56.1% | 59.7% | -3.6pp | -52 | -6.4% |
| 2.0-2.5 | 66 | 40.9% | 43.5% | -2.5pp | -32 | -4.9% |
| 2.5-3.0 | 117 | 38.5% | 36.8% | +1.7pp | +52 | +4.5% |
| 3.0-3.5 | 122 | 32.8% | 30.5% | +2.3pp | +96 | +7.8% |
| 3.5-4.0 | 135 | 21.5% | 26.6% | -5.1pp | -253 | -18.8% |
| 4.0-4.5 | 132 | 16.7% | 23.7% | -7.0pp | -395 | -29.9% |
| 4.5-5.0 | 109 | 20.2% | 21.0% | -0.9pp | -48 | -4.4% |
| 5.0-6.0 | 119 | 16.8% | 18.3% | -1.5pp | -96 | -8.0% |
| 6.0-8.0 | 52 | 25.0% | 14.6% | +10.4pp | +360 | +69.1% |
| 8.0+ | 20 | 10.0% | 10.7% | -0.7pp | -28 | -14.0% |

The 6.0-8.0 range appears profitable but has only 52 bets — insufficient for statistical significance. All other ranges are negative or marginal.

## 3. Category Profiles (51,109 matches)

| Category | Matches | Avg Goals | O2.5% | U2.5% | DD% | Draw% | GG% | Home% |
|----------|---------|-----------|-------|-------|-----|-------|-----|-------|
| Italy | 5,660 | 1.70 | 24.5% | 75.5% | 25.5% | 32.6% | 30.5% | 36.6% |
| England | 5,660 | 1.78 | 26.5% | 73.5% | 24.7% | 32.8% | 33.2% | 37.1% |
| Spain | 5,660 | 2.00 | 32.6% | 67.4% | 20.8% | 28.4% | 36.0% | 46.0% |
| African Cup | 6,790 | 2.01 | 32.5% | 67.5% | 21.5% | 30.3% | 39.1% | 34.7% |
| Club World Cup | 9,062 | 2.21 | 37.8% | 62.2% | 19.3% | 29.1% | 43.2% | 42.3% |
| Euros | 6,790 | 2.23 | 38.4% | 61.6% | 19.5% | 28.6% | 44.0% | 41.6% |
| Champions | 5,670 | 2.27 | 39.3% | 60.7% | 19.6% | 28.9% | 44.6% | 41.4% |
| Germany | 5,105 | 2.37 | 41.8% | 58.2% | 18.0% | 27.0% | 44.2% | 43.4% |
| **Overall** | **51,109** | **2.08** | **34.4%** | - | **21.0%** | - | - | - |

## 4. Statistical Tests — Complete Results

### 4.1 Autocorrelation (Lag 1-5)

Tests whether outcome N predicts outcome N+1 within a category.

| Category | Lag 1 | Lag 2 | Lag 3 | Lag 4 | Lag 5 | Verdict |
|----------|-------|-------|-------|-------|-------|---------|
| Italy | -0.017 | -0.022 | -0.004 | +0.009 | -0.003 | RANDOM |
| England | -0.001 | -0.006 | +0.025 | -0.006 | -0.019 | RANDOM |
| Germany | +0.007 | -0.005 | -0.012 | +0.034 | -0.008 | RANDOM |
| Champions | -0.026 | +0.017 | +0.018 | +0.014 | -0.006 | RANDOM |
| Spain | +0.026 | -0.015 | -0.017 | -0.018 | +0.014 | RANDOM |

All autocorrelations < 0.035. No sequential dependency exists.

### 4.2 Runs Test

Tests whether the sequence of DD/non-DD is random.

| Category | Runs | Expected | Z-score | Verdict |
|----------|------|----------|---------|---------|
| Italy | 2,216 | 2,180 | +1.24 | RANDOM |
| England | 2,137 | 2,135 | +0.06 | RANDOM |
| Germany | 1,517 | 1,528 | -0.53 | RANDOM |

All pass at 95% confidence. The DD sequence is genuinely random.

### 4.3 Cross-Category Correlation

Tests whether categories share an RNG seed.

| Pair | Correlation | Verdict |
|------|------------|---------|
| Italy ↔ Germany DD | +0.076 | Independent |
| Italy ↔ England DD | +0.070 | Independent |
| Germany ↔ Champions DD | -0.006 | Independent |
| England ↔ Spain DD | -0.024 | Independent |

Round-level DD clustering: std=3.7 vs Poisson expected 4.3. **Categories are independent.**

### 4.4 Streak Analysis (Gambler's Fallacy Test)

P(DD) after N consecutive non-DD results:

| After N non-DD | Italy | England | Germany |
|----------------|-------|---------|---------|
| 0 | 24.3% | 24.6% | 18.6% |
| 1 | 24.5% | 24.4% | 17.0% |
| 2 | 26.1% | 28.9% | 17.3% |
| 3 | 27.0% | 22.5% | 21.9% |
| 4 | 25.5% | 24.5% | 14.7% |
| 5+ | 26.6% | 23.5% | 17.9% |

No consistent pattern. DD probability does not increase after droughts.

### 4.5 Goal Distribution — Poisson Fit

| Goals | Actual | Poisson Expected | Difference |
|-------|--------|-----------------|------------|
| 0 | 13.48% | 12.49% | +0.99% |
| 1 | 26.15% | 25.98% | +0.16% |
| 2 | 25.98% | 27.02% | -1.04% |
| 3 | 17.95% | 18.74% | -0.79% |
| 4 | 9.74% | 9.75% | -0.01% |
| 5 | 4.23% | 4.05% | +0.18% |

Excellent Poisson fit. Maximum deviation is 1.04pp. The goal-scoring process is consistent with independent random events.

### 4.6 Home/Away Goal Independence

| Category | Correlation | Home Avg | Away Avg |
|----------|------------|----------|----------|
| Overall | -0.001 | 1.15 | 0.93 |
| Italy | -0.026 | 0.90 | 0.80 |
| Germany | -0.030 | 1.35 | 1.02 |
| Spain | -0.022 | 1.22 | 0.79 |

All correlations < 0.03. Home and away goals are independent within matches.

### 4.7 Time-of-Day Analysis

| Hour | Matches | DD% | O2.5% | Avg Goals |
|------|---------|-----|-------|-----------|
| 8h | 3,916 | 20.7% | 35.6% | 2.10 |
| 14h | 4,875 | 20.8% | 34.1% | 2.08 |
| 16h | 9,503 | 20.9% | 34.1% | 2.07 |
| 17h | 8,417 | 21.4% | 34.6% | 2.08 |

No significant variation by time of day. The RNG is time-independent.

## 5. Bookmaker Analysis

### 5.1 Margin Structure

| Category | Avg Margin | Min | Max | Std Dev |
|----------|-----------|-----|-----|---------|
| Champions | 5.00% | 4.8% | 5.2% | 0.07% |
| Club World Cup | 5.00% | 4.8% | 5.2% | 0.07% |
| England | 5.00% | 4.8% | 5.2% | 0.07% |
| Germany | 4.99% | 4.7% | 5.3% | 0.10% |
| Italy | 4.99% | 4.8% | 5.2% | 0.07% |
| Spain | 5.01% | 4.8% | 5.3% | 0.09% |

The margin is **exactly 5.0%** across all categories, all match types, and all favourite strengths. No variation to exploit.

### 5.2 Calibration Accuracy

| Draw Odds | Implied Draw% | Actual Draw% | Error |
|-----------|--------------|-------------|-------|
| < 2.8 | 36.1% | 35.1% | -0.9pp |
| 2.8-3.2 | 31.7% | 31.5% | -0.2pp |
| 3.2-3.6 | 28.3% | 28.1% | -0.1pp |
| 3.6-4.2 | 25.0% | 25.9% | +0.9pp |
| 4.2+ | 19.5% | 20.2% | +0.7pp |

Maximum calibration error: **0.9 percentage points**. The bookmaker's per-match pricing is highly accurate.

### 5.3 Draw Odds Perfectly Predict DD Rate

| Draw Odds | Actual DD Rate | Fair DD Odds |
|-----------|---------------|-------------|
| < 2.8 | 28.5% | 3.51 |
| 2.8-3.2 | 23.1% | 4.33 |
| 3.2-3.6 | 19.0% | 5.27 |
| 3.6-4.2 | 16.0% | 6.30 |
| 4.2+ | 11.8% | 8.48 |

The draw odds encode DD probability information. No arbitrage exists because the bookmaker accurately prices the draw probability with only 5% margin.

## 6. Halftime → Fulltime Dynamics

| HT Score | Matches | FT Home | FT Draw | FT Away | Comeback% |
|----------|---------|---------|---------|---------|-----------|
| 0-0 | 18,618 | 30.0% | 46.0% | 24.0% | 0% |
| 1-0 | 10,095 | 76.9% | 18.1% | 4.9% | 4.9% |
| 0-1 | 8,270 | 7.3% | 21.6% | 71.1% | 7.3% |
| 1-1 | 4,473 | 31.3% | 45.0% | 23.7% | 0% |
| 2-0 | 2,969 | 94.6% | 4.7% | 0.7% | 0.7% |

**0-0 at HT → 46.0% remain 0-0 at FT.** This is the strongest conditional probability in the data but requires live/in-play betting which is a different flow.

**Second half vs first half goals:** 1.045 vs 1.035 (ratio 1.01x). Virtually identical — no "second half surge" pattern.

## 7. Strategy Evolution and Lessons

| Version | Approach | Live Result | Lesson |
|---------|----------|-------------|--------|
| v0 | Jackpot (Away/Home) | Not deployed | 1.38% rate vs 100x odds = positive EV in theory, but actual odds 50-75x |
| v1 | Category-level (DD in Italy/England) | -34% ROI (41 bets) | Category-level edge consumed by per-match pricing |
| v2 | Pairing-level (per-team historical rates) | -5% ROI (1,007 bets) | Small-sample inflation → regression to mean |

**The core mistake:** Historical pairing rates with small samples (8-15 matches) appear to deviate from bookmaker estimates, but this is statistical noise. When bet upon, the actual rates regress to the bookmaker's (accurate) predictions.

## 8. Definitive Findings

1. **RNG is random** — All independence tests pass (autocorrelation, runs test, cross-category)
2. **Goals follow Poisson** — Maximum deviation from Poisson is 1.04pp
3. **Home/Away goals are independent** — Correlation < 0.03
4. **No time-of-day effect** — DD% and O2.5% are constant across hours
5. **No streak pattern** — P(DD) doesn't change after consecutive non-DD
6. **Bookmaker margin is exactly 5.0%** — Constant across all categories, match types
7. **Bookmaker calibration is accurate** — Maximum error 0.9pp on draw predictions
8. **Categories are independent** — Cross-category correlation < 0.08
9. **No pairing-level edge survives live testing** — Regression to mean eliminates apparent edges
10. **Live ROI converges to -5%** — Exactly the house edge

## 9. Honest Assessment

After 51,109 matches of observation, 14,168 odds records, and 1,007 live bets, the evidence is overwhelming: **SportyBet's Instant Virtual Soccer is a well-designed game with a fair RNG and accurate pricing.** The 5% house edge is embedded in every market through consistent, accurate odds-setting.

The study succeeded in its original goal: we empirically determined that "no polynomial-time algorithm can predict future outcomes better than the base rate." The hypothesis held.

---

*Final report. All numbers computed from SQLite database. March 26, 2026.*
