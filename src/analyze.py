"""
Statistical analysis pipeline for SportyBet HT/FT RNG study.

Focuses on:
1. HT/FT outcome distribution across all 9 selections
2. Away/Home (jackpot at 100.00 odds) frequency and patterns
3. Category and team-level analysis
4. Independence tests (chi-squared, runs test, autocorrelation)
5. Pattern detection (FFT, transition matrix, cross-category correlation)
"""

import argparse
import sys
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
from scipy import stats as sp_stats
from scipy.fft import fft

from src.db import (
    get_connection, init_db, get_total_stats, get_htft_distribution,
    get_jackpots, get_jackpot_rate_by_category, get_jackpot_teams,
    get_matches_by_category, get_all_matches, export_to_csv,
    CATEGORIES, HTFT_OUTCOMES, JACKPOT_OUTCOME, DB_PATH,
)

REPORTS_DIR = Path(__file__).parent.parent / "reports"


def load_dataframe(conn) -> pd.DataFrame:
    """Load all matches into a pandas DataFrame."""
    matches = get_all_matches(conn)
    if not matches:
        print("❌ No data in database. Run the bot first to collect data.")
        sys.exit(1)
    df = pd.DataFrame(matches)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ─────────────────────────────────────────────────────────────
# 1. DESCRIPTIVE STATISTICS
# ─────────────────────────────────────────────────────────────

def descriptive_stats(df: pd.DataFrame) -> None:
    """Print comprehensive descriptive statistics."""
    print("\n" + "=" * 70)
    print("DESCRIPTIVE STATISTICS")
    print("=" * 70)

    total = len(df)
    rounds = df["round_id"].nunique()
    cats = df["category"].nunique()
    jackpots = df["is_jackpot"].sum()

    print(f"\nTotal matches:     {total}")
    print(f"Total rounds:      {rounds}")
    print(f"Categories:        {cats}")
    print(f"Matches per round: {total / rounds:.1f}" if rounds > 0 else "")

    print(f"\n{'─' * 40}")
    print("HT/FT OUTCOME DISTRIBUTION (ALL DATA)")
    print(f"{'─' * 40}")

    htft_counts = df["htft_result"].value_counts()
    for outcome in HTFT_OUTCOMES:
        count = htft_counts.get(outcome, 0)
        pct = count / total * 100 if total > 0 else 0
        marker = " ◀ JACKPOT" if outcome == JACKPOT_OUTCOME else ""
        print(f"  {outcome:<12}  {count:>6}  ({pct:>5.2f}%){marker}")

    print(f"\n  Total:       {total:>6}")
    print(f"\n  Jackpots (Away/Home): {jackpots} / {total} = {jackpots/total*100:.3f}%")
    print(f"  Expected at 1% (100.00 odds): {total * 0.01:.1f}")
    print(f"  Ratio to expected: {jackpots / (total * 0.01):.2f}x" if total > 0 else "")


def category_breakdown(df: pd.DataFrame) -> None:
    """Print HT/FT distribution per category."""
    print(f"\n{'=' * 70}")
    print("HT/FT DISTRIBUTION BY CATEGORY")
    print(f"{'=' * 70}")

    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat]
        n = len(cat_df)
        jackpots = cat_df["is_jackpot"].sum()
        jp_rate = jackpots / n * 100 if n > 0 else 0

        print(f"\n  {cat} ({n} matches, {jackpots} jackpots = {jp_rate:.2f}%)")
        htft_counts = cat_df["htft_result"].value_counts()
        for outcome in HTFT_OUTCOMES:
            count = htft_counts.get(outcome, 0)
            pct = count / n * 100 if n > 0 else 0
            bar = "█" * int(pct / 2)
            print(f"    {outcome:<12}  {count:>4}  ({pct:>5.2f}%)  {bar}")


