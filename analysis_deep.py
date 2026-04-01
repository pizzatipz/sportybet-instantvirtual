"""
Deep dive analysis on the two signals that showed significance:
1. The 60-65x sub-bracket (p=0.031 uncorrected)
2. Category differences (p < 0.000001)

Plus: Can we combine BOTH signals (category + odds bracket) for a real edge?
"""

import sqlite3
import numpy as np
from scipy import stats
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent / "data" / "sportybet.db"
conn = sqlite3.connect(str(DB_PATH))

# ── Rebuild joined dataset ──
pairing_odds = conn.execute("""
    SELECT category, home_team, away_team, AVG(odds) as avg_odds
    FROM market_odds
    WHERE market='HT/FT' AND selection='Away/ Home'
    GROUP BY category, home_team, away_team
""").fetchall()
odds_lookup = {(c, h, a): o for c, h, a, o in pairing_odds}

all_matches = conn.execute("""
    SELECT category, home_team, away_team, is_jackpot, round_id
    FROM matches ORDER BY id
""").fetchall()

joined = []
for cat, home, away, is_jp, rid in all_matches:
    key = (cat, home, away)
    if key in odds_lookup:
        joined.append({
            "category": cat, "home_team": home, "away_team": away,
            "is_jackpot": is_jp, "ah_odds": odds_lookup[key], "round_id": rid,
        })

total_matches = len(all_matches)
total_joined = len(joined)


def wilson_ci(hits, n, z=1.96):
    if n == 0:
        return 0.0, 0.0, 0.0
    p = hits / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * np.sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return p, max(0, center - margin), min(1, center + margin)


def one_prop_z_test(hits, n, p0, alt="greater"):
    p_hat = hits / n
    se = np.sqrt(p0 * (1 - p0) / n)
    z = (p_hat - p0) / se
    if alt == "greater":
        return z, 1 - stats.norm.cdf(z)
    elif alt == "less":
        return z, stats.norm.cdf(z)
    return z, 2 * (1 - stats.norm.cdf(abs(z)))


# ═══════════════════════════════════════════════════════════
#  PART 1: 60-65x BRACKET — MULTIPLE COMPARISON CORRECTION
# ═══════════════════════════════════════════════════════════

print("=" * 70)
print("  DEEP DIVE 1: 60-65x BRACKET WITH BONFERRONI CORRECTION")
print("=" * 70)

brackets_def = [
    ("<30", 0, 30), ("30-40", 30, 40), ("40-50", 40, 50),
    ("50-55", 50, 55), ("55-60", 55, 60), ("60-65", 60, 65),
    ("65-75", 65, 75), ("75-90", 75, 90), ("90-100", 90, 100), ("100+", 100, 999),
]

# Collect all p-values for Bonferroni correction
pvals = []
bracket_stats = []
for label, lo, hi in brackets_def:
    b_data = [m for m in joined if lo <= m["ah_odds"] < hi]
    n = len(b_data)
    if n == 0:
        continue
    hits = sum(m["is_jackpot"] for m in b_data)
    avg_odds = np.mean([m["ah_odds"] for m in b_data])
    implied = 1.0 / avg_odds
    rate, ci_lo, ci_hi = wilson_ci(hits, n)
    z, pval = one_prop_z_test(hits, n, implied, alt="greater")
    pvals.append(pval)
    bracket_stats.append((label, n, hits, rate, avg_odds, implied, z, pval, ci_lo, ci_hi))

# Bonferroni correction: multiply each p-value by number of tests
n_tests = len(pvals)
print(f"\n  Number of brackets tested: {n_tests}")
print(f"  Bonferroni threshold: 0.05/{n_tests} = {0.05/n_tests:.4f}")

print(f"\n  {'Bracket':>10} {'N':>8} {'Hits':>6} {'Rate':>7} {'Implied':>8} {'Raw p':>9} {'Bonf p':>9} {'Sig?':>5}")
print("  " + "-" * 75)
for label, n, hits, rate, avg_odds, implied, z, pval, ci_lo, ci_hi in bracket_stats:
    bonf_p = min(pval * n_tests, 1.0)
    sig = "YES" if bonf_p < 0.05 else "no"
    print(f"  {label:>10} {n:>8,} {hits:>6} {rate*100:>6.2f}% {implied*100:>7.2f}% {pval:>9.5f} {bonf_p:>9.5f} {sig:>5}")

