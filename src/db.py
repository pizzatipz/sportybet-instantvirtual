"""
SQLite storage layer for SportyBet HT/FT RNG study.

Stores match results scraped from the virtual soccer results screen,
with focus on HT/FT market outcomes and the Away/Home jackpot.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "data" / "sportybet.db"

CATEGORIES = [
    "England", "Spain", "Germany", "Champions",
    "Italy", "African Cup", "Euros", "Club World Cup",
]

HTFT_OUTCOMES = [
    "Home/Home", "Home/Draw", "Home/Away",
    "Draw/Home", "Draw/Draw", "Draw/Away",
    "Away/Home", "Away/Draw", "Away/Away",
]

JACKPOT_OUTCOME = "Away/Home"


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Get a database connection with WAL mode and foreign keys enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS rounds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id    TEXT NOT NULL UNIQUE,
            timestamp   TEXT NOT NULL,
            scraped_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS matches (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id        TEXT NOT NULL,
            category        TEXT NOT NULL,
            home_team       TEXT NOT NULL,
            away_team       TEXT NOT NULL,
            ht_home_goals   INTEGER NOT NULL,
            ht_away_goals   INTEGER NOT NULL,
            ft_home_goals   INTEGER NOT NULL,
            ft_away_goals   INTEGER NOT NULL,
            ht_result       TEXT NOT NULL,
            ft_result       TEXT NOT NULL,
            htft_result     TEXT NOT NULL,
            is_jackpot      INTEGER DEFAULT 0,
            FOREIGN KEY (round_id) REFERENCES rounds(round_id)
        );

        CREATE TABLE IF NOT EXISTS htft_odds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id    TEXT NOT NULL,
            category    TEXT NOT NULL,
            home_team   TEXT NOT NULL,
            away_team   TEXT NOT NULL,
            home_home   REAL,
            home_draw   REAL,
            home_away   REAL,
            draw_home   REAL,
            draw_draw   REAL,
            draw_away   REAL,
            away_home   REAL,
            away_draw   REAL,
            away_away   REAL,
            FOREIGN KEY (round_id) REFERENCES rounds(round_id)
        );

        CREATE TABLE IF NOT EXISTS bets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id    TEXT,
            timestamp   TEXT NOT NULL,
            category    TEXT,
            home_team   TEXT NOT NULL,
            away_team   TEXT NOT NULL,
            market      TEXT DEFAULT 'HT/FT',
            selection   TEXT NOT NULL,
            odds        REAL NOT NULL,
            stake       REAL NOT NULL,
            htft_result TEXT,
            won         INTEGER,
            payout      REAL DEFAULT 0,
            profit      REAL,
            FOREIGN KEY (round_id) REFERENCES rounds(round_id)
        );

        CREATE INDEX IF NOT EXISTS idx_matches_round ON matches(round_id);
        CREATE INDEX IF NOT EXISTS idx_matches_category ON matches(category);
        CREATE INDEX IF NOT EXISTS idx_matches_htft ON matches(htft_result);
        CREATE INDEX IF NOT EXISTS idx_matches_jackpot ON matches(is_jackpot);
        CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);

        CREATE TABLE IF NOT EXISTS fixture_odds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id    TEXT,
            scraped_at  TEXT NOT NULL,
            category    TEXT NOT NULL,
            home_team   TEXT NOT NULL,
            away_team   TEXT NOT NULL,
            odds_1      REAL,
            odds_x      REAL,
            odds_2      REAL,
            ou_05_over  REAL,
            ou_05_under REAL,
            ou_15_over  REAL,
            ou_15_under REAL,
            ou_25_over  REAL,
            ou_25_under REAL,
            ou_35_over  REAL,
            ou_35_under REAL,
            ou_45_over  REAL,
            ou_45_under REAL,
            ou_55_over  REAL,
            ou_55_under REAL,
            htft_hh     REAL,
            htft_hd     REAL,
            htft_ha     REAL,
            htft_dh     REAL,
            htft_dd     REAL,
            htft_da     REAL,
            htft_ah     REAL,
            htft_ad     REAL,
            htft_aa     REAL,
            dc_1x       REAL,
            dc_12       REAL,
            dc_x2       REAL,
            gg          REAL,
            ng          REAL,
            source      TEXT DEFAULT 'detail'
        );

        CREATE INDEX IF NOT EXISTS idx_fixture_odds_round ON fixture_odds(round_id);
        CREATE INDEX IF NOT EXISTS idx_fixture_odds_teams ON fixture_odds(category, home_team, away_team);

        CREATE TABLE IF NOT EXISTS market_odds (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id    TEXT,
            scraped_at  TEXT NOT NULL,
            category    TEXT NOT NULL,
            home_team   TEXT NOT NULL,
            away_team   TEXT NOT NULL,
            market      TEXT NOT NULL,
            selection   TEXT NOT NULL,
            odds        REAL NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_market_odds_round ON market_odds(round_id);
        CREATE INDEX IF NOT EXISTS idx_market_odds_market ON market_odds(market, selection);
        CREATE INDEX IF NOT EXISTS idx_market_odds_teams ON market_odds(category, home_team, away_team);
    """)
    conn.commit()


