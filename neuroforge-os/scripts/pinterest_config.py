#!/usr/bin/env python3
"""
NeuroForge OS — Pinterest Pipeline Configuration (BANDERSNATCH)
================================================================
Centralized config for the Bandersnatch Pinterest content pipeline.

BANDERSNATCH is a southern-gothic world that sells clothing — the office
publishes documents, it does not advertise. Every caption obeys canon:
  - the animal is never shown or described whole. damage only.
  - never explain. publish documents.
  - lowercase clerk voice. no "shop now", no discounts, no urgency.
  - what is not known is not in the file.

Env vars required:
    PINTEREST_ACCESS_TOKEN  — OAuth2 bearer token (pins:read, pins:write, boards:read)
    ANTHROPIC_API_KEY       — for caption generation via Claude
"""

SITE = "https://bandersnatch.world"
STORE = "https://bandersnatch-2.myshopify.com"

# Destinations — maps mood tags to where a pin should send people.
# (This replaces the old artist-track catalog: pins link into the county.)
DESTINATIONS = {
    "county": {
        "title": "the county, 1935–1945",
        "url": f"{SITE}/history.html",
        "use_for": "FSA plates, vintage photography, timeline, americana",
    },
    "record": {
        "title": "the record",
        "url": f"{SITE}/record.html",
        "use_for": "entries, found objects, unexplained events, documents",
    },
    "bestiary": {
        "title": "the bestiary",
        "url": f"{SITE}/bestiary.html",
        "use_for": "the animal (damage only — never whole), the cardinal, omens",
    },
    "holdings": {
        "title": "the holdings",
        "url": f"{SITE}/file.html",
        "use_for": "the clothing — editions of 24, numbered, sealed in wax",
    },
    "virginia": {
        "title": "the photographers",
        "url": f"{SITE}/virginia.html",
        "use_for": "field photographers, cameras, film, darkroom content",
    },
    "store": {
        "title": "the store",
        "url": STORE,
        "use_for": "direct product pins — a specific holding with its photos",
    },
}

VALID_MOODS = list(DESTINATIONS.keys())

# Pinterest board definitions.
# pinterest_id is filled once the Bandersnatch Pinterest account exists —
# set the real board IDs via env or edit here after boards are created.
PINTEREST_BOARDS = {
    "the-file": {
        "name": "the file",
        "pinterest_id": None,  # real board ID once the account exists
        "content_types": ["holdings", "screen prints", "editions of 24", "wax seals"],
    },
    "the-county": {
        "name": "the county, 1935–1945",
        "pinterest_id": None,
        "content_types": ["FSA photography", "1930s americana", "rural gothic", "film grain"],
    },
    "the-bestiary": {
        "name": "the bestiary",
        "pinterest_id": None,
        "content_types": ["the cardinal", "damage", "omens", "field notes"],
    },
    "southern-gothic": {
        "name": "southern gothic",
        "pinterest_id": None,
        "content_types": ["moodboards", "dark americana", "chapel ruins", "kudzu"],
    },
}

# Niche tag → board mapping
NICHE_TO_BOARD = {
    "southern-gothic": "southern-gothic",
    "dark-academia": "southern-gothic",
    "americana": "the-county",
    "vintage-photography": "the-county",
    "gothic-fashion": "the-file",
    "graphic-tees": "the-file",
    "folklore": "the-bestiary",
}

VALID_NICHES = list(NICHE_TO_BOARD.keys())

# Caption templates — 4 register types the engine cycles through.
# These are STYLE EXAMPLES for the clerk, not literal copy.
CAPTION_TEMPLATES = {
    "A": [  # the record — an entry, filed
        "entry 90-042: a trap was found at the county line, new-set and unsprung. filed.",
        "the chapel bells rang at four in the morning. the chapel has no bells. filed.",
        "a canister of film was left on the counter overnight. it is marked vii. it has not been developed.",
    ],
    "B": [  # the county — a photograph and its taking
        "crossroads store, 1935. the man on the porch would not give his name.",
        "farmhouse at the county line, 1938. what was taken: the house, the fence, the weather.",
        "church interior, empty, 1939. the congregation is not in the file.",
    ],
    "C": [  # the holdings — the clothing, stated as fact
        "lot no. 3. screen printed, edition of 24, numbered by hand, sealed in wax. when it is gone it is gone.",
        "the office does not restock. each holding is printed once, in an edition of 24.",
        "every seal is pressed by hand. no two sit the same.",
    ],
    "D": [  # minimal — the office at its most spare
        "the file is not closed.",
        "what is not known is not in the file.",
        "one county, photographed since 1935.",
    ],
}

CAPTION_TYPE_CYCLE = ["A", "B", "C", "D"]

# Hashtag sets
BASE_HASHTAGS = [
    "#southerngothic",
    "#darkacademia",
    "#americana",
    "#gothic",
    "#screenprint",
]

NICHE_HASHTAGS = {
    "southern-gothic": [
        "#southerngothicaesthetic",
        "#ruralgothic",
        "#ethelcain",
        "#darkamericana",
        "#gothicaesthetic",
    ],
    "dark-academia": [
        "#darkacademiaaesthetic",
        "#darkacademiastyle",
        "#moodboard",
        "#vintageaesthetic",
        "#academiacore",
    ],
    "americana": [
        "#vintageamericana",
        "#1930s",
        "#dustbowl",
        "#oldphotos",
        "#ruralamerica",
    ],
    "vintage-photography": [
        "#filmgrain",
        "#vintagephotography",
        "#blackandwhitephotography",
        "#filmphotography",
        "#foundphotos",
    ],
    "gothic-fashion": [
        "#altfashion",
        "#gothicfashion",
        "#graphictee",
        "#limitededition",
        "#vintagestyle",
    ],
    "graphic-tees": [
        "#graphictees",
        "#screenprinting",
        "#bandtee",
        "#vintagetee",
        "#tshirtdesign",
    ],
    "folklore": [
        "#folklore",
        "#folkhorror",
        "#cryptid",
        "#superstition",
        "#appalachia",
    ],
}

# Posting schedule — optimal windows for the 18-35 aesthetic audience (EST)
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
    "southern gothic aesthetic",
    "dark academia outfit inspiration",
    "ethel cain aesthetic",
    "rural gothic americana",
    "1930s vintage photography",
    "screen printed tee outfit",
    "gothic fashion moodboard",
    "abandoned church aesthetic",
    "folk horror aesthetic",
    "film grain photography vintage",
]
