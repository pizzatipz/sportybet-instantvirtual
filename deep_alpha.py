"""
DEEP ALPHA SEARCH — Beyond HT/FT
Looking at ALL markets derivable from our data:
1X2, O/U, GG/NG, Correct Score, Double Chance, HT Result, FT Result,
Total Goals, Home/Away Goals, Handicap, Halftime O/U, Second Half patterns, etc.

We have HT and FT scores for 29,000+ matches — we can reconstruct
EVERY market's outcome from this data.
"""
import sys, io, sqlite3, math
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent))

DB = Path("data/sportybet.db")
conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row

total_rounds = conn.execute("SELECT COUNT(*) FROM rounds").fetchone()[0]
total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

print("=" * 75)
print("  DEEP ALPHA SEARCH — ALL MARKETS")
print(f"  Dataset: {total_rounds} rounds | {total_matches} matches")
print("=" * 75)

# Load all matches
matches = conn.execute("""
    SELECT m.*, r.id as round_order FROM matches m
    JOIN rounds r ON m.round_id = r.round_id
    ORDER BY r.id, m.id
""").fetchall()
matches = [dict(m) for m in matches]

# ═══════════════════════════════════════════════════════════════
# MARKET 1: 1X2 (Full-Time Result)
# Typical odds: Home ~2.5, Draw ~3.0, Away ~3.0
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 1: 1X2 (Full-Time Result)")
print("=" * 75)

ft_results = Counter(m['ft_result'] for m in matches)
total = len(matches)

print(f"\n  {'Result':<10} {'Count':>7} {'Rate':>7} {'Implied Odds':>13} {'Typical Odds':>13} {'Edge':>7}")
print("  " + "-" * 60)

# Typical 1X2 odds for virtual soccer (observed from scraping)
typical_odds = {'Home': 2.5, 'Draw': 3.0, 'Away': 3.0}
for result in ['Home', 'Draw', 'Away']:
    count = ft_results[result]
    rate = count / total
    implied = 1 / rate if rate > 0 else 999
    typical = typical_odds[result]
    edge = (rate * typical - 1) * 100
    print(f"  {result:<10} {count:>7} {rate*100:>6.2f}% {implied:>12.2f} {typical:>12.2f} {edge:>+6.1f}%")

# By category
print(f"\n  1X2 by category:")
cats = sorted(set(m['category'] for m in matches))
for cat in cats:
    cat_matches = [m for m in matches if m['category'] == cat]
    n = len(cat_matches)
    home = sum(1 for m in cat_matches if m['ft_result'] == 'Home') / n * 100
    draw = sum(1 for m in cat_matches if m['ft_result'] == 'Draw') / n * 100
    away = sum(1 for m in cat_matches if m['ft_result'] == 'Away') / n * 100
    print(f"    {cat:<18} H:{home:>5.1f}%  D:{draw:>5.1f}%  A:{away:>5.1f}%")

# ═══════════════════════════════════════════════════════════════
# MARKET 2: Over/Under Goals
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 2: Over/Under Total Goals")
print("=" * 75)

total_goals = [m['ft_home_goals'] + m['ft_away_goals'] for m in matches]
avg_goals = sum(total_goals) / len(total_goals)
print(f"\n  Average total goals: {avg_goals:.3f}")

# O/U lines
lines = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]
print(f"\n  {'Line':<8} {'Over%':>7} {'Under%':>7} {'Typical Over':>13} {'Over Edge':>10} {'Typical Under':>14} {'Under Edge':>11}")
print("  " + "-" * 75)

