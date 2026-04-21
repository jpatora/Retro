"""
RetroAchievements Companion App.

Flask app providing:
  - Dashboard (profile, recent unlocks, masteries)
  - Weekly Report (rolling 7-day summary)
  - What To Play Tonight (picker from Want to Play list)
  - Hunt Tracker (single-game focus view)
  - Mastery Candidates (near-complete games)
"""
import os
import random
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, abort
from dotenv import load_dotenv

from ra_client import RAClient

load_dotenv()

RA_USERNAME = os.environ.get("RA_USERNAME", "").strip()
RA_API_KEY = os.environ.get("RA_API_KEY", "").strip()

if not RA_USERNAME or not RA_API_KEY:
    print("WARNING: RA_USERNAME or RA_API_KEY not set. Check your .env file.")

app = Flask(__name__)
app.config["RA_USERNAME"] = RA_USERNAME

ra = RAClient(RA_USERNAME, RA_API_KEY) if RA_USERNAME and RA_API_KEY else None


def _require_client():
    if ra is None:
        abort(500, description="RA client not configured. Set RA_USERNAME and RA_API_KEY in .env")


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.route("/")
def dashboard():
    return render_template("dashboard.html", username=RA_USERNAME)


@app.route("/weekly")
def weekly_report():
    return render_template("weekly.html", username=RA_USERNAME)


@app.route("/play-tonight")
def play_tonight():
    return render_template("play_tonight.html", username=RA_USERNAME)


@app.route("/hunt")
def hunt_tracker():
    return render_template("hunt.html", username=RA_USERNAME)


@app.route("/mastery")
def mastery_candidates():
    return render_template("mastery.html", username=RA_USERNAME)


# ---------------------------------------------------------------------------
# JSON API routes (called by the page JavaScript)
# ---------------------------------------------------------------------------

@app.route("/api/dashboard")
def api_dashboard():
    _require_client()
    profile = ra.get_user_profile()
    summary = ra.get_user_summary(recent_games=10)
    awards = ra.get_user_awards()
    recent = ra.get_user_recent_achievements(minutes=60 * 24 * 30)  # last 30 days

    # Pull mastered games list from awards
    mastered = []
    for award in (awards or {}).get("VisibleUserAwards", []) or []:
        if award.get("AwardType") in ("Mastery/Completion", "Game Beaten"):
            mastered.append(award)

    return jsonify({
        "profile": profile,
        "summary": summary,
        "awards_summary": {
            "total_awards": (awards or {}).get("TotalAwardsCount", 0),
            "mastery_count": (awards or {}).get("MasteryAwardsCount", 0),
            "beaten_count": (awards or {}).get("BeatenHardcoreAwardsCount", 0),
        },
        "mastered": mastered[:24],
        "recent_unlocks": recent[:20],
    })


@app.route("/api/weekly")
def api_weekly():
    _require_client()
    days = int(request.args.get("days", 7))
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    start_ts = int(start.timestamp())
    end_ts = int(now.timestamp())

    achievements = ra.get_achievements_earned_between(start_ts, end_ts)

    # Aggregate
    total_achievements = len(achievements)
    total_points = sum(int(a.get("Points", 0) or 0) for a in achievements)
    total_retropoints = sum(int(a.get("TrueRatio", 0) or 0) for a in achievements)

    # Group by day for chart
    by_day: dict[str, dict] = {}
    for a in achievements:
        date_str = (a.get("Date") or "")[:10]
        if not date_str:
            continue
        day = by_day.setdefault(date_str, {"count": 0, "points": 0})
        day["count"] += 1
        day["points"] += int(a.get("Points", 0) or 0)

    # Fill missing days with zeros
    daily = []
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        daily.append({
            "date": d,
            "count": by_day.get(d, {}).get("count", 0),
            "points": by_day.get(d, {}).get("points", 0),
        })

    # Group by game
    by_game: dict[str, dict] = {}
    for a in achievements:
        gid = str(a.get("GameID"))
        g = by_game.setdefault(gid, {
            "game_id": a.get("GameID"),
            "game_title": a.get("GameTitle"),
            "console": a.get("ConsoleName"),
            "game_icon": a.get("GameIcon"),
            "count": 0,
            "points": 0,
        })
        g["count"] += 1
        g["points"] += int(a.get("Points", 0) or 0)

    top_games = sorted(by_game.values(), key=lambda x: x["points"], reverse=True)[:10]

    return jsonify({
        "days": days,
        "start": start.isoformat(),
        "end": now.isoformat(),
        "totals": {
            "achievements": total_achievements,
            "points": total_points,
            "retropoints": total_retropoints,
        },
        "daily": daily,
        "top_games": top_games,
        "achievements": achievements[:100],
    })


