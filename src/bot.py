"""
Playwright-based bot for scraping SportyBet Instant Virtual Soccer results.

Primary mode: Scrapes ALL match results from ALL categories after each round
completes, collecting HT and FT scores to derive HT/FT market outcomes.

The key insight: after each round, SportyBet shows results for ALL categories
(England, Spain, Germany, Champions, Italy, African Cup, Euros, Club World Cup)
and ALL teams — giving us 40+ data points per round for free.
"""

import argparse
import asyncio
import sys
import re
from pathlib import Path
from datetime import datetime, timezone

from playwright.async_api import async_playwright, Page, BrowserContext

from src.db import (
    get_connection, init_db, insert_round, insert_matches_bulk,
    round_exists, get_total_stats, CATEGORIES, insert_htft_odds_bulk,
)

# Persistent browser profile directory
PROFILE_DIR = Path(__file__).parent.parent / "data" / "browser_profile"

# SportyBet virtual soccer URL
SPORTYBET_VIRTUALS_URL = "https://www.sportybet.com/ng/sporty-instant-virtuals?from=games"

# ──────────────────────────────────────────────────────────
#  ADAPTIVE BETTING STRATEGY
#  Re-learns from all collected data every LEARN_INTERVAL rounds.
#  Updates target categories and teams based on actual jackpot rates.
# ──────────────────────────────────────────────────────────

LEARN_INTERVAL = 10  # Re-analyze data every N rounds
MIN_SAMPLES = 50     # Minimum matches for a team/category before trusting its rate
CATEGORY_THRESHOLD = 1.5    # Bet on categories with jackpot rate >= this %
TEAM_MIN_JACKPOTS = 2      # Team needs >= this many jackpots to be targeted
MIN_ODDS = 50.0            # Only bet when Away/Home odds >= this value

# Categories with PROVEN negative EV — never bet here regardless of teams
BLACKLIST_CATEGORIES = {"England", "Italy"}

# Initial targets (from 328 rounds / 29,131 matches analysis)
# These get overwritten by learn_from_data() after first interval.
TARGET_CATEGORIES = {"Club World Cup", "Germany", "Champions"}
TARGET_HOME_TEAMS = {
    "PSG", "ARS", "ATM", "BAY", "NEW", "ENG", "FLU", "HIL",
    "RMA", "SVK", "CIV",
}
TARGET_AWAY_TEAMS = {
    "FLA", "CHE", "JUV", "PAC", "AIN", "BMU", "ITA", "KOE",
    "UKR", "ZMB",
}


def learn_from_data(conn) -> dict:
    """Analyze all collected data and update strategy targets.

    Queries the database for:
    - Jackpot rates by category
    - Teams most involved in jackpots (home and away)
    - Overall jackpot rate vs implied
    - Recent trends (last 20 rounds vs all time)

    Returns a report dict and updates the global target sets.
    """
    global TARGET_CATEGORIES, TARGET_HOME_TEAMS, TARGET_AWAY_TEAMS

    total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    if total < 100:
        return {"status": "insufficient_data", "total_matches": total}

    total_jp = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE is_jackpot=1"
    ).fetchone()[0]
    overall_rate = total_jp / total if total > 0 else 0

    # ── Category analysis ────────────────────────────────
    cat_rows = conn.execute("""
        SELECT category, COUNT(*) as n, SUM(is_jackpot) as jp,
               ROUND(SUM(is_jackpot) * 100.0 / COUNT(*), 3) as rate
        FROM matches GROUP BY category ORDER BY rate DESC
    """).fetchall()

    new_categories = set()
    cat_report = []
    for r in cat_rows:
        rate = r['jp'] / r['n'] * 100 if r['n'] > 0 else 0
        blacklisted = r['category'] in BLACKLIST_CATEGORIES
        qualifies = rate >= CATEGORY_THRESHOLD and r['n'] >= MIN_SAMPLES and not blacklisted
        cat_report.append({
            "category": r['category'], "matches": r['n'],
            "jackpots": r['jp'], "rate": round(rate, 2),
            "targeted": qualifies, "blacklisted": blacklisted,
        })
        if qualifies:
            new_categories.add(r['category'])

    # ── Home team analysis (comeback teams) ──────────────
    home_rows = conn.execute("""
        SELECT home_team, COUNT(*) as n, SUM(is_jackpot) as jp
        FROM matches GROUP BY home_team
        HAVING jp >= ?
        ORDER BY jp DESC
    """, (TEAM_MIN_JACKPOTS,)).fetchall()

    new_home_teams = set()
    home_report = []
    for r in home_rows:
        rate = r['jp'] / r['n'] * 100 if r['n'] > 0 else 0
        new_home_teams.add(r['home_team'])
        home_report.append({
            "team": r['home_team'], "matches": r['n'],
            "jackpots": r['jp'], "rate": round(rate, 2),
        })

    # ── Away team analysis (choke teams) ─────────────────
    away_rows = conn.execute("""
        SELECT away_team, COUNT(*) as n, SUM(is_jackpot) as jp
        FROM matches GROUP BY away_team
        HAVING jp >= ?
        ORDER BY jp DESC
    """, (TEAM_MIN_JACKPOTS,)).fetchall()

    new_away_teams = set()
    away_report = []
    for r in away_rows:
        rate = r['jp'] / r['n'] * 100 if r['n'] > 0 else 0
        new_away_teams.add(r['away_team'])
        away_report.append({
            "team": r['away_team'], "matches": r['n'],
            "jackpots": r['jp'], "rate": round(rate, 2),
        })

    # ── Recent trend (last 20 rounds) ────────────────────
    recent_rows = conn.execute("""
        SELECT m.is_jackpot FROM matches m
        JOIN rounds r ON m.round_id = r.round_id
        ORDER BY r.id DESC LIMIT 1780
    """).fetchall()  # ~20 rounds × 89 matches
    recent_total = len(recent_rows)
    recent_jp = sum(r['is_jackpot'] for r in recent_rows)
    recent_rate = recent_jp / recent_total * 100 if recent_total > 0 else 0

    # ── Detect changes ───────────────────────────────────
    added_cats = new_categories - TARGET_CATEGORIES
    removed_cats = TARGET_CATEGORIES - new_categories
    added_home = new_home_teams - TARGET_HOME_TEAMS
    removed_home = TARGET_HOME_TEAMS - new_home_teams
    added_away = new_away_teams - TARGET_AWAY_TEAMS
    removed_away = TARGET_AWAY_TEAMS - new_away_teams

    # ── Apply updates ────────────────────────────────────
    TARGET_CATEGORIES = new_categories
    TARGET_HOME_TEAMS = new_home_teams
    TARGET_AWAY_TEAMS = new_away_teams

    report = {
        "status": "updated",
        "total_matches": total,
        "total_jackpots": total_jp,
        "overall_rate": round(overall_rate * 100, 2),
        "recent_rate": round(recent_rate, 2),
        "categories": cat_report,
        "home_teams": home_report[:15],
        "away_teams": away_report[:15],
        "target_categories": sorted(new_categories),
        "target_home_teams": sorted(new_home_teams),
        "target_away_teams": sorted(new_away_teams),
        "changes": {
            "added_categories": sorted(added_cats),
            "removed_categories": sorted(removed_cats),
            "added_home_teams": sorted(added_home),
            "removed_home_teams": sorted(removed_home),
            "added_away_teams": sorted(added_away),
            "removed_away_teams": sorted(removed_away),
        },
    }
    return report


def print_learning_report(report: dict) -> None:
    """Print a summary of what the strategy learned."""
    if report.get("status") == "insufficient_data":
        print(f"  📚 Not enough data yet ({report['total_matches']} matches)")
        return

    print(f"\n  {'=' * 50}")
    print(f"  📚 STRATEGY UPDATE (learned from {report['total_matches']} matches)")
    print(f"  {'=' * 50}")
    print(f"  Overall jackpot rate: {report['overall_rate']}%")
    print(f"  Recent rate (last ~20 rounds): {report['recent_rate']}%")

    trend = ""
    if report['recent_rate'] > report['overall_rate'] + 0.2:
        trend = " 📈 trending UP"
    elif report['recent_rate'] < report['overall_rate'] - 0.2:
        trend = " 📉 trending DOWN"
    else:
        trend = " ➡️ stable"
    print(f"  Trend: {trend}")

    print(f"\n  Target categories ({len(report['target_categories'])}):")
    for cr in report['categories']:
        marker = " ✓" if cr['targeted'] else ""
        print(f"    {cr['category']:<18} {cr['rate']:>5.2f}% ({cr['jackpots']}/{cr['matches']}){marker}")

    changes = report['changes']
    has_changes = any(v for v in changes.values())
    if has_changes:
        print(f"\n  🔄 Changes since last update:")
        if changes['added_categories']:
            print(f"    + Categories: {', '.join(changes['added_categories'])}")
        if changes['removed_categories']:
            print(f"    - Categories: {', '.join(changes['removed_categories'])}")
        if changes['added_home_teams']:
            print(f"    + Home teams: {', '.join(changes['added_home_teams'][:8])}")
        if changes['removed_home_teams']:
            print(f"    - Home teams: {', '.join(changes['removed_home_teams'][:8])}")
        if changes['added_away_teams']:
            print(f"    + Away teams: {', '.join(changes['added_away_teams'][:8])}")
        if changes['removed_away_teams']:
            print(f"    - Away teams: {', '.join(changes['removed_away_teams'][:8])}")
    else:
        print(f"\n  No strategy changes — current targets remain optimal.")

    print(f"  {'=' * 50}")


