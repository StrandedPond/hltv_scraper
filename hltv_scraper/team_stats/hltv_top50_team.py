import os
import sys
import csv
import time
from scrapling.fetchers import StealthySession

# Allow importing from sibling utils directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "utils"))
try:
    from utils.roster_continuity import get_changed_teams
except ImportError:
    def get_changed_teams():
        return set()

def scrape_hltv_teams():
    team_stats = []
    
    # We maintain a dynamic list of keys so that any new stat boxes HLTV adds 
    # will automatically become columns in the CSV without breaking the script.
    all_keys = ["Team", "Timeframe", "Profile URL"]
    csv_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_cs2_all_teams.csv")
    scraped_teams = set()

    # --- Load teams with major roster changes so they are force re-scraped ---
    changed_teams = get_changed_teams()
    if changed_teams:
        print(f"\n⚠️  Roster continuity: {len(changed_teams)} team(s) flagged for force re-scrape:")
        for t in sorted(changed_teams):
            print(f"   • {t}")
        print()

    # --- NEW: Check if file exists and load existing data ---
    if os.path.exists(csv_filename):
        print(f"Found existing file: {csv_filename}. Loading previous data...")
        with open(csv_filename, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            # Load existing column headers
            if reader.fieldnames:
                for key in reader.fieldnames:
                    if key not in all_keys:
                        all_keys.append(key)
            
            # Load existing rows and track completed teams
            for row in reader:
                team_stats.append(row)
                if "Team" in row and row["Team"]:
                    scraped_teams.add(row["Team"])
                    
        print(f"Loaded {len(scraped_teams)} previously scraped teams. These will be skipped.\n")
    # --------------------------------------------------------

    with StealthySession(headless=True, solve_cloudflare=True) as session:
        print("Navigating to HLTV CS2 Top 50 Teams page and bypassing Cloudflare...")
        
        # 1. Fetch the main Top 50 teams page
        page = session.fetch("https://www.hltv.org/stats/teams?csVersion=CS2&startDate=all")
        
        # 2. Extract Team Names and URLs from the leaderboard table
        teams = []
        base_url = "https://www.hltv.org"
        
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
        
        print(f"Found {len(teams)} teams in the Top 50. Starting extraction...\n")

        # 3. Iterate through each team
        for i, team in enumerate(teams):
            team_name = team['name']
            
            # --- Skip if already scraped, UNLESS roster changed significantly ---
            if team_name in scraped_teams:
                if team_name.lower() in changed_teams:
                    print(f"[{i+1}/{len(teams)}] Force re-scraping: {team_name} (major roster change detected ⚠️ )")
                    # Remove stale rows for this team so we write fresh data
                    team_stats[:] = [r for r in team_stats if r.get("Team", "").lower() != team_name.lower()]
                else:
                    print(f"[{i+1}/{len(teams)}] Skipping Team: {team_name} (Already scraped, roster stable)")
                    continue
            # --------------------------------------------
            
            print(f"[{i+1}/{len(teams)}] Processing Team: {team_name}")
            
            try:
                # Fetch the base team page to read its unique timeframe dropdown options
                team_page = session.fetch(team['url'])
                time_options = team_page.css("select.stats-sub-navigation-simple-filter-time option")
                
                if not time_options:
                    print(f"  -> No timeframe dropdown found for {team_name}. Skipping.")
                    time.sleep(2)
                    continue

                # 4. Iterate through the target timeframes
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
                            "Team": team_name,
                            "Timeframe": time_label,
                            "Profile URL": team['url']
                        }
                        
                        # 5. Locate the standard metric boxes
                        boxes = stats_page.css(".columns .col.standard-box.big-padding")
                        
                        for box in boxes:
                            label = box.css(".small-label-below::text").get()
                            value = box.css(".large-strong::text").get() or box.css(".large.strong::text").get()
                            
                            if label and value:
                                label = label.strip()
                                value = value.strip()
                                
                                # 6. Split Wins / draws / losses
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
                                        
                        team_stats.append(data)
                        print(f"  -> Scraped timeframe: {time_label}")
                        
                        time.sleep(2)
                        
            except Exception as e:
                print(f"Failed to scrape {team_name}: {e}")

    # 7. Output everything back to the CSV (Overwrite with combined data)
    with open(csv_filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys)
        writer.writeheader()
        writer.writerows(team_stats)
        
    print(f"\nScraping completed! Data strictly saved to {csv_filename}")

if __name__ == "__main__":
    scrape_hltv_teams()