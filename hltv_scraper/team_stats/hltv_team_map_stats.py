import os
import csv
import time
from scrapling.fetchers import StealthySession

def scrape_hltv_team_maps():
    team_map_stats = []
    
    # Dynamic list of keys, prepopulated with our core identifiers
    all_keys = ["Team", "Map", "Timeframe", "Profile URL"]
    csv_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_cs2_team_map_stats.csv")
    scraped_teams = set()
    
    if os.path.exists(csv_filename):
        print(f"Found existing file: {csv_filename}. Loading previous data...")
        with open(csv_filename, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                for key in reader.fieldnames:
                    if key not in all_keys:
                        all_keys.append(key)
            for row in reader:
                team_map_stats.append(row)
                if "Team" in row and row["Team"]:
                    scraped_teams.add(row["Team"])
        print(f"Loaded {len(scraped_teams)} previously scraped teams (Note: we will update them).\n")
    
    with StealthySession(headless=True, solve_cloudflare=True) as session:
        print("Navigating to HLTV CS2 Top 50 Teams page and bypassing Cloudflare...")
        
        # 1. Fetch the main Top 50 teams page
        page = session.fetch("https://www.hltv.org/stats/teams?csVersion=CS2&startDate=all")
        
        teams = []
        base_url = "https://www.hltv.org"
        
        # Isolate the main table and extract all anchor tags pointing to team profiles
        for row in page.css("table.stats-table tbody tr"):
            a_tag = row.css("td a[href*='/stats/teams/']")
            if a_tag:
                href = a_tag.css("::attr(href)").get()
                name = a_tag.css("::text").get()
                
                if href and name:
                    full_url = base_url + href if href.startswith('/') else href
                    teams.append({
                        "name": name.strip(),
                        "url": full_url
                    })
        
        print(f"Found {len(teams)} teams. Starting Maps extraction...\n")

        # 2. Iterate through each team
        for i, team in enumerate(teams):
            print(f"[{i+1}/{len(teams)}] Processing Team: {team['name']}")
            
            try:
                # Fetch the base team page
                team_page = session.fetch(team['url'])
                
                # 3. Target the first .tabs.standard-box inside .stats-top-menu
                tabs_boxes = team_page.css(".stats-top-menu .tabs.standard-box")
                if not tabs_boxes:
                    continue
                    
                # Find the anchor with text "Maps"
                maps_link = None
                for a in tabs_boxes[0].css("a"):
                    text = a.css("::text").get()
                    if text and "Maps" in text:
                        maps_link = a.css("::attr(href)").get()
                        break
                        
                if not maps_link:
                    print(f"  -> Could not find 'Maps' tab for {team['name']}. Skipping.")
                    time.sleep(2)
                    continue
                    
                # Fetch the Maps hub page for the team
                maps_url = base_url + maps_link if maps_link.startswith('/') else maps_link
                maps_page = session.fetch(maps_url)
                
                # 4. Target the second .tabs.standard-box which contains all the specific map links
                maps_tabs_boxes = maps_page.css(".stats-top-menu .tabs.standard-box")
                if len(maps_tabs_boxes) < 2:
                    continue
                    
                map_anchors = maps_tabs_boxes[1].css("a")
                
                # 5. Iterate through every map in that second box
                for map_a in map_anchors:
                    map_name = (map_a.css("::text").get() or "Unknown").strip()
                    map_href = map_a.css("::attr(href)").get()
                    
                    if not map_href:
                        continue
                        
                    map_url = base_url + map_href if map_href.startswith('/') else map_href
                    individual_map_page = session.fetch(map_url)
                    
                    # Extract timeframe options from this specific map page
                    time_options = individual_map_page.css("select.stats-sub-navigation-simple-filter-time option")
                    
                    # 6. Iterate through the target timeframes
                    for option in time_options:
                        option_text = (option.css("::text").get() or "").strip().lower()
                        
                        if option_text in ["last month", "last 3 months", "last 6 months", "last 12 months"]:
                            if "3" in option_text:
                                time_label = "Last 3 Months"
                            elif "6" in option_text:
                                time_label = "Last 6 Months"
                            elif "12" in option_text:
                                time_label = "Last 12 Months"
                            else:
                                time_label = "Last Month"
                                
                            data_link = option.css("::attr(data-link)").get()
                            if not data_link:
                                continue
                                
                            time_url = base_url + data_link if data_link.startswith('/') else data_link
                            stats_page = session.fetch(time_url)
                            
                            data = {
                                "Team": team['name'],
                                "Map": map_name,
                                "Timeframe": time_label,
                                "Profile URL": team['url']
                            }
                            
                            # 7. Locate the row stats inside .stats-rows.standard-box
                            stats_rows = stats_page.css(".stats-rows.standard-box .stats-row")
                            
                            for row in stats_rows:
                                # Target text blocks directly inside child spans to bypass tag layout changes
                                span_texts = [t.strip() for t in row.css("span::text").getall() if t.strip()]
                                
                                if len(span_texts) >= 2:
                                    label = span_texts[0]
                                    value = span_texts[1]
                                    
                                    # 8. Handle the specific "Wins / draws / losses" split request
                                    if label.lower() == "wins / draws / losses":
                                        parts = [p.strip() for p in value.split('/')]
                                        data["Wins"] = parts[0] if len(parts) > 0 else "0"
                                        data["Draws"] = parts[1] if len(parts) > 1 else "0"
                                        data["Losses"] = parts[2] if len(parts) > 2 else "0"
                                        
                                        for k in ["Wins", "Draws", "Losses"]:
                                            if k not in all_keys:
                                                all_keys.append(k)
                                    else:
                                        data[label] = value
                                        if label not in all_keys:
                                            all_keys.append(label)
                                            
                            team_map_stats.append(data)
                            print(f"  -> Scraped: {map_name} | {time_label} (Played: {data.get('Times played', '0')})")
                            
                            # Standard delay to safe-proof session handling
                            time.sleep(2)
                            
            except Exception as e:
                print(f"Failed to scrape {team['name']}: {e}")

    # 9. Output to CSV
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
        # Dynamically constructed headers map the arbitrary stats to columns
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(team_map_stats)
        
    print(f"\nScraping completed! Data successfully saved to {csv_filename}")

if __name__ == "__main__":
    scrape_hltv_team_maps()