# Typical O/U odds (from virtual soccer)
typical_ou = {
    0.5: (1.13, 6.0), 1.5: (1.60, 2.30), 2.5: (2.90, 1.42),
    3.5: (6.0, 1.13), 4.5: (12.0, 1.03), 5.5: (25.0, 1.01)
}
for line in lines:
    over = sum(1 for g in total_goals if g > line)
    under = sum(1 for g in total_goals if g < line)
    # Equal to line = push (not counted)
    over_pct = over / total * 100
    under_pct = under / total * 100
    
    t_over, t_under = typical_ou.get(line, (2.0, 2.0))
    over_edge = (over/total * t_over - 1) * 100
    under_edge = (under/total * t_under - 1) * 100
    
    print(f"  {line:<8} {over_pct:>6.1f}% {under_pct:>6.1f}% {t_over:>12.2f} {over_edge:>+9.1f}% {t_under:>13.2f} {under_edge:>+10.1f}%")

# O/U by category
print(f"\n  Over 2.5 goals by category:")
for cat in cats:
    cat_goals = [m['ft_home_goals'] + m['ft_away_goals'] for m in matches if m['category'] == cat]
    over25 = sum(1 for g in cat_goals if g > 2.5) / len(cat_goals) * 100
    avg = sum(cat_goals) / len(cat_goals)
    print(f"    {cat:<18} Over 2.5: {over25:>5.1f}%  Avg goals: {avg:.2f}")

# ═══════════════════════════════════════════════════════════════
# MARKET 3: GG/NG (Both Teams to Score)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 3: GG/NG (Both Teams To Score)")
print("=" * 75)

gg = sum(1 for m in matches if m['ft_home_goals'] > 0 and m['ft_away_goals'] > 0)
ng = total - gg
gg_pct = gg / total * 100
ng_pct = ng / total * 100

# Typical GG/NG odds
gg_odds = 2.38
ng_odds = 1.59
gg_edge = (gg/total * gg_odds - 1) * 100
ng_edge = (ng/total * ng_odds - 1) * 100

print(f"\n  GG (Yes): {gg_pct:.2f}% | Typical odds: {gg_odds} | Edge: {gg_edge:+.1f}%")
print(f"  NG (No):  {ng_pct:.2f}% | Typical odds: {ng_odds} | Edge: {ng_edge:+.1f}%")

print(f"\n  GG/NG by category:")
for cat in cats:
    cm = [m for m in matches if m['category'] == cat]
    gg_cat = sum(1 for m in cm if m['ft_home_goals'] > 0 and m['ft_away_goals'] > 0) / len(cm) * 100
    print(f"    {cat:<18} GG: {gg_cat:>5.1f}%")

# ═══════════════════════════════════════════════════════════════
# MARKET 4: Correct Score
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 4: Correct Score Distribution")
print("=" * 75)

scores = Counter(f"{m['ft_home_goals']}-{m['ft_away_goals']}" for m in matches)
print(f"\n  {'Score':<8} {'Count':>6} {'Rate':>7} {'Implied Odds':>13}")
print("  " + "-" * 38)
for score, count in scores.most_common(15):
    rate = count / total
    implied = 1 / rate
    print(f"  {score:<8} {count:>6} {rate*100:>6.2f}% {implied:>12.1f}")

# ═══════════════════════════════════════════════════════════════
# MARKET 5: Half-Time Result (1X2 at HT)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 5: Half-Time 1X2")
print("=" * 75)

ht_results = Counter(m['ht_result'] for m in matches)
print(f"\n  {'HT Result':<10} {'Count':>7} {'Rate':>7} {'Implied Odds':>13}")
print("  " + "-" * 40)
for result in ['Home', 'Draw', 'Away']:
    count = ht_results[result]
    rate = count / total
    implied = 1 / rate if rate > 0 else 999
    print(f"  {result:<10} {count:>7} {rate*100:>6.2f}% {implied:>12.2f}")

# ═══════════════════════════════════════════════════════════════
# MARKET 6: Double Chance
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 6: Double Chance")
print("=" * 75)

