# SportyBet Instant Virtual Soccer — Complete Analysis Report

*31,515 matches across 355 rounds + 231 real fixture odds. March 25, 2026.*

---

## 1. Executive Summary

This study analyzed SportyBet's Instant Virtual Soccer outcomes across 31,515 matches to determine whether exploitable patterns exist in the RNG (Random Number Generator).

**Key findings:**
1. The RNG produces statistically significant category-level biases (Italy/England are low-scoring; Germany is high-scoring)
2. The bookmaker prices matches with a consistent 5.0% margin
3. The bookmaker's per-match pricing has moderate accuracy (correlation 0.53)
4. **Specific team pairings deviate from bookmaker pricing, creating +EV opportunities on 44% of fixtures**
5. A pairing-based value betting strategy projects NGN +6,950/day at NGN 10 stake

---

## 2. Data Collection

| Metric | Value |
|--------|-------|
| Source | SportyBet Instant Virtual Soccer (Nigeria) |
| URL | `https://www.sportybet.com/ng/sporty-instant-virtuals?from=games` |
| Tool | Custom Playwright bot (Chromium) |
| Matches | 31,515 |
| Rounds | 355 |
| Categories | 8 (England, Spain, Germany, Champions, Italy, African Cup, Euros, Club World Cup) |
| Matches per round | ~89 |
| Odds fixtures scraped | 231 from 3 rounds |

---

## 3. HT/FT Market Distribution

| Outcome | Count | Rate |
|---------|-------|------|
| Home/Home | 7,981 | 25.32% |
| Draw/Draw | 6,605 | 20.96% |
| Away/Away | 5,609 | 17.80% |
| Draw/Home | 4,301 | 13.65% |
| Draw/Away | 3,499 | 11.10% |
| Home/Draw | 1,392 | 4.42% |
| Away/Draw | 1,336 | 4.24% |
| Away/Home | 435 | 1.38% |
| Home/Away | 357 | 1.13% |

---

## 4. Category Analysis

### 4.1 Goals and Outcome Profiles

| Category | n | Avg Goals | O2.5% | U2.5% | DD% | Draw% | AH% |
|----------|---|-----------|-------|-------|-----|-------|-----|
| Italy | 3,530 | 1.69 | 24.4% | 75.6% | 25.7% | 32.6% | 0.8% |
| England | 3,530 | 1.77 | 26.1% | 73.9% | 24.2% | 32.0% | 0.9% |
| Spain | 3,530 | 1.99 | 32.1% | 67.9% | 20.7% | 28.2% | 1.1% |
| African Cup | 4,248 | 2.02 | 33.0% | 67.0% | 21.5% | 30.4% | 1.4% |
| Club World Cup | 5,680 | 2.20 | 37.4% | 62.6% | 19.2% | 28.9% | 1.9% |
| Euros | 4,260 | 2.22 | 38.1% | 61.9% | 19.4% | 28.5% | 1.4% |
| Champions | 3,550 | 2.27 | 39.9% | 60.1% | 19.7% | 29.0% | 1.6% |
| Germany | 3,187 | 2.39 | 42.3% | 57.7% | 18.2% | 27.7% | 1.7% |

### 4.2 Key Observations

- **Italy and England** are "goal deserts" — avg 1.69 and 1.77 goals, highest DD rates (25.7%, 24.2%)
- **Germany** is the "goal fest" — avg 2.39 goals, highest O2.5 rate (42.3%)
- The spread between lowest (Italy 24.4%) and highest (Germany 42.3%) O2.5 rate is **17.9 percentage points** — enormous
- DD rates vary from 18.2% (Germany) to 25.7% (Italy) — a 7.5pp spread

### 4.3 Statistical Significance

All category deviations from the overall average are highly significant (Z > 4 for the extremes):
- Italy DD Z = +6.8, Italy U2.5 Z = +12.5
- Germany O2.5 Z = +9.4
- England DD Z = +4.9

---

## 5. Bookmaker Analysis

### 5.1 Margin

Measured from 231 O/U 2.5 odds pairs and 10 1X2 odds triplets:
- **O/U margin: 5.0%** (range 4.7%-5.3%)
- **1X2 margin: 5.0%** (range 4.9%-5.1%)

The margin is consistent and provides no category-level arbitrage.

### 5.2 Actual Offered Odds (from 231 fixtures)

| Market | Category | Avg Odds | Min | Max |
|--------|----------|----------|-----|-----|
| O2.5 | Italy | 3.82 | 2.76 | 5.13 |
| O2.5 | England | 3.50 | 2.15 | 5.45 |
| O2.5 | Germany | 2.66 | 1.43 | 4.65 |
| O2.5 | Champions | 2.39 | 1.83 | 3.16 |
| U2.5 | Italy | 1.29 | 1.17 | 1.45 |
| U2.5 | England | 1.35 | 1.15 | 1.71 |
| U2.5 | Germany | 1.71 | 1.20 | 2.86 |
| DD | Italy | 3.58 | 2.93 | 4.31 |
| DD | England | 3.89 | 2.85 | 5.46 |
| DD | Germany | 5.43 | 3.09 | 10.39 |

