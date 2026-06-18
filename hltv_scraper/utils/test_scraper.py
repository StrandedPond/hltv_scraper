from scrapling.fetchers import StealthySession
from interactive_url import parse_stats
import json

with StealthySession(headless=True, solve_cloudflare=True) as session:
    session.fetch("https://www.hltv.org")
    page_all = session.fetch("https://www.hltv.org/stats/players/19015/bymas?csVersion=CS2&startDate=all")
    page_lan = session.fetch("https://www.hltv.org/stats/players/19015/bymas?csVersion=CS2&startDate=all&matchType=Lan")
    page_ct1 = session.fetch("https://www.hltv.org/stats/players/19015/bymas?csVersion=CS2&startDate=all&side=COUNTER_TERRORIST")
    page_ct2 = session.fetch("https://www.hltv.org/stats/players/19015/bymas?csVersion=CS2&startDate=all&playerSide=COUNTER_TERRORIST")
    
    print("All KPR:", parse_stats(page_all).get("kpr"))
    print("Lan KPR:", parse_stats(page_lan).get("kpr"))
    print("CT1 KPR:", parse_stats(page_ct1).get("kpr"))
    print("CT2 KPR:", parse_stats(page_ct2).get("kpr"))