dc = {
    '1X': sum(1 for m in matches if m['ft_result'] in ('Home', 'Draw')),
    '12': sum(1 for m in matches if m['ft_result'] in ('Home', 'Away')),
    'X2': sum(1 for m in matches if m['ft_result'] in ('Draw', 'Away')),
}
print(f"\n  {'Selection':<10} {'Count':>7} {'Rate':>7}")
print("  " + "-" * 28)
for sel, count in dc.items():
    print(f"  {sel:<10} {count:>7} {count/total*100:>6.2f}%")

# ═══════════════════════════════════════════════════════════════
# MARKET 7: Home/Away Team Total Goals
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 7: Home/Away Team Goals")
print("=" * 75)

home_goals = [m['ft_home_goals'] for m in matches]
away_goals = [m['ft_away_goals'] for m in matches]
avg_home = sum(home_goals) / len(home_goals)
avg_away = sum(away_goals) / len(away_goals)
print(f"\n  Avg home goals: {avg_home:.3f}")
print(f"  Avg away goals: {avg_away:.3f}")

# Home Over 0.5
home_o05 = sum(1 for g in home_goals if g > 0) / total * 100
home_o15 = sum(1 for g in home_goals if g > 1) / total * 100
away_o05 = sum(1 for g in away_goals if g > 0) / total * 100
away_o15 = sum(1 for g in away_goals if g > 1) / total * 100
print(f"\n  Home Over 0.5: {home_o05:.1f}% | Home Over 1.5: {home_o15:.1f}%")
print(f"  Away Over 0.5: {away_o05:.1f}% | Away Over 1.5: {away_o15:.1f}%")

# ═══════════════════════════════════════════════════════════════
# MARKET 8: Second Half Performance
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 8: Second Half Analysis")
print("=" * 75)

# Derive 2nd half scores
for m in matches:
    m['2h_home'] = m['ft_home_goals'] - m['ht_home_goals']
    m['2h_away'] = m['ft_away_goals'] - m['ht_away_goals']
    m['2h_total'] = m['2h_home'] + m['2h_away']
    if m['2h_home'] > m['2h_away']:
        m['2h_result'] = 'Home'
    elif m['2h_home'] == m['2h_away']:
        m['2h_result'] = 'Draw'
    else:
        m['2h_result'] = 'Away'

avg_2h = sum(m['2h_total'] for m in matches) / total
print(f"\n  Avg 2nd half goals: {avg_2h:.3f}")
print(f"  Avg 1st half goals: {sum(m['ht_home_goals']+m['ht_away_goals'] for m in matches)/total:.3f}")

h2_results = Counter(m['2h_result'] for m in matches)
print(f"\n  2nd Half 1X2:")
for r in ['Home', 'Draw', 'Away']:
    print(f"    {r}: {h2_results[r]/total*100:.1f}%")

# 2nd half O/U
h2_over05 = sum(1 for m in matches if m['2h_total'] > 0.5) / total * 100
h2_over15 = sum(1 for m in matches if m['2h_total'] > 1.5) / total * 100
h2_over25 = sum(1 for m in matches if m['2h_total'] > 2.5) / total * 100
print(f"\n  2nd Half Over 0.5: {h2_over05:.1f}%")
print(f"  2nd Half Over 1.5: {h2_over15:.1f}%")
print(f"  2nd Half Over 2.5: {h2_over25:.1f}%")

# ═══════════════════════════════════════════════════════════════
# MARKET 9: Comeback / Lead Changes
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 9: Lead Changes & Comebacks")
print("=" * 75)

# How often does the HT leader win the match?
ht_home_lead = [m for m in matches if m['ht_result'] == 'Home']
ht_away_lead = [m for m in matches if m['ht_result'] == 'Away']
ht_draw = [m for m in matches if m['ht_result'] == 'Draw']

