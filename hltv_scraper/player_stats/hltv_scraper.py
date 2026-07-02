import json
import time
import os
import sys
_PARENT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, _PARENT)
from utils.hltv_session import make_session, safe_fetch, jitter_sleep

def parse_stats(page):
    """Helper function to extract stats from the page layout."""
    stats = {}
    
    # 1. Parse the new bottom boxes for KPR, ADR, KAST
    boxes = page.css(".player-summary-stat-box-data-wrapper")
    for box in boxes:
        # Extract immediate text node to avoid grabbing tooltip text
        label = box.css(".player-summary-stat-box-data-text.traditionalData::text").get()
        val_text = box.css(".player-summary-stat-box-data.traditionalData::text").get()
        
        if label and val_text:
            label = label.strip().upper()
            val_text = val_text.replace('%', '').strip()
            
            try:
                if "KPR" in label:
                    stats['kpr'] = float(val_text)
                elif "ADR" in label:
                    stats['adr'] = float(val_text)
                elif "KAST" in label:
                    stats['kast'] = float(val_text) / 100.0  # Convert 67.3% to 0.673
            except ValueError:
                pass

    # 2. Parse the traditional column rows for HS% and Rounds
    for row in page.css(".columns .stats-row"):
        spans = [s.strip() for s in row.css("span::text").getall() if s.strip()]
        if len(spans) >= 2:
            label = spans[0]
            val = spans[1].replace('%', '')
            try:
                if "Headshot %" in label:
                    stats['hs_rate'] = float(val) / 100.0 # Convert 63.4% to 0.634
                elif "Rounds played" in label:
                    stats['rounds_played'] = int(val)
            except ValueError:
                pass
                
    return stats

