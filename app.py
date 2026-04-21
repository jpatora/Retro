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
from pokemon_catalog import POKEMON_TITLES, find_best_match

load_dotenv()

RA_USERNAME = os.environ.get("RA_USERNAME", "").strip()
RA_API_KEY = os.environ.get("RA_API_KEY", "").strip()

if not RA_USERNAME or not RA_API_KEY:
    print("WARNING: RA_USERNAME or RA_API_KEY not set. Check your .env file.")

app = Flask(__name__)
app.config["RA_USERNAME"] = RA_USERNAME

ra = RAClient(RA_USERNAME, RA_API_KEY) if RA_USERNAME and RA_API_KEY else None


def _int(val, default: int = 0) -> int:
    """
    Coerce an RA API value to int. The API returns numbers as strings,
    sometimes with decimals (e.g. "55.00%"). Handles None, empty strings,
    percent signs, and decimal strings gracefully.
    """
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        try:
            s = str(val).replace("%", "").strip()
            return int(float(s))
        except (ValueError, TypeError):
            return default


def _require_client():
    if ra is None:
        abort(500, description=(
            "RA client not configured. Copy .env.example to .env in the same folder "
            "as app.py, then restart the server."
        ))


@app.errorhandler(500)
def handle_500(err):
    msg = getattr(err, "description", None) or "Internal server error"
    # Return JSON for /api routes so the frontend can display the real reason.
    if request.path.startswith("/api/"):
        return jsonify({"error": msg}), 500
    return f"<h1>500</h1><p>{msg}</p>", 500


@app.errorhandler(Exception)
def handle_uncaught(err):
    if request.path.startswith("/api/"):
        return jsonify({"error": f"{type(err).__name__}: {err}"}), 500
    raise err


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


@app.route("/pokemon")
def pokemon_page():
    return render_template("pokemon.html", username=RA_USERNAME)


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
    total_points = sum(_int(a.get("Points", 0)) for a in achievements)
    total_retropoints = sum(_int(a.get("TrueRatio", 0)) for a in achievements)

    # Group by day for chart
    by_day: dict[str, dict] = {}
    for a in achievements:
        date_str = (a.get("Date") or "")[:10]
        if not date_str:
            continue
        day = by_day.setdefault(date_str, {"count": 0, "points": 0})
        day["count"] += 1
        day["points"] += _int(a.get("Points", 0))

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
        g["points"] += _int(a.get("Points", 0))

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
        achievements_total = _int(g.get("AchievementsPublished", 0))
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

        num_awarded = _int(progress.get("NumAwardedToUser", 0))
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
            "points": _int(g.get("PointsTotal", 0)),
            "players_total": _int(g.get("NumPossibleAchievements", 0)),
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


@app.route("/api/debug/hunt/<int:game_id>")
def api_debug_hunt(game_id: int):
    """Dump the raw RA API response for a game so we can inspect field names."""
    _require_client()
    progress = ra.get_game_info_and_progress(game_id) or {}
    # Show the top-level keys + a sample achievement
    achievements = progress.get("Achievements") or {}
    sample_key = next(iter(achievements), None)
    sample = achievements.get(sample_key) if sample_key else None
    return jsonify({
        "top_level_keys": sorted(progress.keys()),
        "sample_achievement_keys": sorted(sample.keys()) if sample else None,
        "sample_achievement": sample,
        "num_achievements_total": len(achievements),
        "num_with_DateEarned": sum(1 for a in achievements.values() if a.get("DateEarned")),
        "num_with_DateEarnedHardcore": sum(1 for a in achievements.values() if a.get("DateEarnedHardcore")),
        "NumAwardedToUser": progress.get("NumAwardedToUser"),
        "NumAwardedToUserHardcore": progress.get("NumAwardedToUserHardcore"),
        "UserCompletion": progress.get("UserCompletion"),
        "UserCompletionHardcore": progress.get("UserCompletionHardcore"),
        "requested_as_username": ra.username,
    })