if ht_home_lead:
    home_lead_wins = sum(1 for m in ht_home_lead if m['ft_result'] == 'Home') / len(ht_home_lead) * 100
    home_lead_draws = sum(1 for m in ht_home_lead if m['ft_result'] == 'Draw') / len(ht_home_lead) * 100
    home_lead_loses = sum(1 for m in ht_home_lead if m['ft_result'] == 'Away') / len(ht_home_lead) * 100
    print(f"\n  When HOME leads at HT ({len(ht_home_lead)} matches):")
    print(f"    Wins FT: {home_lead_wins:.1f}% | Draws FT: {home_lead_draws:.1f}% | Loses FT: {home_lead_loses:.1f}%")

if ht_away_lead:
    away_lead_wins = sum(1 for m in ht_away_lead if m['ft_result'] == 'Away') / len(ht_away_lead) * 100
    away_lead_draws = sum(1 for m in ht_away_lead if m['ft_result'] == 'Draw') / len(ht_away_lead) * 100
    away_lead_loses = sum(1 for m in ht_away_lead if m['ft_result'] == 'Home') / len(ht_away_lead) * 100
    print(f"\n  When AWAY leads at HT ({len(ht_away_lead)} matches):")
    print(f"    Wins FT: {away_lead_wins:.1f}% | Draws FT: {away_lead_draws:.1f}% | Loses FT: {away_lead_loses:.1f}%")

if ht_draw:
    draw_home = sum(1 for m in ht_draw if m['ft_result'] == 'Home') / len(ht_draw) * 100
    draw_draw = sum(1 for m in ht_draw if m['ft_result'] == 'Draw') / len(ht_draw) * 100
    draw_away = sum(1 for m in ht_draw if m['ft_result'] == 'Away') / len(ht_draw) * 100
    print(f"\n  When DRAW at HT ({len(ht_draw)} matches):")
    print(f"    Home wins: {draw_home:.1f}% | Stays draw: {draw_draw:.1f}% | Away wins: {draw_away:.1f}%")

# ═══════════════════════════════════════════════════════════════
# MARKET 10: Handicap Analysis
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 10: Handicap Analysis")
print("=" * 75)

margins = [m['ft_home_goals'] - m['ft_away_goals'] for m in matches]
margin_counter = Counter(margins)

print(f"\n  {'Margin':<10} {'Count':>7} {'Rate':>7}")
print("  " + "-" * 28)
for margin in sorted(margin_counter.keys()):
    count = margin_counter[margin]
    label = f"H+{margin}" if margin > 0 else f"A+{abs(margin)}" if margin < 0 else "Draw"
    print(f"  {label:<10} {count:>7} {count/total*100:>6.2f}%")

# ═══════════════════════════════════════════════════════════════
# MARKET 11: Odd/Even Goals
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 11: Odd/Even Total Goals")
print("=" * 75)

odd = sum(1 for g in total_goals if g % 2 == 1)
even = sum(1 for g in total_goals if g % 2 == 0)
print(f"\n  Odd:  {odd/total*100:.2f}% ({odd}/{total})")
print(f"  Even: {even/total*100:.2f}% ({even}/{total})")

# ═══════════════════════════════════════════════════════════════
# MARKET 12: Goal Bounds (Exact Total Goals)
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  MARKET 12: Exact Total Goals")
print("=" * 75)

goal_counter = Counter(total_goals)
print(f"\n  {'Goals':<8} {'Count':>7} {'Rate':>7} {'Implied Odds':>13}")
print("  " + "-" * 38)
for g in sorted(goal_counter.keys()):
    count = goal_counter[g]
    rate = count / total
    implied = 1 / rate if rate > 0 else 999
    print(f"  {g:<8} {count:>7} {rate*100:>6.2f}% {implied:>12.1f}")

# ═══════════════════════════════════════════════════════════════
# ALPHA SEARCH: Find the BIGGEST edges across all markets
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  ALPHA SEARCH: Biggest Edges Across All Markets")
print("=" * 75)

# Collect all potential bets with their edge
alphas = []