@app.route("/api/play-tonight")
def api_play_tonight():
    _require_client()
    minutes_available = int(request.args.get("minutes", 60))
    exclude_started = request.args.get("exclude_started", "true").lower() == "true"

    wtp = ra.get_user_want_to_play() or {}
    results = wtp.get("Results", []) if isinstance(wtp, dict) else []

    candidates = []
    for g in results:
        achievements_total = int(g.get("AchievementsPublished", 0) or 0)
        if achievements_total == 0:
            continue

        # Get the user's existing progress on this game (if any) to filter
        game_id = g.get("ID") or g.get("GameID")
        if not game_id:
            continue

        try:
            progress = ra.get_game_info_and_progress(int(game_id))
        except Exception:
            progress = {}

        num_awarded = int(progress.get("NumAwardedToUser", 0) or 0)
        if exclude_started and num_awarded > 0:
            continue

        # Rough time estimate: use average session length if provided,
        # otherwise assume ~4 min per achievement as a default heuristic.
        est_minutes = achievements_total * 4

        candidates.append({
            "game_id": game_id,
            "title": g.get("Title"),
            "console": g.get("ConsoleName"),
            "icon": g.get("ImageIcon"),
            "achievements": achievements_total,
            "points": int(g.get("PointsTotal", 0) or 0),
            "players_total": int(g.get("NumPossibleAchievements", 0) or 0),
            "est_minutes": est_minutes,
            "user_progress_pct": (
                round(100 * num_awarded / achievements_total, 1)
                if achievements_total else 0
            ),
        })

    # Filter by time available (allow +/- 50%)
    fit = [c for c in candidates if c["est_minutes"] <= minutes_available * 1.5]
    if not fit:
        fit = candidates  # fallback: show everything if nothing fits

    pick = random.choice(fit) if fit else None

    return jsonify({
        "minutes_available": minutes_available,
        "total_candidates": len(candidates),
        "fitting_candidates": len(fit),
        "pick": pick,
        "alternatives": random.sample(fit, min(4, len(fit))) if fit else [],
    })


@app.route("/api/hunt/<int:game_id>")
def api_hunt(game_id: int):
    _require_client()
    progress = ra.get_game_info_and_progress(game_id) or {}
    distribution = ra.get_game_progression(game_id) or {}

    achievements_dict = progress.get("Achievements") or {}
    achievements = []
    for ach_id, a in achievements_dict.items():
        achievements.append({
            "id": int(ach_id),
            "title": a.get("Title"),
            "description": a.get("Description"),
            "points": int(a.get("Points", 0) or 0),
            "badge": a.get("BadgeName"),
            "type": a.get("type"),
            "earned_hardcore": bool(a.get("DateEarnedHardcore")),
            "earned": bool(a.get("DateEarned")),
            "date_earned": a.get("DateEarnedHardcore") or a.get("DateEarned"),
            "num_awarded": int(a.get("NumAwarded", 0) or 0),
            "num_awarded_hardcore": int(a.get("NumAwardedHardcore", 0) or 0),
        })

    # Separate earned vs remaining
    remaining = [a for a in achievements if not a["earned_hardcore"]]
    earned = [a for a in achievements if a["earned_hardcore"]]

    # Sort remaining by rarity (most-unlocked first = easiest)
    num_distinct = int(progress.get("NumDistinctPlayersCasual", 1) or 1)
    for a in remaining:
        a["rarity_pct"] = (
            round(100 * a["num_awarded"] / num_distinct, 1)
            if num_distinct else 0
        )
    remaining.sort(key=lambda a: a["num_awarded"], reverse=True)

    return jsonify({
        "game": {
            "id": game_id,
            "title": progress.get("Title"),
            "console": progress.get("ConsoleName"),
            "icon": progress.get("ImageIcon"),
            "developer": progress.get("Developer"),
            "publisher": progress.get("Publisher"),
            "genre": progress.get("Genre"),
            "released": progress.get("Released"),
        },
        "progress": {
            "earned": len(earned),
            "total": len(achievements),
            "points_earned": int(progress.get("UserCompletion", "0%").replace("%", "") or 0),
            "percent": round(100 * len(earned) / len(achievements), 1) if achievements else 0,
        },
        "remaining": remaining,
        "earned": earned,
    })


@app.route("/api/mastery")
def api_mastery():
    _require_client()
    threshold = int(request.args.get("threshold", 80))

    progress = ra.get_user_completion_progress() or {}
    games = progress.get("Results", []) if isinstance(progress, dict) else []

    candidates = []
    for g in games:
        total = int(g.get("MaxPossible", 0) or 0)
        earned = int(g.get("NumAwarded", 0) or 0)
        earned_hc = int(g.get("NumAwardedHardcore", 0) or 0)
        if total == 0:
            continue

        pct_soft = 100 * earned / total
        pct_hard = 100 * earned_hc / total

        # Already mastered? Skip.
        if pct_hard >= 100:
            continue

        # Take the best of hardcore or casual for the threshold check
        best_pct = max(pct_soft, pct_hard)
        if best_pct < threshold:
            continue

        candidates.append({
            "game_id": g.get("GameID"),
            "title": g.get("Title"),
            "console": g.get("ConsoleName"),
            "icon": g.get("ImageIcon"),
            "total_achievements": total,
            "earned": earned,
            "earned_hardcore": earned_hc,
            "remaining": total - earned_hc,
            "pct_soft": round(pct_soft, 1),
            "pct_hard": round(pct_hard, 1),
            "most_recent": g.get("MostRecentAwardedDate"),
        })

    # Sort by fewest remaining first (easiest to knock out)
    candidates.sort(key=lambda c: (c["remaining"], -c["pct_hard"]))

    return jsonify({
        "threshold": threshold,
        "count": len(candidates),
        "candidates": candidates,
    })


@app.route("/api/search-game")
def api_search_game():
    """Helper used by the hunt tracker to search user's recent games by title."""
    _require_client()
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"results": []})

    progress = ra.get_user_completion_progress() or {}
    games = progress.get("Results", []) if isinstance(progress, dict) else []

    matches = [
        {
            "game_id": g.get("GameID"),
            "title": g.get("Title"),
            "console": g.get("ConsoleName"),
            "icon": g.get("ImageIcon"),
        }
        for g in games
        if query in (g.get("Title") or "").lower()
    ][:25]

    return jsonify({"results": matches})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
