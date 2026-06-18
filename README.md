# CS2 Player Props Pipeline

An automated data ingestion and machine learning pipeline for scraping CS2 match results, team statistics, and player performance metrics from HLTV to power player prop predictions.

## Overview
This repository contains two main components:
1. **`hltv_scraper/`**: A suite of Python scrapers utilizing `scrapling` and `playwright` to bypass Cloudflare and extract comprehensive CS2 statistics.
2. **`cs2_prediction/`**: A machine learning pipeline that consumes the extracted `.csv` data to build datasets and train prediction models.

## Automated CI/CD Data Ingestion
This repository uses GitHub Actions to ensure the statistical datasets are always up to date:
- **Daily Scraper (`scrape_daily.yml`)**: Runs every day at 6:00 AM Manila Time (22:00 UTC). Scrapes the latest match results, individual match scoreboards, and Valve's official team rankings.
- **Weekly Scraper (`scrape_weekly.yml`)**: Runs every Monday at 6:00 AM Manila Time (22:00 UTC). Performs heavy aggregation of Team Map Stats, Top 50 rankings, and detailed individual Player Stats.

### Managing Player Scrapes
To add or remove specific players from the deep-dive weekly scrape, simply update the `hltv_scraper/player_urls.json` file with their specific HLTV player URL. The weekly GitHub action will automatically read this file and process everyone listed.

## Local Setup
1. Install requirements:
   ```bash
   pip install -r hltv_scraper/requirements.txt
   playwright install chromium
   ```
2. Manually trigger scrapers (if needed) from the `hltv_scraper/` subdirectories.

## Disclaimer
This project is for educational and statistical analysis purposes only.