# Holm-Bonferroni (less conservative)
sorted_pvals = sorted(enumerate(pvals), key=lambda x: x[1])
holm_sig = set()
for rank, (idx, pv) in enumerate(sorted_pvals):
    threshold = 0.05 / (n_tests - rank)
    if pv < threshold:
        holm_sig.add(idx)
    else:
        break

print(f"\n  Holm-Bonferroni significant brackets: ", end="")
if holm_sig:
    for idx in holm_sig:
        print(f"{bracket_stats[idx][0]} ", end="")
    print()
else:
    print("NONE")

# Direct verdict on 60-65x
b6065 = [s for s in bracket_stats if s[0] == "60-65"][0]
bonf_p_6065 = min(b6065[7] * n_tests, 1.0)
print(f"\n  60-65x bracket after Bonferroni correction:")
print(f"    Raw p = {b6065[7]:.5f} → Corrected p = {bonf_p_6065:.5f}")
if bonf_p_6065 < 0.05:
    print(f"    ★ SURVIVES correction — this is a genuine signal")
else:
    print(f"    ✗ Does NOT survive correction — likely a false positive from testing 10 brackets")


# ═══════════════════════════════════════════════════════════
#  PART 2: CATEGORY × ODDS BRACKET INTERACTION
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  DEEP DIVE 2: CATEGORY × ODDS BRACKET INTERACTION")
print("=" * 70)

# The best categories are Club World Cup, Germany, Champions
# Can we find an edge when we restrict to these categories AND specific brackets?

good_cats = {"Club World Cup", "Germany", "Champions"}
bad_cats = {"Italy", "England"}

print(f"\n  Top categories: {', '.join(good_cats)}")
print(f"  Bottom categories: {', '.join(bad_cats)}")

# Bracket analysis within top categories only
print(f"\n  AH rate in TOP categories by odds bracket:")
print(f"  {'Bracket':>10} {'N':>8} {'Hits':>6} {'Rate':>7} {'AvgOdds':>8} {'Implied':>8} {'EV':>8} {'p-val':>8}")
print("  " + "-" * 75)

best_combo = None
best_ev = -999
for label, lo, hi in brackets_def:
    b_data = [m for m in joined if lo <= m["ah_odds"] < hi and m["category"] in good_cats]
    n = len(b_data)
    if n < 50:
        continue
    hits = sum(m["is_jackpot"] for m in b_data)
    avg_odds = np.mean([m["ah_odds"] for m in b_data])
    implied = 1.0 / avg_odds
    rate, ci_lo, ci_hi = wilson_ci(hits, n)
    z, pval = one_prop_z_test(hits, n, implied, alt="greater")
    ev = (rate * avg_odds - 1) * 100
    print(f"  {label:>10} {n:>8,} {hits:>6} {rate*100:>6.2f}% {avg_odds:>7.1f}x {implied*100:>7.2f}% {ev:>+7.1f}% {pval:>8.5f}")
    if ev > best_ev:
        best_ev = ev
        best_combo = (label, n, hits, rate, avg_odds, implied, ev, pval)

print(f"\n  Best combo in top categories: {best_combo[0]} bracket")
print(f"    {best_combo[2]}/{best_combo[1]} = {best_combo[3]*100:.2f}% at avg {best_combo[4]:.1f}x odds")
print(f"    EV = {best_combo[6]:+.1f}%, p = {best_combo[7]:.5f}")

# Same for bottom categories
print(f"\n  AH rate in BOTTOM categories by odds bracket:")
print(f"  {'Bracket':>10} {'N':>8} {'Hits':>6} {'Rate':>7} {'AvgOdds':>8} {'EV':>8}")
print("  " + "-" * 60)
for label, lo, hi in brackets_def:
    b_data = [m for m in joined if lo <= m["ah_odds"] < hi and m["category"] in bad_cats]
    n = len(b_data)
    if n < 50:
        continue
    hits = sum(m["is_jackpot"] for m in b_data)
    avg_odds = np.mean([m["ah_odds"] for m in b_data])
    rate = hits / n
    ev = (rate * avg_odds - 1) * 100
    print(f"  {label:>10} {n:>8,} {hits:>6} {rate*100:>6.2f}% {avg_odds:>7.1f}x {ev:>+7.1f}%")


