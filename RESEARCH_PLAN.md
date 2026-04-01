# SportyBet Instant Virtual Soccer — Research Plan & Continuity Document

**Last updated:** March 31, 2026
**Repo:** `pizzatipz/sportybet-instantvirtual`
**Branch:** `main`

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Current State](#2-current-state)
3. [Database Schema](#3-database-schema)
4. [How the Bot Works](#4-how-the-bot-works)
5. [Findings So Far](#5-findings-so-far)
6. [Hypotheses to Test](#6-hypotheses-to-test)
7. [Data Collection Plan](#7-data-collection-plan)
8. [Analysis Plan (Post-Collection)](#8-analysis-plan-post-collection)
9. [Strategy Redesign Plan](#9-strategy-redesign-plan)
10. [Deployment Guide (Hetzner)](#10-deployment-guide-hetzner)
11. [Key Files Reference](#11-key-files-reference)
12. [Known Issues](#12-known-issues)
13. [Important Warnings](#13-important-warnings)

---

## 1. Project Overview

**What is this?**
An automated system that scrapes match results from SportyBet's "Instant Virtual Soccer" game, collects odds data, and places bets on the HT/FT (Half-Time/Full-Time) market targeting the "Away/Home" jackpot outcome.

**The game:**
- URL: `https://www.sportybet.com/ng/sporty-instant-virtuals?from=games`
- Virtual soccer matches run every ~5 minutes in a continuous loop
- Each round has 77 fixtures across 8 categories
- The game runs inside an iframe on the SportyBet page
- RNG-driven outcomes — no real teams, no real matches

**The target bet:**
- HT/FT market → "Away/Home" selection (away team leads at half-time, home team wins full-time)
- This is marked as "jackpot" by SportyBet — it's the rarest HT/FT outcome
- Odds typically range from 20x to 100x per fixture
- Overall hit rate: ~1.6% across all fixtures

**The hypothesis:**
SportyBet systematically underprices the Away/Home outcome in the 55-75x odds range. The actual hit rate in that range appears to be ~1.74% vs the implied 1.56%, giving a ~10.6% EV edge. This needs to be proven with statistical significance.

---

## 2. Current State

### STATUS: RESEARCH CONCLUDED (April 1, 2026)

Data collection is complete. Both services (`sportybot`, `sportybot-api`) are stopped and disabled on the Hetzner server. The primary hypothesis (H1) was not confirmed. No exploitable edge exists.

### Final data:
| Table | Records |
|-------|---------|
| rounds | 1,469 |
| matches | 130,741 |
| bets | 0 (observe-only mode) |
| market_odds | 504,951 |
| — HT/FT odds | 68,382 |
| — Away/Home odds | 7,598 |
| jackpots | 2,014 (1.54%) |

### Analysis results:
- **H1 (55-75x edge): NOT SIGNIFICANT** (p=0.45, ROI=-0.7%)
- **H2 (category differences): SIGNIFICANT** but priced into odds by bookmaker
- **H3 (50-55x dead zone): SIGNIFICANT** (p=0.017) — avoid this bracket
- **H4 (100x trap): NOT SIGNIFICANT** (p=0.32)
- **H5 (stability): STABLE** — RNG is random (runs test p=0.66)
- **H6 (odds vs category): Category effect is priced in** — high-AH categories get lower odds

### Phase 1 results (from local machine, pre-server):
- **Old strategy (bets 1-215):** 1 win / 215 bets, -68.7% ROI
- **New strategy (bets 216-321):** ~4 wins / ~106 bets, +82.4% ROI (small sample luck)
- **Overall Phase 1:** ~5 wins in 321 bets, approximately -NGN 200 net

### Conclusion:
The bookmaker's RNG and pricing are well-calibrated. No strategy tested produces positive expected value after proper statistical correction. The initial "signal" in the 55-75x bracket was noise from small sample sizes.

---

## 3. Database Schema

Located at `data/sportybet.db` (SQLite, WAL mode).

### `rounds`
```
id          INTEGER PRIMARY KEY
round_id    TEXT UNIQUE      -- slug from iframe URL, e.g. "260330205207uRndqzpbt2286"
timestamp   TEXT             -- when the round occurred
scraped_at  TEXT             -- when we scraped it
```

### `matches`
```
id              INTEGER PRIMARY KEY
round_id        TEXT             -- FK to rounds
category        TEXT             -- "England", "Germany", "Champions", etc.
home_team       TEXT             -- 3-letter abbreviation, e.g. "MAI", "BMU"
away_team       TEXT             -- same
ht_home_goals   INTEGER
ht_away_goals   INTEGER
ft_home_goals   INTEGER
ft_away_goals   INTEGER
ht_result       TEXT             -- "Home", "Draw", "Away"
ft_result       TEXT             -- same
htft_result     TEXT             -- "Home/Home", "Away/Home", etc. (9 possibilities)
is_jackpot      INTEGER          -- 1 if htft_result = "Away/Home", else 0
```
~89 matches per round (77 fixtures but Club World Cup has 16, others have 9-12).

### `market_odds`
```
id          INTEGER PRIMARY KEY
round_id    TEXT
scraped_at  TEXT
category    TEXT
home_team   TEXT
away_team   TEXT
market      TEXT             -- "HT/FT", "O/U", "1X2", "Correct Score", etc.
selection   TEXT             -- "Away/ Home", "Over 2.5", "Home", etc.
odds        REAL
```
~9 HT/FT selections per fixture, plus O/U lines, 1X2, and other markets. This table has 1.3M rows.

**IMPORTANT:** The `round_id` format differs between `matches` and `market_odds`:
- matches: `260329204654uRnd5r82l9635` (extracted from iframe URL during results)
- market_odds: `R20260329212116` (generated timestamp during odds scraping)

They do NOT share the same round_ids. To join them, use `category + home_team + away_team` (fixtures repeat frequently across rounds with similar odds).

### `bets`
```
id          INTEGER PRIMARY KEY
round_id    TEXT
timestamp   TEXT
category    TEXT
home_team   TEXT
away_team   TEXT
market      TEXT             -- always "HT/FT" for current strategy
selection   TEXT             -- always "Away/Home" for current strategy
odds        REAL
stake       REAL             -- always 10.0 currently
htft_result TEXT             -- filled during settlement
won         INTEGER          -- 1 or 0, NULL if unsettled
payout      REAL
profit      REAL             -- payout - stake (negative if lost)
```

### `fixture_odds` and `htft_odds`
Legacy tables from earlier scraping attempts. Both empty (0 rows). Can be ignored.

---

## 4. How the Bot Works

### Architecture
```
src/
  __main__.py    -- CLI entry: `python -m src bot [--flags]`
  bot.py         -- Playwright browser automation (~3,400 lines)
  db.py          -- SQLite schema, insert/query functions
  strategies.py  -- Adaptive jackpot strategy engine
  analyze.py     -- Statistical analysis (unused during collection)

Server-side support files:
  status.py      -- CLI status dashboard
  api.py         -- JSON status API (port 8007, behind nginx)
  verify_data.py -- Data verification script
  watchdog.sh    -- Process watchdog (kills if hung >10 min)
```

### CLI commands
```bash
# Main modes:
python -m src bot --rounds 0 --headless         # Observe mode with HT/FT odds scraping (CURRENT)
python -m src bot --rounds 0 --headless --steady # Jackpot strategy betting
python -m src bot --rounds 0 --bet              # Legacy strategy (place_strategic_bets)
python -m src bot --rounds 0 --scrape-odds --headless  # Dedicated odds scraping only
python -m src bot --inspect                     # Open browser to examine DOM

# Flags:
--rounds N       # 0 = run forever, N = stop after N rounds
--headless       # Run without visible browser (required for server)
--steady         # Use jackpot strategy from strategies.py
--scrape-odds    # Dedicated odds-only scraping mode
```

### Auto-login
The bot supports automatic login via environment variables:
```bash
# In .env file (gitignored):
SPORTYBET_PHONE=08012345678
SPORTYBET_PASSWORD=yourpassword
```
On startup, if the persistent browser session is expired, the bot:
1. Clicks the Login button on the SportyBet page
2. Fills phone number and password from env vars
3. Submits the form and waits for NGN balance to appear
4. Falls back to manual login if auto-login fails

Session expiry during operation also triggers auto-login automatically.

### Round lifecycle (observe mode — current deployment)
1. **Detect screen** — betting, live, or results
2. **Betting screen:**
   - Scrape 77 fixtures with 1X2 odds from the fixture list
   - Store 1X2 odds to `market_odds` table
   - **Open each fixture's detail page** (per category tab):
     - Scrape all HT/FT, O/U, and other market odds
     - Store to `market_odds` table
     - 5-minute global timeout — if scraping all 77 fixtures takes too long, moves on
     - 10-second timeout per fixture's `scrape_all_market_odds()` call
   - Place 1 throwaway bet (Away/Home on first fixture, NGN 10) to trigger results
   - Click "Open Bets" → "Kick Off" → "Skip to Result"
3. **Results screen:**
   - Scrape all 89 match results across 8 category tabs
   - Store to DB with HT/FT derivation (ht_result, ft_result, htft_result, is_jackpot)
   - Click "Next Round" → repeat

### Persistent browser profile
Login cookies are saved at `data/browser_profile/`. The bot auto-logs in using credentials from `.env` if the session has expired. No manual intervention needed for headless server operation.

### Key constraint
- The bot REQUIRES at least 1 bet per round to see results (SportyBet won't show results without a placed bet)
- In observe mode, it places 1 "Away/Home" bet on the first fixture as a throwaway (NGN 10/round)

---

## 5. Findings So Far

### HT/FT outcome distribution (10,997 matches)
| Outcome | Count | Rate | Fair Odds |
|---------|-------|------|-----------|
| Home/Home | ~2,500 | 24.7% | 4.1x |
| Draw/Draw | ~2,100 | 20.9% | 4.8x |
| Away/Away | ~1,780 | 17.7% | 5.6x |
| Draw/Home | ~1,440 | 14.4% | 7.0x |
| Draw/Away | ~1,100 | 10.9% | 9.2x |
| Home/Draw | ~450 | 4.5% | 22.4x |
| Away/Draw | ~440 | 4.3% | 23.0x |
| **Away/Home** | **~175** | **1.6%** | **63.7x** |
| Home/Away | ~110 | 1.1% | 90.9x |

### AH rate by category
| Category | Matches | AH Hits | Rate | Fair Odds |
|----------|---------|---------|------|-----------|
| Germany | ~1,050 | 23 | 2.22% | 45x |
| Champions | ~1,160 | 26 | 2.24% | 45x |
| Club World Cup | ~1,860 | 35 | 1.89% | 53x |
| England | ~1,150 | 19 | 1.65% | 61x |
| Spain | ~1,140 | 16 | 1.40% | 71x |
| Euros | ~1,390 | 20 | 1.44% | 69x |
| African Cup | ~1,390 | 16 | 1.15% | 88x |
| Italy | ~1,090 | 10 | 0.92% | 109x |

### AH hit rate by offered odds bracket (THE KEY DATA)
This was computed by matching fixtures across `market_odds` and `matches` tables via `category + home_team + away_team`:

| Bracket | Fixtures | Hits | Rate | Avg Odds | Implied | EV |
|---------|----------|------|------|----------|---------|-----|
| <30x | 405 | 18 | 4.44% | 25.6x | 3.91% | +13.8% |
| 30-40x | 1,056 | 31 | 2.94% | 35.6x | 2.81% | +4.4% |
| 40-50x | 1,276 | 27 | 2.12% | 45.4x | 2.20% | -4.0% |
| **50-55x** | **580** | **7** | **1.21%** | **52.6x** | **1.90%** | **-36.5%** |
| **55-60x** | **726** | **14** | **1.93%** | **57.5x** | **1.74%** | **+10.9%** |
| **60-65x** | **676** | **12** | **1.78%** | **62.5x** | **1.60%** | **+10.9%** |
| **65-75x** | **1,013** | **16** | **1.58%** | **69.9x** | **1.43%** | **+10.4%** |
| 75-90x | 1,256 | 13 | 1.04% | 82.4x | 1.21% | -14.7% |
| 90-100x | 800 | 9 | 1.12% | 94.7x | 1.06% | +6.5% |
| 100x | 1,557 | 9 | 0.58% | 100.0x | 1.00% | -42.2% |

**The pattern:** Hit rate is ABOVE implied in the 55-75x range but BELOW implied in 40-55x and 75-100x. The 50-55x range is a "dead zone" where SportyBet prices accurately. 100x is a pure trap.

**NONE of these results are statistically significant** at 95% confidence. All Wilson CI lower bounds for EV are negative. We need more data.

---

## 6. Hypotheses to Test

### H1: The 55-75x bracket edge is real (PRIMARY)
- **Claim:** AH hit rate in 55-75x > 1.56% (implied by avg odds)
- **Observed:** 1.74% (42/2,415)
- **Test:** One-proportion z-test, one-sided
- **Needed:** 30,443 fixtures at 80% power → **1,538 rounds**
- **Status:** Not significant (current CI: [1.29%, 2.34%])

### H2: Category matters for AH rate
- **Claim:** Germany/Champions have genuinely higher AH rates than Italy
- **Observed:** Germany 2.22% vs Italy 0.92%
- **Test:** Two-proportion z-test
- **Needed:** 1,435 matches per category → **~144 rounds**
- **Status:** Almost provable (currently at 69% of needed data)

### H3: The 50-55x dead zone is real
- **Claim:** AH hit rate at 50-55x < implied 1.90%
- **Observed:** 1.21% (7/580)
- **Needed:** ~1,820 fixtures → **~383 rounds**
- **Status:** Not significant

### H4: 100x odds are a trap
- **Claim:** AH hit rate at 100x < 1.00% (implied)
- **Observed:** 0.58% (9/1,557)
- **Status:** Close to provable — needs ~200 more rounds

### H5: Overall AH rate is stable over time
- **Claim:** AH rate doesn't drift from ~1.6%
- **Test:** Control chart / sequential analysis
- **Needed:** 12,944 matches to detect 0.3pp shift → **~146 rounds**
- **Status:** Provable with current data, but need rolling window analysis

### H6: The edge is in odds brackets, not categories
- **Claim:** After controlling for offered odds, category adds no additional predictive value
- **Test:** Logistic regression (odds + category + interaction terms)
- **Needed:** ~2,000 rounds for sufficient cell sizes
- **Status:** Not testable yet

---

## 7. Data Collection Plan

### Phase 1: Pure data collection (observe-only mode)
```bash
python -m src bot --rounds 0 --headless
```

**What this does:**
- Places 1 min bet per round (NGN 10) to access results
- Scrapes all 89 match results per round
- Scrapes all market odds for every fixture (HT/FT, O/U, 1X2, etc.)
- Stores everything to SQLite
- Does NOT place strategic bets

**Target:** 1,500 rounds minimum (80% power for H1)
**Estimated time:** ~6-7 days continuous on Hetzner
**Cost:** NGN 15,000 in throwaway bets (1,500 rounds × NGN 10)

### Phase 2: Analysis (after collection)
Run the analysis scripts detailed in Section 8. Determine which hypotheses are proven/disproven.

### Phase 3: Deploy proven strategy
If H1 is confirmed, implement the adaptive odds-bracket strategy and switch to live betting.

### Milestones to track:
| Rounds | What can be answered |
|--------|---------------------|
| 200 | H2 (category differences), H5 (stability) |
| 400 | H3 (dead zone), H4 (100x trap) |
| 1,000 | First signs of H1 significance |
| 1,500 | H1 conclusive at 80% power |
| 2,000 | H1 at 90% power, H6 (odds vs category) |
| 5,000 | All hypotheses at >99% power |

---

## 8. Analysis Plan (Post-Collection)

### Analysis 1: Per-bracket hit rate with significance
```sql
-- Join market_odds to matches via category + teams
-- (round_ids don't match between tables — see Section 3)
SELECT
    bracket,
    COUNT(*) as n,
    SUM(CASE WHEN m.htft_result='Away/Home' THEN 1 ELSE 0 END) as hits,
    AVG(mo.odds) as avg_odds
FROM (
    SELECT category, home_team, away_team, AVG(odds) as avg_odds,
        CASE
            WHEN AVG(odds) < 55 THEN '<55'
            WHEN AVG(odds) < 75 THEN '55-75'
            ELSE '75+'
        END as bracket
    FROM market_odds
    WHERE market='HT/FT' AND selection='Away/ Home'
    GROUP BY category, home_team, away_team
) mo
JOIN (
    SELECT category, home_team, away_team,
           htft_result, COUNT(*) as appearances
    FROM matches GROUP BY category, home_team, away_team
) m ON mo.category=m.category
    AND mo.home_team=m.home_team AND mo.away_team=m.away_team
GROUP BY bracket
```
Then compute Wilson CIs and one-proportion z-tests for each bracket.

### Analysis 2: Category regression
```python
# Logistic regression: htft_result == 'Away/Home' ~ odds + category
import statsmodels.api as sm
# If category coefficient is significant after controlling for odds,
# then category matters beyond the odds themselves
```

### Analysis 3: Stability over time
```python
# Compute 50-round rolling AH rate
# Plot control chart with ±2σ bounds
# Check for structural breaks (Chow test)
```

### Analysis 4: Per-fixture odds consistency
```python
# For each unique fixture (category + teams):
#   - How variable are the AH odds across rounds?
#   - Do fixtures with lower variance have more predictable outcomes?
```

### Analysis 5: Kelly staking optimization
```python
# Given proven hit rate and odds distribution:
#   - Compute optimal Kelly fraction
#   - Simulate bankroll paths at full/half/quarter Kelly
#   - Determine minimum bankroll for survival
```

---

## 9. Strategy Redesign Plan

After data collection proves/disproves hypotheses, implement:

### If H1 is confirmed (55-75x edge exists):
```python
# Adaptive Odds-Bracket Strategy
def should_bet(category, ah_odds, db_conn):
    # 1. Check minimum data: category has 200+ matches in DB
    # 2. Check odds in profitable range (computed dynamically from data)
    # 3. Compute category-specific AH rate from all historical data
    # 4. Compute EV = (category_ah_rate × offered_odds) - 1
    # 5. Only bet if EV > 5% (MIN_EV_THRESHOLD)
    # 6. Apply rolling circuit breaker (pause if last 50 bets < 0.5% hit rate)
    # 7. Sort all qualified bets by EV, take top N per round
    pass
```

**Key design principles:**
- NO hardcoded categories or odds ranges — everything derived from data
- Recompute profitable odds brackets every 10 rounds
- All categories eligible if they have enough data and show +EV at offered odds
- Circuit breaker: if rolling 50-bet hit rate < 0.5%, pause betting for 5 rounds
- Trend monitor: if overall AH rate drops below 1.3%, pause all betting
- Max 12 bets per round (limit exposure)
- Kelly-based staking (half-Kelly of bankroll)

### If H1 is NOT confirmed (no edge):
The game has no exploitable edge. Stop betting. The system becomes a pure data collection tool for academic interest.

---

## 10. Deployment Guide (Hetzner) — CURRENT LIVE DEPLOYMENT

### Server details
- **Host:** 188.34.136.239 (Hetzner, 64 GB RAM, Ubuntu)
- **Location:** `/opt/probodds/sportybet/`
- **Python:** 3.12, venv at `.venv/`
- **Browser:** Playwright Chromium headless
- **Credentials:** `.env` file (gitignored, owner-read only)

### Services running
| Service | Purpose | Port |
|---------|---------|------|
| `sportybot.service` | Data collection bot (Playwright + Chromium) | — |
| `sportybot-api.service` | JSON status API | 8007 (behind nginx) |

### systemd service configuration
```ini
# /etc/systemd/system/sportybot.service
[Unit]
Description=SportyBet Virtual Soccer Data Collector
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/probodds/sportybet
ExecStart=/opt/probodds/sportybet/watchdog.sh
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=sportybot
Environment=HOME=/root

[Install]
WantedBy=multi-user.target
```

The `watchdog.sh` wrapper runs the bot and monitors stdout. If no output for 10 minutes (indicating the bot is hung on a Playwright call), it kills the process. systemd's `Restart=on-failure` then restarts it after 30 seconds.

### Auto-login configuration
```bash
# /opt/probodds/sportybet/.env (chmod 600)
SPORTYBET_PHONE=08012345678
SPORTYBET_PASSWORD=yourpassword
```

The bot loads these on startup and auto-logs in when:
1. First launch (no saved session)
2. Session expiry during operation
3. Restart after crash

No manual login or VNC/X11 forwarding needed.

### Monitoring
```bash
# Live dashboard (browser/phone)
https://probodds.com/sportybot/

# JSON API
curl -s https://probodds.com/api/sportybot/status | python3 -m json.tool

# CLI status
ssh root@188.34.136.239 "cd /opt/probodds/sportybet && .venv/bin/python status.py"

# Live logs
ssh root@188.34.136.239 "journalctl -u sportybot -f"

# Service control
ssh root@188.34.136.239 "systemctl status|restart|stop sportybot"
```

### Database backup
```bash
# Manual backup
ssh root@188.34.136.239 "cp /opt/probodds/sportybet/data/sportybet.db /opt/probodds/backups/sportybet_\$(date +%Y%m%d).db"

# Download to local
scp root@188.34.136.239:/opt/probodds/sportybet/data/sportybet.db ./data/
```

### Updating the bot
```bash
ssh root@188.34.136.239 "cd /opt/probodds/sportybet && git pull origin main && systemctl restart sportybot"
```

---

## 11. Key Files Reference

| File | Purpose | Lines |
|------|---------|-------|
| `src/bot.py` | Browser automation, auto-login, odds scraping, result scraping | ~3,400 |
| `src/db.py` | SQLite schema and CRUD operations | ~350 |
| `src/strategies.py` | Jackpot strategy engine with adaptive learning | ~300 |
| `src/__main__.py` | CLI entry point | ~20 |
| `src/analyze.py` | Analysis utilities (for post-collection) | ~50 |
| `status.py` | CLI status dashboard (rounds, matches, jackpots, categories) | ~80 |
| `api.py` | JSON HTTP status API (port 8007) | ~80 |
| `verify_data.py` | Data verification (table counts, odds breakdown, join test) | ~70 |
| `watchdog.sh` | Process watchdog — kills if no output >10 min | ~20 |
| `.env.example` | Credentials template | ~3 |
| `requirements.txt` | Python dependencies | ~9 |
| `data/sportybet.db` | The database (**primary asset** — back up regularly) | — |
| `data/browser_profile/` | Chromium login session cookies | — |

### bot.py key functions:
- `auto_login(page)` → Automatic login using env var credentials
- `wait_for_login(page)` → Navigate + auto-login or manual login fallback
- `handle_session_expired(page)` → Auto-login on session expiry
- `run_scraper(...)` → Main loop (the entry point)
- `scrape_round_results(page)` → Scrape all match results from results screen
- `scrape_betting_screen(page)` → Scrape fixture list + 1X2 odds
- `scrape_all_market_odds(page)` → Scrape HT/FT, O/U, 1X2, etc. from detail page
- `detect_screen(page)` → Returns "betting", "live", "results", or "unknown"
- `recover_iframe(page)` → Re-locate iframe after page reload
- `run_odds_scraper(...)` → Dedicated odds-only scraping mode

---

## 12. Known Issues

### HT/FT odds scraping can hang (MITIGATED)
- **Cause:** Playwright `evaluate()` or page interaction blocks the asyncio event loop when a detail page is unresponsive
- **Previous impact:** Bot would hang indefinitely, no new rounds scraped
- **Mitigation (current):**
  1. `asyncio.wait_for(scrape_all_market_odds(...), timeout=10.0)` per fixture
  2. `time.monotonic()` 5-minute global timeout for entire odds scraping loop
  3. `watchdog.sh` kills the process if no stdout for 10 minutes
  4. `systemd Restart=on-failure` auto-restarts after 30 seconds
- **Impact if triggered:** Some HT/FT odds for that round are missed, but results are still scraped normally on the next round

### Round ID mismatch between tables
- `matches.round_id` comes from the iframe URL during results scraping
- `market_odds.round_id` is a timestamp generated during odds scraping
- They NEVER match. **Join on `category + home_team + away_team` instead.**
- This is a design bug from when odds scraping was a separate pass

### Observe mode throwaway bet cost
- SportyBet requires at least 1 placed bet to show match results
- The bot places an "Away/Home" bet on the first fixture (NGN 10) each round
- Cost: NGN 10/round × 1,500 rounds = NGN 15,000 (~$9 USD)
- These throwaway bets are NOT tracked in the `bets` table

### OOM crashes on low-memory machines (RESOLVED)
- **Cause:** Chromium `STATUS_BREAKPOINT` on Windows with limited RAM
- **Fix:** Hetzner 64GB server + headless mode — no OOM since deployment
- **History:** Occurred every 5-15 rounds on local Windows machine

---

## 13. Important Warnings

1. **Do NOT kill all python/chrome processes blindly.** Other services (parlay trader, basketball, collector) run on the same server. Use `systemctl stop sportybot` or `kill` only the specific PID.

2. **The database is the most valuable asset.** Back it up regularly. All analysis depends on having a large, clean dataset. The database is at `/opt/probodds/sportybet/data/sportybet.db`.

3. **Phase 2 is observe-only.** Do NOT switch to `--steady` mode until 1,500+ rounds of data are collected and analyzed. The strategy can only be validated with sufficient statistical power.

4. **The edge (if it exists) is small.** ~0.18 percentage points above implied rate. Expected ROI ~10% with high variance. Cold streaks of 10-20 rounds with zero wins are normal.

5. **SportyBet could change the RNG at any time.** Monitor the overall jackpot rate on the dashboard. If it drifts below 1.3% sustained, the RNG may have changed.

6. **The parlay system runs on port 8006.** Do NOT use port 8006 for anything sportybot-related. The sportybot API is on port 8007.

---

*This document should be given to any new session/agent working on this project. It contains everything needed to understand, deploy, and continue the research.*