def derive_result(home_goals: int, away_goals: int) -> str:
    """Derive Home/Draw/Away result from goal counts."""
    if home_goals > away_goals:
        return "Home"
    elif home_goals == away_goals:
        return "Draw"
    else:
        return "Away"


def derive_htft(ht_home: int, ht_away: int, ft_home: int, ft_away: int) -> str:
    """Derive HT/FT outcome string from scores."""
    ht = derive_result(ht_home, ht_away)
    ft = derive_result(ft_home, ft_away)
    return f"{ht}/{ft}"


def insert_round(conn: sqlite3.Connection, round_id: str, timestamp: str = None) -> bool:
    """Insert a round. Returns False if round already exists (idempotent)."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    scraped_at = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute(
            "INSERT INTO rounds (round_id, timestamp, scraped_at) VALUES (?, ?, ?)",
            (round_id, timestamp, scraped_at),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # Round already exists


def insert_match(
    conn: sqlite3.Connection,
    round_id: str,
    category: str,
    home_team: str,
    away_team: str,
    ht_home_goals: int,
    ht_away_goals: int,
    ft_home_goals: int,
    ft_away_goals: int,
) -> int:
    """Insert a match result with derived HT/FT fields. Returns the row id."""
    ht_result = derive_result(ht_home_goals, ht_away_goals)
    ft_result = derive_result(ft_home_goals, ft_away_goals)
    htft_result = f"{ht_result}/{ft_result}"
    is_jackpot = 1 if htft_result == JACKPOT_OUTCOME else 0

    cursor = conn.execute(
        """INSERT INTO matches
           (round_id, category, home_team, away_team,
            ht_home_goals, ht_away_goals, ft_home_goals, ft_away_goals,
            ht_result, ft_result, htft_result, is_jackpot)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (round_id, category, home_team, away_team,
         ht_home_goals, ht_away_goals, ft_home_goals, ft_away_goals,
         ht_result, ft_result, htft_result, is_jackpot),
    )
    conn.commit()
    return cursor.lastrowid


