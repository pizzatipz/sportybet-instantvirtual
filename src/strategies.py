"""
Strategy backtester for SportyBet HT/FT jackpot (Away/Home at 100.00 odds).

Tests various betting strategies against collected data to determine
if any approach yields positive expected value on the jackpot bet.
"""

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from src.db import (
    get_connection, init_db, get_all_matches,
    CATEGORIES, JACKPOT_OUTCOME,
)


JACKPOT_ODDS = 100.0
DEFAULT_STAKE = 10.0  # ₦10


@dataclass
class BetResult:
    """Result of a single bet."""
    round_id: str
    category: str
    home_team: str
    away_team: str
    stake: float
    won: bool
    payout: float
    profit: float


@dataclass
class StrategyResult:
    """Aggregate results of running a strategy."""
    name: str
    total_bets: int = 0
    wins: int = 0
    total_staked: float = 0.0
    total_payout: float = 0.0
    total_profit: float = 0.0
    max_drawdown: float = 0.0
    longest_losing_streak: int = 0
    bets: list = field(default_factory=list)

    @property
    def roi(self) -> float:
        return (self.total_profit / self.total_staked * 100) if self.total_staked > 0 else 0.0

    @property
    def hit_rate(self) -> float:
        return (self.wins / self.total_bets * 100) if self.total_bets > 0 else 0.0

    @property
    def ev_per_bet(self) -> float:
        return self.total_profit / self.total_bets if self.total_bets > 0 else 0.0


def _compute_drawdown_and_streaks(result: StrategyResult) -> None:
    """Compute max drawdown and longest losing streak from bet list."""
    if not result.bets:
        return

    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    losing_streak = 0
    max_streak = 0

    for bet in result.bets:
        cumulative += bet.profit
        peak = max(peak, cumulative)
        dd = peak - cumulative
        max_dd = max(max_dd, dd)

        if not bet.won:
            losing_streak += 1
            max_streak = max(max_streak, losing_streak)
        else:
            losing_streak = 0

    result.max_drawdown = max_dd
    result.longest_losing_streak = max_streak


# ─────────────────────────────────────────────────────────────
# STRATEGIES
# ─────────────────────────────────────────────────────────────

def strategy_flat_every_match(df: pd.DataFrame, stake: float = DEFAULT_STAKE) -> StrategyResult:
    """Bet Away/Home on every single match at flat stake."""
    result = StrategyResult(name="Flat Bet (Every Match)")

    for _, row in df.iterrows():
        won = row["htft_result"] == JACKPOT_OUTCOME
        payout = stake * JACKPOT_ODDS if won else 0.0
        profit = payout - stake

        result.total_bets += 1
        result.total_staked += stake
        result.total_payout += payout
        result.total_profit += profit
        if won:
            result.wins += 1

        result.bets.append(BetResult(
            round_id=row["round_id"], category=row["category"],
            home_team=row["home_team"], away_team=row["away_team"],
            stake=stake, won=won, payout=payout, profit=profit,
        ))

    _compute_drawdown_and_streaks(result)
    return result


def strategy_category_specific(df: pd.DataFrame, stake: float = DEFAULT_STAKE) -> StrategyResult:
    """Bet only in the category with the highest observed jackpot rate.

    Uses first 50% of data to identify the best category, tests on the rest.
    """
    result = StrategyResult(name="Best Category Only")

    # Split data
    midpoint = len(df) // 2
    train = df.iloc[:midpoint]
    test = df.iloc[midpoint:]

    if len(train) < 20 or len(test) < 20:
        result.name += " (insufficient data)"
        return result

    # Find best category in training data
    cat_rates = train.groupby("category")["is_jackpot"].mean()
    best_cat = cat_rates.idxmax()

    # Bet on test data, only in best category
    test_cat = test[test["category"] == best_cat]
    for _, row in test_cat.iterrows():
        won = row["htft_result"] == JACKPOT_OUTCOME
        payout = stake * JACKPOT_ODDS if won else 0.0
        profit = payout - stake

        result.total_bets += 1
        result.total_staked += stake
        result.total_payout += payout
        result.total_profit += profit
        if won:
            result.wins += 1

        result.bets.append(BetResult(
            round_id=row["round_id"], category=row["category"],
            home_team=row["home_team"], away_team=row["away_team"],
            stake=stake, won=won, payout=payout, profit=profit,
        ))

    _compute_drawdown_and_streaks(result)
    result.name += f" ({best_cat})"
    return result


