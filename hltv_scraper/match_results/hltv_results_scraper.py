import os
import csv
import time
from datetime import datetime
from dateutil.relativedelta import relativedelta
from scrapling.fetchers import StealthySession

# ==========================================
# SET THIS TO TRUE TO TEST A SMALL SAMPLE FIRST!
# It will scrape exactly 2 matches and gracefully stop.
TEST_MODE = False 
# ==========================================

class AutoHealingSession:
    """A wrapper that automatically restarts the browser if Playwright/Cloudflare crashes it."""
    def __init__(self):
        self.session = StealthySession(headless=True, solve_cloudflare=True)
        self.session.__enter__()

    def fetch(self, url):
        try:
            return self.session.fetch(url)
        except Exception as e:
            print(f"\n⚠️ Browser crashed or closed: {e}")
            print("🔄 Auto-healing: Starting a fresh stealth browser session...")
            time.sleep(2)
            try:
                self.session.__exit__(None, None, None)
            except:
                pass
            self.session = StealthySession(headless=True, solve_cloudflare=True)
            self.session.__enter__()
            return self.session.fetch(url)
            
    def close(self):
        try:
            self.session.__exit__(None, None, None)
        except:
            pass

def clean_text(text):
    if not text: return ""
    return " ".join(text.strip().split())

