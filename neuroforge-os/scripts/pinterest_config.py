#!/usr/bin/env python3
"""
NeuroForge OS — Pinterest Pipeline Configuration
==================================================
Centralized config for the Florra × Ebril Pinterest content pipeline.

Env vars required:
    PINTEREST_ACCESS_TOKEN  — OAuth2 bearer token (pins:read, pins:write, boards:read)
    ANTHROPIC_API_KEY       — for caption generation via Claude
"""

# Ebril's track catalog — maps mood tags to track metadata
EBRIL_TRACKS = {
    "introspective": {
        "title": "Stranger in You",
        "artist": "Ebril",
        "spotify_url": "https://open.spotify.com/artist/ebril",
        "use_for": "reflective, emotional, deep content",
    },
    "uplifting": {
        "title": "Bloom",
        "artist": "Ebril",
        "spotify_url": "https://open.spotify.com/artist/ebril",
        "use_for": "growth, morning routines, nature",
    },
    "melancholy": {
        "title": "Paper Walls",
        "artist": "Ebril",
        "spotify_url": "https://open.spotify.com/artist/ebril",
        "use_for": "moody, rainy day, sad girl aesthetic",
    },
    "warm": {
        "title": "Golden Hour",
        "artist": "Ebril",
        "spotify_url": "https://open.spotify.com/artist/ebril",
        "use_for": "sunset, golden light, cozy content",
    },
    "dreamy": {
        "title": "Wildflower",
        "artist": "Ebril",
        "spotify_url": "https://open.spotify.com/artist/ebril",
        "use_for": "ethereal, wanderlust, soft content",
    },
}

# Pinterest board definitions
PINTEREST_BOARDS = {
    "aesthetic-mood": {
        "name": "Aesthetic Mood",
        "pinterest_id": "florra/aesthetic-mood",
        "content_types": ["golden hour", "soft visuals", "film grain", "moody"],
    },
    "music-discovery": {
        "name": "Music Discovery",
        "pinterest_id": "florra/music-discovery",
        "content_types": ["vinyl", "playlists", "artist spotlights", "headphones"],
    },
    "lifestyle-inspo": {
        "name": "Lifestyle Inspo",
        "pinterest_id": "florra/lifestyle-inspo",
        "content_types": ["routines", "journaling", "coffee", "reading"],
    },
    "fashion-forward": {
        "name": "Fashion Forward",
        "pinterest_id": "florra/fashion-forward",
        "content_types": ["outfit inspo", "thrift", "street style"],
    },
    "wellness-growth": {
        "name": "Wellness & Growth",
        "pinterest_id": "florra/wellness-growth",
        "content_types": ["self-care", "meditation", "fitness", "growth"],
    },
}

# Niche tag → board mapping
NICHE_TO_BOARD = {
    "aesthetic": "aesthetic-mood",
    "golden-hour": "aesthetic-mood",
    "cottagecore": "aesthetic-mood",
    "music": "music-discovery",
    "lifestyle": "lifestyle-inspo",
    "fashion": "fashion-forward",
    "wellness": "wellness-growth",
}

VALID_NICHES = [
    "aesthetic",
    "lifestyle",
    "music",
    "fashion",
    "wellness",
    "golden-hour",
    "cottagecore",
]

VALID_MOODS = ["introspective", "uplifting", "melancholy", "warm", "dreamy"]

# Caption templates — 4 types that get cycled
CAPTION_TEMPLATES = {
    "A": [
        "add {track} to your playlist and thank me later",
        "the song you didn't know you needed: {track} by Ebril",
        "if this video had a soundtrack it would be {track}",
    ],
    "B": [
        "{aesthetic_caption} | currently listening to Ebril on repeat",
        "{aesthetic_caption} | soundtrack: {track} by @ebrilmusic",
        "{aesthetic_caption} | {track} playing in the background",
    ],
    "C": [
        "POV: you just found your new favorite artist: Ebril",
        "this + Ebril's new song {track} = the whole vibe",
        "saving this for later (and adding Ebril to the queue)",
    ],
    "D": [
        "{track} — Ebril",
        "mood: {mood_word}. song: {track}. artist: Ebril.",
        "{track} on repeat",
    ],
}

CAPTION_TYPE_CYCLE = ["A", "B", "C", "D"]

# Hashtag sets
BASE_HASHTAGS = [
    "#ebrilmusic",
    "#indiefolk",
    "#indiemusic",
    "#newmusic",
    "#musicdiscovery",
]

NICHE_HASHTAGS = {
    "aesthetic": [
        "#aestheticvibes",
        "#moodboard",
        "#softaesthetic",
        "#goldenhouraesthetic",
        "#filmgrain",
    ],
    "golden-hour": [
        "#goldenhour",
        "#sunsetvibes",
        "#goldenhouraesthetic",
        "#warmtones",
        "#magichour",
    ],
    "cottagecore": [
        "#cottagecore",
        "#cottagecoreaesthetic",
        "#naturelover",
        "#slowliving",
        "#rurallife",
    ],
    "lifestyle": [
        "#morningroutine",
        "#lifestyleinspo",
        "#thatgirl",
        "#dailyroutine",
        "#cozyvibes",
    ],
    "fashion": [
        "#outfitinspo",
        "#fashioninspo",
        "#ootd",
        "#thriftfinds",
        "#streetstyle",
    ],
    "wellness": [
        "#selfcare",
        "#wellness",
        "#growthmindset",
        "#journaling",
        "#mindfulness",
    ],
    "music": [
        "#playlistvibes",
        "#vinylrecords",
        "#songoftheday",
        "#acousticmusic",
        "#singersongwriter",
    ],
}

# Posting schedule — optimal windows for female 18-35 audience (EST)
POSTING_WINDOWS = [
    {"label": "morning", "start_hour": 6, "end_hour": 8},
    {"label": "midday", "start_hour": 11, "end_hour": 13},
    {"label": "evening", "start_hour": 19, "end_hour": 21},
    {"label": "late-night", "start_hour": 21, "end_hour": 23},
]

MAX_PINS_PER_HOUR = 5
WEEKLY_PIN_TARGET = (50, 75)

# Pinterest API
PINTEREST_API_BASE = "https://api.pinterest.com/v5"
PINTEREST_RATE_LIMIT_PER_MIN = 50
PINTEREST_RATE_BACKOFF_SEC = 300
PINTEREST_MEDIA_POLL_SEC = 30
PINTEREST_MEDIA_TIMEOUT_SEC = 600

# Trend research keywords — used by the trend scout
TREND_RESEARCH_QUERIES = [
    "indie folk aesthetic pinterest",
    "golden hour playlist pinterest trending",
    "female singer songwriter discovery",
    "cottagecore music aesthetic",
    "soft girl aesthetic playlist",
    "vinyl records aesthetic trending",
    "journaling aesthetic music",
    "sunset drive playlist vibes",
    "morning routine indie music",
    "wellness routine acoustic",
]
