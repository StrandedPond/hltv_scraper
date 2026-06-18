import csv
import os
import time
import re
from datetime import datetime
from scrapling.fetchers import StealthySession

# Define the absolute cutoff date (Adjust the year if you meant 2024!)
CUTOFF_DATE = datetime(2025, 12, 7)
CSV_FILENAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_valve_rankings.csv")

def parse_hltv_date(header_text):
    """Extracts and parses the date from the HLTV ranking header text."""
    if not header_text:
        return None
        
    # Matches formats like "on June 8th, 2026" or "on May 1st, 2026"
    match = re.search(r'on\s+([A-Za-z]+)\s+(\d+)(?:st|nd|rd|th)?,\s+(\d{4})', header_text, re.IGNORECASE)
    if match:
        month_str, day_str, year_str = match.groups()
        date_str = f"{month_str} {day_str} {year_str}"
        try:
            return datetime.strptime(date_str, "%B %d %Y")
        except ValueError:
            return None
    return None

def scrape_valve_rankings():
    base_url = "https://www.hltv.org"
    
    # Start at the root Valve ranking page. HLTV automatically serves the latest available!
    # This natively bypasses the issue of "today's ELO hasn't updated yet".
    start_url = "https://www.hltv.org/valve-ranking/teams"
    
    # 1. Load previously scraped dates to avoid duplicating effort
    scraped_dates = set()
    all_keys = ["Date", "Rank", "Team", "Points"]
    file_exists = os.path.exists(CSV_FILENAME)
    
    if file_exists:
        with open(CSV_FILENAME, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "Date" in row and row["Date"]:
                    scraped_dates.add(row["Date"])
        print(f"Loaded {len(scraped_dates)} existing dates from {CSV_FILENAME}. These will be skipped.")

    with StealthySession(headless=True, solve_cloudflare=True) as session:
        current_page_url = start_url
        
        while current_page_url:
            print(f"\nNavigating to: {current_page_url}")
            page = session.fetch(current_page_url)
            
            # --- Date & Existence Check ---
            header_texts = page.css(".regional-ranking-header-text::text").getall()
            header_text = "".join(header_texts).strip()
            
            current_date = parse_hltv_date(header_text)
            
            if not current_date:
                print(f"❌ Could not parse date from header: '{header_text}'. The layout may have changed. Stopping.")
                break
                
            date_str_formatted = current_date.strftime("%Y-%m-%d")
            print(f" -> Found Ranking for Date: {date_str_formatted}")
            
            # Check against hard cutoff
            if current_date < CUTOFF_DATE:
                print(f"🛑 Reached {date_str_formatted}, which is older than our cutoff ({CUTOFF_DATE.strftime('%Y-%m-%d')}). Stopping.")
                break
                
            # --- Scraping Logic ---
            if date_str_formatted in scraped_dates:
                print(f"🛑 Already scraped data for {date_str_formatted}. Stopping scraper since we caught up.")
                break
            else:
                team_boxes = page.css("div.ranking div.ranked-team.standard-box")
                print(f" -> Extracting {len(team_boxes)} teams...")
                
                daily_data = []
                for index, box in enumerate(team_boxes):
                    team_name = box.css("span.name::text").get()
                    points_raw = box.css("span.points::text").get()
                    
                    # Clean points string from "(2004 Valve points)" to just "2004"
                    points = "".join(filter(str.isdigit, points_raw)) if points_raw else "0"
                    
                    if team_name:
                        daily_data.append({
                            "Date": date_str_formatted,
                            "Rank": index + 1,
                            "Team": team_name.strip(),
                            "Points": points
                        })
                
                # Append in real-time so we don't lose data if it crashes
                if daily_data:
                    with open(CSV_FILENAME, mode="a", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=all_keys)
                        if not file_exists:
                            writer.writeheader()
                            file_exists = True
                        writer.writerows(daily_data)
                        
                    scraped_dates.add(date_str_formatted)
                    print(f"✅ Saved {len(daily_data)} teams for {date_str_formatted}.")
                else:
                    print(f"⚠️ No teams found on {date_str_formatted}. Moving on.")
            
            # --- Pagination (Moving Backward in Time) ---
            prev_button = page.css(".pagination-prev")
            if prev_button:
                classes = prev_button.css("::attr(class)").get("")
                if "inactive" in classes:
                    print("🛑 Previous button is inactive. Reached the earliest available data on HLTV.")
                    break
                    
                next_href = prev_button.css("::attr(href)").get()
                if next_href:
                    current_page_url = base_url + next_href if next_href.startswith('/') else next_href
                    time.sleep(1.5) # Prevent rate limiting
                else:
                    break
            else:
                print("🛑 No previous pagination button found.")
                break

    print(f"\n🎉 Scraping completed!")

if __name__ == "__main__":
    scrape_valve_rankings()