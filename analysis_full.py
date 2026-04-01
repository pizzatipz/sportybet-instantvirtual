"""
SportyBet Instant Virtual Soccer — Full Statistical Analysis
=============================================================

Tests all 6 hypotheses from RESEARCH_PLAN.md against the collected data.
Each test uses proper statistical methods with confidence intervals and p-values.

Hypotheses:
  H1: The 55-75x bracket edge is real (PRIMARY)
  H2: Category matters for AH rate
  H3: The 50-55x dead zone is real
  H4: 100x odds are a trap
  H5: Overall AH rate is stable over time
  H6: The edge is in odds brackets, not categories
"""

import sqlite3
import numpy as np
from scipy import stats
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "sportybet.db"
conn = sqlite3.connect(str(DB_PATH))

# ═══════════════════════════════════════════════════════════
#  SECTION 0: DATA OVERVIEW
# ═══════════════════════════════════════════════════════════

print("=" * 70)
print("  SPORTYBET VIRTUAL SOCCER — FULL STATISTICAL ANALYSIS")
print("=" * 70)

rounds = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
jackpots = conn.execute("SELECT COUNT(*) FROM matches WHERE is_jackpot=1").fetchone()[0]
market_odds_total = conn.execute("SELECT COUNT(*) FROM market_odds").fetchone()[0]
htft_odds = conn.execute("SELECT COUNT(*) FROM market_odds WHERE market='HT/FT'").fetchone()[0]
ah_odds = conn.execute("SELECT COUNT(*) FROM market_odds WHERE market='HT/FT' AND selection='Away/ Home'").fetchone()[0]

print(f"\n  Data collected:")
print(f"    Rounds:           {rounds:,}")
print(f"    Matches:          {matches:,}")
print(f"    Jackpots (AH):    {jackpots:,} ({jackpots/matches*100:.2f}%)")
print(f"    Market odds:      {market_odds_total:,}")
print(f"    HT/FT odds:       {htft_odds:,}")
print(f"    AH odds:          {ah_odds:,}")

# ── HT/FT outcome distribution ──
print(f"\n  HT/FT Outcome Distribution ({matches:,} matches):")
outcomes = conn.execute("""
    SELECT htft_result, COUNT(*) as n
    FROM matches GROUP BY htft_result ORDER BY n DESC
""").fetchall()
for outcome, n in outcomes:
    rate = n / matches * 100
    fair_odds = matches / n if n > 0 else 0
    print(f"    {outcome:<15} {n:>7,}  ({rate:>5.2f}%)  fair odds: {fair_odds:.1f}x")

# ── AH rate by category ──
print(f"\n  AH Rate by Category:")
cats = conn.execute("""
    SELECT category, COUNT(*) as n, SUM(is_jackpot) as jp
    FROM matches GROUP BY category ORDER BY CAST(jp AS FLOAT)/n DESC
""").fetchall()
for cat, n, jp in cats:
    rate = jp / n * 100
    print(f"    {cat:<18} {n:>7,} matches | {jp:>4} AH | {rate:.2f}%")


# ═══════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def wilson_ci(hits, n, z=1.96):
    """Wilson score confidence interval for a proportion."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = hits / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return p, max(0, center - margin), min(1, center + margin)


def one_prop_z_test(hits, n, p0, alternative="greater"):
    """One-proportion z-test.
    H0: p = p0, H1: p > p0 (or < p0, or != p0)
    Returns z-statistic and p-value.
    """
    p_hat = hits / n
    se = np.sqrt(p0 * (1 - p0) / n)
    z = (p_hat - p0) / se
    if alternative == "greater":
        pval = 1 - stats.norm.cdf(z)
    elif alternative == "less":
        pval = stats.norm.cdf(z)
    else:
        pval = 2 * (1 - stats.norm.cdf(abs(z)))
    return z, pval


def two_prop_z_test(hits1, n1, hits2, n2):
    """Two-proportion z-test. H0: p1 = p2, H1: p1 != p2."""
    p1 = hits1 / n1
    p2 = hits2 / n2
    p_pool = (hits1 + hits2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    z = (p1 - p2) / se
    pval = 2 * (1 - stats.norm.cdf(abs(z)))
    return z, pval


# ═══════════════════════════════════════════════════════════
#  BUILD THE JOINED DATASET: matches + AH odds per pairing
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  BUILDING ANALYSIS DATASET")
print("=" * 70)

# Get average AH odds per fixture pairing
pairing_odds = conn.execute("""
    SELECT category, home_team, away_team, AVG(odds) as avg_odds, COUNT(*) as odds_count
    FROM market_odds
    WHERE market='HT/FT' AND selection='Away/ Home'
    GROUP BY category, home_team, away_team
