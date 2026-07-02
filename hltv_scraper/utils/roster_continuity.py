"""
roster_continuity.py
====================
Fetches the current live 5-man roster for every team in the HLTV CS2 Top 50
and compares it against the previously stored snapshot in hltv_rosters.csv.

Teams whose roster has changed significantly (< ROSTER_CHANGE_THRESHOLD overlap)
are flagged so the downstream team-stat scrapers can force a full re-scrape.

Outputs
-------
hltv_rosters.csv   — one row per team, 5 player columns, last_checked timestamp,
                     and a roster_change_flag boolean.

Standalone usage
----------------
    python hltv_scraper/utils/roster_continuity.py
"""

import csv
import os
from datetime import datetime

# hltv_session lives in the same utils/ directory as this file
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
from hltv_session import make_session, safe_fetch, jitter_sleep

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.join(_HERE, "..", "..")

TEAMS_CSV   = os.path.join(_ROOT, "hltv_cs2_all_teams.csv")
ROSTERS_CSV = os.path.join(_ROOT, "hltv_rosters.csv")
BASE_URL    = "https://www.hltv.org"
TOP50_URL   = "https://www.hltv.org/stats/teams?csVersion=CS2&startDate=all"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROSTER_CHANGE_THRESHOLD = 0.4   # overlap < 40 % → major roster change
MAX_PLAYERS_TRACKED     = 5     # we track the starting 5

ROSTER_FIELDNAMES = [
    "team", "profile_url",
    "player_1", "player_2", "player_3", "player_4", "player_5",
    "last_checked", "roster_change_flag",
]


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def _load_snapshot() -> dict[str, dict]:
    """Return {team_lower: row_dict} from hltv_rosters.csv, empty dict if missing."""
    if not os.path.exists(ROSTERS_CSV):
        return {}
    with open(ROSTERS_CSV, mode="r", encoding="utf-8") as f:
        return {row["team"].lower(): row for row in csv.DictReader(f)}


