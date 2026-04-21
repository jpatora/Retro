"""
RetroAchievements API client.

Thin wrapper around the RA web API with simple in-memory caching
to respect rate limits.

API reference: https://api-docs.retroachievements.org/
"""
import os
import time
import requests
from typing import Any, Optional
from functools import wraps

BASE_URL = "https://retroachievements.org/API"
DEFAULT_TIMEOUT = 15


class RAClient:
    def __init__(self, username: str, api_key: str, cache_ttl: int = 300):
        """
        :param username: Your RA username (used as 'z' param on most endpoints).
        :param api_key: Your RA web API key.
        :param cache_ttl: Seconds to cache responses in memory (default 5 min).
        """
        self.username = username
        self.api_key = api_key
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}

    # ---------- Low-level request ----------

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        params = dict(params or {})
        # RA uses 'z' for authenticated caller username and 'y' for API key.
        params.setdefault("z", self.username)
        params["y"] = self.api_key

        # Cache key is endpoint + sorted params (minus API key)
        cache_params = {k: v for k, v in params.items() if k != "y"}
        cache_key = f"{endpoint}?{sorted(cache_params.items())}"

        now = time.time()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self.cache_ttl:
            return cached[1]

        url = f"{BASE_URL}/{endpoint}"
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()

        # Some endpoints return empty strings on failure rather than JSON
        try:
            data = resp.json()
        except ValueError:
            data = None

        self._cache[cache_key] = (now, data)
        return data

    def clear_cache(self):
        self._cache.clear()

    # ---------- User endpoints ----------

    def get_user_profile(self, username: Optional[str] = None) -> dict:
        """Basic profile info: points, rank, avatar, etc."""
        return self._get("API_GetUserProfile.php", {"u": username or self.username})

    def get_user_summary(self, username: Optional[str] = None, recent_games: int = 5) -> dict:
        """Richer summary: recent games, awards, last activity."""
        return self._get(
            "API_GetUserSummary.php",
            {"u": username or self.username, "g": recent_games, "a": recent_games},
        )

    def get_user_recent_achievements(self, minutes: int = 60 * 24 * 7) -> list:
        """Achievements earned in the last N minutes (default: last 7 days)."""
        data = self._get(
            "API_GetUserRecentAchievements.php",
            {"u": self.username, "m": minutes},
        )
        return data if isinstance(data, list) else []

    def get_achievements_earned_between(self, start_ts: int, end_ts: int) -> list:
        """Unix timestamps. Returns achievements earned in range."""
        data = self._get(
            "API_GetAchievementsEarnedBetween.php",
            {"u": self.username, "f": start_ts, "t": end_ts},
        )
        return data if isinstance(data, list) else []

    def get_user_completion_progress(self, username: Optional[str] = None) -> dict:
        """All games the user has played with progress metadata."""
        return self._get(
            "API_GetUserCompletionProgress.php",
            {"u": username or self.username},
        )

    def get_user_awards(self, username: Optional[str] = None) -> dict:
        """Site awards / badges earned."""
        return self._get("API_GetUserAwards.php", {"u": username or self.username})

    def get_user_want_to_play(self, username: Optional[str] = None) -> dict:
        """User's Want to Play list."""
        return self._get(
            "API_GetUserWantToPlayList.php",
            {"u": username or self.username},
        )

    def get_game_info_and_progress(self, game_id: int, username: Optional[str] = None) -> dict:
        """Game metadata + the user's progress on it."""
        return self._get(
            "API_GetGameInfoAndUserProgress.php",
            {"u": username or self.username, "g": game_id, "a": 1},
        )

    # ---------- Game endpoints ----------

    def get_game(self, game_id: int) -> dict:
        return self._get("API_GetGame.php", {"i": game_id})

    def get_game_list(self, console_id: int, has_achievements_only: bool = True) -> list:
        """
        Get the complete list of games for a console.
        NOTE: Response can be large; RA asks that this be cached aggressively.
        """
        data = self._get(
            "API_GetGameList.php",
            {"i": console_id, "f": 1 if has_achievements_only else 0},
        )
        return data if isinstance(data, list) else []

    def get_game_extended(self, game_id: int) -> dict:
        return self._get("API_GetGameExtended.php", {"i": game_id})

    def get_game_progression(self, game_id: int) -> dict:
        """Average time-to-unlock metadata per achievement."""
        return self._get("API_GetGameProgression.php", {"i": game_id})

    def get_achievement_of_the_week(self) -> dict:
        return self._get("API_GetAchievementOfTheWeek.php")
