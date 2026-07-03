import csv
import os

class Exporter:
    def __init__(self, matches_file=None, players_file=None):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.matches_file = matches_file or os.path.join(base_dir, "../matches.csv")
        self.players_file = players_file or os.path.join(base_dir, "../player_stats.csv")

        # Initialize files with headers if they don't exist
        if not os.path.exists(self.matches_file):
            with open(self.matches_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "event", "date", "map", "team_left", "team_right",
                    "score_left", "score_right",
                    "first_half_left", "first_half_right", "second_half_left", "second_half_right",
                    "total_rounds", "winner", "left_team_started", "match_url"
                ])

        if not os.path.exists(self.players_file):
            with open(self.players_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "event", "date", "map", "team", "player_name",
                    "opening_kd", "multi_kills", "kast", "clutches",
                    "kills", "headshots", "assists", "deaths", "adr", "round_swing", "rating"
                ])

    def export_match(self, match_data):
        with open(self.matches_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "event", "date", "map", "team_left", "team_right",
                "score_left", "score_right",
                "first_half_left", "first_half_right", "second_half_left", "second_half_right",
                "total_rounds", "winner", "left_team_started", "match_url"
            ])
            writer.writerow(match_data)

    def export_players(self, players_data_list):
        if not players_data_list:
            return
        with open(self.players_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "event", "date", "map", "team", "player_name",
                "opening_kd", "multi_kills", "kast", "clutches",
                "kills", "headshots", "assists", "deaths", "adr", "round_swing", "rating"
            ])
            writer.writerows(players_data_list)