def _save_snapshot(rows: list[dict]) -> None:
    with open(ROSTERS_CSV, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ROSTER_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _players_from_row(row: dict) -> set[str]:
    """Extract the non-empty player names from a snapshot row."""
    return {
        row.get(f"player_{i}", "").strip().lower()
        for i in range(1, MAX_PLAYERS_TRACKED + 1)
        if row.get(f"player_{i}", "").strip()
    }


# ---------------------------------------------------------------------------
# Roster overlap calculation
# ---------------------------------------------------------------------------

def roster_overlap(old_players: set[str], new_players: set[str]) -> float:
    """
    Returns the fraction of the OLD roster still present in the NEW roster.
    0.0 = completely new team, 1.0 = identical roster.
    Returns 1.0 if old_players is empty (first time seen → no change flagged).
    """
    if not old_players:
        return 1.0
    return len(old_players & new_players) / len(old_players)


# ---------------------------------------------------------------------------
# HLTV roster fetcher
# ---------------------------------------------------------------------------

def _fetch_team_list(session) -> list[dict]:
    """Scrape the Top 50 page and return [{name, profile_url}, ...]."""
    print("📋 Fetching Top 50 team list from HLTV …")
    page = safe_fetch(session, TOP50_URL, jitter=False)
    if page is None:
        print("  ❌ Could not fetch team list.")
        return []
    teams = []
    for row in page.css("table.stats-table tbody tr"):
        a_tag = row.css("td a[href*='/stats/teams/']")
        if a_tag:
            href = a_tag.css("::attr(href)").get()
            name = a_tag.css("::text").get()
            if href and name:
                full_url = BASE_URL + href if href.startswith("/") else href
                teams.append({"name": name.strip(), "profile_url": full_url})
    print(f"  ✅ Found {len(teams)} teams.")
    return teams


def _fetch_roster(session, team_name: str, profile_url: str) -> list[str]:
    """
    Fetch the current active roster from the team's HLTV profile page.
    Returns a list of up to 5 player names (lowercase, stripped).
    Falls back to [] on any error.
    """
    try:
        page = safe_fetch(session, profile_url)
        if page is None:
            return []

        # Primary selector: the "Players" box on the team overview page
        players = []

        # Try .players-cell a (team overview card)
        for a in page.css(".players-cell a, .lineupBox .player a, .squad-table tbody tr .playersBox a"):
            name = (a.css("::text").get() or "").strip()
            if name and name.lower() not in players:
                players.append(name.lower())
            if len(players) >= MAX_PLAYERS_TRACKED:
                break

        # Fallback: any link that points to a player profile
        if not players:
            for a in page.css("a[href*='/player/']"):
                name = (a.css("::text").get() or "").strip()
                if name and len(name) > 1 and name.lower() not in players:
                    players.append(name.lower())
                if len(players) >= MAX_PLAYERS_TRACKED:
                    break

        return players[:MAX_PLAYERS_TRACKED]
    except Exception as exc:
        print(f"  ⚠️  Could not fetch roster for {team_name}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def check_all_rosters(session=None) -> dict[str, float]:
    """
    Run the full roster continuity check for all Top 50 teams.

    Parameters
    ----------
    session : StealthySession, optional
        Pass an existing session to reuse; a new one is created otherwise.

    Returns
    -------
    dict[str, float]
        {team_name_lower: overlap_ratio} for every team processed.
        Teams with overlap < ROSTER_CHANGE_THRESHOLD have roster_change_flag=True
        in hltv_rosters.csv.
    """
    snapshot = _load_snapshot()
    overlap_map: dict[str, float] = {}
    new_rows: list[dict] = []

    def _run(sess):
        teams = _fetch_team_list(sess)
        now   = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        for i, team in enumerate(teams):
            team_key = team["name"].lower()
            print(f"[{i+1}/{len(teams)}] Checking roster: {team['name']}")

            new_players_list = _fetch_roster(sess, team["name"], team["profile_url"])
            new_players_set  = set(new_players_list)

            old_row     = snapshot.get(team_key, {})
            old_players = _players_from_row(old_row)

            overlap = roster_overlap(old_players, new_players_set)
            overlap_map[team_key] = overlap

            changed = overlap < ROSTER_CHANGE_THRESHOLD and bool(old_players)

            if changed:
                print(
                    f"  ⚠️  Major roster change detected for {team['name']} "
                    f"(overlap={overlap:.0%}) — will force re-scrape"
                )
            elif not old_players:
                print(f"  ℹ️  First-time snapshot for {team['name']}: {new_players_list}")
            else:
                print(f"  ✅ Roster stable for {team['name']} (overlap={overlap:.0%})")

            # Build player columns
            player_cols = {f"player_{j+1}": (new_players_list[j] if j < len(new_players_list) else "") for j in range(MAX_PLAYERS_TRACKED)}

            new_rows.append({
                "team":               team["name"],
                "profile_url":        team["profile_url"],
                **player_cols,
                "last_checked":       now,
                "roster_change_flag": str(changed),
            })

            jitter_sleep(1.5)  # be polite to HLTV

        _save_snapshot(new_rows)
        print(f"\n✅ Roster snapshot saved to {ROSTERS_CSV}")

    if session is not None:
        _run(session)
    else:
        with make_session() as sess:
            print("Initializing session …")
            _run(sess)

    return overlap_map


def get_changed_teams() -> set[str]:
    """
    Read hltv_rosters.csv and return a set of lowercased team names
    whose roster_change_flag is True.

    Used by the scraper scripts to decide which teams to force-re-scrape.
    """
    if not os.path.exists(ROSTERS_CSV):
        return set()
    changed = set()
    with open(ROSTERS_CSV, mode="r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("roster_change_flag", "").strip().lower() == "true":
                changed.add(row["team"].lower())
    return changed


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    overlaps = check_all_rosters()
    print("\nOverlap summary:")
    for team, ratio in sorted(overlaps.items(), key=lambda x: x[1]):
        flag = "⚠️  CHANGED" if ratio < ROSTER_CHANGE_THRESHOLD else "✅ stable"
        print(f"  {team:<30} {ratio:.0%}  {flag}")