def jackpot_deep_dive(df: pd.DataFrame) -> None:
    """Detailed analysis of Away/Home (jackpot) occurrences."""
    print(f"\n{'=' * 70}")
    print("JACKPOT (AWAY/HOME) DEEP DIVE")
    print(f"{'=' * 70}")

    jp = df[df["is_jackpot"] == 1]

    if jp.empty:
        print("\n  No jackpots found in data yet.")
        return

    print(f"\n  Total jackpots: {len(jp)}")
    print(f"  Overall rate: {len(jp)/len(df)*100:.3f}%")

    # By category
    print(f"\n  {'─' * 40}")
    print("  JACKPOTS BY CATEGORY")
    cat_jp = jp.groupby("category").size().sort_values(ascending=False)
    for cat, count in cat_jp.items():
        cat_total = len(df[df["category"] == cat])
        print(f"    {cat:<15}  {count:>3} / {cat_total:>5} = {count/cat_total*100:.2f}%")

    # By home team (team that came back to win)
    print(f"\n  {'─' * 40}")
    print("  TEAMS THAT CAME BACK TO WIN (HOME TEAM IN JACKPOT)")
    home_jp = jp.groupby(["home_team", "category"]).size().sort_values(ascending=False)
    for (team, cat), count in home_jp.head(15).items():
        print(f"    {team:<20} ({cat:<15})  {count}")

    # By away team (team that led at HT but lost)
    print(f"\n  {'─' * 40}")
    print("  TEAMS THAT BLEW HT LEAD (AWAY TEAM IN JACKPOT)")
    away_jp = jp.groupby(["away_team", "category"]).size().sort_values(ascending=False)
    for (team, cat), count in away_jp.head(15).items():
        print(f"    {team:<20} ({cat:<15})  {count}")

    # Score patterns
    print(f"\n  {'─' * 40}")
    print("  COMMON SCORE PATTERNS IN JACKPOTS")
    jp["score_pattern"] = (
        jp["ht_home_goals"].astype(str) + "-" + jp["ht_away_goals"].astype(str) +
        " → " +
        jp["ft_home_goals"].astype(str) + "-" + jp["ft_away_goals"].astype(str)
    )
    patterns = jp["score_pattern"].value_counts()
    for pattern, count in patterns.head(10).items():
        print(f"    {pattern:<15}  {count}")

    # Inter-arrival: rounds between jackpots per category
    print(f"\n  {'─' * 40}")
    print("  ROUNDS BETWEEN JACKPOTS (per category)")
    for cat in sorted(jp["category"].unique()):
        cat_all = df[df["category"] == cat].copy()
        cat_all = cat_all.sort_values("timestamp")
        # Get round-level jackpot indicators
        round_jp = cat_all.groupby("round_id")["is_jackpot"].max()
        if round_jp.sum() < 2:
            continue
        # Find positions of jackpots
        jp_positions = np.where(round_jp.values == 1)[0]
        gaps = np.diff(jp_positions)
        if len(gaps) > 0:
            print(f"    {cat:<15}  mean={gaps.mean():.1f}  "
                  f"min={gaps.min()}  max={gaps.max()}  "
                  f"median={np.median(gaps):.0f}  (n={len(gaps)})")


# ─────────────────────────────────────────────────────────────
# 2. INDEPENDENCE TESTS
# ─────────────────────────────────────────────────────────────

def chi_squared_test(df: pd.DataFrame) -> None:
    """Chi-squared goodness-of-fit: do HT/FT outcomes match implied probabilities?"""
    print(f"\n{'=' * 70}")
    print("CHI-SQUARED GOODNESS-OF-FIT TEST")
    print(f"{'=' * 70}")

    # If we don't have odds data, test against uniform distribution
    # and against theoretical HT/FT probabilities
    observed = df["htft_result"].value_counts()
    total = len(df)

    # Ensure all outcomes are represented
    obs_values = [observed.get(o, 0) for o in HTFT_OUTCOMES]

    # Test 1: Against uniform distribution (each outcome equally likely)
    expected_uniform = [total / 9] * 9
    chi2, p_uniform = sp_stats.chisquare(obs_values, expected_uniform)
    print(f"\n  vs Uniform (each 11.1%):")
    print(f"    χ² = {chi2:.4f}, p = {p_uniform:.6f}")
    print(f"    {'REJECT' if p_uniform < 0.05 else 'CANNOT REJECT'} uniform at α=0.05")

    # Test 2: Against reasonable HT/FT probabilities
    # In real football, approximate HT/FT probabilities:
    # HH~25%, HD~10%, HA~3%, DH~15%, DD~12%, DA~5%, AH~1%, AD~5%, AA~24%
    # These are rough approximations — virtual soccer may differ
    theoretical = [0.25, 0.10, 0.03, 0.15, 0.12, 0.05, 0.01, 0.05, 0.24]
    expected_theoretical = [p * total for p in theoretical]
    chi2_t, p_theoretical = sp_stats.chisquare(obs_values, expected_theoretical)
    print(f"\n  vs Theoretical football HT/FT probs:")
    print(f"    χ² = {chi2_t:.4f}, p = {p_theoretical:.6f}")
    print(f"    {'REJECT' if p_theoretical < 0.05 else 'CANNOT REJECT'} at α=0.05")

    # Per-category chi-squared
    print(f"\n  Per-category tests (vs overall distribution):")
    overall_props = np.array(obs_values) / total
    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat]
        cat_n = len(cat_df)
        cat_obs = [cat_df["htft_result"].value_counts().get(o, 0) for o in HTFT_OUTCOMES]
        cat_exp = [p * cat_n for p in overall_props]
        # Skip if expected counts too low
        if min(cat_exp) < 1:
            print(f"    {cat:<15}  SKIPPED (not enough data)")
            continue
        chi2_c, p_c = sp_stats.chisquare(cat_obs, cat_exp)
        sig = "*" if p_c < 0.05 else " "
        print(f"    {cat:<15}  χ²={chi2_c:>8.3f}  p={p_c:.4f} {sig}")


