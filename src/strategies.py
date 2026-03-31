"""
Jackpot Strategy Engine — Adaptive Value Betting on Away/Home HT/FT

Phase 3 strategy based on 9,751 matches deep dive.

Key findings:
- Away/Home overall rate: 1.57% (fair odds = 63.7x)
- Odds above 65x are -EV traps (house edge too large)
- Only 3 categories have AH rate >= 1.8%:
    Germany 2.22% (fair=45x), Champions 2.00% (fair=50x),
    Club World Cup 1.88% (fair=53x)
- All other categories (England 1.47%, Spain 1.48%, Euros 1.44%,
    African Cup 1.14%, Italy 0.92%) are -EV at offered odds
- Sweet spot: 50-65x odds in Germany/Champions/CWC = genuine +EV

The adaptive system:
1. Tracks JP rates per category x odds-range from ALL data
2. Recomputes every LEARN_INTERVAL rounds
3. Only enables category x range combos with EV > MIN_EV_THRESHOLD
4. Hard caps odds at MAX_ODDS (65x) — nothing above this
5. Only evaluates 3 proven categories
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ──────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────

LEARN_INTERVAL = 10          # Re-analyze every N rounds
MIN_MATCHES_CATEGORY = 200   # Min matches in a category before trusting rates
MIN_ODDS_RECORDS = 50        # Min AH odds records for a category x range
MIN_EV_THRESHOLD = 0.05      # Only bet when EV > 5%
MAX_BETS_PER_ROUND = 30      # SportyBet limit
DEFAULT_STAKE = 10.0
MAX_ODDS = 65.0              # Hard cap — odds above this are -EV traps

# Odds ranges for jackpot analysis (capped at MAX_ODDS)
ODDS_RANGES = [
    ('50-57', 50, 57),
    ('57-65', 57, 65),
]

# Only categories with AH rate >= 1.8% (proven from 9,751 matches)
# Germany 2.22%, Champions 2.00%, Club World Cup 1.88%
ALL_CATEGORIES = [
    'Germany', 'Champions', 'Club World Cup',
]


# ──────────────────────────────────────────────────────────
#  ACTIVE MARKET TRACKING
# ──────────────────────────────────────────────────────────

@dataclass
class ActiveMarket:
    """A category x odds-range combo that is currently enabled for betting."""
    category: str
    odds_lo: float
    odds_hi: float
    range_label: str
    jp_rate: float        # actual jackpot rate from data
    implied_rate: float   # bookmaker implied rate (1/avg_odds)
    avg_odds: float       # average AH odds in this range
    ev: float             # expected value = jp_rate * avg_odds - 1
    n_matches: int        # matches used to compute jp_rate
    n_odds: int           # odds records in this range
    enabled: bool = True

    @property
    def ev_pct(self) -> float:
        return self.ev * 100


@dataclass
class SteadyState:
    """Runtime performance tracking."""
    total_bets: int = 0
    total_wins: int = 0
    total_staked: float = 0.0
    total_profit: float = 0.0
    peak_profit: float = 0.0
    max_drawdown: float = 0.0
    current_streak: int = 0
    max_streak: int = 0
    rounds_played: int = 0
    rounds_won: int = 0
    round_bets_count: int = 0
    round_profit: float = 0.0
    market_stats: dict = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        return self.total_wins / self.total_bets if self.total_bets > 0 else 0.0

    @property
    def roi(self) -> float:
        return self.total_profit / self.total_staked if self.total_staked > 0 else 0.0

    def start_round(self):
        self.round_bets_count = 0
        self.round_profit = 0.0

    def record_bet(self, market_key: str, stake: float, won: bool, payout: float):
        profit = payout - stake
        self.total_bets += 1
        self.total_staked += stake
        self.total_profit += profit
        self.round_bets_count += 1
        self.round_profit += profit
        if won:
            self.total_wins += 1
            self.current_streak = 0
        else:
            self.current_streak += 1
            self.max_streak = max(self.max_streak, self.current_streak)
        self.peak_profit = max(self.peak_profit, self.total_profit)
        dd = self.peak_profit - self.total_profit
        self.max_drawdown = max(self.max_drawdown, dd)
        if market_key not in self.market_stats:
            self.market_stats[market_key] = {
                'bets': 0, 'wins': 0, 'staked': 0.0, 'profit': 0.0,
            }
        ms = self.market_stats[market_key]
        ms['bets'] += 1
        ms['wins'] += int(won)
        ms['staked'] += stake
        ms['profit'] += profit

    def end_round(self):
        self.rounds_played += 1
        if self.round_profit > 0:
            self.rounds_won += 1


# ──────────────────────────────────────────────────────────
#  ADAPTIVE LEARNING
# ──────────────────────────────────────────────────────────

def learn_from_data(conn: sqlite3.Connection) -> dict:
    """Analyze ALL data and determine which category x odds-range combos are +EV.

    Returns a report dict with active_markets list.
    """
    total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    total_rounds = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
    total_jackpots = conn.execute("SELECT COUNT(*) FROM matches WHERE is_jackpot=1").fetchone()[0]

    if total_matches < 100:
        return {'status': 'insufficient_data', 'total_matches': total_matches}

    # Get JP rate per category
    cat_stats = {}
    for row in conn.execute('''
        SELECT category, COUNT(*) as n,
               SUM(CASE WHEN is_jackpot=1 THEN 1 ELSE 0 END) as jp
        FROM matches GROUP BY category
    ''').fetchall():
        cat_stats[row['category']] = {
            'n': row['n'], 'jp': row['jp'],
            'rate': row['jp'] / row['n'] if row['n'] > 0 else 0,
        }

    # Get AH odds distribution per category x range
    ah_odds = conn.execute('''
        SELECT category, odds FROM market_odds
        WHERE market='HT/FT' AND selection IN ('Away/ Home', '2/1', 'Away/Home')
        AND odds > 0
    ''').fetchall()

    # Build category x range analysis
    active_markets = []
    all_analysis = []

    for cat in ALL_CATEGORIES:
        cs = cat_stats.get(cat)
        if not cs or cs['n'] < MIN_MATCHES_CATEGORY:
            continue

        cat_jp_rate = cs['rate']
        cat_ah = [r for r in ah_odds if r['category'] == cat]

        for label, lo, hi in ODDS_RANGES:
            range_odds = [r['odds'] for r in cat_ah if lo <= r['odds'] < hi]
            if len(range_odds) < MIN_ODDS_RECORDS:
                continue

            avg_odds = sum(range_odds) / len(range_odds)
            implied = 1 / avg_odds

            # Use category-wide JP rate (most reliable with our sample sizes)
            ev = cat_jp_rate * avg_odds - 1

            market = ActiveMarket(
                category=cat, odds_lo=lo, odds_hi=hi,
                range_label=label, jp_rate=cat_jp_rate,
                implied_rate=implied, avg_odds=avg_odds,
                ev=ev, n_matches=cs['n'], n_odds=len(range_odds),
                enabled=(ev > MIN_EV_THRESHOLD),
            )
            all_analysis.append(market)
            if market.enabled:
                active_markets.append(market)

    # Sort active by EV
    active_markets.sort(key=lambda m: m.ev, reverse=True)

    return {
        'status': 'updated',
        'total_matches': total_matches,
        'total_rounds': total_rounds,
        'total_jackpots': total_jackpots,
        'overall_jp_rate': total_jackpots / total_matches if total_matches > 0 else 0,
        'category_stats': cat_stats,
        'all_analysis': all_analysis,
        'active_markets': active_markets,
    }


def should_bet_jackpot(category: str, ah_odds: float, active_markets: list) -> Optional[ActiveMarket]:
    """Check if we should bet Away/Home on this fixture.

    Hard filters:
    - Category must be in ALL_CATEGORIES (Germany, Champions, Club World Cup)
    - Odds must be in [50, MAX_ODDS) range
    - Must match an enabled ActiveMarket with EV > threshold

    Returns the matching ActiveMarket if +EV, or None.
    """
    if category not in ALL_CATEGORIES:
        return None
    if ah_odds >= MAX_ODDS or ah_odds < 50:
        return None
    for m in active_markets:
        if m.category == category and m.odds_lo <= ah_odds < m.odds_hi and m.enabled:
            return m
    return None


def print_strategy_report(report: dict) -> None:
    """Print the adaptive strategy report."""
    if report.get('status') != 'updated':
        print(f"  Not enough data ({report.get('total_matches', 0)} matches)")
        return

    print(f"\n  {'=' * 65}")
    print(f"  JACKPOT STRATEGY — ADAPTIVE REPORT")
    print(f"  Data: {report['total_matches']} matches / {report['total_rounds']} rounds")
    print(f"  Overall JP rate: {report['overall_jp_rate']*100:.2f}%")
    print(f"  {'=' * 65}")

    print(f"\n  Category JP rates:")
    for cat, cs in sorted(report['category_stats'].items()):
        marker = " ✓" if cs['rate'] > 0.015 else ""
        print(f"    {cat:<18} {cs['rate']*100:.2f}% ({cs['jp']}/{cs['n']}){marker}")

    active = report['active_markets']
    print(f"\n  Active markets ({len(active)}):")
    print(f"  {'Category':<18} {'Range':<10} {'AvgOdds':>8} {'JP Rate':>8} {'Implied':>8} {'EV':>8}")
    for m in active:
        print(f"  {m.category:<18} {m.range_label:<10} {m.avg_odds:>7.1f} "
              f"{m.jp_rate*100:>7.2f}% {m.implied_rate*100:>7.2f}% {m.ev_pct:>+7.1f}%")

    print(f"  {'=' * 65}")


def print_performance_report(state: SteadyState) -> None:
    """Print runtime performance."""
    print(f"\n  {'=' * 55}")
    print(f"  JACKPOT PERFORMANCE")
    print(f"  {'=' * 55}")
    print(f"  Bets: {state.total_bets}  Wins: {state.total_wins}  "
          f"WinRate: {state.win_rate*100:.1f}%")
    print(f"  Staked: NGN {state.total_staked:.0f}  "
          f"Profit: NGN {state.total_profit:+.0f}  "
          f"ROI: {state.roi*100:+.1f}%")
    print(f"  Max DD: NGN {state.max_drawdown:.0f}  "
          f"Max Streak: {state.max_streak}")
    if state.rounds_played > 0:
        pct = state.rounds_won / state.rounds_played * 100
        print(f"  Rounds: {state.rounds_played}  "
              f"Winning: {state.rounds_won}/{state.rounds_played} ({pct:.0f}%)")
    if state.market_stats:
        print(f"\n  Per-market:")
        for key in sorted(state.market_stats.keys()):
            ms = state.market_stats[key]
            wr = ms['wins'] / ms['bets'] * 100 if ms['bets'] > 0 else 0
            roi = ms['profit'] / ms['staked'] * 100 if ms['staked'] > 0 else 0
            print(f"    {key:<30} {ms['bets']:>4}b {wr:>5.1f}%wr NGN {ms['profit']:>+8.0f} ROI {roi:>+5.1f}%")
    print(f"  {'=' * 55}")


# ──────────────────────────────────────────────────────────
#  BET LOGGING AND SETTLEMENT
# ──────────────────────────────────────────────────────────

def log_bet(conn, round_id, category, home_team, away_team,
            market, selection, odds, stake) -> int:
    """Log a pending bet. Returns row id."""
    cursor = conn.execute(
        """INSERT INTO bets
           (round_id, timestamp, category, home_team, away_team,
            market, selection, odds, stake)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (round_id, datetime.now(timezone.utc).isoformat(),
         category, home_team, away_team, market, selection, odds, stake),
    )
    conn.commit()
    return cursor.lastrowid


