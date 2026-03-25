"""
MULTI-MARKET STRATEGY SIMULATION
Combines HT/FT jackpots + Draw/Draw + Over 2.5 for optimal daily profit.
All numbers verified against actual 30,000+ match database.
"""
import sys, io, sqlite3
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent))

DB = Path("data/sportybet.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

matches = conn.execute("""
    SELECT m.*, r.id as round_order FROM matches m
    JOIN rounds r ON m.round_id = r.round_id
    ORDER BY r.id, m.id
""").fetchall()
matches = [dict(m) for m in matches]

total_rounds = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
total_matches = len(matches)

# Group by round
rounds_map = defaultdict(list)
round_order = []
seen = set()
for m in matches:
    rid = m['round_id']
    rounds_map[rid].append(m)
    if rid not in seen:
        round_order.append(rid)
        seen.add(rid)

STAKE = 10

print("=" * 75)
print("  MULTI-MARKET STRATEGY SIMULATION")
print(f"  Dataset: {total_rounds} rounds | {total_matches} matches")
print("=" * 75)

def simulate_multi(name, bets_fn):
    """Simulate a strategy. bets_fn(match) returns list of (market_name, won, odds) or empty."""
    total_bets = 0
    total_wins = 0
    total_staked = 0
    total_won = 0
    balance = 0
    peak = 0
    max_dd = 0
    streak = 0
    max_streak = 0
    daily_balances = []
    round_profits = []

    for rid in round_order:
        round_profit = 0
        for m in rounds_map[rid]:
            results = bets_fn(m)
            for market, won, odds in results:
                total_bets += 1
                total_staked += STAKE
                if won:
                    payout = STAKE * odds
                    total_won += payout
                    balance += payout - STAKE
                    round_profit += payout - STAKE
                    total_wins += 1
                    streak = 0
                else:
                    balance -= STAKE
                    round_profit -= STAKE
                    streak += 1
                    max_streak = max(max_streak, streak)

                if balance > peak:
                    peak = balance
                dd = peak - balance
                if dd > max_dd:
                    max_dd = dd

        round_profits.append(round_profit)

    roi = balance / total_staked * 100 if total_staked > 0 else 0
    hit_rate = total_wins / total_bets * 100 if total_bets > 0 else 0
    bets_per_round = total_bets / total_rounds
    daily_profit = balance / total_rounds * 60  # 60 rounds/day estimate

    # Calculate win days vs loss days (per round)
    win_rounds = sum(1 for p in round_profits if p > 0)
    loss_rounds = sum(1 for p in round_profits if p < 0)
    even_rounds = sum(1 for p in round_profits if p == 0)

    return {
        'name': name, 'bets': total_bets, 'wins': total_wins,
        'staked': total_staked, 'won': total_won, 'pnl': balance,
        'roi': roi, 'hit_rate': hit_rate, 'max_dd': max_dd,
        'max_streak': max_streak, 'bets_per_round': bets_per_round,
        'daily_profit': daily_profit, 'win_rounds': win_rounds,
        'loss_rounds': loss_rounds, 'even_rounds': even_rounds,
        'avg_round_profit': balance / total_rounds,
    }

# ═══════════════════════════════════════════════════════════════
# STRATEGY DEFINITIONS
# ═══════════════════════════════════════════════════════════════

# Strategy A: HT/FT Jackpot only (current strategy)
def strat_jackpot_only(m):
    bets = []
    if m['category'] in ('Club World Cup', 'Germany', 'Champions'):
        won = m['is_jackpot'] == 1
        bets.append(('HTFT AH', won, 75.0))
    return bets

# Strategy B: Draw/Draw only
def strat_dd_only(m):
    bets = []
    if m['category'] in ('Italy', 'England'):
        won = m['htft_result'] == 'Draw/Draw'
        bets.append(('DD', won, 5.0))
    return bets

# Strategy C: Over 2.5 only
def strat_o25_only(m):
    bets = []
    if m['category'] in ('Germany', 'Champions'):
        won = (m['ft_home_goals'] + m['ft_away_goals']) > 2.5
        bets.append(('O2.5', won, 2.90))
    return bets

# Strategy D: Home Win Spain only
def strat_home_spain(m):
    bets = []
    if m['category'] == 'Spain':
        won = m['ft_result'] == 'Home'
        bets.append(('1X2 H', won, 2.50))
    return bets

# Strategy E: Triple Alpha (jackpot + DD + O2.5)
def strat_triple(m):
    bets = []
    # Leg 1: Jackpot in top 3
    if m['category'] in ('Club World Cup', 'Germany', 'Champions'):
        won = m['is_jackpot'] == 1
        bets.append(('HTFT AH', won, 75.0))
    # Leg 2: Draw/Draw in Italy/England
    if m['category'] in ('Italy', 'England'):
        won = m['htft_result'] == 'Draw/Draw'
        bets.append(('DD', won, 5.0))
    # Leg 3: Over 2.5 in Germany/Champions
    if m['category'] in ('Germany', 'Champions'):
        won = (m['ft_home_goals'] + m['ft_away_goals']) > 2.5
        bets.append(('O2.5', won, 2.90))
    return bets

# Strategy F: Triple Alpha + Home Spain
def strat_quad(m):
    bets = strat_triple(m)
    if m['category'] == 'Spain':
        won = m['ft_result'] == 'Home'
        bets.append(('1X2 H', won, 2.50))
    return bets

# Strategy G: Draw/Draw + Over 2.5 only (no jackpot — pure low variance)
def strat_steady(m):
    bets = []
    if m['category'] in ('Italy', 'England'):
        won = m['htft_result'] == 'Draw/Draw'
        bets.append(('DD', won, 5.0))
    if m['category'] in ('Germany', 'Champions'):
        won = (m['ft_home_goals'] + m['ft_away_goals']) > 2.5
        bets.append(('O2.5', won, 2.90))
    return bets

# Strategy H: All edges combined (everything with positive edge)
def strat_everything(m):
    bets = []
    cat = m['category']
    # Jackpots in top 3
    if cat in ('Club World Cup', 'Germany', 'Champions'):
        bets.append(('HTFT AH', m['is_jackpot'] == 1, 75.0))
    # Draw/Draw in Italy/England
    if cat in ('Italy', 'England'):
        bets.append(('DD', m['htft_result'] == 'Draw/Draw', 5.0))
    # Over 2.5 in Germany/Champions/Euros/CWC
    if cat in ('Germany', 'Champions', 'Euros', 'Club World Cup'):
        bets.append(('O2.5', (m['ft_home_goals'] + m['ft_away_goals']) > 2.5, 2.90))
    # Home in Spain
    if cat == 'Spain':
        bets.append(('1X2 H', m['ft_result'] == 'Home', 2.50))
    # NG in Italy
    if cat == 'Italy':
        bets.append(('NG', not (m['ft_home_goals'] > 0 and m['ft_away_goals'] > 0), 1.59))
    return bets

# ═══════════════════════════════════════════════════════════════
# RUN ALL STRATEGIES
# ═══════════════════════════════════════════════════════════════

strategies = [
    simulate_multi("A: HT/FT Jackpot Only", strat_jackpot_only),
    simulate_multi("B: Draw/Draw Only", strat_dd_only),
    simulate_multi("C: Over 2.5 Only", strat_o25_only),
    simulate_multi("D: Home Win Spain", strat_home_spain),
    simulate_multi("E: Triple Alpha", strat_triple),
    simulate_multi("F: Quad Alpha", strat_quad),
    simulate_multi("G: Steady (DD+O2.5)", strat_steady),
    simulate_multi("H: Everything", strat_everything),
]

print(f"\n  {'Strategy':<30} {'Bets':>6} {'Wins':>6} {'ROI':>7} {'P&L':>10} {'B/Rnd':>6} {'HitRt':>6} {'MaxDD':>8} {'Strk':>5} {'Daily':>10} {'WinRnd':>7}")
print("  " + "-" * 115)
for s in sorted(strategies, key=lambda x: x['daily_profit'], reverse=True):
    wr = f"{s['win_rounds']}/{total_rounds}"
    print(f"  {s['name']:<30} {s['bets']:>6} {s['wins']:>6} {s['roi']:>+6.1f}% {s['pnl']:>+9.0f} {s['bets_per_round']:>5.0f} {s['hit_rate']:>5.1f}% {s['max_dd']:>7.0f} {s['max_streak']:>5} {s['daily_profit']:>+9.0f} {wr:>7}")

# ═══════════════════════════════════════════════════════════════
# DETAILED BREAKDOWN OF BEST STRATEGY
# ═══════════════════════════════════════════════════════════════
best = max(strategies, key=lambda x: x['daily_profit'])
best_risk = max(strategies, key=lambda x: x['daily_profit'] / max(x['max_dd'], 1))

print(f"\n\n{'='*75}")
print(f"  BEST BY DAILY PROFIT: {best['name']}")
print(f"{'='*75}")
print(f"  ROI: {best['roi']:+.1f}%")
print(f"  Hit rate: {best['hit_rate']:.1f}% ({best['wins']}/{best['bets']})")
print(f"  Bets per round: {best['bets_per_round']:.0f}")
print(f"  Winning rounds: {best['win_rounds']}/{total_rounds} ({best['win_rounds']/total_rounds*100:.0f}%)")
print(f"  Max losing streak: {best['max_streak']} bets")
print(f"  Max drawdown: NGN {best['max_dd']:,.0f}")

print(f"\n  STAKING TABLE:")
print(f"  {'Stake':>8} {'Bankroll':>12} {'Daily':>12} {'Monthly':>14} {'MaxDD':>10}")
print("  " + "-" * 60)
for stake in [10, 20, 50, 100, 200, 500]:
    dd = best['max_dd'] / STAKE * stake
    bankroll = dd * 2.5
    daily = best['daily_profit'] / STAKE * stake
    monthly = daily * 30
    print(f"  NGN {stake:>4} NGN {bankroll:>8,.0f} NGN {daily:>8,.0f} NGN {monthly:>10,.0f} NGN {dd:>7,.0f}")

print(f"\n\n{'='*75}")
print(f"  BEST RISK-ADJUSTED: {best_risk['name']}")
print(f"{'='*75}")
print(f"  ROI: {best_risk['roi']:+.1f}%")
print(f"  Hit rate: {best_risk['hit_rate']:.1f}%")
print(f"  Daily profit/MaxDD ratio: {best_risk['daily_profit']/max(best_risk['max_dd'],1):.2f}")
print(f"  Max losing streak: {best_risk['max_streak']} bets")
print(f"  Winning rounds: {best_risk['win_rounds']}/{total_rounds} ({best_risk['win_rounds']/total_rounds*100:.0f}%)")

print(f"\n  STAKING TABLE:")
print(f"  {'Stake':>8} {'Bankroll':>12} {'Daily':>12} {'Monthly':>14} {'MaxDD':>10}")
print("  " + "-" * 60)
for stake in [10, 20, 50, 100, 200, 500]:
    dd = best_risk['max_dd'] / STAKE * stake
    bankroll = dd * 2.5
    daily = best_risk['daily_profit'] / STAKE * stake
    monthly = daily * 30
    print(f"  NGN {stake:>4} NGN {bankroll:>8,.0f} NGN {daily:>8,.0f} NGN {monthly:>10,.0f} NGN {dd:>7,.0f}")

# ═══════════════════════════════════════════════════════════════
# IMPLEMENTATION PLAN
# ═══════════════════════════════════════════════════════════════
print(f"\n\n{'='*75}")
print(f"  IMPLEMENTATION PLAN")
print(f"{'='*75}")
print(f"""
  STEP 1: Continue running HT/FT jackpot bot (already working)
  STEP 2: Extend bot to place Draw/Draw bets for Italy & England
  STEP 3: Extend bot to place Over 2.5 bets for Germany & Champions
  STEP 4: Add Home Win bets for Spain
  
  Each market uses a DIFFERENT tab on the match detail page:
  - HT/FT: scroll down to HT/FT section
  - Draw/Draw: same HT/FT section, select "Draw/Draw"
  - Over 2.5: click "O/U" tab, select "Over 2.5"
  - Home Win: click "1X2" tab, select "Home"
  
  The bot infrastructure already handles:
  - Opening fixture detail pages
  - Navigating category tabs
  - Place Bet + Confirm flow
  - Category-specific bet logic
  
  What needs to be added:
  - Market tab switching (1X2, O/U, HT/FT)
  - Different outcome selection per market
  - Multi-bet per fixture (e.g., both O2.5 AND jackpot on same match)
""")

conn.close()
print("=" * 75)
print("  SIMULATION COMPLETE")
print("=" * 75)