@app.route("/api/hunt/<int:game_id>")
def api_hunt(game_id: int):
    _require_client()
    progress = ra.get_game_info_and_progress(game_id) or {}

    achievements_dict = progress.get("Achievements") or {}
    achievements = []
    for ach_id, a in achievements_dict.items():
        # Different RA endpoints / API versions may use different casings
        date_earned = a.get("DateEarned") or a.get("dateEarned")
        date_earned_hc = a.get("DateEarnedHardcore") or a.get("dateEarnedHardcore")

        achievements.append({
            "id": int(ach_id),
            "title": a.get("Title") or a.get("title"),
            "description": a.get("Description") or a.get("description"),
            "points": _int(a.get("Points") or a.get("points")),
            "badge": a.get("BadgeName") or a.get("badgeName"),
            "type": a.get("type") or a.get("Type"),
            "earned_hardcore": bool(date_earned_hc),
            "earned": bool(date_earned or date_earned_hc),
            "date_earned": date_earned_hc or date_earned,
            "num_awarded": _int(a.get("NumAwarded") or a.get("numAwarded")),
            "num_awarded_hardcore": _int(a.get("NumAwardedHardcore") or a.get("numAwardedHardcore")),
        })

    # Separate earned vs remaining. Use earned (softcore) since hardcore
    # may be empty for users who played in softcore mode.
    remaining = [a for a in achievements if not a["earned"]]
    earned = [a for a in achievements if a["earned"]]

    # Sort remaining by rarity (most-unlocked first = easiest)
    num_distinct = _int(progress.get("NumDistinctPlayersCasual"), 1) or 1
    for a in remaining:
        a["rarity_pct"] = (
            round(100 * a["num_awarded"] / num_distinct, 1)
            if num_distinct else 0
        )
    remaining.sort(key=lambda a: a["num_awarded"], reverse=True)

    # Use the authoritative summary counts from the API when available.
    # Fall back to our parsed list count if missing.
    num_earned_from_api = _int(progress.get("NumAwardedToUser"))
    num_earned_hc_from_api = _int(progress.get("NumAwardedToUserHardcore"))
    total_achievements = len(achievements)

    # If the per-achievement DateEarned fields are missing but the summary
    # shows earned > 0, warn the user we couldn't resolve which specific
    # ones were earned.
    warning = None
    if num_earned_from_api > 0 and len(earned) == 0:
        warning = (
            f"RA reports {num_earned_from_api} achievements earned but did not "
            f"return per-achievement unlock dates. The earned/remaining lists "
            f"below may be incomplete."
        )

    percent_overall = (
        round(100 * num_earned_from_api / total_achievements, 1)
        if total_achievements else 0
    )

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
            "earned": num_earned_from_api or len(earned),
            "earned_hardcore": num_earned_hc_from_api or sum(1 for a in earned if a["earned_hardcore"]),
            "total": total_achievements,
            "percent": percent_overall,
        },
        "warning": warning,
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
        total = _int(g.get("MaxPossible", 0))
        earned = _int(g.get("NumAwarded", 0))
        earned_hc = _int(g.get("NumAwardedHardcore", 0))
        if total == 0:
            continue

        pct_soft = 100 * earned / total
        pct_hard = 100 * earned_hc / total

        # Skip fully-100% hardcore masteries — those aren't candidates for anything.
        # Don't skip softcore-100% games here; if user is in hardcore mode those
        # still show as candidates for hardcore completion.
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
            "remaining": total - earned,
            "remaining_hardcore": total - earned_hc,
            "pct_soft": round(pct_soft, 1),
            "pct_hard": round(pct_hard, 1),
            "most_recent": g.get("MostRecentAwardedDate"),
        })

    # Default sort: fewest remaining (softcore) first. Frontend re-sorts
    # based on active mode anyway.
    candidates.sort(key=lambda c: (c["remaining"], -c["pct_soft"]))

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


