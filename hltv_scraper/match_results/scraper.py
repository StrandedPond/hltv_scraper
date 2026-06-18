import time
from datetime import datetime, timedelta
from scrapling import Fetcher
from scrapling.fetchers import StealthySession

from parser import Parser
from exporters import Exporter

class HLTVScraper:
    def __init__(self):
        self.base_url = "https://www.hltv.org"
        self.start_url = "https://www.hltv.org/results?stars=1"
        self.fetcher = Fetcher()
        self.exporter = Exporter()
        self.cutoff_date = datetime.now() - timedelta(days=183)
        self.stop_scraping = False
        self.new_batch = []
        
        # --- NEW: Load scraped URLs ---
        self.scraped_urls = set()
        matches_csv = getattr(self.exporter, 'matches_file', "matches.csv")
        import os, csv
        if os.path.exists(matches_csv):
            print(f"Found existing file: {matches_csv}. Loading previous data...")
            with open(matches_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if "match_url" in row and row["match_url"]:
                        self.scraped_urls.add(row["match_url"])
            print(f"Loaded {len(self.scraped_urls)} previously scraped matches. Will stop when encountered.")
        # ------------------------------

    def start(self):
        print(f"Starting scraping. Cutoff date is {self.cutoff_date.strftime('%Y-%m-%d')}")
        current_url = self.start_url
        
        while current_url and not self.stop_scraping:
            print(f"\nFetching results page: {current_url}")
            page = self.fetcher.get(current_url)
            
            # Find all match links
            match_elements = page.css(".result-con a.a-reset")
            match_links = [a.attrib.get('href') for a in match_elements if a.attrib.get('href')]
            
            for match_link in match_links:
                if self.stop_scraping:
                    break
                    
                match_url = self.base_url + match_link
                
                # --- NEW: Duplicate check to know when to stop scraping ---
                if match_url in self.scraped_urls:
                    print(f"    [!] Reached already scraped match: {match_url}. Stopping scraper.")
                    self.stop_scraping = True
                    break
                # ----------------------------------------------------------
                
                self.process_match(match_url)
                time.sleep(2) # Sleep between matches
                
            if self.stop_scraping:
                print("Cutoff date reached. Stopping pagination.")
                break
                
            # Pagination
            pagination_bottom = page.css(".pagination-component.pagination-bottom")
            if pagination_bottom:
                next_page_el = pagination_bottom[0].css("a.pagination-next")
                if next_page_el and next_page_el[0].attrib.get('href'):
                    current_url = self.base_url + next_page_el[0].attrib.get('href')
                else:
                    current_url = None
            else:
                current_url = None

        # Export all collected results in reverse order (chronological, oldest to newest)
        if self.new_batch:
            print(f"\nExporting {len(self.new_batch)} matches in chronological order...")
            # Each match might have multiple maps, so reversing the batch puts older matches first.
            for match_data, players_data in reversed(self.new_batch):
                self.exporter.export_match(match_data)
                self.exporter.export_players(players_data)

    def process_match(self, match_url):
        print(f"  -> Processing match: {match_url}")
        try:
            match_page = self.fetcher.get(match_url)
            stats_links = [a.attrib.get('href') for a in match_page.css("a") 
                           if a.attrib.get('href') and '/stats/matches/mapstatsid/' in a.attrib.get('href')]
            
            # Deduplicate preserving order
            seen = set()
            unique_stats_links = []
            for link in stats_links:
                if link not in seen:
                    unique_stats_links.append(link)
                    seen.add(link)
            
            if not unique_stats_links:
                # Fallback to overall stats link if no mapstatsid (for very old or single map matches)
                stats_links = [a.attrib.get('href') for a in match_page.css("a") 
                               if a.attrib.get('href') and '/stats/matches/' in a.attrib.get('href') and 'mapstatsid' not in a.attrib.get('href')]
                if not stats_links:
                    print("     [SKIP] No stats link found.")
                    return
                unique_stats_links = [stats_links[0]]
                
            for stats_link in unique_stats_links:
                stats_url = self.base_url + stats_link
                print(f"     -> Fetching stats: {stats_url}")
                
                # Use StealthySession for stats page to bypass Cloudflare
                with StealthySession(headless=True, solve_cloudflare=True) as session:
                    stats_page = session.fetch(stats_url)
                    parsed_results = Parser.parse_stats_page(stats_page, match_url)
                    
                    for res in parsed_results:
                        match_data = res['match_data']
                        players_data = res['players_data']
                        
                        if not match_data['date']:
                            continue
                            
                        # Check date for cutoff
                        try:
                            match_date = datetime.strptime(match_data['date'], "%Y-%m-%d %H:%M")
                            if match_date < self.cutoff_date:
                                print(f"     [STOP] Match date {match_data['date']} is older than 6 months.")
                                self.stop_scraping = True
                                return
                        except ValueError:
                            pass # Ignore malformed dates
                            
                        self.new_batch.append((match_data, players_data))
                        print(f"     [SUCCESS] Processed {match_data['map']} ({match_data['team_left']} vs {match_data['team_right']})")
                        
        except Exception as e:
            print(f"     [ERROR] Failed to process {match_url}: {e}")

if __name__ == "__main__":
    scraper = HLTVScraper()
    scraper.start()
    print("\nScraping complete!")