def fixture_matches_strategy(fixture: dict) -> bool:
    """Check if a fixture matches our betting strategy.

    A fixture qualifies if:
    1. NOT in a blacklisted category (England, Italy), AND
    2. Either:
       - It's in a target category, OR
       - The home team is a known comeback team, OR
       - The away team is a known choke team
    """
    cat = fixture.get("category", "")
    
    # Hard exclude: never bet in negative-EV categories
    if cat in BLACKLIST_CATEGORIES:
        return False
    
    if cat in TARGET_CATEGORIES:
        return True
    if fixture.get("home_team") in TARGET_HOME_TEAMS:
        return True
    if fixture.get("away_team") in TARGET_AWAY_TEAMS:
        return True
    return False


async def launch_browser(headless: bool = False, persistent: bool = True) -> tuple:
    """Launch browser with persistent profile for session/cookie reuse.

    The persistent profile (data/browser_profile/) keeps login cookies
    between runs so the user only has to log in once.

    If the profile is locked by a zombie process, falls back to a
    fresh non-persistent context (user will need to re-login).
    """
    pw = await async_playwright().start()

    if persistent:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            context = await pw.chromium.launch_persistent_context(
                str(PROFILE_DIR),
                headless=headless,
                viewport={"width": 1280, "height": 900},
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else await context.new_page()
            return pw, context, page
        except Exception as e:
            print(f"⚠️  Persistent profile failed ({e})")
            print("   Falling back to fresh browser (you may need to re-login).")

    # Non-persistent fallback
    browser = await pw.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await context.new_page()
    return pw, context, page


async def wait_for_login(page: Page):
    """Navigate to SportyBet, handle login if needed, and return the
    iframe Frame containing the virtual soccer content.

    Login strategy (in priority order):
    1. Persistent browser profile preserves cookies — if already logged in
       from a previous run, no action needed.
    2. Auto-detect login state via the page's `loginStatus` JS variable.
    3. If not logged in, pause and wait for the user to log in manually
       in the browser window.
    """
    print("\n" + "=" * 60)
    print("SPORTYBET VIRTUAL SOCCER — RESULT SCRAPER")
    print("=" * 60)

    await page.goto(SPORTYBET_VIRTUALS_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)  # let JS hydrate

    # ── Check if already logged in ───────────────────────────
    logged_in = await _check_logged_in(page)

    if logged_in:
        print("✅ Already logged in (session from persistent profile).")
    else:
        print("\n⚠️  Not logged in.")
        print("   Please log in using the browser window that opened.")
        print("   (Your session will be saved for future runs.)")
        print("\n   Waiting for login...")

        # Poll until the user logs in (check every 3 seconds)
        for _ in range(200):  # ~10 min max wait
            await asyncio.sleep(3)
            if await _check_logged_in(page):
                print("✅ Login detected!")
                # Reload page to pick up authenticated state
                await page.goto(
                    SPORTYBET_VIRTUALS_URL,
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                await asyncio.sleep(3)
                break
        else:
            print("❌ Login timed out. Please restart and try again.")
            raise SystemExit(1)

    # ── Wait for the iframe to appear ────────────────────────
    print("⏳ Waiting for virtual soccer to load...")
    iframe_el = None
    for _ in range(30):
        iframe_el = await page.query_selector(
            "iframe#instantwin-sport, iframe[src*='instant-virtuals'], "
            "iframe[src*='sporty-instant']"
        )
        if iframe_el:
            break
        await asyncio.sleep(1)

    if iframe_el:
        frame = await iframe_el.content_frame()
        if frame:
            await frame.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(2)
            print("🖼️  Found iframe — scraping inside it.")
            return frame

    print("⚠️  No iframe detected — using outer page.")
    return page


async def _check_logged_in(page: Page) -> bool:
    """Check if the user is logged in on the outer SportyBet page.

    Uses the most reliable signal: whether the page shows an NGN balance
    or "My Account" in the top header (only visible when logged in).
    The Login/Register buttons are only shown when logged out.
    """
    try:
        result = await page.evaluate(r"""() => {
            // Check if "My Account" text is visible in the header
            const body = document.body.textContent || '';
            if (body.includes('My Account') && body.match(/NGN\s*[\d,]+/)) {
                return true;
            }
            // Check if Login button is visible (means NOT logged in)
            const loginBtn = document.querySelector('button.login-btn, [class*="login-btn"]');
            if (loginBtn && loginBtn.offsetHeight > 0) {
                return false;
            }
            // Check for phone/password input fields (login form visible)
            const phoneInput = document.querySelector('input[placeholder*="Mobile"], input[placeholder*="Phone"]');
            if (phoneInput && phoneInput.offsetHeight > 0) {
                return false;
            }
            // Check JS variable as a last resort
            if (typeof window.loginStatus !== 'undefined') {
                return window.loginStatus === true;
            }
            return false;
        }""")
        return result
    except Exception:
        return False


async def scrape_round_results(page: Page) -> tuple[str | None, list[dict]]:
    """
    Scrape all match results from the current results screen.

    The page must already be on the results view (inside the iframe).
    Clicks through each category tab (England, Spain, …) to collect
    every match's HT and FT scores.

    Returns:
        (round_id, list of match dicts) or (None, []) if scraping fails.
    """
    matches = []

    try:
        # ── 0. Dismiss any popups/overlays blocking the page ─────
        await dismiss_win_splash(page)
        # Disable pointer-events on wrapper overlays so clicks pass through.
        # #instant-win-wrapper wraps the whole results area — don't hide it,
        # just make it transparent to clicks.
        await page.evaluate(r"""() => {
            const iw = document.querySelector('#instant-win-wrapper');
            if (iw) { iw.style.pointerEvents = 'none'; }
            // Remove pointer events from winngin-pop if still around
            const wp = document.querySelector('#winngin-pop');
            if (wp) { wp.style.display = 'none'; }
        }""")
        # Use force=True for all tab clicks below to bypass any remaining overlays

        # ── 1. Extract round ID from the iframe URL ──────────────
        round_id = None
        try:
            url = page.url
            # URL pattern: .../football/<round_slug>?sportId=...
            slug_match = re.search(r'/football/([^?/]+)', url)
            if slug_match:
                round_id = slug_match.group(1)
        except Exception:
            pass
        if not round_id:
            round_id = f"R{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # ── 2. Iterate over every category tab ───────────────────
        tabs = await page.query_selector_all("li.sport-type-item")
        tab_names = []
        for tab in tabs:
            name = (await tab.text_content() or "").strip()
            if name and name != "My Events":
                tab_names.append((tab, name))

        if not tab_names:
            print("⚠️  No category tabs found.")
            return round_id, []

        for tab, category in tab_names:
            # Click the tab to switch categories (force=True bypasses overlays)
            await tab.click(force=True)
            await asyncio.sleep(0.6)  # let results render

            # ── 3. Scrape match rows for this category ───────────
            rows = await page.query_selector_all(".liveResult-matches-item")
            for row in rows:
                match_data = await _extract_match(row, category, round_id)
                if match_data:
                    matches.append(match_data)

            print(f"  {category}: {sum(1 for m in matches if m['category'] == category)} matches")

        return round_id, matches

    except Exception as e:
        print(f"❌ Error scraping results: {e}")
        return None, []


async def _extract_match(row, category: str, round_id: str) -> dict | None:
    """
    Extract a single match's data from a .liveResult-matches-item element.

    DOM structure (discovered via --inspect):
      div.team-match
        div.teamName   → home team abbreviation
        div.teamScore
          span.score   → FT home goals
          span         → "-"
          span.score   → FT away goals
          div.teamHalfScore → "First Half X-Y"
        div.teamName   → away team abbreviation
    """
    try:
        header = await row.query_selector(".liveResult-matches-item__header")
        if not header:
            return None

        team_match = await header.query_selector(".team-match")
        if not team_match:
            return None

        # Team names: two .teamName elements (home first, away second)
        name_els = await team_match.query_selector_all(".teamName")
        if len(name_els) < 2:
            return None
        home_team = (await name_els[0].text_content() or "").strip()
        away_team = (await name_els[1].text_content() or "").strip()
        if not home_team or not away_team:
            return None

        # FT score: span.score elements inside .teamScore
        score_el = await team_match.query_selector(".teamScore")
        if not score_el:
            return None
        score_spans = await score_el.query_selector_all("span.score")
        if len(score_spans) < 2:
            return None
        ft_home = int((await score_spans[0].text_content() or "").strip())
        ft_away = int((await score_spans[1].text_content() or "").strip())

        # HT score: .teamHalfScore text like "First Half 1-1"
        ht_el = await score_el.query_selector(".teamHalfScore")
        if not ht_el:
            return None
        ht_text = (await ht_el.text_content() or "").strip()
        ht_match = re.search(r'(\d+)\s*-\s*(\d+)', ht_text)
        if not ht_match:
            return None
        ht_home = int(ht_match.group(1))
        ht_away = int(ht_match.group(2))

        return {
            "round_id": round_id,
            "category": category,
            "home_team": home_team,
            "away_team": away_team,
            "ht_home_goals": ht_home,
            "ht_away_goals": ht_away,
            "ft_home_goals": ft_home,
            "ft_away_goals": ft_away,
        }
    except Exception:
        return None


async def detect_screen(page) -> str:
    """Detect which screen is currently displayed inside the iframe.

    Returns one of: 'betting', 'live', 'results', 'unknown'
    """
    url = page.url if hasattr(page, 'url') else ""

    # Results screen has .liveResult-matches-item elements
    result_el = await page.query_selector(".liveResult-matches-item")
    if result_el:
        return "results"

    # Betting screen has .event-list elements and the quickgame URL (no /live/)
    event_el = await page.query_selector(".event-list")
    if event_el:
        return "betting"

    # Live/animation screen — URL contains /live/ but no results yet
    if "/live/" in url:
        return "live"

    return "unknown"


async def scrape_betting_screen(page) -> tuple[str | None, list[dict]]:
    """
    Scrape the pre-match betting screen to capture fixture list and 1X2 odds.

    This runs on the betting screen (before the round starts).
    All categories are shown at once in a scrollable list grouped by
    league-sub-title-wrapper headers.

    Returns:
        (round_id, list of fixture dicts with odds)

    Each fixture dict contains:
        round_id, category, home_team, away_team, odds_1, odds_x, odds_2
    """
    fixtures = []
    try:
        # Extract round slug from URL
        round_id = None
        url = page.url if hasattr(page, 'url') else ""
        slug_match = re.search(r'quickgame(?:/live/football/([^?/]+))?', url)
        if slug_match and slug_match.group(1):
            round_id = slug_match.group(1)

        # The betting screen has a split layout:
        #   left column (.table-team-column): teams grouped by league
        #   right column (.table-market-outcome-column): odds in same order
        #
        # We need to read both in parallel.

        # Left column: teams
        team_rows = await page.query_selector_all(
            ".table-team-column .event-list.spacer-team"
        )
        # Right column: odds (market cells in same order)
        odds_rows = await page.query_selector_all(
            ".table-market-outcome-column .event-list.spacer-market"
        )

        # League headers to track current category
        # All rows (headers + matches) in the left column
        all_left_items = await page.query_selector_all(
            ".table-team-column .m-table > .m-table-row.title-container.spacer-team, "
            ".table-team-column .m-table > .event-list.spacer-team"
        )

        current_category = "Unknown"
        fixture_idx = 0

        for item in all_left_items:
            class_attr = await item.get_attribute("class") or ""

            if "title-container" in class_attr:
                # This is a league header
                header_el = await item.query_selector(
                    ".league-sub-title-wrapper span"
                )
                if header_el:
                    current_category = (
                        await header_el.text_content() or ""
                    ).strip()
                continue

            # This is a match row — extract team names
            team_els = await item.query_selector_all(
                ".teams-info span:not(.vs)"
            )
            teams = []
            for el in team_els:
                t = (await el.text_content() or "").strip()
                if t:
                    teams.append(t)

            if len(teams) < 2:
                fixture_idx += 1
                continue

            fixture = {
                "category": current_category,
                "home_team": teams[0],
                "away_team": teams[1],
                "odds_1": None,
                "odds_x": None,
                "odds_2": None,
            }

            # Extract odds from the corresponding row
            if fixture_idx < len(odds_rows):
                odds_els = await odds_rows[fixture_idx].query_selector_all(
                    ".iw-outcome span"
                )
                odds_values = []
                for el in odds_els:
                    txt = (await el.text_content() or "").strip()
                    try:
                        odds_values.append(float(txt))
                    except ValueError:
                        pass
                if len(odds_values) >= 3:
                    fixture["odds_1"] = odds_values[0]
                    fixture["odds_x"] = odds_values[1]
                    fixture["odds_2"] = odds_values[2]

            if round_id:
                fixture["round_id"] = round_id

            fixtures.append(fixture)
            fixture_idx += 1

        return round_id, fixtures

    except Exception as e:
        print(f"❌ Error scraping betting screen: {e}")
        return None, []


async def wait_for_results(page, timeout_s: int = 180) -> bool:
    """Wait for the results screen to appear after match animation.

    Polls for .liveResult-matches-item to show up.
    Returns True when results are visible, False on timeout.
    """
    print("⏳ Waiting for match to finish...")
    try:
        await page.wait_for_selector(
            ".liveResult-matches-item",
            timeout=timeout_s * 1000,
        )
        await asyncio.sleep(1)  # let all results settle
        return True
    except Exception:
        return False


async def click_next_round(page) -> bool:
    """Click the 'Next Round' button. Returns True if found and clicked.
    
    Also handles the winning splash screen popup that may appear after
    results — it has its own 'Next Round' button in the center.
    """
    # First try to dismiss any winning splash popup
    await dismiss_win_splash(page)

    btn = await page.query_selector(
        "span[data-cms-key='next_round'], div[data-cms-key='next_round']"
    )
    if btn:
        await btn.click()
        await asyncio.sleep(2)
        return True
    return False


async def dismiss_win_splash(page) -> bool:
    """Dismiss the winning splash screen popup if present.
    
    After results, if any bet won, a popup appears with id='winngin-pop'.
    We HIDE it (don't click Next Round inside it) so we can still see 
    and scrape the results behind it.
    """
    try:
        hidden = await page.evaluate(r"""() => {
            const pop = document.querySelector('#winngin-pop');
            if (pop && pop.offsetHeight > 0) {
                pop.style.display = 'none';
                return true;
            }
            return false;
        }""")
        if hidden:
            print("  🎉 Win splash hidden (results visible now)")
            await asyncio.sleep(1)
            return True
        return False
    except Exception:
        return False


# ──────────────────────────────────────────────────────────
#  HT/FT ODDS SCRAPING
# ──────────────────────────────────────────────────────────

# The 9 HT/FT outcome labels as SportyBet displays them
HTFT_LABELS = [
    "Home/Home", "Home/Draw", "Home/Away",
    "Draw/Home", "Draw/Draw", "Draw/Away",
    "Away/Home", "Away/Draw", "Away/Away",
]

# Map SportyBet's "Home/ Home" labels → our DB keys
_LABEL_TO_KEY = {
    "Home/ Home": "home_home", "Home/ Draw": "home_draw", "Home/ Away": "home_away",
    "Draw/ Home": "draw_home", "Draw/ Draw": "draw_draw", "Draw/ Away": "draw_away",
    "Away/ Home": "away_home", "Away/ Draw": "away_draw", "Away/ Away": "away_away",
    "Home/Home": "home_home", "Home/Draw": "home_draw", "Home/Away": "home_away",
    "Draw/Home": "draw_home", "Draw/Draw": "draw_draw", "Draw/Away": "draw_away",
    "Away/Home": "away_home", "Away/Draw": "away_draw", "Away/Away": "away_away",
    "1/1": "home_home", "1/X": "home_draw", "1/2": "home_away",
    "X/1": "draw_home", "X/X": "draw_draw", "X/2": "draw_away",
    "2/1": "away_home", "2/X": "away_draw", "2/2": "away_away",
}


async def open_fixture_detail(page, fixture_idx: int) -> bool:
    """Click a fixture row on the betting screen to open its detail page.

    Returns True if navigation succeeded.
    """
    rows = await page.query_selector_all(
        ".event-list.spacer-team .event-list__main .teams-cell"
    )
    if fixture_idx >= len(rows):
        return False
    await rows[fixture_idx].click()
    await asyncio.sleep(1.5)
    # Verify we're on the detail page (it has market containers)
    detail = await page.query_selector("span[data-op='event_detail__market']")
    return detail is not None


async def go_back_to_betting(page) -> bool:
    """Click the back arrow to return to the betting list."""
    back = await page.query_selector(
        "[data-op='iv-header-back-icon'], .m-left-icon"
    )
    if back:
        await back.click()
        await asyncio.sleep(1.5)
        return True
    return False


async def scrape_htft_odds_from_detail(page) -> dict | None:
    """
    On a match detail page, scroll to the HT/FT section and extract
    the 9 outcome odds.

    DOM structure (from inspect):
      div.market
        span[data-op="event_detail__market"].text → "HT/FT"
        div.market__content
          div.m-table-row  (×3 rows, 3 outcomes each)
            div.iw-outcome.m-outcome-odds-des
              em → "Home/ Home"   (label)
              em → "4.17"         (odds)

    Returns dict with keys like 'home_home', 'away_home' etc, or None.
    """
    try:
        result = await page.evaluate(r"""() => {
            // Find the HT/FT market header
            const headers = document.querySelectorAll('span[data-op="event_detail__market"]');
            let htftHeader = null;
            for (const h of headers) {
                if ((h.textContent || '').trim().match(/^HT\s*\/\s*FT/i)) {
                    htftHeader = h;
                    break;
                }
            }
            if (!htftHeader) return null;

            // Scroll it into view
            htftHeader.scrollIntoView({ behavior: 'instant', block: 'center' });

            // Walk up to the .market container, then find .market__content
            let market = htftHeader.closest('.market');
            if (!market) return null;

            const outcomes = market.querySelectorAll('.iw-outcome');
            const odds = [];
            for (const oc of outcomes) {
                const ems = oc.querySelectorAll('em');
                if (ems.length >= 2) {
                    odds.push({
                        label: (ems[0].textContent || '').trim(),
                        value: (ems[1].textContent || '').trim(),
                    });
                }
            }
            return odds.length > 0 ? odds : null;
        }""")

        if not result:
            return None

        out = {}
        for item in result:
            key = _LABEL_TO_KEY.get(item["label"])
            if key:
                try:
                    out[key] = float(item["value"])
                except ValueError:
                    pass

        return out if out else None
    except Exception:
        return None


async def select_htft_outcome(page, selection: str) -> bool:
    """
    On a match detail page, scroll to HT/FT and click the specified outcome.

    Args:
        page: The iframe frame (on match detail page)
        selection: e.g. "Away/ Home" or "Home/ Away"

    Returns True if the outcome was found and clicked.
    """
    try:
        clicked = await page.evaluate(r"""(selection) => {
            const headers = document.querySelectorAll('span[data-op="event_detail__market"]');
            let market = null;
            for (const h of headers) {
                if ((h.textContent || '').trim().match(/^HT\s*\/\s*FT/i)) {
                    market = h.closest('.market');
                    break;
                }
            }
            if (!market) return false;

            const outcomes = market.querySelectorAll('.iw-outcome');
            for (const oc of outcomes) {
                const ems = oc.querySelectorAll('em');
                if (ems.length >= 2) {
                    const label = (ems[0].textContent || '').trim();
                    if (label === selection) {
                        oc.scrollIntoView({ behavior: 'instant', block: 'center' });
                        oc.click();
                        return true;
                    }
                }
            }
            return false;
        }""", selection)
        if clicked:
            await asyncio.sleep(0.5)
        return clicked
    except Exception:
        return False


async def click_betslip(page) -> bool:
    """Click the 'Betslip' button at the bottom."""
    btn = await page.query_selector(
        "span[data-cms-key='betslip'], span[data-op='iv-betslip-button']"
    )
    if btn:
        await btn.click()
        await asyncio.sleep(1.5)
        return True
    return False


async def click_place_bet(page) -> bool:
    """Click the 'Place Bet' button in the inline betslip.

    After selecting an outcome, the inline betslip appears at the bottom
    with a 'Place Bet' button (data-cms-key='place_bet' inside
    #quick-bet-container).
    """
    try:
        # Wait for the betslip to fully render
        for _ in range(10):
            clicked = await page.evaluate(r"""() => {
                // Search for Place Bet by data attribute
                let btn = document.querySelector('span[data-cms-key="place_bet"]');
                if (btn && btn.offsetHeight > 0) { btn.click(); return 'cms'; }

                // Search by class
                btn = document.querySelector('.place-bet:not(.bet-disabled)');
                if (btn && btn.offsetHeight > 0) { btn.click(); return 'class'; }

                // Search by text content
                const els = document.querySelectorAll('span, div, button');
                for (const el of els) {
                    const txt = (el.textContent || '').trim();
                    if (txt === 'Place Bet' && el.offsetHeight > 0 && el.children.length < 3) {
                        el.click();
                        return 'text';
                    }
                }
                return null;
            }""")
            if clicked:
                print(f"    (Place Bet found via: {clicked})")
                await asyncio.sleep(2)
                return True
            await asyncio.sleep(0.5)

        return False
    except Exception as e:
        print(f"    (Place Bet error: {e})")
        return False


async def click_confirm(page) -> bool:
    """Click the 'Confirm' button after Place Bet.

    After clicking Place Bet, the button transforms into a 'Confirm' button
    at the same location: div#confirm-btn inside #quick-bet-container.
    """
    try:
        for _ in range(10):
            # Primary: the exact element from SportyBet DOM
            btn = await page.query_selector("#confirm-btn")
            if btn:
                await btn.click(force=True)
                await asyncio.sleep(2)
                return True

            # Fallback: data-cms-key
            btn = await page.query_selector("div[data-cms-key='confirm']")
            if btn:
                await btn.click(force=True)
                await asyncio.sleep(2)
                return True

            await asyncio.sleep(0.5)

        return False
    except Exception as e:
        print(f"    (Confirm error: {e})")
        return False


async def click_kick_off(page) -> bool:
    """Click the 'Kick Off' button at the bottom right of the iframe.
    
    After confirming a bet, the Betslip button transforms into 'Kick Off'
    in the same .nav-bottom-right position.
    """
    try:
        for _ in range(15):
            # The button is in the nav-bottom-right area (where Betslip was)
            for selector in [
                ".nav-bottom-right .action-button-sub-container",
                ".nav-bottom-right span",
                ".nav-bottom-right div",
                "span[data-op='iv-betslip-button']",
                "span[data-cms-key='betslip']",
                "#kick-off-btn",
                "div[data-cms-key='kick_off']",
                "span[data-cms-key='kick_off']",
            ]:
                btn = await page.query_selector(selector)
                if btn:
                    text = (await btn.text_content() or "").strip()
                    if any(kw in text.lower() for kw in ["kick", "start", "play"]) or not text:
                        await btn.click(force=True)
                        await asyncio.sleep(2)
                        return True

            # JS fallback
            clicked = await page.evaluate(r"""() => {
                // Check nav-bottom-right first
                const right = document.querySelector('.nav-bottom-right');
                if (right && right.offsetHeight > 0) {
                    right.click();
                    return 'nav-right';
                }
                // Text search
                const els = document.querySelectorAll('span, button, div, a');
                for (const el of els) {
                    const txt = (el.textContent || '').trim();
                    if ((txt === 'Kick Off' || txt === 'KICK OFF' || txt === 'Kick off')
                        && el.offsetHeight > 0 && el.children.length < 3) {
                        el.click();
                        return txt;
                    }
                }
                return null;
            }""")
            if clicked:
                print(f"    (Kick Off found via: {clicked})")
                await asyncio.sleep(2)
                return True
            await asyncio.sleep(1)

        return False
    except Exception as e:
        print(f"    (Kick Off error: {e})")
        return False


async def click_skip_to_result(page) -> bool:
    """Click 'Skip to Result' button during the match animation.
    
    The button is in the bottom area of the iframe, same region as
    Next Round / Kick Off / Betslip.
    """
    try:
        for _ in range(15):
            # Try nav-bottom area first (where all action buttons live)
            for selector in [
                "[data-cms-key='skip_to_result']",
                "[data-cms-key='skip']",
                "[data-op*='skip']",
                ".nav-bottom-right span",
                ".nav-bottom-left span",
            ]:
                btn = await page.query_selector(selector)
                if btn:
                    text = (await btn.text_content() or "").strip()
                    if "skip" in text.lower() or "result" in text.lower():
                        await btn.click(force=True)
                        await asyncio.sleep(2)
                        return True

            # JS fallback — find small elements with exact-ish text
            clicked = await page.evaluate(r"""() => {
                const els = document.querySelectorAll('span, button, div, a');
                for (const el of els) {
                    const txt = (el.textContent || '').trim();
                    if (txt.length < 30 && txt.includes('Skip') 
                        && (txt.includes('Result') || txt.includes('result'))
                        && el.offsetHeight > 0) {
                        el.click();
                        return txt;
                    }
                }
                return null;
            }""")
            if clicked:
                print(f"    (Skip found via: {clicked})")
                await asyncio.sleep(2)
                return True
            await asyncio.sleep(1)

        return False
    except Exception as e:
        print(f"    (Skip error: {e})")
        return False


async def place_bet_on_fixture(
    page,
    fixture_idx: int,
    selection: str = "Away/ Home",
) -> dict | None:
    """
    Full bet placement flow for a single fixture:

    1. Click fixture row → match detail page
    2. Scroll to HT/FT section, scrape 9 odds
    3. Click Away/Home (or target selection)
       → inline betslip appears automatically
    4. Click Place Bet
    5. Click Confirm
    6. Return the odds data (Kick Off + Skip handled by caller)
    """
    # Step 1: Open fixture detail
    if not await open_fixture_detail(page, fixture_idx):
        print(f"  ⚠️  Could not open fixture #{fixture_idx}")
        return None

    # Step 2: Scroll to HT/FT and scrape odds
    odds = await scrape_htft_odds_from_detail(page)
    if odds:
        away_home_odds = odds.get("away_home", "?")
        print(f"  📊 HT/FT odds scraped (Away/Home: {away_home_odds})")

    # Step 3: Select the outcome
    if not await select_htft_outcome(page, selection):
        print(f"  ⚠️  Could not select '{selection}'")
        await go_back_to_betting(page)
        return odds

    print(f"  ✅ Selected: {selection}")
    await asyncio.sleep(1)

    # Step 4: Click Place Bet
    if not await click_place_bet(page):
        print("  ⚠️  Place Bet button not found")
        await go_back_to_betting(page)
        return odds
    print("  📝 Place Bet clicked")

    # Step 5: Click Confirm
    if not await click_confirm(page):
        print("  ⚠️  Confirm button not found")
    else:
        print("  ✅ Bet confirmed!")

    return odds


async def full_bet_and_kickoff(page, fixture_idx: int = 0, selection: str = "Away/ Home"):
    """
    Complete betting cycle:
    1. Place bet + confirm
    2. Kick Off
    3. Skip to Result
    4. Next Round

    Returns HT/FT odds dict or None.
    """
    odds = await place_bet_on_fixture(page, fixture_idx, selection)

    # Kick Off
    await asyncio.sleep(1)
    if await click_kick_off(page):
        print("  ⚽ Kick Off!")
    else:
        print("  ⚠️  Kick Off not found")

    # Skip to Result
    await asyncio.sleep(3)
    if await click_skip_to_result(page):
        print("  ⏭️  Skipped to result")

    return odds


async def place_strategic_bets(page, fixtures: list[dict], selection: str = "Away/ Home"):
    """Place bets on qualifying fixtures using category tabs for navigation."""
    MAX_BETS_PER_ROUND = 30  # SportyBet limit

    from collections import defaultdict as _dd
    by_category = _dd(list)
    for idx, f in enumerate(fixtures):
        if fixture_matches_strategy(f):
            by_category[f["category"]].append(f)

    total_qualifying = sum(len(v) for v in by_category.values())
    if total_qualifying == 0:
        print("  No fixtures match the strategy this round.")
        return 0

    # Cap at 30 bets — distribute evenly across ALL target categories
    if total_qualifying > MAX_BETS_PER_ROUND:
        print(f"\n  {total_qualifying} qualifying fixtures, capping at {MAX_BETS_PER_ROUND}")

        # Round-robin: take fixtures from each target category evenly
        target_cats = [c for c in by_category if c in TARGET_CATEGORIES]
        other_cats = [c for c in by_category if c not in TARGET_CATEGORIES]

        new_by_cat = _dd(list)
        remaining = MAX_BETS_PER_ROUND

        if target_cats:
            # Distribute evenly across target categories
            per_cat = max(1, remaining // len(target_cats))
            for cat in target_cats:
                take = min(per_cat, len(by_category[cat]), remaining)
                new_by_cat[cat] = by_category[cat][:take]
                remaining -= take

            # If any slots left, fill from target categories that have more
            for cat in target_cats:
                if remaining <= 0:
                    break
                extra = by_category[cat][len(new_by_cat[cat]):]
                take = min(len(extra), remaining)
                new_by_cat[cat].extend(extra[:take])
                remaining -= take

        # Fill remaining slots from non-target categories
        for cat in other_cats:
            if remaining <= 0:
                break
            take = min(len(by_category[cat]), remaining)
            new_by_cat[cat] = by_category[cat][:take]
            remaining -= take

        by_category = new_by_cat
        total_qualifying = sum(len(v) for v in by_category.values())

    print(f"\n  \U0001f3af {total_qualifying} fixtures across {len(by_category)} categories:")
    for cat, fxs in by_category.items():
        teams = ", ".join(f"{fx['home_team']}v{fx['away_team']}" for fx in fxs[:3])
        extra = f" +{len(fxs)-3}" if len(fxs) > 3 else ""
        print(f"     {cat}: {teams}{extra}")

    bets_placed = 0
    bet_num = 0

    for cat, cat_fixtures in by_category.items():
        # Click category tab at the top
        tab_clicked = await page.evaluate(r"""(catName) => {
            const tabs = document.querySelectorAll('li.sport-type-item');
            for (const tab of tabs) {
                const txt = (tab.textContent || '').trim();
                if (txt === catName) { tab.click(); return true; }
            }
            return false;
        }""", cat)

        if not tab_clicked:
            print(f"\n  \u26a0\ufe0f  Could not find tab for '{cat}'")
            continue
        await asyncio.sleep(0.8)

        for f in cat_fixtures:
            home = f["home_team"]
            away = f["away_team"]
            bet_num += 1
            print(f"\n  \U0001f4cc Bet {bet_num}/{total_qualifying}: {home} vs {away} ({cat})")

            # Find and click fixture by team names in current category
            clicked = await page.evaluate(r"""(args) => {
                const [home, away] = args;
                const cells = document.querySelectorAll('.event-list .teams-cell, .teams-info-wrap');
                for (const cell of cells) {
                    const txt = cell.textContent || '';
                    if (txt.includes(home) && txt.includes(away)) {
                        cell.scrollIntoView({ behavior: 'instant', block: 'center' });
                        cell.click();
                        return true;
                    }
                }
                return false;
            }""", [home, away])

            if not clicked:
                print(f"    \u26a0\ufe0f  Could not find fixture")
                continue
            await asyncio.sleep(1.5)

            # Verify detail page
            detail = await page.query_selector("span[data-op='event_detail__market']")
            if not detail:
                print(f"    \u26a0\ufe0f  Detail page not loaded")
                await go_back_to_betting(page)
                continue

            # Scrape HT/FT odds
            odds = await scrape_htft_odds_from_detail(page)
            if odds:
                ah_odds = odds.get('away_home')
                print(f"    \U0001f4ca Away/Home odds: {ah_odds}")
                
                # Odds filter: skip if below minimum threshold
                if ah_odds is not None and ah_odds < MIN_ODDS:
                    print(f"    \u26a0\ufe0f  Odds too low ({ah_odds} < {MIN_ODDS}), skipping")
                    await go_back_to_betting(page)
                    continue

            # Select outcome
            if not await select_htft_outcome(page, selection):
                print(f"    \u26a0\ufe0f  Could not select outcome")
                await go_back_to_betting(page)
                continue
            await asyncio.sleep(1)

            # Place Bet
            if not await click_place_bet(page):
                print(f"    \u26a0\ufe0f  Place Bet failed")
                await go_back_to_betting(page)
                continue

            # Confirm
            if await click_confirm(page):
                bets_placed += 1
                print(f"    \u2705 Bet confirmed!")
            else:
                print(f"    \u26a0\ufe0f  Confirm failed")

            # Back to betting list — may need multiple back clicks
            await go_back_to_betting(page)
            await asyncio.sleep(1)
            # Verify we're back on the betting list (league tabs visible)
            for _ in range(5):
                has_tabs = await page.query_selector("li.sport-type-item[data-op='iv-league-tabs']")
                if has_tabs:
                    break
                # Try another back click
                await go_back_to_betting(page)
                await asyncio.sleep(1)

    print(f"\n  \U0001f4b0 {bets_placed}/{total_qualifying} bets placed this round")

    # Click "Open Bets" (bottom left) to show pending bets
    await asyncio.sleep(1)
    open_bets_clicked = False

    # Try Playwright selectors with force click (bypasses badge overlay)
    for selector in [
        "[data-op='iv-main-open-bets']",
        ".nav-bottom-left .action-button-sub-container",
        ".nav-bottom-left span",
        ".nav-bottom-left",
    ]:
        btn = await page.query_selector(selector)
        if btn:
            try:
                await btn.click(force=True)
                open_bets_clicked = True
                print(f"  \U0001f4cb Open Bets clicked ({selector})")
                await asyncio.sleep(2)
                break
            except Exception:
                continue

    if not open_bets_clicked:
        # JS fallback with more aggressive targeting
        result = await page.evaluate(r"""() => {
            // Find the Open Bets text element and force click its parent
            const els = document.querySelectorAll('span, div');
            for (const el of els) {
                const txt = (el.textContent || '').trim();
                if (txt.startsWith('Open Bets') && el.offsetHeight > 0) {
                    // Click the element itself
                    el.click();
                    // Also try dispatching a proper click event
                    el.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                    return txt;
                }
            }
            // Try the action button container in nav-bottom-left
            const container = document.querySelector('.nav-bottom-left .action-button-sub-container');
            if (container) {
                container.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                return 'container-dispatch';
            }
            return null;
        }""")
        if result:
            open_bets_clicked = True
            print(f"  \U0001f4cb Open Bets clicked (JS: {result})")
            await asyncio.sleep(2)

    if not open_bets_clicked:
        print("  \u26a0\ufe0f  Open Bets not found")

    # Now Kick Off should appear (bottom right)
    await asyncio.sleep(1)
    if await click_kick_off(page):
        print("  \u26bd Kick Off!")
    else:
        print("  \u26a0\ufe0f  Kick Off not found, trying Next Round...")
        await click_next_round(page)

    # Skip to Result
    await asyncio.sleep(3)
    if await click_skip_to_result(page):
        print("  \u23ed\ufe0f  Skipped to result")

    return bets_placed


# ──────────────────────────────────────────────────────────
#  ERROR RECOVERY + SESSION MONITORING
# ──────────────────────────────────────────────────────────

async def recover_iframe(page: Page):
    """Re-locate the iframe after a page reload or navigation error.

    Returns the iframe Frame, or the page itself as fallback.
    """
    for _ in range(15):
        iframe_el = await page.query_selector(
            "iframe#instantwin-sport, iframe[src*='instant-virtuals'], "
            "iframe[src*='sporty-instant']"
        )
        if iframe_el:
            frame = await iframe_el.content_frame()
            if frame:
                try:
                    await frame.wait_for_load_state("domcontentloaded")
                except Exception:
                    pass
                await asyncio.sleep(1)
                return frame
        await asyncio.sleep(1)
    return page


async def check_session_alive(page: Page, target) -> bool:
    """Check if the session is still active.

    Detects common signs of session expiry:
    - Login popup appeared
    - Page shows 'Data Failed loading'
    - iframe disappeared or became empty
    """
    try:
        # Check outer page for login prompts
        login_visible = await page.evaluate("""() => {
            const el = document.querySelector('#loginStep');
            if (el && el.offsetHeight > 0) return true;
            const popup = document.querySelector('.m-dialog-main');
            if (popup) {
                const txt = popup.textContent || '';
                if (txt.includes('log in') || txt.includes('Login') || txt.includes('session'))
                    return true;
            }
            return false;
        }""")
        if login_visible:
            return False

        # Check if iframe content is still loaded
        screen = await detect_screen(target)
        if screen == "unknown":
            # Might be a transient state — wait a bit and recheck
            await asyncio.sleep(3)
            screen = await detect_screen(target)
            if screen == "unknown":
                return False

        return True
    except Exception:
        return False


async def handle_session_expired(page: Page) -> bool:
    """Handle a detected session expiry.

    Waits for the user to re-login, then returns True when session is restored.
    Returns False if user doesn't re-login within the timeout.
    """
    print("\n" + "!" * 50)
    print("⚠️  SESSION EXPIRED — Please log in again in the browser.")
    print("!" * 50)

    for _ in range(200):  # ~10 min
        await asyncio.sleep(3)
        if await _check_logged_in(page):
            print("✅ Session restored!")
            await page.goto(
                SPORTYBET_VIRTUALS_URL,
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(3)
            return True
    print("❌ Re-login timed out.")
    return False


async def safe_scrape_round(target, retries: int = 3) -> tuple[str | None, list[dict]]:
    """Scrape round results with retry logic.

    Retries on failure with short delays.
    """
    for attempt in range(1, retries + 1):
        round_id, matches = await scrape_round_results(target)
        if matches:
            return round_id, matches
        if attempt < retries:
            wait = attempt * 2
            print(f"  ⚠️  Scrape attempt {attempt}/{retries} got 0 matches, "
                  f"retrying in {wait}s...")
            await asyncio.sleep(wait)
    return round_id, matches


async def manual_entry_mode(conn, round_id: str) -> list[dict]:
    """
    Fallback: let the user manually enter results if auto-scraping fails.
    Useful for initial data collection while we figure out the DOM.
    """
    print("\n📝 MANUAL ENTRY MODE")
    print("Enter match results in this format:")
    print("  category | home_team | away_team | ht_home | ht_away | ft_home | ft_away")
    print("Example:")
    print("  England | Arsenal | Chelsea | 0 | 1 | 2 | 1")
    print("Type 'done' when finished, 'skip' to skip this round.\n")

    matches = []
    while True:
        line = input("> ").strip()
        if line.lower() == "done":
            break
        if line.lower() == "skip":
            return []

        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 7:
            print("  ❌ Need exactly 7 fields separated by |. Try again.")
            continue

        try:
            matches.append({
                "round_id": round_id,
                "category": parts[0],
                "home_team": parts[1],
                "away_team": parts[2],
                "ht_home_goals": int(parts[3]),
                "ht_away_goals": int(parts[4]),
                "ft_home_goals": int(parts[5]),
                "ft_away_goals": int(parts[6]),
            })
            print(f"  ✓ Added: {parts[1]} vs {parts[2]}")
        except ValueError:
            print("  ❌ Goals must be numbers. Try again.")

    return matches


async def run_scraper(rounds: int = 0, headless: bool = False, manual: bool = False,
                      place_bets: bool = False) -> None:
    """
    Main scraping loop — handles the full round lifecycle:

    1. Detect current screen (betting / live / results)
    2. On BETTING screen:
       - If place_bets: click fixture → scroll to HT/FT → select Away/Home →
         Place Bet → Kick Off
       - Otherwise: just scrape fixtures and click Next Round
    3. On RESULTS screen: scrape all match results across categories
    4. Click "Next Round" and repeat

    Includes error recovery, session expiry detection, and retry logic.
    """
    conn = get_connection()
    init_db(conn)

    if manual:
        await _run_manual_loop(conn, rounds)
        conn.close()
        return

    pw, context, page = await launch_browser(headless=headless)

    try:
        target = await wait_for_login(page)
        consecutive_errors = 0

        # Initial strategy learning from existing data
        print("\n  📚 Loading strategy from historical data...")
        report = learn_from_data(conn)
        print_learning_report(report)

        rounds_scraped = 0
        while rounds == 0 or rounds_scraped < rounds:
            # ── Periodic re-learning ─────────────────────────────
            if rounds_scraped > 0 and rounds_scraped % LEARN_INTERVAL == 0:
                print("\n  📚 Re-learning strategy from updated data...")
                report = learn_from_data(conn)
                print_learning_report(report)

            print(f"\n{'─' * 50}")
            print(f"Round cycle #{rounds_scraped + 1}")

            # ── Session health check ─────────────────────────────
            try:
                session_ok = await check_session_alive(page, target)
            except Exception:
                session_ok = False
            if not session_ok:
                if not await handle_session_expired(page):
                    print("Cannot continue without login. Stopping.")
                    break
                target = await recover_iframe(page)
                continue

            # ── Detect which screen we're on ─────────────────────
            try:
                screen = await detect_screen(target)
            except Exception:
                print("⚠️  Lost connection to page, recovering...")
                target = await recover_iframe(page)
                continue
            print(f"📍 Screen: {screen}")

            # ── BETTING screen: place bet + start round ─────────
            if screen == "betting":
                round_id, fixtures = await scrape_betting_screen(target)
                if fixtures:
                    print(f"📋 Pre-match: {len(fixtures)} fixtures scraped")
                    for f in fixtures[:3]:
                        odds = f"{f['odds_1']}/{f['odds_x']}/{f['odds_2']}"
                        print(f"   {f['category']}: {f['home_team']} vs {f['away_team']}  [{odds}]")
                    if len(fixtures) > 3:
                        print(f"   ... and {len(fixtures) - 3} more")

                    if place_bets:
                        # Strategic multi-fixture betting:
                        # Bet Away/Home on all fixtures matching our strategy
                        # (target categories + jackpot-prone teams)
                        bets = await place_strategic_bets(
                            target, fixtures, selection="Away/ Home"
                        )
                    else:
                        # Observe mode — place 1 bet to trigger the full flow
                        # (SportyBet requires a bet to show results)
                        print("\n  📡 Observe mode — placing 1 min bet...")
                        
                        # Open first fixture
                        if await open_fixture_detail(target, 0):
                            # Select Away/Home
                            await select_htft_outcome(target, "Away/ Home")
                            await asyncio.sleep(1)
                            # Place Bet
                            if await click_place_bet(target):
                                print("  📝 Place Bet clicked")
                                # Confirm
                                if await click_confirm(target):
                                    print("  ✅ Bet confirmed!")
                            
                            # Go back to betting list
                            await go_back_to_betting(target)
                            await asyncio.sleep(1)
                        
                        # Now click Open Bets → Kick Off → Skip
                        # Open Bets (bottom left)
                        for selector in [
                            "[data-op='iv-main-open-bets']",
                            ".nav-bottom-left .action-button-sub-container",
                            ".nav-bottom-left span",
                            ".nav-bottom-left",
                        ]:
                            btn = await target.query_selector(selector)
                            if btn:
                                await btn.click(force=True)
                                print("  📋 Open Bets clicked")
                                await asyncio.sleep(2)
                                break

                        # Kick Off (bottom right)
                        if await click_kick_off(target):
                            print("  ⚽ Kick Off!")
                        
                        # Skip to Result
                        await asyncio.sleep(3)
                        if await click_skip_to_result(target):
                            print("  ⏭️  Skipped to result")
                else:
                    print("⚠️  Could not scrape betting screen fixtures.")
                    if await click_next_round(target):
                        print("⏭️  'Next Round' clicked — match starting...")
                    else:
                        print("Press Enter when the match starts...")
                        await asyncio.get_event_loop().run_in_executor(None, input)

                # Re-acquire iframe (Next Round navigates the iframe to /live/)
                await asyncio.sleep(3)
                target = await recover_iframe(page)

                # Wait for results
                if not await wait_for_results(target, timeout_s=180):
                    target = await recover_iframe(page)
                    if not await wait_for_results(target, timeout_s=60):
                        print("⏳ Results not detected. Press Enter when visible...")
                        await asyncio.get_event_loop().run_in_executor(None, input)
                        target = await recover_iframe(page)

                screen = await detect_screen(target)

            # ── LIVE screen: wait for results ────────────────────
            elif screen == "live":
                if not await wait_for_results(target, timeout_s=180):
                    target = await recover_iframe(page)
                    if not await wait_for_results(target, timeout_s=60):
                        print("⏳ Results not detected. Press Enter when visible...")
                        await asyncio.get_event_loop().run_in_executor(None, input)
                screen = await detect_screen(target)

            # ── RESULTS screen: scrape all match results ─────────
            if screen == "results":
                round_id, matches = await safe_scrape_round(target, retries=3)

                if not matches:
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        print("❌ Too many consecutive failures. Stopping.")
                        break
                    print("No matches found via auto-scrape.")
                    choice = input("'m' manual, 'r' retry, 'q' quit: ").strip().lower()
                    if choice == "m":
                        if round_id is None:
                            round_id = f"R{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                        matches = await manual_entry_mode(conn, round_id)
                    elif choice == "q":
                        break
                    else:
                        continue

                if not matches:
                    continue

                consecutive_errors = 0  # reset on success

                if round_exists(conn, round_id):
                    print(f"Round {round_id} already scraped, skipping.")
                else:
                    insert_round(conn, round_id)
                    count = insert_matches_bulk(conn, matches)
                    jackpots = sum(1 for m in matches if _is_jackpot(m))

                    print(f"✅ Round {round_id} | {count} matches stored | {jackpots} jackpot(s)")

                    stats = get_total_stats(conn)
                    print(f"   📊 Total: {stats['total_rounds']} rounds, "
                          f"{stats['total_matches']} matches, "
                          f"{stats['total_jackpots']} jackpots "
                          f"({stats['jackpot_rate']:.2%})")

                rounds_scraped += 1

                # Advance to next round
                if rounds == 0 or rounds_scraped < rounds:
                    if await click_next_round(target):
                        print("⏭️  'Next Round' clicked...")
                        await asyncio.sleep(3)
                    else:
                        print("Press Enter when the next betting screen is visible...")
                        await asyncio.get_event_loop().run_in_executor(None, input)

            elif screen == "unknown":
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    print("❌ Too many consecutive failures. Stopping.")
                    break
                print(f"⚠️  Unknown screen state, attempting recovery...")
                try:
                    await page.goto(
                        SPORTYBET_VIRTUALS_URL,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                    await asyncio.sleep(3)
                    target = await recover_iframe(page)
                except Exception as e:
                    print(f"  Recovery failed: {e}")
                    await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user.")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    finally:
        stats = get_total_stats(conn)
        print(f"\n{'=' * 50}")
        print(f"SESSION SUMMARY")
        print(f"  Rounds: {stats['total_rounds']}")
        print(f"  Matches: {stats['total_matches']}")
        print(f"  Jackpots (Away/Home): {stats['total_jackpots']}")
        print(f"  Jackpot rate: {stats['jackpot_rate']:.2%}")
        print(f"{'=' * 50}\n")

        conn.close()
        await context.close()
        await pw.stop()


async def _run_manual_loop(conn, rounds: int) -> None:
    """Run manual entry loop without browser."""
    print("\n" + "=" * 60)
    print("SPORTYBET VIRTUAL SOCCER — MANUAL DATA ENTRY")
    print("=" * 60)
    print("Enter results as you see them on screen.\n")

    rounds_entered = 0
    while rounds == 0 or rounds_entered < rounds:
        round_id = input(f"\nRound ID (or press Enter for auto, 'q' to quit): ").strip()
        if round_id.lower() == "q":
            break
        if not round_id:
            round_id = f"R{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        if round_exists(conn, round_id):
            print(f"Round {round_id} already exists, skipping.")
            continue

        matches = await manual_entry_mode(conn, round_id)
        if not matches:
            continue

        insert_round(conn, round_id)
        count = insert_matches_bulk(conn, matches)
        jackpots = sum(1 for m in matches if _is_jackpot(m))

        print(f"\n✅ Round {round_id} | {count} matches | {jackpots} jackpot(s)")

        stats = get_total_stats(conn)
        print(f"   📊 Total: {stats['total_rounds']} rounds, "
              f"{stats['total_matches']} matches, "
              f"{stats['total_jackpots']} jackpots "
              f"({stats['jackpot_rate']:.2%})")

        rounds_entered += 1


def _is_jackpot(match: dict) -> bool:
    """Check if a match dict represents an Away/Home jackpot."""
    from src.db import derive_htft
    htft = derive_htft(
        match["ht_home_goals"], match["ht_away_goals"],
        match["ft_home_goals"], match["ft_away_goals"],
    )
    return htft == "Away/Home"


async def auto_inspect(target, outer_page=None) -> dict:
    """
    Automatically analyse the current page/frame DOM to discover selectors
    for virtual‑soccer results.  Saves screenshot + HTML dump + a
    JSON report to data/.

    Args:
        target: Page or Frame to analyse.
        outer_page: If target is a Frame, pass the outer Page for screenshots.

    Returns the analysis dict so the caller can display it.
    """
    import json

    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Screenshot (frames can't screenshot — use outer page)
    screenshot_src = outer_page if outer_page else target
    ss_path = data_dir / f"inspect_{ts}.png"
    await screenshot_src.screenshot(path=str(ss_path), full_page=True)
    print(f"📸  Screenshot  → {ss_path}")

    # 2. Full HTML dump
    html_path = data_dir / f"inspect_{ts}.html"
    html_content = await target.content()
    html_path.write_text(html_content, encoding="utf-8")
    print(f"📄  HTML dump   → {html_path}")

    # 3. Deep JS‑based DOM analysis
    analysis = await target.evaluate(r"""() => {
        /* ── helpers ─────────────────────────────────────────── */
        const uniq = arr => [...new Set(arr)];
        const text = el => (el.textContent || '').trim();
        const tag  = el => el.tagName.toLowerCase();
        const cls  = el => [...(el.classList || [])];
        const attrs = el => {
            const out = {};
            for (const a of el.attributes || [])
                if (a.name.startsWith('data-') || a.name === 'id' || a.name === 'class' || a.name === 'role')
                    out[a.name] = a.value;
            return out;
        };
        const path = el => {
            const parts = [];
            while (el && el !== document.body) {
                let s = tag(el);
                if (el.id) s += '#' + el.id;
                else if (el.classList.length) s += '.' + [...el.classList].join('.');
                parts.unshift(s);
                el = el.parentElement;
            }
            return parts.join(' > ');
        };

        /* ── 1. Catalogue *all* unique class names & data attrs ─ */
        const allClasses = new Set();
        const allDataAttrs = new Set();
        const allIds = new Set();
        document.querySelectorAll('*').forEach(el => {
            cls(el).forEach(c => allClasses.add(c));
            for (const a of el.attributes || []) {
                if (a.name.startsWith('data-')) allDataAttrs.add(a.name + '=' + a.value.slice(0,60));
                if (a.name === 'id') allIds.add(a.value);
            }
        });

        /* ── 2. Find elements whose text looks like a score ───── */
        const scorePattern = /\b\d+\s*[-:]\s*\d+\b/;
        const htftPattern  = /\(?\d+\)?\s*[-:]\s*\(?\d+\)?/;
        const scoreEls = [];
        document.querySelectorAll('*').forEach(el => {
            // only leaf‑ish elements (no huge parents)
            if (el.children.length > 10) return;
            const t = text(el);
            if (t.length > 0 && t.length < 200 && scorePattern.test(t)) {
                scoreEls.push({
                    path: path(el),
                    tag: tag(el),
                    attrs: attrs(el),
                    text: t.slice(0, 150),
                });
            }
        });

        /* ── 3. Find elements that look like team/league names ── */
        const teamKeywords = [
            'arsenal','chelsea','liverpool','manchester','tottenham','barcelona',
            'real madrid','bayern','dortmund','juventus','milan','inter','napoli',
            'psg','ajax','benfica','porto','celtic','rangers','al ahly',
            'england','spain','germany','champions','italy','african','euros',
            'club world','premier','la liga','bundesliga','serie a',
        ];
        const teamEls = [];
        document.querySelectorAll('*').forEach(el => {
            if (el.children.length > 5) return;
            const t = text(el).toLowerCase();
            if (t.length > 2 && t.length < 100) {
                for (const kw of teamKeywords) {
                    if (t.includes(kw)) {
                        teamEls.push({
                            path: path(el),
                            tag: tag(el),
                            attrs: attrs(el),
                            text: text(el).slice(0, 100),
                            keyword: kw,
                        });
                        break;
                    }
                }
            }
        });

        /* ── 4. Find likely "round" / "matchday" indicators ───── */
        const roundKeywords = ['round','matchday','match day','week','md ','rd ','game','fixture'];
        const roundEls = [];
        document.querySelectorAll('*').forEach(el => {
            if (el.children.length > 5) return;
            const t = text(el).toLowerCase();
            if (t.length > 2 && t.length < 100) {
                for (const kw of roundKeywords) {
                    if (t.includes(kw)) {
                        roundEls.push({
                            path: path(el),
                            tag: tag(el),
                            attrs: attrs(el),
                            text: text(el).slice(0, 100),
                        });
                        break;
                    }
                }
            }
        });

        /* ── 5. Find iframes (content may be inside one) ──────── */
        const iframes = [...document.querySelectorAll('iframe')].map(f => ({
            src: f.src,
            id: f.id,
            class: f.className,
            width: f.width,
            height: f.height,
        }));

        /* ── 6. Class names containing suggestive substrings ──── */
        const interesting = [
            'result','score','team','match','fixture','league','category',
            'tournament','round','half','ht','ft','goal','virtual','soccer',
            'football','event','odds','market','outcome','game','table',
            'row','cell','home','away','draw','live','instant',
        ];
        const interestingClasses = {};
        for (const kw of interesting) {
            const hits = [...allClasses].filter(c => c.toLowerCase().includes(kw));
            if (hits.length) interestingClasses[kw] = hits;
        }

        /* ── 7. Walk main visible container looking for tables ── */
        const tables = [...document.querySelectorAll('table')].map(t => ({
            path: path(t),
            rows: t.rows.length,
            firstRowText: t.rows[0] ? text(t.rows[0]).slice(0, 200) : '',
            attrs: attrs(t),
        }));

        /* ── 8. Visible text dump (first 5000 chars of body) ──── */
        const bodyText = text(document.body).slice(0, 5000);

        return {
            url: location.href,
            title: document.title,
            totalElements: document.querySelectorAll('*').length,
            uniqueClassCount: allClasses.size,
            iframes,
            tables,
            interestingClasses,
            scoreElements: scoreEls.slice(0, 50),
            teamElements:  teamEls.slice(0, 50),
            roundElements: roundEls.slice(0, 20),
            sampleIds:     [...allIds].slice(0, 50),
            sampleDataAttrs: [...allDataAttrs].slice(0, 80),
            bodyTextPreview: bodyText,
        };
    }""")

    # 4. Save analysis JSON
    report_path = data_dir / f"inspect_{ts}.json"
    report_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"🔍  Analysis    → {report_path}")

    # 5. Pretty‑print summary
    print(f"\n{'═' * 60}")
    print(f"  PAGE: {analysis.get('url')}")
    print(f"  TITLE: {analysis.get('title')}")
    print(f"  Elements: {analysis.get('totalElements')} | Unique classes: {analysis.get('uniqueClassCount')}")
    print(f"{'═' * 60}")

    if analysis.get("iframes"):
        print(f"\n📦 IFRAMES ({len(analysis['iframes'])}):")
        for f in analysis["iframes"]:
            print(f"   src={f.get('src','')[:120]}  id={f.get('id','')}  class={f.get('class','')}")

    if analysis.get("tables"):
        print(f"\n📊 TABLES ({len(analysis['tables'])}):")
        for t in analysis["tables"]:
            print(f"   rows={t['rows']}  path={t['path'][:100]}")
            if t["firstRowText"]:
                print(f"        first row: {t['firstRowText'][:120]}")

    if analysis.get("interestingClasses"):
        print(f"\n🏷️  INTERESTING CSS CLASSES:")
        for kw, classes in sorted(analysis["interestingClasses"].items()):
            print(f"   {kw}: {', '.join(classes[:8])}")

    if analysis.get("scoreElements"):
        print(f"\n⚽ SCORE‑LIKE ELEMENTS ({len(analysis['scoreElements'])}):")
        for s in analysis["scoreElements"][:15]:
            print(f"   [{s['tag']}] {s['text'][:80]}")
            print(f"        path: {s['path'][:100]}")

    if analysis.get("teamElements"):
        print(f"\n👕 TEAM/LEAGUE ELEMENTS ({len(analysis['teamElements'])}):")
        for t in analysis["teamElements"][:15]:
            print(f"   [{t['tag']}] {t['text'][:80]}  (kw: {t['keyword']})")
            print(f"        path: {t['path'][:100]}")

    if analysis.get("roundElements"):
        print(f"\n🔄 ROUND/MATCHDAY ELEMENTS ({len(analysis['roundElements'])}):")
        for r in analysis["roundElements"][:10]:
            print(f"   [{r['tag']}] {r['text'][:80]}")
            print(f"        path: {r['path'][:100]}")

    if analysis.get("sampleDataAttrs"):
        print(f"\n📌 DATA ATTRIBUTES (sample):")
        for a in analysis["sampleDataAttrs"][:20]:
            print(f"   {a}")

    print(f"\n📝 BODY TEXT PREVIEW (first 800 chars):")
    preview = analysis.get("bodyTextPreview", "")[:800]
    print(preview)

    print(f"\n{'═' * 60}")
    print("Files saved in data/.  Examine the HTML dump & screenshot")
    print("for further detail, then update selectors in bot.py.")
    print(f"{'═' * 60}\n")

    return analysis


async def inspect_page(target, outer_page=None) -> None:
    """Interactive inspection mode: examine the page/frame to find correct selectors."""
    # outer_page is used for screenshots when target is a Frame
    screenshot_src = outer_page if outer_page else target

    # Run automatic analysis first
    print("\n🔍 Running automatic DOM analysis...\n")
    await auto_inspect(target, outer_page=outer_page)

    print("\n🔍 INTERACTIVE INSPECT MODE")
    print("Commands:")
    print("  screenshot          — Take a screenshot")
    print("  dump                — Save full page HTML")
    print("  select <css>        — Query selector and show text")
    print("  selectall <css>     — Query all matching selectors")
    print("  eval <js>           — Run JavaScript in page")
    print("  reanalyze           — Re-run automatic DOM analysis")
    print("  quit                — Exit inspect mode\n")

    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    while True:
        cmd = input("inspect> ").strip()
        if not cmd:
            continue

        if cmd == "quit":
            break
        elif cmd == "reanalyze":
            await auto_inspect(target, outer_page=outer_page)
        elif cmd == "screenshot":
            path = data_dir / f"inspect_{datetime.now().strftime('%H%M%S')}.png"
            await screenshot_src.screenshot(path=str(path), full_page=True)
            print(f"  Saved: {path}")
        elif cmd == "dump":
            path = data_dir / f"inspect_{datetime.now().strftime('%H%M%S')}.html"
            path.write_text(await target.content(), encoding="utf-8")
            print(f"  Saved: {path}")
        elif cmd.startswith("select "):
            selector = cmd[7:].strip()
            try:
                el = await target.query_selector(selector)
                if el:
                    text = await el.text_content()
                    print(f"  Found: {text[:200] if text else '(empty)'}")
                else:
                    print("  Not found.")
            except Exception as e:
                print(f"  Error: {e}")
        elif cmd.startswith("selectall "):
            selector = cmd[10:].strip()
            try:
                els = await target.query_selector_all(selector)
                print(f"  Found {len(els)} elements:")
                for i, el in enumerate(els[:20]):
                    text = await el.text_content()
                    print(f"    [{i}] {text[:100] if text else '(empty)'}")
            except Exception as e:
                print(f"  Error: {e}")
        elif cmd.startswith("eval "):
            js = cmd[5:].strip()
            try:
                result = await target.evaluate(js)
                print(f"  Result: {result}")
            except Exception as e:
                print(f"  Error: {e}")
        else:
            print("  Unknown command.")


def main():
    parser = argparse.ArgumentParser(
        description="SportyBet Virtual Soccer Result Scraper — HT/FT Data Collection"
    )
    parser.add_argument(
        "--rounds", type=int, default=0,
        help="Number of rounds to scrape (0 = run until stopped, default: 0)"
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run browser in headless mode (not recommended for first run)"
    )
    parser.add_argument(
        "--manual", action="store_true",
        help="Manual data entry mode (no browser, type results yourself)"
    )
    parser.add_argument(
        "--bet", action="store_true",
        help="Place bets on Away/Home each round (requires login + balance)"
    )
    parser.add_argument(
        "--inspect", action="store_true",
        help="Launch browser in inspect mode to examine page DOM"
    )
    args = parser.parse_args()

    if args.inspect:
        asyncio.run(_inspect_mode())
    else:
        asyncio.run(run_scraper(
            rounds=args.rounds,
            headless=args.headless,
            manual=args.manual,
            place_bets=args.bet,
        ))


async def _inspect_mode():
    """Run the interactive page inspector.

    Captures multiple screens of the round lifecycle:
    1. Results screen (after a round finishes)
    2. Betting/pre-match screen (after clicking Next Round)
    3. Live/animation screen (while match is playing)
    """
    pw, context, page = await launch_browser(headless=False, persistent=False)
    try:
        await page.goto(SPORTYBET_VIRTUALS_URL, wait_until="domcontentloaded", timeout=30000)
        print("Browser launched.")
        print("Wait for a round to finish so results are showing, then come back.")
        input("Press Enter when the RESULTS screen is visible...")

        # Find the iframe
        iframe_el = await page.query_selector(
            "iframe#instantwin-sport, iframe[src*='instant-virtuals'], "
            "iframe[src*='sporty-instant']"
        )
        target = page
        if iframe_el:
            frame = await iframe_el.content_frame()
            if frame:
                print("🖼️  Found iframe — analysing content inside it.")
                await frame.wait_for_load_state("domcontentloaded")
                await asyncio.sleep(2)
                target = frame

        # ── Screen 1: Results screen ──────────────────────────
        print("\n" + "=" * 60)
        print("  SCREEN 1: RESULTS")
        print("=" * 60)
        analysis_results = await auto_inspect(target, outer_page=page if target != page else None)

        # ── Screen 2: Click "Next Round" to see the betting screen ─
        print("\n📍 Now clicking 'Next Round' to capture the BETTING screen...")
        next_btn = await target.query_selector(
            "div[data-cms-key='next_round'], .btn-right"
        )
        if next_btn:
            await next_btn.click()
            await asyncio.sleep(3)  # wait for betting screen to load

            print("\n" + "=" * 60)
            print("  SCREEN 2: BETTING / PRE-MATCH")
            print("=" * 60)
            analysis_betting = await auto_inspect(target, outer_page=page if target != page else None)

            # ── Screen 3: Wait for match to start playing ─────────
            print("\nWaiting for the match animation to start...")
            print("(This might take a moment — the countdown needs to finish)")
            input("Press Enter when the match is PLAYING or FINISHED to capture that screen too,\nor type 'skip' to go straight to interactive mode: ")

            cmd = ""  # already consumed by input above
            print("\n" + "=" * 60)
            print("  SCREEN 3: LIVE / ANIMATION")
            print("=" * 60)
            analysis_live = await auto_inspect(target, outer_page=page if target != page else None)
        else:
            print("⚠️  'Next Round' button not found. Are you on the results screen?")

        # ── Interactive mode for further exploration ───────────
        outer = page if target != page else None
        await inspect_page(target, outer_page=outer)
    finally:
        await context.close()
        await pw.stop()


if __name__ == "__main__":
    main()
