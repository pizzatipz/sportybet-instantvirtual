# Steady Strategy — Post-Mortem

*This document records the full strategy evolution, what was tried, what failed, and why.*

## Final Result

**1,007 live bets. -5.0% ROI. The house edge won.**

## Strategy Evolution

### v0: Jackpot Hunting (Away/Home at 100x odds)
- Observed rate: 1.38% vs 1.00% implied
- Statistically significant (Z=6.64) but actual odds averaged 50-75x, not 100x
- Massive variance (max losing streak: 280 bets)
- Never deployed live

### v1: Category-Level (DD in Italy/England, O2.5 in Germany)
- Based on Z-tests showing elevated category rates
- 41 live bets: -34% ROI
- **Failed because:** bookmaker already adjusts per-match odds for category patterns

### v2: Pairing-Level (per-team historical rates vs offered odds)
- Compare each (category, home, away) pairing's historical rate to bookmaker odds
- Bet only when EV > 0
- 966 live bets: -4.2% ROI
- **Failed because:** small-sample rates regressed to the mean

### v2.1: DD-Focused (Drop O2.5 and U2.5)
- Analysis showed DD was the only market with positive live ROI at one point
- Under 2.5 was -11.2% ROI → dropped
- Over 2.5 restricted to odds ≥ 5.0
- Subsequent rounds showed DD also converging to house edge

## Root Causes of Failure

### 1. Small Sample Inflation
Historical pairing rates with 8-15 matches of history appeared elevated due to noise. When bet upon, outcomes regressed to the true (lower) rate.

### 2. Bookmaker Accuracy
The bookmaker's 1X2 odds accurately predict outcome probabilities with < 1pp error per category. Their per-match pricing encodes the same information we tried to exploit with pairing rates.

### 3. Constant 5% Margin
The margin is exactly 5.0% across all categories, match types, and favourite strengths. No structural weakness exists.

## Key Lessons

1. **Category-level biases are real** (Italy is low-scoring, Germany is high-scoring) but the bookmaker **already prices them in**
2. **Small samples lie** — a pairing with 4 DD in 10 matches (40%) looks like an edge, but the true rate is likely ~21%
3. **Backtesting on historical rates overestimates edge** because it assumes rates are stable, but they regress to mean
4. **The bookmaker's model is sophisticated** — their 1X2 odds correlate 0.53 with actual outcomes, which is enough to absorb category/pairing-level biases
5. **1,007 live bets is sufficient** to conclude — the ROI confidence interval excludes any meaningful positive edge

## Live Betting Summary

| Round Range | Bets | Wins | Win Rate | ROI |
|-------------|------|------|----------|-----|
| First third | 335 | 115 | 34% | +3.1% |
| Middle third | 335 | 103 | 31% | -4.0% |
| Last third | 337 | 80 | 24% | -13.9% |
| **Total** | **1,007** | **298** | **29.6%** | **-5.0%** |

The initial positive ROI was noise. As more bets accumulated, performance converged to the house edge.
