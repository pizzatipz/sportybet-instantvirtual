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
    round_exists, get_total_stats, CATEGORIES,
)

# Persistent browser profile directory
PROFILE_DIR = Path(__file__).parent.parent / "data" / "browser_profile"

# SportyBet virtual soccer URL (adjust if needed)
SPORTYBET_VIRTUALS_URL = "https://www.sportybet.com/ng/virtual"


async def launch_browser(headless: bool = False) -> tuple:
    """Launch browser with persistent profile for session reuse."""
    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return pw, context, page


async def wait_for_login(page: Page) -> None:
    """Navigate to SportyBet and wait for user to log in manually."""
    print("\n" + "=" * 60)
    print("SPORTYBET VIRTUAL SOCCER — RESULT SCRAPER")
    print("=" * 60)

    await page.goto(SPORTYBET_VIRTUALS_URL, wait_until="domcontentloaded", timeout=30000)
    print("\n1. Please log in to SportyBet if not already logged in.")
    print("2. Navigate to Instant Virtual Soccer.")
    print("3. Find the HT/FT results display.")
    print("\nPress Enter when you're on the results page...")
    await asyncio.get_event_loop().run_in_executor(None, input)
    print("Ready to scrape!\n")


async def scrape_round_results(page: Page) -> tuple[str | None, list[dict]]:
    """
    Scrape all match results from the current results screen.

    This is the core scraping function. It needs to be adapted to SportyBet's
    actual DOM structure. The function is written with generic selectors that
    should be updated based on the actual page structure.

    Returns:
        (round_id, list of match dicts) or (None, []) if scraping fails.

    Each match dict contains:
        round_id, category, home_team, away_team,
        ht_home_goals, ht_away_goals, ft_home_goals, ft_away_goals
    """
    matches = []

    # ──────────────────────────────────────────────────────────────
    # IMPORTANT: The selectors below are PLACEHOLDERS.
    # When you first run the bot, use --inspect mode to examine
    # the actual DOM structure and update these selectors.
    # ──────────────────────────────────────────────────────────────

    # Strategy: Take a screenshot and dump page content so we can
    # identify the correct selectors.
    try:
        # Try to find the round ID from the page
        round_id = None
        round_el = await page.query_selector("[class*='round'], [class*='Round'], [class*='matchday'], [data-round]")
        if round_el:
            round_text = await round_el.text_content()
            if round_text:
                # Extract numeric round ID
                nums = re.findall(r'\d+', round_text)
                if nums:
                    round_id = f"R{nums[0]}"

        if not round_id:
            # Fallback: use timestamp as round ID
            round_id = f"R{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        # Take a diagnostic screenshot on first run
        screenshot_path = Path(__file__).parent.parent / "data" / "page_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)

        # Dump the page HTML for selector analysis
        html_path = Path(__file__).parent.parent / "data" / "page_dump.html"
        content = await page.content()
        html_path.write_text(content, encoding="utf-8")

        print(f"📸 Screenshot saved to: {screenshot_path}")
        print(f"📄 Page HTML saved to: {html_path}")
        print("   → Examine these files to identify the correct DOM selectors.")
        print("   → Then update scrape_round_results() in bot.py.\n")

        # ──────────────────────────────────────────────────────────
        # GENERIC SCRAPING ATTEMPT
        # Try multiple common patterns for virtual sports results
        # ──────────────────────────────────────────────────────────

        # Pattern 1: Look for category/league sections with match rows
        category_sections = await page.query_selector_all(
            "[class*='league'], [class*='League'], [class*='category'], "
            "[class*='Category'], [class*='tournament'], [class*='group']"
        )

        if category_sections:
            print(f"Found {len(category_sections)} category sections.")
            for section in category_sections:
                category_name = await _extract_category_name(section)
                match_rows = await section.query_selector_all(
                    "[class*='match'], [class*='Match'], [class*='event'], "
                    "[class*='fixture'], [class*='result'], tr"
                )
                for row in match_rows:
                    match_data = await _extract_match_from_row(row, category_name, round_id)
                    if match_data:
                        matches.append(match_data)

        # Pattern 2: Flat list of results with category labels
        if not matches:
            result_rows = await page.query_selector_all(
                "[class*='result-row'], [class*='ResultRow'], "
                "[class*='match-result'], [class*='MatchResult']"
            )
            if result_rows:
                print(f"Found {len(result_rows)} result rows (flat layout).")
                for row in result_rows:
                    match_data = await _extract_match_from_row(row, "Unknown", round_id)
                    if match_data:
                        matches.append(match_data)

        if not matches:
            print("⚠️  Could not automatically scrape results.")
            print("   Please examine the screenshot and HTML dump,")
            print("   then update the selectors in bot.py.")

        return round_id, matches

    except Exception as e:
        print(f"❌ Error scraping results: {e}")
        return None, []


async def _extract_category_name(section) -> str:
    """Try to extract the category/league name from a section element."""
    # Try header/title elements within section
    for sel in ["h2", "h3", "h4", "[class*='title']", "[class*='name']", "[class*='header']"]:
        el = await section.query_selector(sel)
        if el:
            text = await el.text_content()
            if text:
                text = text.strip()
                # Try to match against known categories
                for cat in CATEGORIES:
                    if cat.lower() in text.lower():
                        return cat
                return text
    return "Unknown"