# ═══════════════════════════════════════════════════════════
#  PART 3: PER-CATEGORY FULL ANALYSIS (no odds filter)
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  DEEP DIVE 3: PER-CATEGORY ANALYSIS (ALL MATCHES)")
print("=" * 70)

# Using ALL matches (not just those with odds), since category effect
# was proven significant on the full dataset
cats_full = conn.execute("""
    SELECT category, COUNT(*) as n, SUM(is_jackpot) as jp
    FROM matches GROUP BY category ORDER BY CAST(jp AS FLOAT)/n DESC
""").fetchall()

overall_rate = sum(jp for _, _, jp in cats_full) / sum(n for _, n, _ in cats_full)
print(f"\n  Overall AH rate: {overall_rate*100:.3f}%")
print(f"\n  {'Category':<18} {'N':>8} {'JP':>6} {'Rate':>7} {'95% CI':>20} {'vs overall':>12} {'p-val':>9}")
print("  " + "-" * 85)

for cat, n, jp in cats_full:
    rate, ci_lo, ci_hi = wilson_ci(jp, n)
    z, pval = one_prop_z_test(jp, n, overall_rate, alt="two-sided")
    diff = (rate - overall_rate) * 100
    sig = "*" if pval < 0.05 else ""
    print(f"  {cat:<18} {n:>8,} {jp:>6} {rate*100:>6.2f}% [{ci_lo*100:.2f}%-{ci_hi*100:.2f}%] {diff:>+10.2f}pp {pval:>9.5f} {sig}")


# ═══════════════════════════════════════════════════════════
#  PART 4: SIMULATED STRATEGY — TOP 3 CATEGORIES, ALL ODDS
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  STRATEGY SIMULATION: TOP 3 CATEGORIES")
print("=" * 70)

# If we bet AH on EVERY match in the top 3 categories at offered odds,
# what would the P&L be? Using joined data (with odds).
top3_all = [m for m in joined if m["category"] in good_cats]
n_t3 = len(top3_all)
hits_t3 = sum(m["is_jackpot"] for m in top3_all)
rate_t3 = hits_t3 / n_t3
avg_odds_t3 = np.mean([m["ah_odds"] for m in top3_all])

cost_t3 = n_t3 * 10
revenue_t3 = sum(m["ah_odds"] * 10 for m in top3_all if m["is_jackpot"])
profit_t3 = revenue_t3 - cost_t3
roi_t3 = profit_t3 / cost_t3 * 100

print(f"\n  Strategy: Bet NGN 10 on AH for every match in Club World Cup + Germany + Champions")
print(f"  Bets:     {n_t3:,}")
print(f"  Wins:     {hits_t3}")
print(f"  Hit rate: {rate_t3*100:.2f}%")
print(f"  Avg odds: {avg_odds_t3:.1f}x")
print(f"  Revenue:  NGN {revenue_t3:,.0f}")
print(f"  Cost:     NGN {cost_t3:,.0f}")
print(f"  Profit:   NGN {profit_t3:+,.0f}")
print(f"  ROI:      {roi_t3:+.1f}%")

# Now restrict to 55-75x bracket within top 3 categories
top3_5575 = [m for m in joined if m["category"] in good_cats and 55 <= m["ah_odds"] < 75]
n_t35 = len(top3_5575)
hits_t35 = sum(m["is_jackpot"] for m in top3_5575)
rate_t35 = hits_t35 / n_t35 if n_t35 > 0 else 0
avg_odds_t35 = np.mean([m["ah_odds"] for m in top3_5575]) if top3_5575 else 0

cost_t35 = n_t35 * 10
revenue_t35 = sum(m["ah_odds"] * 10 for m in top3_5575 if m["is_jackpot"])
profit_t35 = revenue_t35 - cost_t35
roi_t35 = profit_t35 / cost_t35 * 100 if cost_t35 > 0 else 0

implied_t35 = 1 / avg_odds_t35 if avg_odds_t35 > 0 else 0
z_t35, p_t35 = one_prop_z_test(hits_t35, n_t35, implied_t35, alt="greater") if n_t35 > 0 else (0, 1)

