# RetroAchievements Companion

A Flask app that wraps the RetroAchievements web API into a personal dashboard
with five features:

- **Dashboard** — profile, points, rank, recent unlocks, masteries gallery
- **Weekly Report** — rolling 7/14/30-day summary with Chart.js bar chart
- **Play Tonight** — random picker from your Want to Play list, time-filtered
- **Hunt Tracker** — focus view on a single game, remaining achievements sorted by rarity
- **Mastery Candidates** — games you're close to finishing, ranked by fewest remaining

Styled in a navy / steel-blue palette (`#243F72` / `#2E5B8A`) for that Bluestem feel.

## Setup

```bash
python -m venv venv
source venv/bin/activate      # or: venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# edit .env and set RA_USERNAME and RA_API_KEY
python app.py
```

Then open http://localhost:5000.

## Deploy to Railway

1. Push this folder to a GitHub repo.
2. In Railway: New Project → Deploy from GitHub Repo → select this repo.
3. In the service's Variables tab, add `RA_USERNAME` and `RA_API_KEY`.
4. Railway will use the `Procfile` automatically.

## Files

```
ra_app/
├── app.py              # Flask routes (page + JSON API)
├── ra_client.py        # RetroAchievements API wrapper with in-memory caching
├── requirements.txt
├── Procfile            # Railway / Heroku
├── .env.example
├── templates/
│   ├── base.html       # Shared layout + nav
│   ├── dashboard.html
│   ├── weekly.html
│   ├── play_tonight.html
│   ├── hunt.html
│   └── mastery.html
└── static/
    └── css/style.css
```

## Notes / known caveats

- **Field names not validated against live data.** The app was built strictly
  from the official RA API docs. Response field names *should* match, but if
  you hit a blank stat or missing icon, inspect the JSON at
  `/api/dashboard`, `/api/weekly`, etc. and tweak the mapping in `app.py`.
  The code uses `.get()` everywhere and will render gracefully with blanks.
- **Caching:** `RAClient` caches responses in memory for 5 minutes by default
  to respect rate limits. Restart the process to force-refresh, or call
  `ra.clear_cache()`.
- **"Play tonight" time estimate** currently assumes ~4 min per achievement
  as a rough heuristic since RA's per-game average session time isn't
  uniformly exposed. Swap in `get_game_progression` data if you want better
  estimates.
- **API key:** you exposed your key in chat while building this, so please
  rotate it on retroachievements.org and update `.env`.