# 1X2 edges by category
for cat in cats:
    cm = [m for m in matches if m['category'] == cat]
    n = len(cm)
    for result, typ_odds in [('Home', 2.5), ('Draw', 3.0), ('Away', 3.0)]:
        rate = sum(1 for m in cm if m['ft_result'] == result) / n
        edge = (rate * typ_odds - 1) * 100
        if abs(edge) > 5:
            alphas.append({
                'market': f"1X2 {result}", 'category': cat,
                'rate': rate*100, 'odds': typ_odds, 'edge': edge, 'n': n,
            })

# GG/NG edges by category
for cat in cats:
    cm = [m for m in matches if m['category'] == cat]
    n = len(cm)
    gg_rate = sum(1 for m in cm if m['ft_home_goals'] > 0 and m['ft_away_goals'] > 0) / n
    for sel, rate, odds in [('GG', gg_rate, 2.38), ('NG', 1-gg_rate, 1.59)]:
        edge = (rate * odds - 1) * 100
        if abs(edge) > 5:
            alphas.append({
                'market': f"GG/NG {sel}", 'category': cat,
                'rate': rate*100, 'odds': odds, 'edge': edge, 'n': n,
            })

# O/U 2.5 edges by category
for cat in cats:
    cm = [m for m in matches if m['category'] == cat]
    n = len(cm)
    goals = [m['ft_home_goals'] + m['ft_away_goals'] for m in cm]
    over = sum(1 for g in goals if g > 2.5) / n
    under = 1 - over
    for sel, rate, odds in [('Over 2.5', over, 2.90), ('Under 2.5', under, 1.42)]:
        edge = (rate * odds - 1) * 100
        if abs(edge) > 5:
            alphas.append({
                'market': f"O/U {sel}", 'category': cat,
                'rate': rate*100, 'odds': odds, 'edge': edge, 'n': n,
            })

# HT/FT edges (already known but include for comparison)
for cat in cats:
    cm = [m for m in matches if m['category'] == cat]
    n = len(cm)
    for htft in ['Home/Home', 'Draw/Draw', 'Away/Away', 'Away/Home']:
        rate = sum(1 for m in cm if m['htft_result'] == htft) / n
        if htft == 'Away/Home':
            odds = 75.0
        elif htft == 'Home/Home':
            odds = 4.0
        elif htft == 'Draw/Draw':
            odds = 5.0
        else:
            odds = 5.5
        edge = (rate * odds - 1) * 100
        if abs(edge) > 10:
            alphas.append({
                'market': f"HT/FT {htft}", 'category': cat,
                'rate': rate*100, 'odds': odds, 'edge': edge, 'n': n,
            })

# 2nd Half result edges
for cat in cats:
    cm = [m for m in matches if m['category'] == cat]
    n = len(cm)
    for result, typ_odds in [('Home', 2.5), ('Draw', 2.2), ('Away', 3.3)]:
        rate = sum(1 for m in cm if m.get('2h_result') == result) / n
        edge = (rate * typ_odds - 1) * 100
        if abs(edge) > 5:
            alphas.append({
                'market': f"2H 1X2 {result}", 'category': cat,
                'rate': rate*100, 'odds': typ_odds, 'edge': edge, 'n': n,
            })

# Sort by edge
alphas.sort(key=lambda x: x['edge'], reverse=True)

print(f"\n  TOP 25 POSITIVE EDGES (potential profit opportunities):")
print(f"  {'Market':<25} {'Category':<18} {'Rate':>6} {'Odds':>5} {'Edge':>7} {'N':>6}")
print("  " + "-" * 72)
for a in alphas[:25]:
    if a['edge'] > 0:
        print(f"  {a['market']:<25} {a['category']:<18} {a['rate']:>5.1f}% {a['odds']:>5.1f} {a['edge']:>+6.1f}% {a['n']:>6}")