print(f"\n  Restricted: Top 3 categories + 55-75x bracket")
print(f"  Bets:     {n_t35:,}")
print(f"  Wins:     {hits_t35}")
print(f"  Hit rate: {rate_t35*100:.2f}%")
print(f"  Implied:  {implied_t35*100:.2f}%")
print(f"  Avg odds: {avg_odds_t35:.1f}x")
print(f"  Revenue:  NGN {revenue_t35:,.0f}")
print(f"  Cost:     NGN {cost_t35:,.0f}")
print(f"  Profit:   NGN {profit_t35:+,.0f}")
print(f"  ROI:      {roi_t35:+.1f}%")
print(f"  p-value:  {p_t35:.5f}")

# Top 3 categories, 60-65x only
top3_6065 = [m for m in joined if m["category"] in good_cats and 60 <= m["ah_odds"] < 65]
n_t36 = len(top3_6065)
hits_t36 = sum(m["is_jackpot"] for m in top3_6065)
rate_t36 = hits_t36 / n_t36 if n_t36 > 0 else 0
avg_odds_t36 = np.mean([m["ah_odds"] for m in top3_6065]) if top3_6065 else 0

cost_t36 = n_t36 * 10
revenue_t36 = sum(m["ah_odds"] * 10 for m in top3_6065 if m["is_jackpot"])
profit_t36 = revenue_t36 - cost_t36
roi_t36 = profit_t36 / cost_t36 * 100 if cost_t36 > 0 else 0

implied_t36 = 1 / avg_odds_t36 if avg_odds_t36 > 0 else 0
z_t36, p_t36 = one_prop_z_test(hits_t36, n_t36, implied_t36, alt="greater") if n_t36 > 0 else (0, 1)

print(f"\n  Restricted: Top 3 categories + 60-65x bracket")
print(f"  Bets:     {n_t36:,}")
print(f"  Wins:     {hits_t36}")
print(f"  Hit rate: {rate_t36*100:.2f}%")
print(f"  Implied:  {implied_t36*100:.2f}%")
print(f"  Avg odds: {avg_odds_t36:.1f}x")
print(f"  Profit:   NGN {profit_t36:+,.0f}")
print(f"  ROI:      {roi_t36:+.1f}%")
print(f"  p-value:  {p_t36:.5f}")


# ═══════════════════════════════════════════════════════════
#  FINAL HONEST ASSESSMENT
# ═══════════════════════════════════════════════════════════

print("\n" + "=" * 70)
print("  FINAL HONEST ASSESSMENT")
print("=" * 70)

print("""
  WHAT IS PROVEN (statistically significant):
  1. Category differences are REAL — Club World Cup, Germany, and
     Champions have genuinely higher AH rates than Italy and England.
  2. The 50-55x bracket IS a dead zone — hit rate is significantly
     below implied probability.
  3. The RNG is random within categories (runs test passed).

  WHAT IS NOT PROVEN:
  1. No specific odds bracket has a significant edge after correcting
     for multiple comparisons (Bonferroni).
  2. The combined 55-75x bracket has essentially zero edge (p=0.45).
  3. The 100x trap hypothesis is not confirmed.

  THE HONEST QUESTION:
  Can the category effect alone create a profitable strategy?
  → The top 3 categories have ~1.74% AH rate vs ~1.12% for bottom 2.
  → But profitability depends on the ODDS offered in those categories.
  → If the bookmaker adjusts odds per category (lower odds where AH
     is more likely), the category edge is already priced in.
""")

# Check: are odds lower in high-AH categories?
print("  Are odds lower in high-AH categories? (if yes, edge is priced in)")
print(f"  {'Category':<18} {'AH Rate':>8} {'Avg AH Odds':>12}")
print("  " + "-" * 40)
for cat in ["Club World Cup", "Germany", "Champions", "Spain", "Euros", "African Cup", "England", "Italy"]:
    cat_joined = [m for m in joined if m["category"] == cat]
    if not cat_joined:
        continue
    rate = sum(m["is_jackpot"] for m in cat_joined) / len(cat_joined) * 100
    avg_o = np.mean([m["ah_odds"] for m in cat_joined])
    print(f"  {cat:<18} {rate:>7.2f}% {avg_o:>11.1f}x")

conn.close()
