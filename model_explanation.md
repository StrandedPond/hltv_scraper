# CS2 Prediction Model Architecture

The machine learning pipeline for this project is designed to predict both **team-level outcomes** (spreads, totals) and **player-level outcomes** (kills, headshots) for Counter-Strike 2 matches. 

The models are trained using the `statsmodels` library in Python and rely on historical data scraped from HLTV. Below is a detailed explanation of how each model is structured, trained, and used for predictions.

---

## 1. Team-Level Models

Team models evaluate the matchup between two teams on a specific map to predict the overall match environment.

### The Round Predictor (Over/Under Totals)
* **Goal:** Predict the total number of rounds that will be played in a single map.
* **Algorithm:** Beta Regression (Fractional Logit)
* **How it works:** 
  The model scales the historical `total_rounds` into a continuous fraction between `[0, 1]` based on minimum and maximum regulation round limits. It trains on this fraction using Beta Regression.
* **Key Features used:**
  * **Competitiveness & Log5 Win Probability:** Derived metrics measuring how evenly matched the two teams are.
  * **Team A & Team B Stats:** Weighted CT win-rates, T win-rates, pistol round win-rates, side asymmetry (how heavily they favor one side), and their historical average rounds played.
  * **Elo Difference:** The difference in Valve rankings/Elo between the two teams.
  * **Map Dummies:** One-hot encoded variables for the specific map being played (e.g., is it Dust2? is it Mirage?).

### The Handicap Predictor (Round Spreads)
* **Goal:** Predict the round margin (the final score difference) between Team A and Team B.
* **Algorithm:** Quantile Regression (`q=0.10`, `0.50`, `0.90`)
* **How it works:**
  Instead of predicting a single average margin (like Linear Regression would), it uses Quantile Regression to predict a *distribution* of margins. By predicting the 10th percentile, 50th percentile (median), and 90th percentile outcomes, the model can generate probabilities for various alternative handicap lines (e.g., -2.5, -4.5).
* **Key Features used:**
  * **Stat Differentials:** The difference in Log5 win probability, CT/T win-rates, and pistol win-rates between the two teams.
  * **Elo Difference & Map Dummies.**

---

## 2. Player-Level Models

Player models take the predicted match environment (how many rounds will be played) and combine it with individual player profiles to predict specific prop betting markets.

### The Kill Model
* **Goal:** Predict the total number of kills a specific player will get on a specific map.
* **Algorithm:** Quantile Regression (`q=0.10`, `0.50`, `0.90`)
* **How it works:**
  Like the Handicap model, this uses Quantile Regression. Because player performance has high variance, knowing the 10th and 90th percentiles allows the system to calculate the exact probability of a player hitting an "Over 15.5 Kills" prop line. 
* **Key Features used:**
  * **KPR (Kills Per Round):** The player's overall, CT-specific, and T-specific KPR.
  * **KAST:** The percentage of rounds the player gets a Kill, Assist, Survives, or is Traded.
  * **Total Rounds:** The number of rounds played in the match (acting as the "exposure" or time-on-ice for the player).
  * **Map Dummies.**

### The Headshot Model
* **Goal:** Predict the total number of headshot kills a player will achieve.
* **Algorithm:** Quantile Regression (`q=0.10`, `0.50`, `0.90`)
* **How it works:**
  A player's headshots are strictly bounded by their total kills. Therefore, this model doesn't just predict headshots in a vacuum; it uses a `predicted_kills_anchor` (calculated as `KPR * Total Rounds`) as its primary baseline feature.
* **Key Features used:**
  * **Predicted Kills Anchor:** The expected number of kills the player will get.
  * **Historical Headshot Rate:** The player's long-term average headshot percentage.
  * **KAST & Map Dummies.**

---

## Summary of the Prediction Flow
1. **Match Data Loaded:** Upcoming match details (teams, map, players) are fed into the system.
2. **Team Stats Extracted:** The system pulls the 6-month historical, opponent-adjusted stats for both teams.
3. **Map Environment Simulated:** The **Round Predictor** and **Handicap Predictor** estimate how long the map will last and who will control the pace.
4. **Player Props Generated:** Using the predicted total rounds, the **Kill Model** and **Headshot Model** output 10th/50th/90th percentile estimations for every player on the server, which are then converted into hit probabilities for sports betting lines.
