import csv
import os
import time
import tempfile
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

from scrapling.fetchers import StealthySession

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_URL        = "https://www.hltv.org"
LEADERBOARD_URL = "https://www.hltv.org/stats/players?csVersion=CS2"
CSV_FILENAME    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../hltv_detailed_players.csv")

# ---------------------------------------------------------------------------
# CSV schema (Updated to reflect true data availability)
# ---------------------------------------------------------------------------
ALL_KEYS = [
    # Identity
    "name", "team", "team_side_start", "map",

    # ── Overall all-time · Both Sides ────────────────────────────────────
    "overall_rating",               
    "overall_rating_t",             
    "overall_rating_ct",            
    "overall_kpr",                  "overall_adr",
    "overall_kast",                 "overall_dpr",
    "overall_round_swing",          "overall_multi_kill",
    "overall_total_kills",          "overall_hs_rate",
    "overall_total_deaths",         "overall_kd_ratio",
    "overall_damage_per_round",     "overall_grenade_dmg_per_round",
    "overall_maps_played",          "overall_rounds_played",
    "overall_assists_per_round",    "overall_deaths_per_round",
    "overall_saved_by_teammate_per_round",
    "overall_saved_teammates_per_round",
    "overall_impact_rating",

    # ── Overall all-time · CT Side ────────────────────────────────────────
    "overall_ct_kpr",               "overall_ct_adr",
    
    # ── Overall all-time · T Side ─────────────────────────────────────────
    "overall_t_kpr",                "overall_t_adr",
    
    # ── Timeframe: last 1 month ──────────────────────────────────────────
    "kpr_1m",    "kpr_ct_1m",    "kpr_t_1m",
    "adr_1m",    "adr_ct_1m",    "adr_t_1m",
    "hs_rate_1m",
    "kast_1m",
    "rounds_played_1m", 

    # ── Timeframe: last 3 months ─────────────────────────────────────────
    "kpr_3m",    "kpr_ct_3m",    "kpr_t_3m",
    "adr_3m",    "adr_ct_3m",    "adr_t_3m",
    "hs_rate_3m",
    "kast_3m",
    "rounds_played_3m",

    # ── Timeframe: last 6 months ─────────────────────────────────────────
    "kpr_6m",    "kpr_ct_6m",    "kpr_t_6m",
    "adr_6m",    "adr_ct_6m",    "adr_t_6m",
    "hs_rate_6m",
    "kast_6m",
    "rounds_played_6m",

    # ── Per-map all-time · Both Sides (populated for ALL maps incl. "All") ─
    "kpr_map_both",         "adr_map_both",
    "hs_rate_map_both",     "kast_map_both",
    "rounds_played_map_both",

    # ── Per-map all-time · CT Side ────────────────────────────────────────
    "kpr_map_ct",           "adr_map_ct",
    
    # ── Per-map all-time · T Side ─────────────────────────────────────────
    "kpr_map_t",            "adr_map_t",
]

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def make_absolute(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE_URL + href

def inject_params(url: str, **kwargs) -> str:
    parsed   = urlparse(url)
    qs       = parse_qs(parsed.query, keep_blank_values=True)
    for k, v in kwargs.items():
        qs[k] = [str(v)]
    new_query = urlencode({k: v[0] for k, v in qs.items()})
    return urlunparse(parsed._replace(query=new_query))

# ---------------------------------------------------------------------------
# Stat parsers
# ---------------------------------------------------------------------------

def _safe_float(text: str) -> float | None:
    if not text: return None
    try:
        return float(text.replace("%", "").replace(",", "").strip())
    except (ValueError, AttributeError):
        return None

def _safe_int(text: str) -> int | None:
    if not text: return None
    try:
        return int(text.replace(",", "").strip())
    except (ValueError, AttributeError):
        return None

def parse_stats(page) -> dict:
    """Extract ALL stats visible on a player stats page."""
    stats = {}

    # ── 1. Summary box (Combined only) ────────────────────────────
    for box in page.css(".player-summary-stat-box-data-wrapper"):
        label_el = box.css(".player-summary-stat-box-data-text:not(.ecoAdjustedData)")
        val_el   = box.css(".player-summary-stat-box-data:not(.ecoAdjustedData)")
        
        label = "".join(label_el.css("::text").getall()).strip().upper()
        val   = "".join(val_el.css("::text").getall()).strip()
        
        if not label or not val: continue
            
        f = _safe_float(val.replace("%", "").strip())
        if f is None: continue
            
        if   "DPR"         in label: stats["dpr"]         = f
        elif "ROUND SWING" in label: stats["round_swing"]  = f
        elif "MULTI-KILL"  in label: stats["multi_kill"]   = f / 100.0
        elif "KAST"        in label: stats["kast"] = f / 100.0

    # ── 2. Ratings (Summary Box) ──────────────────────────────────
    rating_main = page.css(".player-summary-stat-box-rating-data-text::text").get()
    if rating_main:
        stats["rating"] = _safe_float(rating_main)

    for cls, key in [("t-rating", "rating_t"), ("ct-rating", "rating_ct")]:
        el = page.css(f".player-summary-stat-box-side-rating.{cls}")
        if el:
            for txt in el.css("::text").getall():
                v = _safe_float(txt.strip())
                if v is not None:
                    stats[key] = v
                    break

    # ── 3. Statistics table (Combined only) ───────────────────────
    STAT_ROW_MAP = {
        "Total kills":               ("total_kills",                 "int"),
        "Headshot %":                ("hs_rate",                     "pct"),
        "Total deaths":              ("total_deaths",                "int"),
        "K/D Ratio":                 ("kd_ratio",                   "float"),
        "Damage / Round":            ("adr",                        "float"), 
        "Grenade dmg / Round":       ("grenade_dmg_per_round",      "float"),
        "Maps played":               ("maps_played",                "int"),
        "Rounds played":             ("rounds_played",              "int"),
        "Kills / round":             ("kpr",                        "float"), 
        "Assists / round":           ("assists_per_round",          "float"),
        "Deaths / round":            ("deaths_per_round",           "float"),
        "Saved by teammate / round": ("saved_by_teammate_per_round","float"),
        "Saved teammates / round":   ("saved_teammates_per_round",  "float"),
        "Impact rating":             ("impact_rating",              "float"),
    }

    for row in page.css(".statistics .columns .stats-row, .columns .stats-row"):
        spans = row.css("span")
        if len(spans) < 2: continue
            
        label_raw = "".join(spans[0].css("::text").getall()).strip()
        val_raw = "".join(spans[1].css("::text").getall()).strip()
        
        for key_label, (field, cast) in STAT_ROW_MAP.items():
            if key_label in label_raw:
                if cast == "int":
                    stats[field] = _safe_int(val_raw)
                elif cast == "pct":
                    f = _safe_float(val_raw)
                    stats[field] = (f / 100.0) if f is not None else None
                else:
                    stats[field] = _safe_float(val_raw)
                break

    if "adr" in stats:
        stats["damage_per_round"] = stats["adr"]

    # ── 4. Role Stats Container (CT / T Splits for KPR and ADR) ───
    # This grabs exactly what is available in the DOM based on your analysis
    
    # Function to safely grab the data-original-value
    def get_role_stat(title, side_class):
        el = page.css(f".role-stats-row.stats-side-{side_class}[data-per-round-title='{title}']")
        if el:
            val = el.css("::attr(data-original-value)").get()
            return _safe_float(val)
        return None

    # CT Side
    ct_kpr = get_role_stat("Kills per round", "ct")
    ct_adr = get_role_stat("Damage per round", "ct")
    if ct_kpr is not None: stats["ct_kpr"] = ct_kpr
    if ct_adr is not None: stats["ct_adr"] = ct_adr
    
    # T Side
    t_kpr = get_role_stat("Kills per round", "t")
    t_adr = get_role_stat("Damage per round", "t")
    if t_kpr is not None: stats["t_kpr"] = t_kpr
    if t_adr is not None: stats["t_adr"] = t_adr
    
    # Combined (Fallback/Verification)
    comb_kpr = get_role_stat("Kills per round", "combined")
    comb_adr = get_role_stat("Damage per round", "combined")
    if comb_kpr is not None and "kpr" not in stats: stats["kpr"] = comb_kpr
    if comb_adr is not None and "adr" not in stats: stats["adr"] = comb_adr

    return stats


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

def fetch_leaderboard(session) -> list[dict]:
    print(f"\n📋 Fetching leaderboard from {LEADERBOARD_URL} …")
    page = session.fetch(LEADERBOARD_URL)

    players = []
    table   = page.css("table.stats-table.player-ratings-table")
    if not table:
        print("  ⚠️  Leaderboard table not found.")
        return players

    for row in table.css("tbody tr"):
        name_cell = row.css("td.playerCol a")
        team_cell = row.css("td.teamCol")
        if not name_cell: continue
            
        name = name_cell.css("::text").get("").strip()
        href = name_cell.css("::attr(href)").get("").strip()
        
        team = "no_team"
        if team_cell:
            team = team_cell.css("::attr(data-sort)").get("no_team").strip()
            
        if not name or not href: continue
            
        full_url = inject_params(make_absolute(href), csVersion="CS2", startDate="all")
        players.append({"name": name, "url": full_url, "team": team.lower()})

    print(f"  ✅ Found {len(players)} players on the leaderboard.")
    return players

def find_player_in_leaderboard(query: str, leaderboard: list[dict]) -> dict | None:
    q = query.lower()
    for p in leaderboard:
        if q in p["name"].lower(): return p
    return None


# ---------------------------------------------------------------------------
# Core scraper
# ---------------------------------------------------------------------------

def scrape_player(session, target_url: str, team_fallback: str = "no_team") -> None:
    target_url  = inject_params(target_url, csVersion="CS2", startDate="all")
    print(f"\n🔎 Navigating to: {target_url}")
    player_page = session.fetch(target_url)

    # ── Identity ──────────────────────────────────────────────────────────
    player_name = (
        player_page.css(".player-summary-stat-box-left-nickname.text-ellipsis::text").get()
        or player_page.css("h1.summaryNickname::text").get()
        or "Unknown_Player"
    ).strip()

    team_name = (
        player_page.css("a.player-summary-stat-box-left-team-logo-wrapper img::attr(title)").get() 
        or team_fallback
    ).strip().lower()

    print(f"👤 {player_name}  ({team_name.upper()})")

    # ── Overall all-time stats ────────────────────────────────────────────
    # Now we only need to fetch the page ONCE because the CT/T split is loaded in the DOM
    print("  -> Fetching overall stats (Both, CT, T)...")
    s_overall = parse_stats(player_page)                                  

    print(f"     overall_kpr={s_overall.get('kpr')} | ct_kpr={s_overall.get('ct_kpr')} | t_kpr={s_overall.get('t_kpr')}")

    overall_cols = {
        "overall_rating":                           s_overall.get("rating"),
        "overall_rating_t":                         s_overall.get("rating_t"),
        "overall_rating_ct":                        s_overall.get("rating_ct"),
        "overall_round_swing":                      s_overall.get("round_swing"),
        "overall_multi_kill":                       s_overall.get("multi_kill"),
        "overall_kd_ratio":                         s_overall.get("kd_ratio"),
        "overall_damage_per_round":                 s_overall.get("damage_per_round"),
        "overall_grenade_dmg_per_round":            s_overall.get("grenade_dmg_per_round"),
        "overall_maps_played":                      s_overall.get("maps_played"),
        "overall_saved_by_teammate_per_round":      s_overall.get("saved_by_teammate_per_round"),
        "overall_saved_teammates_per_round":        s_overall.get("saved_teammates_per_round"),
        
        "overall_kpr":                              s_overall.get("kpr"),
        "overall_adr":                              s_overall.get("adr"),
        "overall_kast":                             s_overall.get("kast"),
        "overall_dpr":                              s_overall.get("dpr"),
        "overall_hs_rate":                          s_overall.get("hs_rate"),
        "overall_rounds_played":                    s_overall.get("rounds_played"),
        "overall_total_kills":                      s_overall.get("total_kills"),
        "overall_total_deaths":                     s_overall.get("total_deaths"),
        "overall_assists_per_round":                s_overall.get("assists_per_round"),
        "overall_deaths_per_round":                 s_overall.get("deaths_per_round"),
        "overall_impact_rating":                    s_overall.get("impact_rating"),
        
        # New CT/T Extractions
        "overall_ct_kpr":                           s_overall.get("ct_kpr"),
        "overall_ct_adr":                           s_overall.get("ct_adr"),
        "overall_t_kpr":                            s_overall.get("t_kpr"),
        "overall_t_adr":                            s_overall.get("t_adr"),
    }
    
    # ── Timeframe stats ───────────────────────────────────────────────────
    time_options = player_page.css("select.stats-sub-navigation-simple-filter-time option")
    tf_data: dict = {}

    for option in time_options:
        option_text = (option.css("::text").get() or "").strip().lower()
        if   option_text == "last month":      tf = "1m"
        elif option_text == "last 3 months":   tf = "3m"
        elif option_text == "last 6 months":   tf = "6m"
        else: continue

        data_link = option.css("::attr(data-link)").get()
        if not data_link: continue

        # Only one fetch per timeframe now!
        time_url = make_absolute(data_link)
        tf_page  = session.fetch(time_url)
        s_tf     = parse_stats(tf_page)

        tf_data[f"kpr_{tf}"]           = s_tf.get("kpr")
        tf_data[f"adr_{tf}"]           = s_tf.get("adr")
        tf_data[f"hs_rate_{tf}"]       = s_tf.get("hs_rate")
        tf_data[f"rounds_played_{tf}"] = s_tf.get("rounds_played")
        tf_data[f"kast_{tf}"]          = s_tf.get("kast")
        
        # Pull the CT/T split explicitly
        tf_data[f"kpr_ct_{tf}"]        = s_tf.get("ct_kpr")
        tf_data[f"adr_ct_{tf}"]        = s_tf.get("ct_adr")
        tf_data[f"kpr_t_{tf}"]         = s_tf.get("t_kpr")
        tf_data[f"adr_t_{tf}"]         = s_tf.get("t_adr")

        print(f"  -> {tf} | KPR: {s_tf.get('kpr')} (CT: {s_tf.get('ct_kpr')} / T: {s_tf.get('t_kpr')})")
        time.sleep(1.5)

    # ── Per-map stats ─────────────────────────────────────────────────────
    map_elements = player_page.css(".stats-sub-navigation-simple-filter-map-hover .stats-sub-map-grid .stats-sub-map a")
    map_targets: list[tuple[str, str]] = []

    for el in map_elements:
        m_name = (el.css("::text").get() or "Unknown").strip()
        m_href = el.css("::attr(href)").get() or ""
        if not m_href: continue
        map_targets.append((m_name, make_absolute(m_href)))

    print(f"  -> {len(map_targets)} map entries found")

    # ── Write CSV ─────────────────────────────────────────────────────────
    needs_header = not os.path.exists(CSV_FILENAME) or os.path.getsize(CSV_FILENAME) == 0
    with open(CSV_FILENAME, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ALL_KEYS, extrasaction="ignore")
        if needs_header:
            writer.writeheader()

        for m_name, m_url in map_targets:
            # We only need ONE fetch per map now!
            s_map = parse_stats(session.fetch(m_url))
            time.sleep(1.5)

            row = {
                "name":             player_name,
                "team":             team_name,
                "team_side_start":  "N/A",
                "map":              m_name,
                "kpr_map_both":          s_map.get("kpr"),
                "adr_map_both":          s_map.get("adr"),
                "hs_rate_map_both":      s_map.get("hs_rate"),
                "kast_map_both":         s_map.get("kast"),
                "rounds_played_map_both": s_map.get("rounds_played"),
                "kpr_map_ct":            s_map.get("ct_kpr"),
                "adr_map_ct":            s_map.get("ct_adr"),
                "kpr_map_t":             s_map.get("t_kpr"),
                "adr_map_t":             s_map.get("t_adr"),
            }
            row.update(overall_cols)
            row.update(tf_data)
            writer.writerow(row)

            tag = "(All maps)" if m_name.lower() == "all" else f"map {m_name}"
            print(f"     -> {tag:<18}  "
                  f"ct_kpr={s_map.get('ct_kpr')}  t_kpr={s_map.get('t_kpr')}")
            
    print(f"✅ Done — {player_name}'s stats saved to {CSV_FILENAME}!")


# ---------------------------------------------------------------------------
# Interactive entry point
# ---------------------------------------------------------------------------

def main() -> None:
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../player_urls.json")
    if not os.path.exists(json_path):
        print(f"Cannot find {json_path}")
        return
        
    import json
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        queue = []
        for player_name, url in data.items():
            url = url.strip()
            if url:
                if "hltv.org/stats/players/" not in url:
                    print(f"Skipping invalid URL for {player_name}: {url}")
                else:
                    queue.append((url, "no_team"))
                    
        if not queue:
            print("No URLs found filled out in player_urls.json.")
            return
            
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    print(f"\nQueue: {len(queue)} player(s) to scrape.")
    
    with StealthySession(headless=True, solve_cloudflare=True) as session:
        print("Initializing scraper - bypassing Cloudflare...")
        session.fetch(BASE_URL)

        for i, (target_url, team_fallback) in enumerate(queue, 1):
            try:
                scrape_player(session, target_url, team_fallback)
            except Exception as exc:
                print(f"  Scraping failed: {exc}")

        print(f"\nQueue complete -- {len(queue)} player(s) processed.")

if __name__ == "__main__":
    main()