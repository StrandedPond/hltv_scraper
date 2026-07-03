"""
scraper.py — HLTV Match Results Scraper
========================================
Scrapes starred match results from HLTV, parses per-map stats pages, and
appends new rows to matches.csv and player_stats.csv.

Improvements over the original:
- Uses the shared hltv_session utility (solve_cloudflare=False, per-request
  timeout, CF detection, jitter delays) — no more 3-second overhead per fetch
- A single StealthySession is reused for the entire run instead of spawning a
  new browser per match stats URL
- Replaced bare time.sleep() with jitter_sleep()
- Added None guards on every safe_fetch call
"""

import os
import sys
import csv
from datetime import datetime, timedelta

_PARENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(_PARENT, "utils"))

from hltv_session import make_session, safe_fetch, jitter_sleep
from parser import Parser
from exporters import Exporter


class HLTVScraper:
    BASE_URL  = "https://www.hltv.org"
    START_URL = "https://www.hltv.org/results?stars=1"

    def __init__(self):
        self.exporter     = Exporter()
        self.cutoff_date  = datetime.now() - timedelta(days=183)
        self.stop_scraping = False
        self.new_batch    = []

        # Load already-scraped match URLs so we stop when we hit one
        self.scraped_urls: set[str] = set()
        matches_csv = self.exporter.matches_file
        if os.path.exists(matches_csv):
            print(f"Found existing file: {matches_csv}. Loading previous data...")
            with open(matches_csv, mode="r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row.get("match_url"):
                        self.scraped_urls.add(row["match_url"])
            print(f"Loaded {len(self.scraped_urls)} previously scraped matches.\n")

    def start(self):
        print(f"Starting scraper. Cutoff date: {self.cutoff_date.strftime('%Y-%m-%d')}")
        current_url = self.START_URL

        with make_session() as session:
            # ── Paginate results pages ──────────────────────────────────────
            while current_url and not self.stop_scraping:
                print(f"\nFetching results page: {current_url}")
                page = safe_fetch(session, current_url)
                if page is None:
                    print("  [WARN] Could not load results page — stopping pagination.")
                    break

                match_links = [
                    a.attrib.get("href")
                    for a in page.css(".result-con a.a-reset")
                    if a.attrib.get("href")
                ]

                for match_link in match_links:
                    if self.stop_scraping:
                        break

                    match_url = self.BASE_URL + match_link

                    if match_url in self.scraped_urls:
                        print(f"  [STOP] Reached already-scraped match: {match_url}")
                        self.stop_scraping = True
                        break

                    self._process_match(session, match_url)
                    jitter_sleep(2)

                if self.stop_scraping:
                    break

                # Pagination
                pagination = page.css(".pagination-component.pagination-bottom")
                if pagination:
                    next_el = pagination[0].css("a.pagination-next")
                    if next_el and next_el[0].attrib.get("href"):
                        current_url = self.BASE_URL + next_el[0].attrib.get("href")
                    else:
                        current_url = None
                else:
                    current_url = None

        # Write collected results in chronological order (oldest → newest)
        if self.new_batch:
            print(f"\nExporting {len(self.new_batch)} match maps in chronological order…")
            for match_data, players_data in reversed(self.new_batch):
                self.exporter.export_match(match_data)
                self.exporter.export_players(players_data)
        else:
            print("\nNo new matches found.")

    def _process_match(self, session, match_url: str):
        print(f"  -> Processing: {match_url}")
        try:
            match_page = safe_fetch(session, match_url)
            if match_page is None:
                print("     [SKIP] Could not load match page.")
                return

            # Find per-map stats links
            stats_links = [
                a.attrib.get("href")
                for a in match_page.css("a")
                if a.attrib.get("href") and "/stats/matches/mapstatsid/" in a.attrib.get("href")
            ]

            # Deduplicate preserving order
            seen: set[str] = set()
            unique_stats_links = []
            for link in stats_links:
                if link not in seen:
                    unique_stats_links.append(link)
                    seen.add(link)

            # Fallback: old-style single-map stats link
            if not unique_stats_links:
                fallback = [
                    a.attrib.get("href")
                    for a in match_page.css("a")
                    if a.attrib.get("href")
                    and "/stats/matches/" in a.attrib.get("href")
                    and "mapstatsid" not in a.attrib.get("href")
                ]
                if not fallback:
                    print("     [SKIP] No stats link found.")
                    return
                unique_stats_links = [fallback[0]]

            for stats_link in unique_stats_links:
                stats_url = self.BASE_URL + stats_link
                print(f"     -> Stats: {stats_url}")

                stats_page = safe_fetch(session, stats_url)
                if stats_page is None:
                    print("     [SKIP] Could not load stats page.")
                    continue

                parsed_results = Parser.parse_stats_page(stats_page, match_url)

                for res in parsed_results:
                    match_data   = res["match_data"]
                    players_data = res["players_data"]

                    if not match_data.get("date"):
                        continue

                    try:
                        match_date = datetime.strptime(match_data["date"], "%Y-%m-%d %H:%M")
                        if match_date < self.cutoff_date:
                            print(f"     [STOP] Date {match_data['date']} older than 6 months.")
                            self.stop_scraping = True
                            return
                    except ValueError:
                        pass

                    self.new_batch.append((match_data, players_data))
                    print(
                        f"     [OK] {match_data['map']} "
                        f"({match_data['team_left']} vs {match_data['team_right']})"
                    )

        except Exception as exc:
            print(f"     [ERROR] {match_url}: {exc}")


if __name__ == "__main__":
    HLTVScraper().start()
    print("\nScraping complete!")