def runs_test(df: pd.DataFrame) -> None:
    """Wald-Wolfowitz runs test on jackpot/non-jackpot sequence per category."""
    print(f"\n{'=' * 70}")
    print("RUNS TEST (JACKPOT SEQUENCE RANDOMNESS)")
    print(f"{'=' * 70}")
    print("  Testing whether jackpot/non-jackpot sequences are random.\n")

    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat].sort_values("timestamp")
        if len(cat_df) < 20:
            continue

        # Per-match jackpot sequence
        seq = cat_df["is_jackpot"].values

        # Count runs
        n1 = np.sum(seq == 1)
        n0 = np.sum(seq == 0)
        if n1 < 2 or n0 < 2:
            print(f"  {cat:<15}  Too few jackpots for runs test")
            continue

        runs = 1
        for i in range(1, len(seq)):
            if seq[i] != seq[i - 1]:
                runs += 1

        # Expected runs and variance under H0
        n = len(seq)
        expected_runs = 1 + 2 * n1 * n0 / n
        var_runs = (2 * n1 * n0 * (2 * n1 * n0 - n)) / (n * n * (n - 1))

        if var_runs <= 0:
            continue

        z = (runs - expected_runs) / np.sqrt(var_runs)
        p_value = 2 * (1 - sp_stats.norm.cdf(abs(z)))

        sig = "*" if p_value < 0.05 else " "
        print(f"  {cat:<15}  runs={runs:>4}  expected={expected_runs:>6.1f}  "
              f"z={z:>6.3f}  p={p_value:.4f} {sig}")