def strategy_after_drought(df: pd.DataFrame, drought_threshold: int = 50,
                           stake: float = DEFAULT_STAKE) -> StrategyResult:
    """Bet after N consecutive non-jackpot matches in a category.

    Theory: if there's a "rebalancing" tendency, jackpots might be more
    likely after a long drought. (They shouldn't be if the RNG is proper.)
    """
    result = StrategyResult(name=f"After Drought (>{drought_threshold} matches)")

    for cat in df["category"].unique():
        cat_df = df[df["category"] == cat].sort_values("timestamp")
        drought = 0

        for _, row in cat_df.iterrows():
            is_jp = row["htft_result"] == JACKPOT_OUTCOME

            if drought >= drought_threshold:
                # Place bet
                won = is_jp
                payout = stake * JACKPOT_ODDS if won else 0.0
                profit = payout - stake

                result.total_bets += 1
                result.total_staked += stake
                result.total_payout += payout
                result.total_profit += profit
                if won:
                    result.wins += 1

                result.bets.append(BetResult(
                    round_id=row["round_id"], category=cat,
                    home_team=row["home_team"], away_team=row["away_team"],
                    stake=stake, won=won, payout=payout, profit=profit,
                ))

            if is_jp:
                drought = 0
            else:
                drought += 1

    _compute_drawdown_and_streaks(result)
    return result


def strategy_cross_category_signal(df: pd.DataFrame, stake: float = DEFAULT_STAKE) -> StrategyResult:
    """When a jackpot occurs in one category, bet on all other categories in the same round.

    Theory: if categories share an RNG seed, jackpots might cluster within rounds.
    """
    result = StrategyResult(name="Cross-Category Signal")

    for round_id in df["round_id"].unique():
        round_df = df[df["round_id"] == round_id]

        # Check if any category has a jackpot
        jp_cats = round_df[round_df["is_jackpot"] == 1]["category"].unique()

        if len(jp_cats) > 0:
            # Bet on matches in other categories in this round
            other = round_df[~round_df["category"].isin(jp_cats)]
            for _, row in other.iterrows():
                won = row["htft_result"] == JACKPOT_OUTCOME
                payout = stake * JACKPOT_ODDS if won else 0.0
                profit = payout - stake

                result.total_bets += 1
                result.total_staked += stake
                result.total_payout += payout
                result.total_profit += profit
                if won:
                    result.wins += 1

                result.bets.append(BetResult(
                    round_id=row["round_id"], category=row["category"],
                    home_team=row["home_team"], away_team=row["away_team"],
                    stake=stake, won=won, payout=payout, profit=profit,
                ))

    _compute_drawdown_and_streaks(result)
    return result


def strategy_martingale(df: pd.DataFrame, base_stake: float = DEFAULT_STAKE,
                        max_stake: float = 5000.0) -> StrategyResult:
    """Martingale on jackpot: double stake after loss, reset on win.

    Capped at max_stake to model realistic bankroll limits.
    """
    result = StrategyResult(name=f"Martingale (base=₦{base_stake}, max=₦{max_stake})")

    current_stake = base_stake
    for _, row in df.iterrows():
        won = row["htft_result"] == JACKPOT_OUTCOME
        payout = current_stake * JACKPOT_ODDS if won else 0.0
        profit = payout - current_stake

        result.total_bets += 1
        result.total_staked += current_stake
        result.total_payout += payout
        result.total_profit += profit
        if won:
            result.wins += 1

        result.bets.append(BetResult(
            round_id=row["round_id"], category=row["category"],
            home_team=row["home_team"], away_team=row["away_team"],
            stake=current_stake, won=won, payout=payout, profit=profit,
        ))

        if won:
            current_stake = base_stake
        else:
            current_stake = min(current_stake * 2, max_stake)

    _compute_drawdown_and_streaks(result)
    return result


def strategy_kelly(df: pd.DataFrame, base_stake: float = DEFAULT_STAKE,
                   bankroll: float = 5000.0) -> StrategyResult:
    """Kelly criterion sizing based on observed jackpot probability.

    Uses first half of data to estimate probability, bets on second half.
    Kelly fraction: f = (bp - q) / b where b=odds-1, p=prob, q=1-p.
    """
    result = StrategyResult(name="Kelly Criterion")

    midpoint = len(df) // 2
    train = df.iloc[:midpoint]
    test = df.iloc[midpoint:]

    if len(train) < 50 or len(test) < 20:
        result.name += " (insufficient data)"
        return result

    # Estimate probability from training data
    p = train["is_jackpot"].mean()
    q = 1 - p
    b = JACKPOT_ODDS - 1  # Net odds

    if p <= 0:
        result.name += " (no jackpots in training)"
        return result

    kelly_fraction = (b * p - q) / b
    if kelly_fraction <= 0:
        result.name += " (negative edge, Kelly says don't bet)"
        return result

    current_bankroll = bankroll
    for _, row in test.iterrows():
        if current_bankroll < 1:
            break

        stake = max(1, current_bankroll * kelly_fraction)
        won = row["htft_result"] == JACKPOT_OUTCOME
        payout = stake * JACKPOT_ODDS if won else 0.0
        profit = payout - stake
        current_bankroll += profit

        result.total_bets += 1
        result.total_staked += stake
        result.total_payout += payout
        result.total_profit += profit
        if won:
            result.wins += 1

        result.bets.append(BetResult(
            round_id=row["round_id"], category=row["category"],
            home_team=row["home_team"], away_team=row["away_team"],
            stake=stake, won=won, payout=payout, profit=profit,
        ))

    _compute_drawdown_and_streaks(result)
    result.name += f" (p={p:.4f}, f={kelly_fraction:.4f})"
    return result


