import sys
from scrapling import Fetcher
from scrapling.fetchers import StealthySession

def run_tests():
    print("Starting tests for HLTV Results Scraper CSS Selectors...")
    fetcher = Fetcher()
    base_url = "https://www.hltv.org"
    
    try:
        # 1. Download first results page
        url = "https://www.hltv.org/results?stars=1"
        print(f"Fetching {url} ...")
        page = fetcher.get(url)
        
        # Verify outer containers on results page
        content_col_list = page.css(".contentCol")
        content_col = content_col_list[0] if content_col_list else None
        if not content_col:
            print("[FAIL] .contentCol not found on results page")
            sys.exit(1)
        print("[OK] contentCol found")
        
        results_list = content_col.css(".results")
        results = results_list[0] if results_list else None
        if not results:
            print("[FAIL] .results not found")
            sys.exit(1)
        print("[OK] results found")
        
        results_holder_list = results.css(".results-holder.allres")
        results_holder = results_holder_list[0] if results_holder_list else None
        if not results_holder:
            print("[FAIL] .results-holder.allres not found")
            sys.exit(1)
        print("[OK] results-holder found")
        
        matches = results_holder.css(".result-con")
        if not matches:
            print("[FAIL] .result-con not found")
            sys.exit(1)
        print(f"[OK] matches found: {len(matches)}")
        
        # Follow the first match link
        match_href = matches[0].css("a.a-reset")[0].attrib.get("href")
        match_url = base_url + match_href
        print(f"\nFetching match page: {match_url} ...")
        match_page = fetcher.get(match_url)
        
        # Find stats link
        stats_links = [a.attrib.get('href') for a in match_page.css("a") 
                       if a.attrib.get('href') and '/stats/matches/' in a.attrib.get('href') and 'mapstatsid' not in a.attrib.get('href')]
        
        if not stats_links:
            print("[FAIL] Could not find stats page link on match page")
            sys.exit(1)
            
        stats_url = base_url + stats_links[0]
        print(f"\nFetching stats page (via StealthySession): {stats_url} ...")
        
        with StealthySession(headless=True, solve_cloudflare=True) as session:
            stats_page = session.fetch(stats_url)
            
            match_info_box_list = stats_page.css(".match-info-box")
            match_info_box = match_info_box_list[0] if match_info_box_list else None
            if not match_info_box:
                print("[FAIL] .match-info-box not found on stats page")
                sys.exit(1)
            print("[OK] match-info-box found")
            
            match_page_link_list = stats_page.css("a.match-page-link.button")
            match_page_link = match_page_link_list[0] if match_page_link_list else None
            if not match_page_link:
                print("[FAIL] a.match-page-link.button not found")
                sys.exit(1)
            print("[OK] match-page-link found")
            
            stats_content_list = stats_page.css(".stats-content")
            if not stats_content_list:
                print("[FAIL] .stats-content not found")
                sys.exit(1)
            print(f"[OK] stats-content sections found: {len(stats_content_list)}")
            
        print("\nAll checks passed successfully!")
        sys.exit(0)
        
    except Exception as e:
        print(f"\nAn error occurred during testing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