async def _extract_match_from_row(row, category: str, round_id: str) -> dict | None:
    """Try to extract match data from a result row element."""
    try:
        text = await row.text_content()
        if not text or len(text.strip()) < 5:
            return None

        # Try to find team names and scores
        # Common patterns: "Team A 2 - 1 Team B" or "Team A 2:1 Team B"
        # With HT score sometimes in parentheses: "Team A 2(1) - 1(0) Team B"

        # Look for score elements
        scores = re.findall(r'(\d+)\s*[-:]\s*(\d+)', text)

        # Look for team name elements
        team_els = await row.query_selector_all(
            "[class*='team'], [class*='Team'], [class*='name'], [class*='Name']"
        )
        teams = []
        for el in team_els:
            t = await el.text_content()
            if t and t.strip():
                teams.append(t.strip())

        if len(teams) >= 2 and len(scores) >= 1:
            home_team = teams[0]
            away_team = teams[1] if len(teams) > 1 else teams[-1]

            if len(scores) >= 2:
                # First score is likely HT, second is FT
                ht_home, ht_away = int(scores[0][0]), int(scores[0][1])
                ft_home, ft_away = int(scores[1][0]), int(scores[1][1])
            else:
                # Only FT score available — can't derive HT/FT
                # Skip this match for HT/FT analysis
                return None

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

        return None
    except Exception:
        return None


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


async def run_scraper(rounds: int = 0, headless: bool = False, manual: bool = False) -> None:
    """
    Main scraping loop.

    Args:
        rounds: Number of rounds to scrape (0 = run indefinitely)
        headless: Run browser in headless mode
        manual: Use manual entry mode instead of auto-scraping
    """
    conn = get_connection()
    init_db(conn)

    if manual:
        # Pure manual entry mode — no browser needed
        await _run_manual_loop(conn, rounds)
        conn.close()
        return

    pw, context, page = await launch_browser(headless=headless)

    try:
        await wait_for_login(page)

        rounds_scraped = 0
        while rounds == 0 or rounds_scraped < rounds:
            print(f"\n{'─' * 50}")
            print(f"Waiting for round results... (scraped: {rounds_scraped})")

            if not manual:
                # Auto-scrape mode
                round_id, matches = await scrape_round_results(page)

                if not matches:
                    print("No matches found via auto-scrape.")
                    choice = input("Enter 'm' for manual entry, 'r' to retry, 'q' to quit: ").strip().lower()
                    if choice == "m":
                        if round_id is None:
                            round_id = f"R{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                        matches = await manual_entry_mode(conn, round_id)
                    elif choice == "q":
                        break
                    else:
                        continue
            else:
                round_id = f"R{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
                matches = await manual_entry_mode(conn, round_id)

            if not matches:
                continue

            # Check for duplicate round
            if round_exists(conn, round_id):
                print(f"Round {round_id} already scraped, skipping.")
                continue

            # Store the round and its matches
            insert_round(conn, round_id)
            count = insert_matches_bulk(conn, matches)

            # Count jackpots in this round
            jackpots = sum(1 for m in matches if _is_jackpot(m))

            print(f"✅ Round {round_id} | {count} matches stored | {jackpots} jackpot(s)")

            # Show running totals
            stats = get_total_stats(conn)
            print(f"   📊 Total: {stats['total_rounds']} rounds, "
                  f"{stats['total_matches']} matches, "
                  f"{stats['total_jackpots']} jackpots "
                  f"({stats['jackpot_rate']:.2%})")

            rounds_scraped += 1

            if rounds == 0 or rounds_scraped < rounds:
                print("\nPress Enter when the next round's results are displayed...")
                await asyncio.get_event_loop().run_in_executor(None, input)

    except KeyboardInterrupt:
        print("\n\n🛑 Stopped by user.")
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


async def inspect_page(page: Page) -> None:
    """Interactive inspection mode: examine the page to find correct selectors."""
    print("\n🔍 INSPECT MODE")
    print("Commands:")
    print("  screenshot          — Take a screenshot")
    print("  dump                — Save full page HTML")
    print("  select <css>        — Query selector and show text")
    print("  selectall <css>     — Query all matching selectors")
    print("  eval <js>           — Run JavaScript in page")
    print("  quit                — Exit inspect mode\n")

    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    while True:
        cmd = input("inspect> ").strip()
        if not cmd:
            continue

        if cmd == "quit":
            break
        elif cmd == "screenshot":
            path = data_dir / f"inspect_{datetime.now().strftime('%H%M%S')}.png"
            await page.screenshot(path=str(path), full_page=True)
            print(f"  Saved: {path}")
        elif cmd == "dump":
            path = data_dir / f"inspect_{datetime.now().strftime('%H%M%S')}.html"
            path.write_text(await page.content(), encoding="utf-8")
            print(f"  Saved: {path}")
        elif cmd.startswith("select "):
            selector = cmd[7:].strip()
            try:
                el = await page.query_selector(selector)
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
                els = await page.query_selector_all(selector)
                print(f"  Found {len(els)} elements:")
                for i, el in enumerate(els[:20]):
                    text = await el.text_content()
                    print(f"    [{i}] {text[:100] if text else '(empty)'}")
            except Exception as e:
                print(f"  Error: {e}")
        elif cmd.startswith("eval "):
            js = cmd[5:].strip()
            try:
                result = await page.evaluate(js)
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
        ))


async def _inspect_mode():
    """Run the interactive page inspector."""
    pw, context, page = await launch_browser(headless=False)
    try:
        await page.goto(SPORTYBET_VIRTUALS_URL, wait_until="domcontentloaded", timeout=30000)
        print("Browser launched. Navigate to the results page, then come back here.")
        input("Press Enter when ready to inspect...")
        await inspect_page(page)
    finally:
        await context.close()
        await pw.stop()


if __name__ == "__main__":
    main()
