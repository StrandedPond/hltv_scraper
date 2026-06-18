import pandas as pd
import os

base_dir = os.path.dirname(os.path.abspath(__file__))
in_csv = os.path.join(base_dir, "../../hltv_cs2_player_stats_scrapling.csv")
out_csv = os.path.join(base_dir, "../../hltv_extended_stats.csv")

# Accessing the data
df = pd.read_csv(in_csv)

# Cleaning of data
df['Headshot %'] = pd.to_numeric(df['Headshot %'].astype(str).str.replace("%",""), errors='coerce')

# Drop data that are missing the important columns
df.dropna(subset=['Player', 'Total Kills', 'Headshot %', 'Rounds played'])

# Compute the stats
# Kills per round (KPR)
df['Kills per Round'] = df['Total Kills'] / df['Rounds played']

# Headshots per round (HPR)
# We lack Total Headshots data so we compute for it first
df['Total Headshots'] = df['Total Kills'] * df['Headshot %'] / 100
df['Headshots per Round'] = df['Total Headshots'] / df['Rounds played']

# Dropping unnecessary columns
df_sorted_cols = df[['Player', 'Total Kills', 'Total Headshots', 'Kills per Round', 'Headshots per Round', 'Rounds played']]

df_sorted_cols.to_csv(out_csv, index=False)
print("Success! Saved calculated metrics to 'hltv_extended_stats.csv'")