def autocorrelation_analysis(df: pd.DataFrame) -> None:
    """Autocorrelation of jackpot sequence and HT/FT outcome encoding."""
    print(f"\n{'=' * 70}")
    print("AUTOCORRELATION ANALYSIS")
    print(f"{'=' * 70}")

    max_lag = 20

    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat].sort_values("timestamp")
        if len(cat_df) < max_lag * 3:
            continue

        print(f"\n  {cat} ({len(cat_df)} matches)")

        # Jackpot sequence autocorrelation
        seq = cat_df["is_jackpot"].values.astype(float)
        mean = np.mean(seq)
        if np.std(seq) == 0:
            print("    Jackpot: no variance (all 0 or all 1)")
            continue

        # Manual autocorrelation (normalized)
        n = len(seq)
        centered = seq - mean
        var = np.sum(centered ** 2)

        significant_lags = []
        conf_bound = 1.96 / np.sqrt(n)  # 95% CI

        for lag in range(1, min(max_lag + 1, n // 3)):
            acf_val = np.sum(centered[:n - lag] * centered[lag:]) / var
            sig = "*" if abs(acf_val) > conf_bound else " "
            if abs(acf_val) > conf_bound:
                significant_lags.append(lag)

        if significant_lags:
            print(f"    ⚠ Significant autocorrelation at lags: {significant_lags}")
        else:
            print(f"    ✓ No significant autocorrelation (lags 1-{min(max_lag, n//3 - 1)})")

        # HT/FT outcome encoding autocorrelation
        outcome_map = {o: i for i, o in enumerate(HTFT_OUTCOMES)}
        encoded = cat_df["htft_result"].map(outcome_map).values.astype(float)
        enc_mean = np.mean(encoded)
        enc_centered = encoded - enc_mean
        enc_var = np.sum(enc_centered ** 2)

        if enc_var > 0:
            sig_lags_enc = []
            for lag in range(1, min(max_lag + 1, n // 3)):
                acf_val = np.sum(enc_centered[:n - lag] * enc_centered[lag:]) / enc_var
                if abs(acf_val) > conf_bound:
                    sig_lags_enc.append(lag)

            if sig_lags_enc:
                print(f"    ⚠ HT/FT outcome autocorrelation at lags: {sig_lags_enc}")
            else:
                print(f"    ✓ No HT/FT outcome autocorrelation")


# ─────────────────────────────────────────────────────────────
# 3. PATTERN DETECTION
# ─────────────────────────────────────────────────────────────

def spectral_analysis(df: pd.DataFrame) -> None:
    """FFT spectral analysis to detect periodic patterns in jackpot occurrences."""
    print(f"\n{'=' * 70}")
    print("SPECTRAL ANALYSIS (FFT)")
    print(f"{'=' * 70}")
    print("  Looking for periodic patterns in jackpot occurrences.\n")

    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat].sort_values("timestamp")
        if len(cat_df) < 50:
            continue

        seq = cat_df["is_jackpot"].values.astype(float)
        seq = seq - np.mean(seq)  # Remove DC component
        n = len(seq)

        # Compute FFT
        ft = fft(seq)
        power = np.abs(ft[:n // 2]) ** 2
        freqs = np.arange(n // 2) / n

        # Skip DC (index 0) and find dominant frequencies
        if len(power) > 1:
            power_no_dc = power[1:]
            freqs_no_dc = freqs[1:]

            # Is there a dominant frequency? (significantly above mean power)
            mean_power = np.mean(power_no_dc)
            std_power = np.std(power_no_dc)
            threshold = mean_power + 3 * std_power  # 3-sigma threshold

            peaks = np.where(power_no_dc > threshold)[0]
            if len(peaks) > 0:
                print(f"  {cat}: ⚠ PERIODIC PATTERNS DETECTED")
                for p in peaks[:5]:
                    period = 1 / freqs_no_dc[p] if freqs_no_dc[p] > 0 else float('inf')
                    print(f"    Period ≈ {period:.1f} matches, power = {power_no_dc[p]:.2f}")
            else:
                print(f"  {cat}: ✓ No significant periodic patterns")


def transition_matrix(df: pd.DataFrame) -> None:
    """Compute 9x9 transition matrix for HT/FT outcomes."""
    print(f"\n{'=' * 70}")
    print("TRANSITION MATRIX (HT/FT OUTCOME → NEXT HT/FT OUTCOME)")
    print(f"{'=' * 70}")

    for cat in sorted(df["category"].unique()):
        cat_df = df[df["category"] == cat].sort_values("timestamp")
        if len(cat_df) < 50:
            continue

        outcomes = cat_df["htft_result"].values
        n_outcomes = len(HTFT_OUTCOMES)
        matrix = np.zeros((n_outcomes, n_outcomes))
        idx = {o: i for i, o in enumerate(HTFT_OUTCOMES)}

        for i in range(len(outcomes) - 1):
            prev = outcomes[i]
            curr = outcomes[i + 1]
            if prev in idx and curr in idx:
                matrix[idx[prev], idx[curr]] += 1

        # Normalize rows to probabilities
        row_sums = matrix.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1  # Avoid division by zero
        prob_matrix = matrix / row_sums

        print(f"\n  {cat}:")
        # Abbreviated labels
        labels = ["HH", "HD", "HA", "DH", "DD", "DA", "AH", "AD", "AA"]
        header = "  From\\To  " + "  ".join(f"{l:>5}" for l in labels)
        print(f"  {header}")
        for i, label in enumerate(labels):
            row = "  ".join(f"{prob_matrix[i, j]:>5.2f}" for j in range(n_outcomes))
            total_n = int(matrix[i].sum())
            print(f"  {label:>7}   {row}  (n={total_n})")

        # Chi-squared test for independence of rows
        # Test if all rows are the same (memoryless)
        if np.min(matrix.sum(axis=1)) >= 5:
            chi2, p_value, dof, _ = sp_stats.chi2_contingency(
                matrix + 0.5  # Add small constant to avoid zero cells
            )
            sig = "⚠ DEPENDENT" if p_value < 0.05 else "✓ Independent"
            print(f"  Independence: χ²={chi2:.2f}, p={p_value:.4f} → {sig}")


def cross_category_correlation(df: pd.DataFrame) -> None:
    """Test whether jackpots in different categories are correlated within rounds."""
    print(f"\n{'=' * 70}")
    print("CROSS-CATEGORY JACKPOT CORRELATION")
    print(f"{'=' * 70}")
    print("  Do categories share the same RNG? (correlated jackpots within rounds)\n")

    # Build a round × category jackpot matrix
    cats = sorted(df["category"].unique())
    if len(cats) < 2:
        print("  Need at least 2 categories for cross-category analysis.")
        return

    round_cat = df.groupby(["round_id", "category"])["is_jackpot"].max().unstack(fill_value=0)

    # Only keep categories that appear in the data
    cats_present = [c for c in cats if c in round_cat.columns]
    if len(cats_present) < 2:
        print("  Not enough categories with data.")
        return

    print(f"  Rounds analyzed: {len(round_cat)}")
    print(f"  Categories: {len(cats_present)}")

    # Pairwise correlation
    print(f"\n  Pairwise jackpot correlation:")
    for i in range(len(cats_present)):
        for j in range(i + 1, len(cats_present)):
            c1, c2 = cats_present[i], cats_present[j]
            if c1 in round_cat.columns and c2 in round_cat.columns:
                a = round_cat[c1].values
                b = round_cat[c2].values
                if np.std(a) > 0 and np.std(b) > 0:
                    corr, p = sp_stats.pearsonr(a, b)
                    sig = "*" if p < 0.05 else " "
                    print(f"    {c1:<15} vs {c2:<15}  r={corr:>6.3f}  p={p:.4f} {sig}")

    # How many categories have a jackpot in the same round?
    jp_per_round = round_cat[cats_present].sum(axis=1)
    multi = jp_per_round[jp_per_round > 1]
    print(f"\n  Rounds with jackpots in multiple categories: {len(multi)} / {len(round_cat)}")
    if len(multi) > 0:
        print(f"  Distribution of jackpot count per round:")
        for count, freq in jp_per_round.value_counts().sort_index().items():
            print(f"    {int(count)} categories: {freq} rounds")


# ─────────────────────────────────────────────────────────────
# 4. GENERATE PLOTS
# ─────────────────────────────────────────────────────────────

def generate_plots(df: pd.DataFrame) -> None:
    """Generate all visualization plots."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid")

    # 1. HT/FT distribution bar chart
    fig, ax = plt.subplots(figsize=(12, 6))
    counts = df["htft_result"].value_counts()
    ordered = [counts.get(o, 0) for o in HTFT_OUTCOMES]
    colors = ["#2196F3" if o != JACKPOT_OUTCOME else "#FF5722" for o in HTFT_OUTCOMES]
    bars = ax.bar(HTFT_OUTCOMES, ordered, color=colors)
    ax.set_xlabel("HT/FT Outcome")
    ax.set_ylabel("Count")
    ax.set_title("HT/FT Outcome Distribution (All Categories)")
    ax.tick_params(axis="x", rotation=45)
    # Add expected line at 1% for Away/Home
    ax.axhline(y=len(df) * 0.01, color="red", linestyle="--", alpha=0.5,
               label=f"1% expected ({len(df)*0.01:.0f})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "htft_distribution.png", dpi=150)
    plt.close(fig)

    # 2. HT/FT by category (faceted)
    cats = sorted(df["category"].unique())
    n_cats = len(cats)
    if n_cats > 0:
        fig, axes = plt.subplots(2, 4, figsize=(20, 10))
        axes = axes.flatten()
        for i, cat in enumerate(cats[:8]):
            ax = axes[i]
            cat_df = df[df["category"] == cat]
            counts = cat_df["htft_result"].value_counts()
            ordered = [counts.get(o, 0) for o in HTFT_OUTCOMES]
            colors = ["#2196F3" if o != JACKPOT_OUTCOME else "#FF5722" for o in HTFT_OUTCOMES]
            ax.bar(range(9), ordered, color=colors)
            ax.set_title(cat)
            ax.set_xticks(range(9))
            ax.set_xticklabels(["HH", "HD", "HA", "DH", "DD", "DA", "AH", "AD", "AA"],
                               fontsize=7, rotation=45)
        for i in range(n_cats, 8):
            axes[i].set_visible(False)
        fig.suptitle("HT/FT Distribution by Category", fontsize=14)
        fig.tight_layout()
        fig.savefig(REPORTS_DIR / "htft_by_category.png", dpi=150)
        plt.close(fig)

    # 3. Jackpot rate by category
    fig, ax = plt.subplots(figsize=(10, 6))
    jp_rates = df.groupby("category")["is_jackpot"].mean() * 100
    jp_rates = jp_rates.sort_values(ascending=True)
    ax.barh(jp_rates.index, jp_rates.values, color="#FF5722")
    ax.axvline(x=1.0, color="black", linestyle="--", alpha=0.5, label="Expected (1%)")
    ax.set_xlabel("Jackpot Rate (%)")
    ax.set_title("Away/Home (Jackpot) Rate by Category")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "jackpot_frequency.png", dpi=150)
    plt.close(fig)

    # 4. Transition matrix heatmap (largest category)
    if len(df) > 50:
        largest_cat = df["category"].value_counts().index[0]
        cat_df = df[df["category"] == largest_cat].sort_values("timestamp")
        outcomes = cat_df["htft_result"].values
        labels = HTFT_OUTCOMES
        idx = {o: i for i, o in enumerate(labels)}
        matrix = np.zeros((9, 9))
        for i in range(len(outcomes) - 1):
            p, c = outcomes[i], outcomes[i + 1]
            if p in idx and c in idx:
                matrix[idx[p], idx[c]] += 1
        row_sums = matrix.sum(axis=1, keepdims=True)
        row_sums[row_sums == 0] = 1
        prob = matrix / row_sums

        fig, ax = plt.subplots(figsize=(10, 8))
        short = ["HH", "HD", "HA", "DH", "DD", "DA", "AH", "AD", "AA"]
        sns.heatmap(prob, annot=True, fmt=".2f", cmap="YlOrRd",
                    xticklabels=short, yticklabels=short, ax=ax)
        ax.set_title(f"HT/FT Transition Matrix — {largest_cat}")
        ax.set_xlabel("Next Outcome")
        ax.set_ylabel("Previous Outcome")
        fig.tight_layout()
        fig.savefig(REPORTS_DIR / "transition_matrix.png", dpi=150)
        plt.close(fig)

    print(f"\n📊 Plots saved to {REPORTS_DIR}/")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def run_analysis(jackpot_only: bool = False, category: str = None,
                 export: str = None, plots: bool = True) -> None:
    """Run the full analysis pipeline."""
    conn = get_connection()
    init_db(conn)

    stats = get_total_stats(conn)
    if stats["total_matches"] == 0:
        print("❌ No data in database. Run the bot first:")
        print("   python -m src.bot --manual")
        print("   python -m src.bot")
        conn.close()
        return

    df = load_dataframe(conn)

    if category:
        df = df[df["category"] == category]
        if df.empty:
            print(f"No data for category '{category}'")
            conn.close()
            return

    # Run analyses
    descriptive_stats(df)

    if not jackpot_only:
        category_breakdown(df)

    jackpot_deep_dive(df)

    if not jackpot_only:
        chi_squared_test(df)
        runs_test(df)
        autocorrelation_analysis(df)
        spectral_analysis(df)
        transition_matrix(df)
        cross_category_correlation(df)

    if plots:
        generate_plots(df)

    if export == "csv":
        export_to_csv(conn, Path(__file__).parent.parent / "data" / "matches_export.csv")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="SportyBet HT/FT RNG Analysis Pipeline"
    )
    parser.add_argument("--jackpot", action="store_true",
                        help="Jackpot-focused analysis only")
    parser.add_argument("--category", type=str, default=None,
                        help="Analyze a specific category only")
    parser.add_argument("--export", type=str, choices=["csv"], default=None,
                        help="Export format")
    parser.add_argument("--no-plots", action="store_true",
                        help="Skip plot generation")
    args = parser.parse_args()

    run_analysis(
        jackpot_only=args.jackpot,
        category=args.category,
        export=args.export,
        plots=not args.no_plots,
    )


if __name__ == "__main__":
    main()