def insert_matches_bulk(conn: sqlite3.Connection, matches: list[dict]) -> int:
    """Insert multiple match results in a single transaction. Returns count inserted."""
    count = 0
    for m in matches:
        ht_result = derive_result(m["ht_home_goals"], m["ht_away_goals"])
        ft_result = derive_result(m["ft_home_goals"], m["ft_away_goals"])
        htft_result = f"{ht_result}/{ft_result}"
        is_jackpot = 1 if htft_result == JACKPOT_OUTCOME else 0

        conn.execute(
            """INSERT INTO matches
               (round_id, category, home_team, away_team,
                ht_home_goals, ht_away_goals, ft_home_goals, ft_away_goals,
                ht_result, ft_result, htft_result, is_jackpot)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (m["round_id"], m["category"], m["home_team"], m["away_team"],
             m["ht_home_goals"], m["ht_away_goals"], m["ft_home_goals"], m["ft_away_goals"],
             ht_result, ft_result, htft_result, is_jackpot),
        )
        count += 1
    conn.commit()
    return count


def round_exists(conn: sqlite3.Connection, round_id: str) -> bool:
    """Check if a round has already been scraped."""
    row = conn.execute(
        "SELECT 1 FROM rounds WHERE round_id = ?", (round_id,)
    ).fetchone()
    return row is not None


def get_total_stats(conn: sqlite3.Connection) -> dict:
    """Get overall summary statistics."""
    stats = {}
    row = conn.execute("SELECT COUNT(*) as n FROM rounds").fetchone()
    stats["total_rounds"] = row["n"]

    row = conn.execute("SELECT COUNT(*) as n FROM matches").fetchone()
    stats["total_matches"] = row["n"]

    row = conn.execute("SELECT COUNT(*) as n FROM matches WHERE is_jackpot = 1").fetchone()
    stats["total_jackpots"] = row["n"]

    if stats["total_matches"] > 0:
        stats["jackpot_rate"] = stats["total_jackpots"] / stats["total_matches"]
    else:
        stats["jackpot_rate"] = 0.0

    return stats


def get_htft_distribution(conn: sqlite3.Connection, category: str = None) -> list[dict]:
    """Get HT/FT outcome distribution, optionally filtered by category."""
    if category:
        rows = conn.execute(
            """SELECT htft_result, COUNT(*) as count
               FROM matches WHERE category = ?
               GROUP BY htft_result ORDER BY count DESC""",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT htft_result, COUNT(*) as count
               FROM matches GROUP BY htft_result ORDER BY count DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_jackpots(conn: sqlite3.Connection, category: str = None) -> list[dict]:
    """Get all jackpot (Away/Home) matches, optionally filtered by category."""
    if category:
        rows = conn.execute(
            """SELECT m.*, r.timestamp FROM matches m
               JOIN rounds r ON m.round_id = r.round_id
               WHERE m.is_jackpot = 1 AND m.category = ?
               ORDER BY r.timestamp""",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT m.*, r.timestamp FROM matches m
               JOIN rounds r ON m.round_id = r.round_id
               WHERE m.is_jackpot = 1
               ORDER BY r.timestamp"""
        ).fetchall()
    return [dict(r) for r in rows]


def get_jackpot_rate_by_category(conn: sqlite3.Connection) -> list[dict]:
    """Get jackpot rate broken down by category."""
    rows = conn.execute(
        """SELECT category,
                  COUNT(*) as total,
                  SUM(is_jackpot) as jackpots,
                  ROUND(CAST(SUM(is_jackpot) AS REAL) / COUNT(*) * 100, 2) as jackpot_pct
           FROM matches
           GROUP BY category
           ORDER BY jackpot_pct DESC"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_jackpot_teams(conn: sqlite3.Connection, as_home: bool = True) -> list[dict]:
    """Get teams most involved in jackpots, either as home or away team."""
    team_col = "home_team" if as_home else "away_team"
    rows = conn.execute(
        f"""SELECT {team_col} as team, category,
                   COUNT(*) as jackpot_count
            FROM matches
            WHERE is_jackpot = 1
            GROUP BY {team_col}, category
            ORDER BY jackpot_count DESC
            LIMIT 30""",
    ).fetchall()
    return [dict(r) for r in rows]


def get_matches_by_category(conn: sqlite3.Connection, category: str) -> list[dict]:
    """Get all matches for a specific category, ordered by round."""
    rows = conn.execute(
        """SELECT m.*, r.timestamp FROM matches m
           JOIN rounds r ON m.round_id = r.round_id
           WHERE m.category = ?
           ORDER BY r.timestamp, m.id""",
        (category,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_matches(conn: sqlite3.Connection) -> list[dict]:
    """Get all matches ordered by round and id."""
    rows = conn.execute(
        """SELECT m.*, r.timestamp FROM matches m
           JOIN rounds r ON m.round_id = r.round_id
           ORDER BY r.timestamp, m.id"""
    ).fetchall()
    return [dict(r) for r in rows]


def export_to_csv(conn: sqlite3.Connection, output_path: Path) -> None:
    """Export all match data to a CSV file."""
    import csv

    matches = get_all_matches(conn)
    if not matches:
        print("No data to export.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=matches[0].keys())
        writer.writeheader()
        writer.writerows(matches)
    print(f"Exported {len(matches)} matches to {output_path}")


def insert_htft_odds(conn: sqlite3.Connection, odds_data: dict) -> int:
    """Insert HT/FT odds for a match. Returns the row id."""
    cursor = conn.execute(
        """INSERT INTO htft_odds
           (round_id, category, home_team, away_team,
            home_home, home_draw, home_away,
            draw_home, draw_draw, draw_away,
            away_home, away_draw, away_away)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (odds_data.get("round_id"), odds_data.get("category"),
         odds_data.get("home_team"), odds_data.get("away_team"),
         odds_data.get("home_home"), odds_data.get("home_draw"),
         odds_data.get("home_away"), odds_data.get("draw_home"),
         odds_data.get("draw_draw"), odds_data.get("draw_away"),
         odds_data.get("away_home"), odds_data.get("away_draw"),
         odds_data.get("away_away")),
    )
    conn.commit()
    return cursor.lastrowid