def settle_bets(conn, round_id, matches) -> dict:
    """Settle unsettled bets against actual results."""
    from src.db import derive_htft

    bets = conn.execute(
        "SELECT * FROM bets WHERE round_id = ? AND won IS NULL",
        (round_id,)
    ).fetchall()

    if not bets:
        return {'settled': 0, 'wins': 0, 'losses': 0, 'profit': 0.0}

    match_lookup = {}
    for m in matches:
        key = (m['category'], m['home_team'], m['away_team'])
        match_lookup[key] = m

    settled = wins = 0
    total_profit = 0.0

    for bet in bets:
        key = (bet['category'], bet['home_team'], bet['away_team'])
        match = match_lookup.get(key)
        if not match:
            continue

        htft = derive_htft(
            match['ht_home_goals'], match['ht_away_goals'],
            match['ft_home_goals'], match['ft_away_goals'],
        )

        won = False
        if bet['market'] == 'HT/FT' and bet['selection'] in ('Away/Home', 'Away/ Home'):
            won = htft == 'Away/Home'
        elif bet['market'] == 'DC' and bet['selection'] == '12':
            won = match['ft_result'] in ('Home', 'Away')

        payout = bet['odds'] * bet['stake'] if won else 0.0
        profit = payout - bet['stake']

        conn.execute(
            "UPDATE bets SET won=?, payout=?, profit=?, htft_result=? WHERE id=?",
            (1 if won else 0, payout, profit, htft, bet['id']),
        )
        settled += 1
        if won:
            wins += 1
        total_profit += profit

    conn.commit()
    return {'settled': settled, 'wins': wins, 'losses': settled - wins, 'profit': total_profit}


def get_session_stats(conn) -> dict:
    """Get aggregate bet stats."""
    row = conn.execute("""
        SELECT COUNT(*) as total,
               COALESCE(SUM(CASE WHEN won=1 THEN 1 ELSE 0 END), 0) as wins,
               COALESCE(SUM(stake), 0) as staked,
               COALESCE(SUM(profit), 0) as profit
        FROM bets WHERE won IS NOT NULL
    """).fetchone()
    total = row[0]
    return {
        'total_bets': total, 'wins': row[1],
        'total_staked': row[2], 'total_profit': row[3],
        'roi': row[3] / row[2] * 100 if row[2] > 0 else 0,
        'win_rate': row[1] / total * 100 if total > 0 else 0,
    }