@app.route("/api/pokemon")
def api_pokemon():
    """
    Cross-reference the canonical Pokémon title list against RA's game lists
    for Game Boy (4), Game Boy Color (6), and Game Boy Advance (5), then pull
    each matched game's user progress.
    """
    _require_client()

    # Fetch per-console game catalogs once. These responses are large but
    # RA's in-memory cache on the client keeps this cheap on repeat calls.
    console_catalogs: dict[int, list] = {}
    for cid in (4, 5, 6, 18):
        try:
            console_catalogs[cid] = ra.get_game_list(cid, has_achievements_only=True)
        except Exception as e:
            console_catalogs[cid] = []
            print(f"Failed to fetch game list for console {cid}: {e}")

    CONSOLE_NAMES = {4: "Game Boy", 6: "Game Boy Color", 5: "Game Boy Advance", 18: "Nintendo DS"}

    results = []
    totals = {
        "games_total": len(POKEMON_TITLES),
        "games_with_sets": 0,
        "games_played": 0,
        "games_played_hardcore": 0,
        "games_mastered": 0,
        "achievements_earned": 0,
        "achievements_earned_hardcore": 0,
        "achievements_available": 0,
        "points_earned": 0,
        "points_earned_hardcore": 0,
        "points_available": 0,
    }

    for entry in POKEMON_TITLES:
        cid = entry["console_id"]
        catalog = console_catalogs.get(cid, [])
        match = find_best_match(entry, catalog)

        row = {
            "title": entry["title"],
            "console": CONSOLE_NAMES[cid],
            "console_id": cid,
            "has_ra_set": False,
            "ra_game_id": None,
            "ra_title": None,
            "icon": None,
            "achievements_total": 0,
            "points_total": 0,
            "num_leaderboards": 0,
            "date_modified": None,
            "earned": 0,
            "earned_hardcore": 0,
            "points_earned": 0,
            "points_earned_hardcore": 0,
            "percent": 0.0,
            "percent_hardcore": 0.0,
            "mastered": False,
            "player_count": 0,
        }

        if match:
            row["has_ra_set"] = True
            row["ra_game_id"] = match.get("ID")
            row["ra_title"] = match.get("Title")
            row["icon"] = match.get("ImageIcon")
            row["achievements_total"] = _int(match.get("NumAchievements"))
            row["points_total"] = _int(match.get("Points"))
            row["num_leaderboards"] = _int(match.get("NumLeaderboards"))
            row["date_modified"] = match.get("DateModified")

            totals["games_with_sets"] += 1
            totals["achievements_available"] += row["achievements_total"]
            totals["points_available"] += row["points_total"]

            # Pull user progress on this specific game
            try:
                progress = ra.get_game_info_and_progress(int(row["ra_game_id"]))
            except Exception as e:
                print(f"Progress fetch failed for {row['ra_title']}: {e}")
                progress = {}

            if progress:
                row["earned"] = _int(progress.get("NumAwardedToUser"))
                row["earned_hardcore"] = _int(progress.get("NumAwardedToUserHardcore"))
                row["points_earned"] = _int(progress.get("UserCompletion"))  # safe via _int
                row["player_count"] = _int(progress.get("NumDistinctPlayersCasual"))

                # Sum up points from individual achievements earned
                ach_dict = progress.get("Achievements") or {}
                pe = 0
                pe_hc = 0
                for a in ach_dict.values():
                    pts = _int(a.get("Points"))
                    if a.get("DateEarned"):
                        pe += pts
                    if a.get("DateEarnedHardcore"):
                        pe_hc += pts
                row["points_earned"] = pe
                row["points_earned_hardcore"] = pe_hc

                if row["achievements_total"]:
                    row["percent"] = round(
                        100 * row["earned"] / row["achievements_total"], 1
                    )
                    row["percent_hardcore"] = round(
                        100 * row["earned_hardcore"] / row["achievements_total"], 1
                    )

                row["mastered"] = (
                    row["achievements_total"] > 0
                    and row["earned_hardcore"] >= row["achievements_total"]
                )

                if row["earned"] > 0:
                    totals["games_played"] += 1
                if row["earned_hardcore"] > 0:
                    totals["games_played_hardcore"] += 1
                if row["mastered"]:
                    totals["games_mastered"] += 1

                totals["achievements_earned"] += row["earned"]
                totals["achievements_earned_hardcore"] += row["earned_hardcore"]
                totals["points_earned"] += row["points_earned"]
                totals["points_earned_hardcore"] += row["points_earned_hardcore"]

        results.append(row)

    # Overall completion percentages
    totals["overall_percent"] = (
        round(100 * totals["achievements_earned"] / totals["achievements_available"], 1)
        if totals["achievements_available"] else 0
    )
    totals["overall_percent_hardcore"] = (
        round(100 * totals["achievements_earned_hardcore"] / totals["achievements_available"], 1)
        if totals["achievements_available"] else 0
    )
    totals["overall_points_percent"] = (
        round(100 * totals["points_earned"] / totals["points_available"], 1)
        if totals["points_available"] else 0
    )
    totals["overall_points_percent_hardcore"] = (
        round(100 * totals["points_earned_hardcore"] / totals["points_available"], 1)
        if totals["points_available"] else 0
    )

    return jsonify({
        "totals": totals,
        "results": results,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