def scrape_hltv_players_maps():
    all_data = []
    base_url = "https://www.hltv.org"
    
    import os
    json_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_players_maps_stats.json")
    scraped_players = set()
    if os.path.exists(json_filename):
        print(f"Found existing file: {json_filename}. Loading previous data...")
        with open(json_filename, "r", encoding="utf-8") as f:
            try:
                existing_data = json.load(f)
                all_data.extend(existing_data)
                for row in existing_data:
                    if "name" in row:
                        scraped_players.add(row["name"])
            except json.JSONDecodeError:
                pass
        print(f"Loaded {len(scraped_players)} previously scraped players (Note: we will update them).\n")
    
    with make_session() as session:
        print("Navigating to HLTV CS2 players page …")

        page = safe_fetch(session, "https://www.hltv.org/stats/players?csVersion=CS2&startDate=all", jitter=False)
        if page is None:
            print("ERROR: Could not load player leaderboard. Aborting.")
            return
        hrefs = page.css("table.stats-table.player-ratings-table td.playerCol a::attr(href)").getall()
        full_hrefs = [base_url + href if href.startswith('/') else href for href in hrefs]
        
        print(f"Found {len(full_hrefs)} players. Starting extraction...\n")

        # Use [:2] here if you want to test it quickly before running the full list
        for i, link in enumerate(full_hrefs):
            try:
                player_page = safe_fetch(session, link)
                if player_page is None:
                    print(f"[{i+1}/{len(full_hrefs)}] Skipping (fetch failed): {link}")
                    continue
                
                # Extract Player Name
                player_name = player_page.css(".player-summary-stat-box-left-nickname.text-ellipsis::text").get()
                if not player_name:
                    player_name = player_page.css("h1.summaryNickname::text").get()
                player_name = player_name.strip() if player_name else f"Unknown_{i}"

                # Extract Team Name
                team_name = player_page.css("a.player-summary-stat-box-left-team-logo-wrapper.a-reset.text-ellipsis img::attr(title)").get()
                team_name = team_name.strip().lower() if team_name else "no_team"

                print(f"[{i+1}/{len(full_hrefs)}] Processing: {player_name}")

                # --- PART 1: OVERALL TIMEFRAMES ---
                time_options = player_page.css("select.stats-sub-navigation-simple-filter-time option")
                overall_stats = {}
                
                for option in time_options:
                    option_text = (option.css("::text").get() or "").strip().lower()
                    data_link = option.css("::attr(data-link)").get()
                    if not data_link:
                        continue
                        
                    time_url = base_url + data_link if data_link.startswith('/') else data_link
                    
                    if option_text == "last month":
                        tf_page = safe_fetch(session, time_url)
                        if tf_page is None: continue
                        stats = parse_stats(tf_page)
                        overall_stats.update({
                            "kpr_1m": stats.get('kpr'), "hs_rate_1m": stats.get('hs_rate'),
                            "adr_1m": stats.get('adr'), "rounds_played_1m": stats.get('rounds_played'),
                            "kast_1m": stats.get('kast')
                        })
                        jitter_sleep(1)

                    elif option_text == "last 3 months":
                        tf_page = safe_fetch(session, time_url)
                        if tf_page is None: continue
                        stats = parse_stats(tf_page)
                        overall_stats.update({
                            "kpr_3m": stats.get('kpr'), "hs_rate_3m": stats.get('hs_rate'),
                            "adr_3m": stats.get('adr'), "rounds_played_3m": stats.get('rounds_played'),
                            "kast_3m": stats.get('kast')
                        })
                        jitter_sleep(1)

                    elif option_text == "last 6 months":
                        tf_page = safe_fetch(session, time_url)
                        if tf_page is None: continue
                        stats = parse_stats(tf_page)
                        overall_stats.update({
                            "kpr_6m": stats.get('kpr'), "hs_rate_6m": stats.get('hs_rate'),
                            "adr_6m": stats.get('adr'), "rounds_played_6m": stats.get('rounds_played'),
                            "kast_6m": stats.get('kast')
                        })
                        jitter_sleep(1)

                # --- PART 2: PER MAP STATS ---
                map_elements = player_page.css(".stats-sub-navigation-simple-filter-map-hover a:not(.stats-sub-map-grid)")
                
                for map_el in map_elements:
                    map_name = (map_el.css("::text").get() or "Unknown").strip()
                    map_href = map_el.css("::attr(href)").get()
                    if not map_href:
                        continue
                        
                    map_url = base_url + map_href if map_href.startswith('/') else map_href
                    map_page = safe_fetch(session, map_url)
                    if map_page is None:
                        continue
                    map_stats = parse_stats(map_page)
                    
                    # Construct the final flattened JSON object for this Player + Map
                    row_data = {
                        "name": player_name,
                        "team": team_name,
                        "team_side": None,
                        "map": map_name,
                        
                        # Timeframe stats
                        "kpr_1m": overall_stats.get('kpr_1m'),
                        "kpr_3m": overall_stats.get('kpr_3m'),
                        "kpr_6m": overall_stats.get('kpr_6m'),
                        
                        # Map stats
                        "kpr_map": map_stats.get('kpr'),
                        "kpr_map_sample": map_stats.get('rounds_played'),
                        
                        "hs_rate_1m": overall_stats.get('hs_rate_1m'),
                        "hs_rate_3m": overall_stats.get('hs_rate_3m'),
                        "hs_rate_6m": overall_stats.get('hs_rate_6m'),
                        
                        "hs_rate_map": map_stats.get('hs_rate'),
                        "hs_rate_map_sample": map_stats.get('rounds_played'),
                        
                        "adr_1m": overall_stats.get('adr_1m'),
                        "adr_3m": overall_stats.get('adr_3m'),
                        "adr_6m": overall_stats.get('adr_6m'),
                        
                        "rounds_played_1m": overall_stats.get('rounds_played_1m'),
                        "rounds_played_3m": overall_stats.get('rounds_played_3m'),
                        "rounds_played_6m": overall_stats.get('rounds_played_6m'),
                        
                        "kast_1m": overall_stats.get('kast_1m'),
                        "kast_3m": overall_stats.get('kast_3m'),
                        "kast_6m": overall_stats.get('kast_6m')
                    }
                    
                    all_data.append(row_data)
                    print(f"  -> Scraped Map: {map_name}")
                    jitter_sleep(2)
                        
            except Exception as e:
                print(f"Failed to scrape {link}: {e}")

    # Output to JSON
    with open(json_filename, mode="w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=4)
        
    print(f"\nScraping completed! Data saved to {json_filename}")

if __name__ == "__main__":
    scrape_hltv_players_maps()