def strategy_team_specific(df: pd.DataFrame, stake: float = DEFAULT_STAKE) -> StrategyResult:
    """Bet only on team pairings that have produced jackpots before.

    Uses first half to find jackpot-producing teams, bets on second half.
    """
    result = StrategyResult(name="Team-Specific")

    midpoint = len(df) // 2
    train = df.iloc[:midpoint]
    test = df.iloc[midpoint:]

    if len(train) < 50 or len(test) < 20:
        result.name += " (insufficient data)"
        return result

    # Find team pairings that produced jackpots
    jp_train = train[train["is_jackpot"] == 1]
    jp_teams = set(zip(jp_train["home_team"], jp_train["away_team"], jp_train["category"]))

    if not jp_teams:
        result.name += " (no jackpots in training)"
        return result

    for _, row in test.iterrows():
        key = (row["home_team"], row["away_team"], row["category"])
        if key in jp_teams:
            won = row["htft_result"] == JACKPOT_OUTCOME
            payout = stake * JACKPOT_ODDS if won else 0.0
            profit = payout - stake

            result.total_bets += 1
            result.total_staked += stake
            result.total_payout += payout
            result.total_profit += profit
            if won:
                result.wins += 1

            result.bets.append(BetResult(
                round_id=row["round_id"], category=row["category"],
                home_team=row["home_team"], away_team=row["away_team"],
                stake=stake, won=won, payout=payout, profit=profit,
            ))

    _compute_drawdown_and_streaks(result)
    return result


# ─────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────

ALL_STRATEGIES = {
    "flat": strategy_flat_every_match,
    "category": strategy_category_specific,
    "drought": strategy_after_drought,
    "cross": strategy_cross_category_signal,
    "martingale": strategy_martingale,
    "kelly": strategy_kelly,
    "team": strategy_team_specific,
}


def run_strategies(strategy_name: str = None) -> None:
    """Run one or all strategies against collected data."""
    conn = get_connection()
    init_db(conn)

    matches = get_all_matches(conn)
    conn.close()

    if not matches:
        print("❌ No data in database. Run the bot first.")
        return

    df = pd.DataFrame(matches)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    print("\n" + "=" * 70)
    print("STRATEGY BACKTESTER — AWAY/HOME JACKPOT (100.00 ODDS)")
    print("=" * 70)
    print(f"\nData: {len(df)} matches, {df['round_id'].nunique()} rounds")
    print(f"Jackpots in data: {df['is_jackpot'].sum()} ({df['is_jackpot'].mean()*100:.2f}%)")

    strategies_to_run = (
        {strategy_name: ALL_STRATEGIES[strategy_name]}
        if strategy_name and strategy_name in ALL_STRATEGIES
        else ALL_STRATEGIES
    )

    results = []
    for name, func in strategies_to_run.items():
        result = func(df)
        results.append(result)

    # Print results table
    print(f"\n{'─' * 90}")
    print(f"{'Strategy':<40} {'Bets':>6} {'Wins':>5} {'Hit%':>6} "
          f"{'Staked':>10} {'P&L':>10} {'ROI':>7} {'MaxDD':>10} {'MaxLoss':>7}")
    print(f"{'─' * 90}")

    for r in results:
        print(f"{r.name:<40} {r.total_bets:>6} {r.wins:>5} {r.hit_rate:>5.1f}% "
              f"₦{r.total_staked:>9,.0f} ₦{r.total_profit:>9,.0f} {r.roi:>6.1f}% "
              f"₦{r.max_drawdown:>9,.0f} {r.longest_losing_streak:>6}")

    print(f"{'─' * 90}")

    # Highlight any profitable strategies
    profitable = [r for r in results if r.total_profit > 0]
    if profitable:
        print(f"\n🎯 {len(profitable)} strategy(ies) show positive P&L:")
        for r in profitable:
            print(f"   → {r.name}: +₦{r.total_profit:,.0f} ({r.roi:.1f}% ROI)")
        print("   ⚠  Small sample warning: may not persist with more data.")
    else:
        print("\n  No strategy produced positive returns. House edge confirmed.")


def main():
    parser = argparse.ArgumentParser(
        description="Backtest Away/Home jackpot betting strategies"
    )
    parser.add_argument("--strategy", type=str, default=None,
                        choices=list(ALL_STRATEGIES.keys()),
                        help="Run a specific strategy only")
    args = parser.parse_args()

    run_strategies(strategy_name=args.strategy)


if __name__ == "__main__":
    main()