print(f"\n  TOP 10 NEGATIVE EDGES (traps to avoid):")
for a in alphas[-10:]:
    if a['edge'] < 0:
        print(f"  {a['market']:<25} {a['category']:<18} {a['rate']:>5.1f}% {a['odds']:>5.1f} {a['edge']:>+6.1f}% {a['n']:>6}")

# ═══════════════════════════════════════════════════════════════
# SEQUENCE PATTERNS: Does the previous match predict the next?
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  SEQUENCE ANALYSIS: Cross-Round Patterns")
print("=" * 75)

# Group by category and round order
cat_sequences = defaultdict(list)
for m in matches:
    cat_sequences[m['category']].append(m)

for cat in ['Club World Cup', 'Germany', 'Champions']:
    seq = cat_sequences[cat]
    # Look at consecutive rounds for this category
    jp_sequence = []
    current_round = None
    round_has_jp = False
    for m in seq:
        if m['round_id'] != current_round:
            if current_round is not None:
                jp_sequence.append(1 if round_has_jp else 0)
            current_round = m['round_id']
            round_has_jp = False
        if m['is_jackpot']:
            round_has_jp = True
    jp_sequence.append(1 if round_has_jp else 0)
    
    # Autocorrelation at lag 1
    if len(jp_sequence) > 10:
        pairs = list(zip(jp_sequence[:-1], jp_sequence[1:]))
        jp_after_jp = sum(1 for a, b in pairs if a == 1 and b == 1)
        jp_count = sum(1 for a, _ in pairs if a == 1)
        nojp_after_nojp = sum(1 for a, b in pairs if a == 0 and b == 0)
        nojp_count = sum(1 for a, _ in pairs if a == 0)
        
        p_jp_jp = jp_after_jp / jp_count if jp_count > 0 else 0
        p_jp_nojp = (nojp_count - nojp_after_nojp) / nojp_count if nojp_count > 0 else 0
        
        print(f"\n  {cat}:")
        print(f"    P(JP next | JP this round) = {p_jp_jp:.3f}")
        print(f"    P(JP next | no JP) = {p_jp_nojp:.3f}")
        print(f"    Base rate = {sum(jp_sequence)/len(jp_sequence):.3f}")

# ═══════════════════════════════════════════════════════════════
# HIDDEN PATTERNS: Scoreline transitions
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 75)
print("  HIDDEN PATTERN: What happens after 0-0 at HT?")
print("=" * 75)

ht_00 = [m for m in matches if m['ht_home_goals'] == 0 and m['ht_away_goals'] == 0]
print(f"\n  Matches with 0-0 at HT: {len(ht_00)} ({len(ht_00)/total*100:.1f}%)")
ft_from_00 = Counter(f"{m['ft_home_goals']}-{m['ft_away_goals']}" for m in ht_00)
print(f"\n  Most common FT scores after 0-0 HT:")
for score, count in ft_from_00.most_common(10):
    print(f"    {score}: {count} ({count/len(ht_00)*100:.1f}%)")

ft_result_from_00 = Counter(m['ft_result'] for m in ht_00)
print(f"\n  FT result after 0-0 HT:")
for r in ['Home', 'Draw', 'Away']:
    print(f"    {r}: {ft_result_from_00[r]/len(ht_00)*100:.1f}%")

# 0-0 at HT → still 0-0 at FT
still_00 = sum(1 for m in ht_00 if m['ft_home_goals'] == 0 and m['ft_away_goals'] == 0)
print(f"\n  0-0 HT -> 0-0 FT: {still_00/len(ht_00)*100:.1f}% (typical Draw/Draw odds ~5.0)")
dd_edge = (still_00/len(ht_00) * 5.0 - 1) * 100
print(f"  Draw/Draw edge from 0-0 HT: {dd_edge:+.1f}%")

conn.close()
print("\n" + "=" * 75)
print("  ANALYSIS COMPLETE")
print("=" * 75)
