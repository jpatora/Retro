"""
Canonical list of mainline + major spin-off Pokémon titles released on
Game Boy, Game Boy Color, and Game Boy Advance (North American releases).

RA Console IDs:
  4 = Game Boy
  6 = Game Boy Color
  5 = Game Boy Advance

Each entry carries:
  - title:        Human-friendly display name
  - console_id:   RA console ID
  - match_terms:  Lowercase substrings, ALL of which must appear in a
                  candidate RA game title to count as a match. This lets us
                  distinguish e.g. "Pokemon Pinball" from
                  "Pokemon Pinball: Ruby & Sapphire".
  - exclude_terms: Substrings that disqualify a candidate (used to avoid
                   false positives where one game's title is a prefix of
                   another).
"""

POKEMON_TITLES = [
    # ---------- Game Boy (console_id = 4) ----------
    {
        "title": "Pokémon Red",
        "console_id": 4,
        "match_terms": ["pokemon", "red"],
        "exclude_terms": ["firered", "rescue"],
    },
    {
        "title": "Pokémon Blue",
        "console_id": 4,
        "match_terms": ["pokemon", "blue"],
        "exclude_terms": ["rescue"],
    },
    {
        "title": "Pokémon Yellow: Special Pikachu Edition",
        "console_id": 4,
        "match_terms": ["pokemon", "yellow"],
        "exclude_terms": [],
    },

    # ---------- Game Boy Color (console_id = 6) ----------
    {
        "title": "Pokémon Gold",
        "console_id": 6,
        "match_terms": ["pokemon", "gold"],
        "exclude_terms": ["heartgold"],
    },
    {
        "title": "Pokémon Silver",
        "console_id": 6,
        "match_terms": ["pokemon", "silver"],
        "exclude_terms": ["soulsilver"],
    },
    {
        "title": "Pokémon Crystal",
        "console_id": 6,
        "match_terms": ["pokemon", "crystal"],
        "exclude_terms": [],
    },
    {
        "title": "Pokémon Pinball",
        "console_id": 6,
        "match_terms": ["pokemon", "pinball"],
        "exclude_terms": ["ruby", "sapphire"],
    },
    {
        "title": "Pokémon Puzzle Challenge",
        "console_id": 6,
        "match_terms": ["pokemon", "puzzle", "challenge"],
        "exclude_terms": [],
    },
    {
        "title": "Pokémon Trading Card Game",
        "console_id": 6,
        "match_terms": ["pokemon", "trading", "card"],
        "exclude_terms": [],
    },

    # ---------- Game Boy Advance (console_id = 5) ----------
    {
        "title": "Pokémon Ruby",
        "console_id": 5,
        "match_terms": ["pokemon", "ruby"],
        "exclude_terms": ["omega", "pinball"],
    },
    {
        "title": "Pokémon Sapphire",
        "console_id": 5,
        "match_terms": ["pokemon", "sapphire"],
        "exclude_terms": ["alpha", "pinball"],
    },
    {
        "title": "Pokémon Emerald",
        "console_id": 5,
        "match_terms": ["pokemon", "emerald"],
        "exclude_terms": [],
    },
    {
        "title": "Pokémon FireRed",
        "console_id": 5,
        "match_terms": ["pokemon", "firered"],
        "exclude_terms": [],
    },
    {
        "title": "Pokémon LeafGreen",
        "console_id": 5,
        "match_terms": ["pokemon", "leafgreen"],
        "exclude_terms": [],
    },
    {
        "title": "Pokémon Pinball: Ruby & Sapphire",
        "console_id": 5,
        "match_terms": ["pokemon", "pinball"],
        "exclude_terms": [],
    },
    {
        "title": "Pokémon Mystery Dungeon: Red Rescue Team",
        "console_id": 5,
        "match_terms": ["pokemon", "mystery", "dungeon"],
        "exclude_terms": [],
    },
]


def _normalize(s: str) -> str:
    """Lowercase + remove common accent/é and punctuation for fuzzy matching."""
    if not s:
        return ""
    return (
        s.lower()
        .replace("é", "e")
        .replace(":", " ")
        .replace("-", " ")
        .replace("  ", " ")
    )


def find_best_match(entry: dict, console_games: list) -> dict | None:
    """
    Search a list of RA games (from API_GetGameList) for the best match
    against a POKEMON_TITLES entry.

    Returns the RA game dict, or None if no acceptable match found.
    Preference: shorter titles win when multiple candidates match, since
    that usually means the main release vs a hack/variant.
    """
    match_terms = [t.lower() for t in entry["match_terms"]]
    exclude_terms = [t.lower() for t in entry.get("exclude_terms", [])]

    candidates = []
    for g in console_games:
        raw_title = g.get("Title", "")
        norm = _normalize(raw_title)

        # All match terms must appear
        if not all(t in norm for t in match_terms):
            continue
        # No exclude term may appear
        if any(t in norm for t in exclude_terms):
            continue
        # Skip hacks / subsets commonly marked with ~ prefix on RA
        if raw_title.startswith("~"):
            continue

        candidates.append(g)

    if not candidates:
        return None

    # Prefer the shortest title (usually the canonical release)
    candidates.sort(key=lambda g: len(g.get("Title", "")))
    return candidates[0]