""").fetchall()

# Build lookup dict
odds_lookup = {}
for cat, home, away, avg_odds, cnt in pairing_odds:
    odds_lookup[(cat, home, away)] = avg_odds

# Get all matches and join to odds
all_matches = conn.execute("""
    SELECT category, home_team, away_team, is_jackpot, round_id
    FROM matches ORDER BY id
""").fetchall()

# Join
joined = []
for cat, home, away, is_jp, rid in all_matches:
    key = (cat, home, away)
    if key in odds_lookup:
        joined.append({
            "category": cat,
            "home_team": home,
            "away_team": away,
            "is_jackpot": is_jp,
            "ah_odds": odds_lookup[key],
            "round_id": rid,
        })

print(f"  Matches with AH odds: {len(joined):,} / {len(all_matches):,} ({len(joined)/len(all_matches)*100:.1f}%)")
print(f"  Unique pairings with odds: {len(odds_lookup):,}")


# ═══════════════════════════════════════════════════════════
#  SECTION 1: PER-BRACKET ANALYSIS (H1, H3, H4)
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  ANALYSIS 1: AH HIT RATE BY ODDS BRACKET")
print("=" * 70)

brackets_def = [
    ("<30", 0, 30),
    ("30-40", 30, 40),
    ("40-50", 40, 50),
    ("50-55", 50, 55),
    ("55-60", 55, 60),
    ("60-65", 60, 65),
    ("65-75", 65, 75),
    ("75-90", 75, 90),
    ("90-100", 90, 100),
    ("100+", 100, 999),
]

print(f"\n  {'Bracket':>10} {'N':>8} {'Hits':>6} {'Rate':>7} {'AvgOdds':>8} {'Implied':>8} {'EV':>8} {'95% CI':>20} {'z':>7} {'p-val':>8} {'Sig?':>5}")
print("  " + "-" * 115)

bracket_results = {}
for label, lo, hi in brackets_def:
    b_data = [m for m in joined if lo <= m["ah_odds"] < hi]
    n = len(b_data)
    hits = sum(m["is_jackpot"] for m in b_data)
    if n == 0:
        continue
    avg_odds = np.mean([m["ah_odds"] for m in b_data])
    implied = 1.0 / avg_odds
    rate, ci_lo, ci_hi = wilson_ci(hits, n)
    ev = (rate * avg_odds - 1) * 100

    # One-proportion z-test vs implied probability
    z, pval = one_prop_z_test(hits, n, implied, alternative="greater")
    sig = "YES" if pval < 0.05 else "no"

    bracket_results[label] = {
        "n": n, "hits": hits, "rate": rate, "avg_odds": avg_odds,
        "implied": implied, "ev": ev, "ci_lo": ci_lo, "ci_hi": ci_hi,
        "z": z, "pval": pval, "sig": sig
    }

    print(f"  {label:>10} {n:>8,} {hits:>6} {rate*100:>6.2f}% {avg_odds:>7.1f}x {implied*100:>7.2f}% {ev:>+7.1f}% [{ci_lo*100:>5.2f}%-{ci_hi*100:>5.2f}%] {z:>7.3f} {pval:>8.5f} {sig:>5}")


# ═══════════════════════════════════════════════════════════
#  H1: THE 55-75x BRACKET EDGE (PRIMARY HYPOTHESIS)
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  HYPOTHESIS H1: 55-75x BRACKET EDGE")
print("=" * 70)

h1_data = [m for m in joined if 55 <= m["ah_odds"] < 75]
h1_n = len(h1_data)
h1_hits = sum(m["is_jackpot"] for m in h1_data)
h1_avg_odds = np.mean([m["ah_odds"] for m in h1_data]) if h1_data else 0
h1_implied = 1.0 / h1_avg_odds if h1_avg_odds > 0 else 0
h1_rate, h1_ci_lo, h1_ci_hi = wilson_ci(h1_hits, h1_n)

print(f"\n  Claim:    AH hit rate in 55-75x > implied probability ({h1_implied*100:.2f}%)")
print(f"  Sample:   {h1_n:,} fixtures in 55-75x bracket")
print(f"  Hits:     {h1_hits}")
print(f"  Observed: {h1_rate*100:.3f}%")
print(f"  Implied:  {h1_implied*100:.3f}%")
print(f"  95% CI:   [{h1_ci_lo*100:.3f}%, {h1_ci_hi*100:.3f}%]")

h1_z, h1_pval = one_prop_z_test(h1_hits, h1_n, h1_implied, alternative="greater")
print(f"  z-stat:   {h1_z:.4f}")
print(f"  p-value:  {h1_pval:.6f}")

if h1_pval < 0.05:
    ev = (h1_rate * h1_avg_odds - 1) * 100
    print(f"\n  *** RESULT: SIGNIFICANT (p < 0.05) ***")
    print(f"  The 55-75x bracket has a genuine edge of {ev:+.1f}% EV")
    print(f"  The CI lower bound ({h1_ci_lo*100:.3f}%) vs implied ({h1_implied*100:.3f}%)")
    ci_lo_ev = (h1_ci_lo * h1_avg_odds - 1) * 100
    print(f"  Worst-case EV (CI lower bound): {ci_lo_ev:+.1f}%")
else:
    print(f"\n  RESULT: NOT SIGNIFICANT (p = {h1_pval:.4f})")
    print(f"  Cannot reject H0 that the hit rate equals the implied probability.")
    shortfall = h1_implied - h1_rate
    print(f"  Observed rate is {'above' if h1_rate > h1_implied else 'below'} implied by {abs(shortfall)*100:.3f}pp")


# ═══════════════════════════════════════════════════════════
#  H2: CATEGORY DIFFERENCES
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  HYPOTHESIS H2: CATEGORY MATTERS FOR AH RATE")
print("=" * 70)

print(f"\n  Testing: Germany/Champions vs Italy (highest vs lowest AH categories)")

cat_data = {}
for cat, n, jp in cats:
    cat_data[cat] = {"n": n, "jp": jp, "rate": jp / n}

# Best vs worst
best_cats = sorted(cats, key=lambda x: x[2]/x[1], reverse=True)[:2]
worst_cat = sorted(cats, key=lambda x: x[2]/x[1])[0]

for label, n, jp in best_cats:
    rate = jp / n * 100
    _, ci_lo, ci_hi = wilson_ci(jp, n)
    print(f"\n  {label}: {jp}/{n} = {rate:.2f}% [{ci_lo*100:.2f}%-{ci_hi*100:.2f}%]")

wlabel, wn, wjp = worst_cat
wrate = wjp / wn * 100
_, wci_lo, wci_hi = wilson_ci(wjp, wn)
print(f"\n  {wlabel}: {wjp}/{wn} = {wrate:.2f}% [{wci_lo*100:.2f}%-{wci_hi*100:.2f}%]")

# Test best vs worst
blabel, bn, bjp = best_cats[0]
z_h2, p_h2 = two_prop_z_test(bjp, bn, wjp, wn)
print(f"\n  Two-proportion z-test ({blabel} vs {wlabel}):")
print(f"    z = {z_h2:.4f}, p = {p_h2:.6f}")
if p_h2 < 0.05:
    print(f"    *** SIGNIFICANT: {blabel} has a genuinely higher AH rate than {wlabel} ***")
else:
    print(f"    NOT SIGNIFICANT: Cannot confirm {blabel} differs from {wlabel}")

# Chi-squared test across all categories
print(f"\n  Chi-squared test (all 8 categories):")
overall_rate = jackpots / matches
cat_observed = np.array([jp for _, _, jp in cats])
cat_expected = np.array([n * overall_rate for _, n, _ in cats])
chi2, chi2_p = stats.chisquare(cat_observed, cat_expected)
print(f"    χ² = {chi2:.4f}, p = {chi2_p:.6f}")
if chi2_p < 0.05:
    print(f"    *** SIGNIFICANT: AH rates differ across categories ***")
else:
    print(f"    NOT SIGNIFICANT: AH rates are consistent across categories")


# ═══════════════════════════════════════════════════════════
#  H3: THE 50-55x DEAD ZONE
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  HYPOTHESIS H3: 50-55x DEAD ZONE")
print("=" * 70)

h3 = bracket_results.get("50-55", {})
if h3:
    h3_implied = h3["implied"]
    h3_z, h3_p = one_prop_z_test(h3["hits"], h3["n"], h3_implied, alternative="less")
    print(f"\n  Claim:    AH hit rate at 50-55x < implied ({h3_implied*100:.2f}%)")
    print(f"  Sample:   {h3['n']:,} fixtures")
    print(f"  Hits:     {h3['hits']}")
    print(f"  Observed: {h3['rate']*100:.3f}%")
    print(f"  95% CI:   [{h3['ci_lo']*100:.3f}%, {h3['ci_hi']*100:.3f}%]")
    print(f"  z-stat:   {h3_z:.4f}")
    print(f"  p-value:  {h3_p:.6f}")
    if h3_p < 0.05:
        print(f"  *** SIGNIFICANT: 50-55x IS a dead zone — hit rate below implied ***")
    else:
        print(f"  NOT SIGNIFICANT: Cannot confirm 50-55x is a dead zone")


# ═══════════════════════════════════════════════════════════
#  H4: 100x TRAP
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  HYPOTHESIS H4: 100x ODDS ARE A TRAP")
print("=" * 70)

h4 = bracket_results.get("100+", {})
if h4:
    h4_implied = 0.01  # 1/100 = 1%
    h4_z, h4_p = one_prop_z_test(h4["hits"], h4["n"], h4_implied, alternative="less")
    print(f"\n  Claim:    AH hit rate at 100x < 1.00% (implied by 100x odds)")
    print(f"  Sample:   {h4['n']:,} fixtures")
    print(f"  Hits:     {h4['hits']}")
    print(f"  Observed: {h4['rate']*100:.3f}%")
    print(f"  95% CI:   [{h4['ci_lo']*100:.3f}%, {h4['ci_hi']*100:.3f}%]")
    print(f"  z-stat:   {h4_z:.4f}")
    print(f"  p-value:  {h4_p:.6f}")
    if h4_p < 0.05:
        print(f"  *** SIGNIFICANT: 100x IS a trap — hit rate significantly below 1% ***")
    else:
        print(f"  NOT SIGNIFICANT: Cannot confirm 100x is a trap")


# ═══════════════════════════════════════════════════════════
#  H5: STABILITY OVER TIME
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  HYPOTHESIS H5: AH RATE STABILITY OVER TIME")
print("=" * 70)

# Get matches in round order with a sequential index
round_list = conn.execute("SELECT round_id FROM rounds ORDER BY id").fetchall()
round_order = {r[0]: i for i, (r,) in enumerate(round_list)}

# Compute rolling AH rate in windows of 50 rounds
window_size = 100  # rounds
round_matches = {}
for m in all_matches:
    rid = m[4]  # round_id
    if rid not in round_matches:
        round_matches[rid] = {"total": 0, "jp": 0}
    round_matches[rid]["total"] += 1
    round_matches[rid]["jp"] += m[3]  # is_jackpot

ordered_rounds = sorted(round_matches.keys(), key=lambda r: round_order.get(r, 0))
cumul_total = []
cumul_jp = []
running_t = 0
running_j = 0
for rid in ordered_rounds:
    running_t += round_matches[rid]["total"]
    running_j += round_matches[rid]["jp"]
    cumul_total.append(running_t)
    cumul_jp.append(running_j)

# Rolling rate in window
overall_ah_rate = jackpots / matches
print(f"\n  Overall AH rate: {overall_ah_rate*100:.3f}% ({jackpots}/{matches})")
print(f"\n  Rolling {window_size}-round AH rate (checking for drift):")

drift_detected = False
for i in range(window_size, len(ordered_rounds)):
    win_total = cumul_total[i] - cumul_total[i - window_size]
    win_jp = cumul_jp[i] - cumul_jp[i - window_size]
    win_rate = win_jp / win_total if win_total > 0 else 0
    
    # Is this window significantly different from overall?
    se = np.sqrt(overall_ah_rate * (1 - overall_ah_rate) / win_total)
    z_drift = (win_rate - overall_ah_rate) / se
    
    # Report quartile summaries
    if i == window_size or i == len(ordered_rounds) // 4 or i == len(ordered_rounds) // 2 or i == 3 * len(ordered_rounds) // 4 or i == len(ordered_rounds) - 1:
        print(f"    Rounds {i-window_size+1}-{i}: {win_jp}/{win_total} = {win_rate*100:.2f}% (z={z_drift:.2f})")
    
    if abs(z_drift) > 2.5:
        drift_detected = True

# Runs test on jackpot sequence
jp_sequence = [m[3] for m in all_matches]  # is_jackpot for all matches in order
n_jp = sum(jp_sequence)
n_njp = len(jp_sequence) - n_jp
# Count runs
runs = 1
for i in range(1, len(jp_sequence)):
    if jp_sequence[i] != jp_sequence[i-1]:
        runs += 1

# Expected runs under independence
expected_runs = (2 * n_jp * n_njp) / (n_jp + n_njp) + 1
var_runs = (2 * n_jp * n_njp * (2 * n_jp * n_njp - n_jp - n_njp)) / ((n_jp + n_njp)**2 * (n_jp + n_njp - 1))
z_runs = (runs - expected_runs) / np.sqrt(var_runs)
p_runs = 2 * (1 - stats.norm.cdf(abs(z_runs)))

print(f"\n  Runs test (independence of jackpot sequence):")
print(f"    Runs observed: {runs:,}, expected: {expected_runs:,.0f}")
print(f"    z = {z_runs:.4f}, p = {p_runs:.6f}")
if p_runs < 0.05:
    print(f"    *** SIGNIFICANT: Jackpot sequence is NOT random ***")
else:
    print(f"    PASS: Jackpot sequence is consistent with randomness")

if drift_detected:
    print(f"\n  ⚠️  DRIFT DETECTED: Some {window_size}-round windows deviated >2.5σ from overall rate")
else:
    print(f"\n  ✅ NO DRIFT: AH rate is stable across all {window_size}-round windows")


# ═══════════════════════════════════════════════════════════
#  H6: ODDS BRACKETS VS CATEGORIES (LOGISTIC REGRESSION)
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  HYPOTHESIS H6: ODDS vs CATEGORY (LOGISTIC REGRESSION)")
print("=" * 70)

try:
    import statsmodels.api as sm
    import pandas as pd

    df = pd.DataFrame(joined)
    df["log_odds"] = np.log(df["ah_odds"])
    
    # Model 1: odds only
    X1 = sm.add_constant(df[["log_odds"]])
    y = df["is_jackpot"]
    model1 = sm.Logit(y, X1).fit(disp=0)
    
    # Model 2: odds + category
    cat_dummies = pd.get_dummies(df["category"], drop_first=True, dtype=float)
    X2 = sm.add_constant(pd.concat([df[["log_odds"]], cat_dummies], axis=1))
    model2 = sm.Logit(y, X2).fit(disp=0)
    
    # Likelihood ratio test
    lr_stat = 2 * (model2.llf - model1.llf)
    lr_df = model2.df_model - model1.df_model
    lr_p = 1 - stats.chi2.cdf(lr_stat, lr_df)
    
    print(f"\n  Model 1 (odds only):        AIC={model1.aic:.1f}, log-L={model1.llf:.1f}")
    print(f"  Model 2 (odds + category):  AIC={model2.aic:.1f}, log-L={model2.llf:.1f}")
    print(f"\n  Likelihood ratio test (does category add value beyond odds?):")
    print(f"    LR statistic: {lr_stat:.4f}")
    print(f"    df: {lr_df}")
    print(f"    p-value: {lr_p:.6f}")
    
    if lr_p < 0.05:
        print(f"    *** SIGNIFICANT: Category adds predictive value beyond just odds ***")
        print(f"\n  Category coefficients (Model 2):")
        for name, coef, pval in zip(model2.params.index, model2.params.values, model2.pvalues.values):
            sig = "*" if pval < 0.05 else ""
            print(f"    {name:<25} coef={coef:>8.4f}  p={pval:.4f} {sig}")
    else:
        print(f"    NOT SIGNIFICANT: Category doesn't matter after controlling for odds")
        print(f"    → The edge (if any) is purely in the odds bracket, not the category")

except ImportError:
    print("  (statsmodels/pandas not available — skipping logistic regression)")


# ═══════════════════════════════════════════════════════════
#  OVERALL EV ANALYSIS: WHAT WOULD BETTING LOOK LIKE?
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  EV SIMULATION: FLAT BETTING ON EACH BRACKET")
print("=" * 70)

print(f"\n  Simulating NGN 10 flat bet on every AH selection per bracket:")
print(f"  {'Bracket':>10} {'Bets':>8} {'Wins':>6} {'Revenue':>10} {'Cost':>10} {'Profit':>10} {'ROI':>8}")
print("  " + "-" * 70)

for label, lo, hi in brackets_def:
    b_data = [m for m in joined if lo <= m["ah_odds"] < hi]
    n = len(b_data)
    hits = sum(m["is_jackpot"] for m in b_data)
    if n == 0:
        continue
    stake = 10.0
    cost = n * stake
    revenue = sum(m["ah_odds"] * stake for m in b_data if m["is_jackpot"])
    profit = revenue - cost
    roi = profit / cost * 100
    print(f"  {label:>10} {n:>8,} {hits:>6} {revenue:>9,.0f} {cost:>9,.0f} {profit:>+9,.0f} {roi:>+7.1f}%")

# Combined 55-75x
h1_cost = h1_n * 10
h1_revenue = sum(m["ah_odds"] * 10 for m in h1_data if m["is_jackpot"])
h1_profit = h1_revenue - h1_cost
h1_roi = h1_profit / h1_cost * 100 if h1_cost > 0 else 0
print(f"\n  55-75x combined: {h1_n:,} bets | {h1_hits} wins | profit: NGN {h1_profit:+,.0f} | ROI: {h1_roi:+.1f}%")


# ═══════════════════════════════════════════════════════════
#  FINAL VERDICT
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  FINAL VERDICT")
print("=" * 70)

verdicts = {
    "H1": "SIGNIFICANT" if (bracket_results.get("55-60", {}).get("pval", 1) < 0.05 or 
           bracket_results.get("60-65", {}).get("pval", 1) < 0.05 or
           bracket_results.get("65-75", {}).get("pval", 1) < 0.05 or
           h1_pval < 0.05) else "NOT SIGNIFICANT",
    "H2": "SIGNIFICANT" if p_h2 < 0.05 else "NOT SIGNIFICANT",
    "H3": "SIGNIFICANT" if (h3 and bracket_results.get("50-55", {}).get("pval", 1) > 0.95) else "NOT SIGNIFICANT",
    "H4": "SIGNIFICANT" if (h4 and h4_p < 0.05) else "NOT SIGNIFICANT",
    "H5": "STABLE" if not drift_detected else "DRIFT DETECTED",
}

for h, v in verdicts.items():
    desc = {
        "H1": "55-75x bracket edge is real",
        "H2": "Category matters for AH rate",
        "H3": "50-55x dead zone is real",
        "H4": "100x odds are a trap",
        "H5": "AH rate is stable over time",
    }[h]
    marker = "✅" if "SIGNIFICANT" in v or "STABLE" in v else "❌"
    print(f"  {marker} {h}: {desc} → {v}")

print(f"\n  {'=' * 66}")
if verdicts["H1"] == "SIGNIFICANT":
    print(f"  CONCLUSION: There IS an exploitable edge in the 55-75x bracket.")
    print(f"  Proceed to strategy deployment (Section 9 of RESEARCH_PLAN.md).")
else:
    print(f"  CONCLUSION: No statistically significant edge found in any bracket.")
    print(f"  The RNG pricing appears fair within the sample collected.")
    print(f"  Consider collecting more data (2,000+ rounds for 90% power)")
    print(f"  or accept that the game has no exploitable edge.")
print(f"  {'=' * 66}")

conn.close()