def insert_market_odds_bulk(conn: sqlite3.Connection, odds_list: list[dict]) -> int:
    """Insert multiple market odds records in one transaction.

    Each dict should have: round_id, category, home_team, away_team,
    market, selection, odds.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    count = 0
    for o in odds_list:
        if not o.get('odds') or not o.get('market') or not o.get('selection'):
            continue
        try:
            odds_val = float(o['odds'])
            if odds_val <= 0:
                continue
        except (ValueError, TypeError):
            continue
        try:
            conn.execute(
                """INSERT INTO market_odds
                   (round_id, scraped_at, category, home_team, away_team,
                    market, selection, odds)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (o.get('round_id'), now,
                 o.get('category', ''), o.get('home_team', ''),
                 o.get('away_team', ''),
                 o['market'], o['selection'], odds_val),
            )
            count += 1
        except Exception:
            continue
    conn.commit()
    return count


def insert_htft_odds_bulk(conn: sqlite3.Connection, odds_list: list[dict]) -> int:
    """Insert multiple HT/FT odds records. Returns count inserted."""
    count = 0
    for o in odds_list:
        conn.execute(
            """INSERT INTO htft_odds
               (round_id, category, home_team, away_team,
                home_home, home_draw, home_away,
                draw_home, draw_draw, draw_away,
                away_home, away_draw, away_away)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (o.get("round_id"), o.get("category"),
             o.get("home_team"), o.get("away_team"),
             o.get("home_home"), o.get("home_draw"),
             o.get("home_away"), o.get("draw_home"),
             o.get("draw_draw"), o.get("draw_away"),
             o.get("away_home"), o.get("away_draw"),
             o.get("away_away")),
        )
        count += 1
    conn.commit()
    return count


def insert_fixture_odds(conn: sqlite3.Connection, odds: dict) -> int:
    """Insert a complete set of fixture odds. Returns the row id."""
    from datetime import datetime, timezone
    cursor = conn.execute(
        """INSERT INTO fixture_odds
           (round_id, scraped_at, category, home_team, away_team,
            odds_1, odds_x, odds_2,
            ou_05_over, ou_05_under, ou_15_over, ou_15_under,
            ou_25_over, ou_25_under, ou_35_over, ou_35_under,
            ou_45_over, ou_45_under, ou_55_over, ou_55_under,
            htft_hh, htft_hd, htft_ha,
            htft_dh, htft_dd, htft_da,
            htft_ah, htft_ad, htft_aa,
            dc_1x, dc_12, dc_x2, gg, ng, source)
           VALUES (?,?,?,?,?, ?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?,
                   ?,?,?, ?,?,?, ?,?,?, ?,?,?, ?,?, ?)""",
        (odds.get('round_id'), datetime.now(timezone.utc).isoformat(),
         odds.get('category', ''), odds.get('home_team', ''), odds.get('away_team', ''),
         odds.get('odds_1'), odds.get('odds_x'), odds.get('odds_2'),
         odds.get('ou_05_over'), odds.get('ou_05_under'),
         odds.get('ou_15_over'), odds.get('ou_15_under'),
         odds.get('ou_25_over'), odds.get('ou_25_under'),
         odds.get('ou_35_over'), odds.get('ou_35_under'),
         odds.get('ou_45_over'), odds.get('ou_45_under'),
         odds.get('ou_55_over'), odds.get('ou_55_under'),
         odds.get('htft_hh'), odds.get('htft_hd'), odds.get('htft_ha'),
         odds.get('htft_dh'), odds.get('htft_dd'), odds.get('htft_da'),
         odds.get('htft_ah'), odds.get('htft_ad'), odds.get('htft_aa'),
         odds.get('dc_1x'), odds.get('dc_12'), odds.get('dc_x2'),
         odds.get('gg'), odds.get('ng'),
         odds.get('source', 'detail')),
    )
    conn.commit()
    return cursor.lastrowid
