import re

class Parser:
    @staticmethod
    def parse_stats_page(page, match_url):
        # We might have multiple .match-info-box-con on some pages, but usually it's one per map on the individual map stats page.
        # But wait! On the overall stats page there are multiple maps!
        # The spec says: "For every map block: Store a separate record."
        
        results = []
        
        # We need to find each map's container.
        # On the overall stats page, there is a .flexbox-column with .mapholder for multi-map, and .match-info-box-con for each map.
        # Wait, if we are fetching the individual map stats pages instead of overall?
        # Actually, the user's tester.py grabs the stats page link. If it's overall, we must parse each map.
        # But wait! The HTML pasted by the user has the match-info-box. If we use the individual map link (like /stats/matches/mapstatsid/...), there is exactly one match-info-box.
        
        # Let's handle the page by finding all .match-info-box
        match_boxes = page.css(".match-info-box-con")
        if not match_boxes:
            # Fallback if the container name is slightly different
            match_boxes = [page]
            
        for box_con in match_boxes:
            info_box = box_con.css(".match-info-box")
            if not info_box:
                continue
            
            info_box = info_box[0]
            
            # Event
            event_el = info_box.css("a[href*='event']")
            event = event_el[0].text.strip() if event_el else ""
            
            # Date
            date_el = info_box.css(".small-text span[data-unix]")
            date = date_el[0].text.strip() if date_el else ""
            
            # Map name (it's a text node right after .small-text)
            # A bit tricky to extract text node directly in scrapling sometimes.
            # Let's get the full text of info_box and find the map name.
            # Usually the map name is something like "Mirage" "Dust2" etc.
            # The HTML looks like: <div class="small-text">...</div>\nMirage\n<div class="team-left">
            map_name = "Unknown"
            html_content = info_box.html_content
            map_match = re.search(r'</div>\s*([a-zA-Z0-9]+)\s*<div class="team-left">', html_content)
            if map_match:
                map_name = map_match.group(1).strip()
            
            # Teams
            team_left_el = info_box.css(".team-left a")
            team_left = team_left_el[0].text.strip() if team_left_el else "Unknown1"
            
            team_right_el = info_box.css(".team-right a")
            team_right = team_right_el[0].text.strip() if team_right_el else "Unknown2"
            
            # Scores
            score_left_el = info_box.css(".team-left .bold")
            score_left = score_left_el[0].text.strip() if score_left_el else "0"
            
            score_right_el = info_box.css(".team-right .bold")
            score_right = score_right_el[0].text.strip() if score_right_el else "0"
            
            # Winner
            winner = None
            if info_box.css(".team-left .won"):
                winner = team_left
            elif info_box.css(".team-right .won"):
                winner = team_right
            
            # Breakdown Parsing
            rounds_left = score_left
            rounds_right = score_right
            total_rounds = str(int(score_left) + int(score_right)) if score_left.isdigit() and score_right.isdigit() else "0"
            
            first_half_left = "0"
            first_half_right = "0"
            second_half_left = "0"
            second_half_right = "0"
            left_team_started = "Unknown"
            
            match_info_rows = box_con.css(".match-info-row")
            for row in match_info_rows:
                bold_text = row.css(".bold")[0].text.strip() if row.css(".bold") else ""
                if "Breakdown" in bold_text:
                    right_html = row.css(".right")[0].html_content if row.css(".right") else ""
                    # The right html looks like:
                    # <span class="won">13</span> : <span class="lost">7</span> ( <span class="ct-color">10</span> : <span class="t-color">2</span> ) ( <span class="t-color">3</span> : <span class="ct-color">5</span> )
                    # Find all ct-color and t-color
                    spans = re.findall(r'<span class="(ct-color|t-color)">(\d+)</span>', right_html)
                    if len(spans) >= 4:
                        first_half_left = spans[0][1]
                        first_half_right = spans[1][1]
                        second_half_left = spans[2][1]
                        second_half_right = spans[3][1]
                        
                        if spans[0][0] == "ct-color":
                            left_team_started = "CT"
                        else:
                            left_team_started = "T"
            
            match_data = {
                "event": event,
                "date": date,
                "map": map_name,
                "team_left": team_left,
                "team_right": team_right,
                "score_left": score_left,
                "score_right": score_right,
                "first_half_left": first_half_left,
                "first_half_right": first_half_right,
                "second_half_left": second_half_left,
                "second_half_right": second_half_right,
                "total_rounds": total_rounds,
                "winner": winner,
                "left_team_started": left_team_started,
                "match_url": match_url
            }
            
            # Player stats
            players_data = []
            
            # Find the stats-content tables.
            # Assuming we fetch individual map stats pages, there are just the tables for this map.
            stats_tables = page.css("table.stats-table.totalstats")
                
            for table in stats_tables:
                # Team name from header
                th_team = table.css("thead th.st-teamname")
                team_name = "Unknown"
                if th_team:
                    team_name = th_team[0].text.strip()
                    if not team_name:
                        img = th_team[0].css("img")
                        if img:
                            team_name = img[0].attrib.get('title', 'Unknown')
                
                rows = table.css("tbody tr")
                for row in rows:
                    player_name_el = row.css(".st-player a")
                    player_name = player_name_el[0].text.strip() if player_name_el else "Unknown"
                    
                    # Extract values (ignoring the gtSmartphone-only spans if they duplicate or contain parenthesis)
                    def extract_stat(td_selector):
                        td = row.css(td_selector)
                        if not td: return ""
                        # get direct text nodes before any <span> like (10)
                        # We can just get text and split by space or paren
                        full_text = td[0].text.strip()
                        return full_text.split("(")[0].strip()
                        
                    opening_kd = extract_stat(".st-opkd.traditional-data")
                    if not opening_kd:
                        # fallback
                        opening_kd = extract_stat(".st-opkd:not(.eco-adjusted-data)")
                        
                    multi_kills = extract_stat(".st-mks")
                    
                    kast = extract_stat(".st-kast.traditional-data") or extract_stat(".st-kast:not(.eco-adjusted-data)")
                    if kast and '%' in kast:
                        try:
                            kast = f"{(float(kast.replace('%', '')) / 100.0):.3f}"
                        except ValueError:
                            pass
                            
                    clutches = extract_stat(".st-clutches")
                    
                    kills_full = row.css(".st-kills.traditional-data") or row.css(".st-kills:not(.eco-adjusted-data)")
                    kills = ""
                    headshots = "0"
                    if kills_full:
                        kills = kills_full[0].text.strip()
                        hs_span = kills_full[0].css("span")
                        if hs_span:
                            headshots = hs_span[0].text.replace("(", "").replace(")", "").strip()
                            
                    assists = extract_stat(".st-assists")
                    deaths = extract_stat(".st-deaths.traditional-data") or extract_stat(".st-deaths:not(.eco-adjusted-data)")
                    adr = extract_stat(".st-adr.traditional-data") or extract_stat(".st-adr:not(.eco-adjusted-data)")
                    round_swing = extract_stat(".st-roundSwing")
                    rating = extract_stat(".st-rating")
                    
                    player_data = {
                        "event": event,
                        "date": date,
                        "map": map_name,
                        "team": team_name,
                        "player_name": player_name,
                        "opening_kd": opening_kd,
                        "multi_kills": multi_kills,
                        "kast": kast,
                        "clutches": clutches,
                        "kills": kills,
                        "headshots": headshots,
                        "assists": assists,
                        "deaths": deaths,
                        "adr": adr,
                        "round_swing": round_swing,
                        "rating": rating
                    }
                    players_data.append(player_data)
            
            results.append({
                "match_data": match_data,
                "players_data": players_data
            })
            
        return results

