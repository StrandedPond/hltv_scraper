import json
import time
import re
import os
from scrapling.fetchers import StealthySession

def fill_player_urls(json_file="player_urls.json"):
    # 1. Load the existing JSON file
    if not os.path.exists(json_file):
        print(f"❌ Error: Could not find '{json_file}' in the current directory.")
        return
        
    with open(json_file, 'r', encoding='utf-8') as f:
        player_data = json.load(f)
        
    # 2. Filter out players that already have a URL
    players_to_search = [name for name, url in player_data.items() if not url.strip()]
    
    print(f"📊 Found {len(player_data)} total players in {json_file}.")
    print(f"🔍 {len(players_to_search)} players still need URLs to be fetched.\n")
    
    if not players_to_search:
        print("✅ All players already have URLs assigned! Nothing to do.")
        return

    base_url = "https://www.hltv.org"
    search_base = "https://www.hltv.org/search?query="

    with StealthySession(headless=True, solve_cloudflare=True) as session:
        print("Initializing Scraper and bypassing Cloudflare...\n")
        
        # Ping the homepage once to establish clearance cookies
        session.fetch(base_url) 
        
        # 3. Loop through the missing players
        for i, player_name in enumerate(players_to_search, 1):
            print(f"[{i}/{len(players_to_search)}] 🔎 Searching for: '{player_name}'")
            search_url = f"{search_base}{player_name}"
            
            try:
                page = session.fetch(search_url)
                
                # Target links inside the search results tables
                links = page.css("table.table td a")
                match_found = False
                
                for link in links:
                    href = link.css("::attr(href)").get()
                    
                    # We only care about player or coach profiles
                    if not href or ("/player/" not in href and "/coach/" not in href):
                        continue
                        
                    # Extract the full text (e.g., "Peter 'stanislaw' Jarguz")
                    full_text = "".join(link.css("::text").getall()).strip()
                    
                    # Regex to find the string enclosed strictly in single quotes
                    alias_match = re.search(r"'([^']+)'", full_text)
                    
                    if alias_match:
                        extracted_alias = alias_match.group(1)
                        
                        # Case-insensitive comparison for exact match
                        if extracted_alias.lower() == player_name.lower():
                            
                            parts = href.strip('/').split('/')
                            if len(parts) >= 3:
                                player_id = parts[1]
                                player_nick = parts[2]
                                
                                # Construct the CS2 stats URL
                                stats_url = f"{base_url}/stats/players/{player_id}/{player_nick}?csVersion=CS2"
                                
                                # Update dictionary
                                player_data[player_name] = stats_url
                                print(f"  ✅ Found: {full_text} -> {stats_url}")
                                match_found = True
                                
                                # --- AUTO-SAVE PROGRESS ---
                                # We save after every successful match so you don't lose data if it crashes
                                with open(json_file, 'w', encoding='utf-8') as f:
                                    json.dump(player_data, f, indent=4)
                                    
                                break # Stop searching this page after the first exact match
                
                if not match_found:
                    print(f"  ❌ No exact single-quote match found for '{player_name}'")
                    
            except Exception as e:
                print(f"  ⚠️ Error searching for {player_name}: {e}")
                
            time.sleep(2) # Protect IP limit between searches

    print(f"\n🎉 Finished processing! Updated URLs are saved in {json_file}")

if __name__ == "__main__":
    fill_player_urls("player_urls.json")