### 5.3 Pricing Accuracy

**Correlation between bookmaker's implied probability and actual pairing rates: 0.53**

The bookmaker is moderately accurate — when they price a match as likely to go over 2.5, it usually does go over more than average. But the pricing is not precise enough to eliminate all value, especially at the individual pairing level.

---

## 6. Strategy Evolution

### 6.1 Phase 1: Jackpot Hunting (Away/Home)

Focus on the 100.00 odds Away/Home jackpot. Observed rate 1.38% vs 1.00% implied. Statistically significant (Z = 6.64) but ultimately unprofitable at realistic odds due to massive variance (max losing streak: 280 bets) and actual odds averaging 50-75x, not 100x.

### 6.2 Phase 2: Category-Level Steady (v1)

Target specific categories with elevated rates:
- DD in Italy/England (rate significantly above average)
- O2.5 in Germany/Champions (rate significantly above average)

**Problem discovered during live testing:** The bookmaker already adjusts odds per match. Typical DD odds in Italy: 3.58 (vs breakeven 3.89). Most O2.5 odds in Champions: 2.0-2.5 (vs breakeven 2.49). The category-level edge was consumed by the bookmaker's per-match pricing.

### 6.3 Phase 3: Pairing-Based Value (v2)

The breakthrough: instead of asking "is DD profitable in Italy?", ask "is DD profitable for THIS specific team pairing at THESE specific odds?"

This works because:
1. The bookmaker uses team strength models that approximate category averages
2. But individual pairings deviate significantly from category averages
3. These deviations are persistent (verified across 355 rounds)
4. The bookmaker doesn't fully price in pairing-specific deviations

---

## 7. Independence Tests

### 7.1 Autocorrelation

DD outcomes in Italy (lag 1-5): all |r| < 0.026. **No sequential dependency.**

### 7.2 Intra-Round Correlation

DD wins and O2.5 wins within the same round: r = 0.026. **Independent — provides real diversification.**

### 7.3 Edge Stability Over Time

DD rate in Italy across 5 time quintiles: 25.6%, 26.2%, 25.3%, 26.0%, 25.7%. **Remarkably stable.**

O2.5 rate in Germany: 44.3%, 44.0%, 39.0%, 43.0%, 40.5%. **Normal variance around 42%.**

---

## 8. Backtest Results

### 8.1 Strategy Comparison (at fixed assumed odds)

| Strategy | Odds | Bets | ROI | Profit |
|----------|------|------|-----|--------|
| O2.5 Germany @2.5 | 2.5 | 3,187 | +5.7% | +1,805 |
| O2.5 Germany @3.0 | 3.0 | 3,187 | +26.8% | +8,540 |
| DD Italy @4.5 | 4.5 | 3,530 | +15.5% | +5,470 |
| DD IT+ENG @5.0 | 5.0 | 7,060 | +24.6% | +17,400 |
| U2.5 IT+ENG @1.4 | 1.4 | 7,060 | +4.7% | +3,306 |
| U2.5 IT+ENG @1.5 | 1.5 | 7,060 | +12.2% | +8,585 |

### 8.2 Pairing-Based Backtest (Real Odds x Real Rates)

With 231 scraped odds matched to historical pairing rates:
- 177 unique +EV fixture-bets found (78% of fixtures have at least one +EV market)
- Capped at 30/round: **NGN +204/round** profit
- Daily projection: **NGN +12,210** at NGN 10 stake

With strict n >= 10 filter: 97 bets, **NGN +116/round**, **NGN +6,950/day**

---

## 9. Technical Implementation

### 9.1 Bot Capabilities

- Persistent browser profile (login once, reuse sessions)
- Category tab navigation
- Fixture detail page odds scraping (O/U all lines, HT/FT 9-way, 1X2)
- Per-fixture EV evaluation against pairing database
- Automated bet placement with Place Bet -> Confirm cycle
- Dialog/overlay dismissal (es-dialog-wrap, winngin-pop)
- Win splash handling
- Results scraping across all 8 categories
- Bet logging and settlement in SQLite
- Session expiry detection and recovery
- Adaptive re-learning every 20 rounds

### 9.2 Database Schema

- **rounds**: round_id, timestamp
- **matches**: category, teams, HT/FT scores, derived results
- **bets**: market, selection, odds, stake, won, payout, profit
- **htft_odds**: 9-way HT/FT odds per match (when scraped)

---

## Appendix: Honest Disclaimers

1. **41 live bets is not statistically significant.** The 9/41 win rate (22%) is below expected (~33%), but 41 bets has a standard error of ~7pp, so this is within normal variance.

2. **Pairing-based edges rely on small samples.** Many pairings have only 8-15 matches of history. Individual pairing rates have wide confidence intervals.

3. **Past performance does not guarantee future results.** If SportyBet updates their RNG or team roster, historical rates become invalid. The strategy re-learns every 20 rounds to adapt.

4. **This is not investment advice.** This is a research project studying RNG patterns in virtual sports.