def scrape_hltv_results():
    base_url = "https://www.hltv.org"
    start_url = "https://www.hltv.org/results?stars=1"
    
    # Calculate the cutoff date (2 months ago from today)
    cutoff_date = datetime.now() - relativedelta(months=2)
    print(f"Target Cutoff Date: {cutoff_date.strftime('%Y-%m-%d')}")
    if TEST_MODE:
        print("⚠️ RUNNING IN TEST MODE - WILL ONLY SCRAPE 2 MATCHES ⚠️\n")

    match_data_list = []
    player_data_list = []
    
    # --- NEW: Check if file exists and load scraped match URLs ---
    scraped_urls = set()
    match_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_match_info.csv")
    if os.path.exists(match_csv):
        print(f"Found existing file: {match_csv}. Loading previous data...")
        with open(match_csv, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "Match URL" in row and row["Match URL"]:
                    scraped_urls.add(row["Match URL"])
        print(f"Loaded {len(scraped_urls)} previously scraped matches. Will stop scraping when encountered.\n")
    # -------------------------------------------------------------
    
    # Pre-populate keys to ensure the columns order in CSV is clean
    player_keys = ["Match URL", "Map", "Team", "Player"]

    # Initialize our self-healing browser
    session = AutoHealingSession()
    
    current_page_url = start_url
    reached_cutoff = False
    matches_processed = 0

    while current_page_url and not reached_cutoff:
        print(f"\nNavigating to: {current_page_url}")
        page = session.fetch(current_page_url)
        
        # Look for sublists which contain the match containers
        result_cons = page.css(".results-holder.allres .results-sublist .result-con")
        print(f" -> Found {len(result_cons)} match containers on this page.")
        
        if len(result_cons) == 0:
            print("❌ No matches found! Cloudflare blocked the DOM load.")
            break

        for con in result_cons:
            if TEST_MODE and matches_processed >= 2:
                reached_cutoff = True
                break

            # Date check directly from the container to save HTTP requests!
            unix_time = con.css("::attr(data-zonedgrouping-entry-unix)").get()
            if unix_time:
                match_date = datetime.fromtimestamp(int(unix_time) / 1000.0)
                if match_date < cutoff_date and not TEST_MODE:
                    print(f"    [!] Reached match from {match_date.strftime('%Y-%m-%d')}. Stopping scraper.")
                    reached_cutoff = True
                    break 
                date_str = match_date.strftime('%Y-%m-%d %H:%M')
            else:
                date_str = "Unknown"

            href = con.css("a.a-reset::attr(href)").get()
            if not href:
                continue
                
            match_link = base_url + href if href.startswith('/') else href
            
            # --- NEW: Duplicate check to know when to stop scraping ---
            if match_link in scraped_urls and not TEST_MODE:
                print(f"\n    [!] Reached already scraped match: {match_link.split('/')[-1]}. Stopping scraper.")
                reached_cutoff = True
                break
            # ----------------------------------------------------------
            
            try:
                match_page = session.fetch(match_link)
                print(f"\n🔎 Processing Match [{date_str}]: {match_link.split('/')[-1]}")

                # 1. Determine Map Types
                center_stats = match_page.css(".flexbox-column .results-center-stats")
                map_urls = []

                if len(center_stats) <= 1:
                    print("   -> Detected Single Map Series")
                    map_urls.append((match_link, match_page))
                else:
                    print("   -> Detected Multi-Map Series")
                    # Skip the first element (the inactive "All" tab)
                    map_blocks = match_page.css(".stats-match-maps a.stats-match-map")[1:]
                    for block in map_blocks:
                        m_href = block.css("::attr(href)").get()
                        if m_href:
                            m_url = base_url + m_href if m_href.startswith('/') else m_href
                            m_page = session.fetch(m_url)
                            map_urls.append((m_url, m_page))
                            time.sleep(1) 

                # 2. Extract Data for Each Map
                for m_url, m_page in map_urls:
                    info_box = m_page.css(".col.match-info-box-col .match-info-box")
                    if not info_box:
                        print(f"   ❌ Could not find match-info-box on map page: {m_url}")
                        continue
                        
                    event_name = clean_text(info_box.css("a.block.text-ellipsis::text").get())

                    # Map Name Extraction (Handles both DOM structures safely)
                    map_name = clean_text(m_page.css(".mapname::text").get())
                    if not map_name:
                        # Fallback for single map pages where map name is loose text
                        raw_texts = [t.strip() for t in info_box.css("::text").getall() if t.strip()]
                        if "Map" in raw_texts:
                            map_index = raw_texts.index("Map")
                            if map_index + 1 < len(raw_texts):
                                map_name = raw_texts[map_index + 1]

                    team_left = clean_text(info_box.css(".team-left a::text").get())
                    team_right = clean_text(info_box.css(".team-right a::text").get())
                    
                    won_rounds = clean_text(info_box.css(".team-left .bold::text").get() or "0")
                    lost_rounds = clean_text(info_box.css(".team-right .bold::text").get() or "0")
                    total_rounds = int(won_rounds) + int(lost_rounds) if won_rounds.isdigit() and lost_rounds.isdigit() else f"{won_rounds}-{lost_rounds}"
                    
                    # Winner Check
                    winner = "Tie"
                    if info_box.css(".team-left .won"): winner = team_left
                    elif info_box.css(".team-right .won"): winner = team_right

                    # Starting CT Side Logic
                    breakdown_row = m_page.css(".match-info-row").nth(0)
                    starting_ct = "Unknown"
                    
                    if breakdown_row:
                        # The 3rd span class in the breakdown always belongs to Team Left's first half
                        span_classes = breakdown_row.css(".right span::attr(class)").getall()
                        if len(span_classes) >= 4:
                            half1_left_class = span_classes[2]
                            if "ct-color" in half1_left_class:
                                starting_ct = team_left
                            elif "t-color" in half1_left_class:
                                starting_ct = team_right

                    match_data = {
                        "Event": event_name,
                        "Date": date_str,
                        "Map": map_name,
                        "Team Left": team_left,
                        "Team Right": team_right,
                        "Team Left Rounds": won_rounds,
                        "Team Right Rounds": lost_rounds,
                        "Total Rounds": total_rounds,
                        "Winner": winner,
                        "Starting CT Team": starting_ct,
                        "Match URL": m_url
                    }
                    match_data_list.append(match_data)
                    print(f"      [Mapped] {team_left} {won_rounds}:{lost_rounds} {team_right} on {map_name} (Won by: {winner})")

                    # -- Player Stats Extraction --
                    stats_tables = m_page.css(".stats-content .stats-table.totalstats")
                    for t_idx, table in enumerate(stats_tables):
                        current_team = team_left if t_idx == 0 else team_right
                        
                        headers = []
                        # Ignore hidden columns
                        for th in table.css("thead th:not(.hidden)"):
                            header_text = "".join(th.css("::text").getall()).strip()
                            headers.append(header_text)
                        
                        for row in table.css("tbody tr"):
                            player_name = clean_text(row.css(".st-player a::text").get())
                            if not player_name: continue
                            
                            p_data = {
                                "Match URL": m_url,
                                "Map": map_name,
                                "Team": current_team,
                                "Player": player_name
                            }
                            
                            tds = row.css("td:not(.hidden)")
                            for i, td in enumerate(tds):
                                if i == 0: continue # Skip player name
                                if i < len(headers):
                                    col_name = headers[i]
                                    # Target traditional data explicitly to avoid eco-adjusted hidden data
                                    raw_val = "".join(td.css("::text").getall())
                                    clean_val = clean_text(td.css(".traditional-data::text").get() or raw_val)
                                    
                                    p_data[col_name] = clean_val
                                    if col_name not in player_keys:
                                        player_keys.append(col_name)
                                        
                            player_data_list.append(p_data)

                    time.sleep(1.5) # Protect IP limit between maps
                
                matches_processed += 1
                
            except Exception as e:
                print(f"❌ Failed to parse match {match_link}: {e}")
                
        if reached_cutoff:
            break 

        # 3. Handle Pagination
        next_page_element = page.css(".pagination-component.pagination-bottom a.pagination-next:not(.inactive)")
        if next_page_element and not TEST_MODE:
            next_href = next_page_element.css("::attr(href)").get()
            current_page_url = base_url + next_href if next_href.startswith('/') else next_href
            time.sleep(2) 
        else:
            current_page_url = None

    # 4. Output to CSVs (Append mode if we already have a file)
    match_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_match_info.csv")
    mode = "a" if os.path.exists(match_csv) else "w"
    with open(match_csv, mode=mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Event", "Date", "Map", "Team Left", "Team Right", "Team Left Rounds", "Team Right Rounds", "Total Rounds", "Winner", "Starting CT Team", "Match URL"])
        if mode == "w":
            writer.writeheader()
        writer.writerows(match_data_list)
        
    player_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_match_player_stats.csv")
    mode_player = "a" if os.path.exists(player_csv) else "w"
    with open(player_csv, mode=mode_player, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=player_keys)
        if mode_player == "w":
            writer.writeheader()
        writer.writerows(player_data_list)
        
    print(f"\n✅ Scraping completed!")
    print(f"Saved Match data to {match_csv}")
    print(f"Saved Player data to {player_csv}")

    # Clean up the stealth session
    session.close()

if __name__ == "__main__":
    scrape_hltv_results()