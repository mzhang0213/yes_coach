"""LOL coaching-state: the single source of truth for the compressed snapshot.

`build_state` is the one place the ~150-byte coaching dict is assembled — it
replaces the three former copies (CoachModel.compressed_state,
gemini.compress_game_state, snapshot_store._STATE_COLS). `LOL_SCHEMA` declares
those fields once. `normalize_events` maps Riot's live event feed onto the
store's generic {id, name, time, raw} shape.
"""

from server.core.schema import Field, StateSchema

LOL_SCHEMA = StateSchema(
    fields=(
        Field("t", int),
        Field("mode", str),
        Field("hp", int),  Field("mhp", int),
        Field("mp", int),  Field("mmp", int),
        Field("g", int),   Field("lvl", int),
        Field("k", int),   Field("d", int),   Field("a", int),
        Field("cs", int),  Field("ad", int),  Field("ap", int),
    ),
    identity_key="champion",
)


def build_state(active: dict, scores: dict, game: dict) -> dict:
    """Strip live LOL data to the coaching-relevant ~150-byte snapshot."""
    active = active or {}
    scores = scores or {}
    game = game or {}
    cs = active.get("championStats", {})
    return {
        "t":   round(game.get("gameTime", 0)),
        "mode": game.get("gameMode", ""),
        "hp":  round(cs.get("currentHealth", 0)),
        "mhp": round(cs.get("maxHealth", 1)),
        "mp":  round(cs.get("resourceValue", 0)),
        "mmp": round(cs.get("resourceMax", 1)),
        "g":   round(active.get("currentGold", 0)),
        "lvl": active.get("level", 1),
        "k":   scores.get("kills", 0),
        "d":   scores.get("deaths", 0),
        "a":   scores.get("assists", 0),
        "cs":  scores.get("creepScore", 0),
        "ad":  round(cs.get("attackDamage", 0)),
        "ap":  round(cs.get("abilityPower", 0)),
    }


def normalize_events(raw_events: list[dict]) -> list[dict]:
    """Map Riot Live-Client events onto the store's generic event shape."""
    return [
        {
            "id":   e.get("EventID"),
            "name": e.get("EventName", ""),
            "time": e.get("EventTime", 0.0),
            "raw":  e,
        }
        for e in (raw_events or [])
    ]


class LolGameState:
    """Live LOL game + pre-game state, written by the LOL data sources and read
    by the LOL UI cards. Opaque to the generic overlay core."""

    def __init__(self):
        self.active_player = {}
        self.active_scores = {}  # /playerscores for the active player (k/d/a/cs)
        self.players = []
        self.game_stats = {}
        self.events = []
        self.map_summary = ""    # one-line minimap CV summary (vision_service)

        # Pre-game (LCU champ select) state.
        self.draft = {}                  # parsed champ-select draft (parse_draft)
        self.rune_recommendation = None  # {primary_style, keystone, ..., payload}
        self.pregame_suggestion = None   # {title, advice} ban/pick text advice
        self.runes_applied = False       # set once a page is written to the client

    def update_active_player(self, raw_data, scores=None):
        self.active_player = raw_data or {}
        if scores is not None:
            self.active_scores = scores

    def update_players(self, raw_data):
        self.players = self._api_filter("players", raw_data) if raw_data else []

    def update_events(self, raw_data):
        self.events = raw_data or []

    def update_game_stats(self, raw_data):
        self.game_stats = self._api_filter("gameStats", raw_data) if raw_data else {}

    def compressed_state(self) -> dict:
        return build_state(self.active_player, self.active_scores, self.game_stats)

    def riot_id(self) -> str:
        return (self.active_player or {}).get("riotId", "")

    def _api_filter(self, category: str, raw_data):
        expand = {"players", "player", "items", "item", "runes", "summonerSpells"}
        if category == "players":
            filtered = []
            for p in raw_data:
                filtered.append(self._api_filter("player", p))
            return filtered
        elif category == "player":
            filtered = {}
            keys = ["championName", "items", "level", "position", "respawnTimer", "runes", "scores", "summonerSpells", "team"]
            for k in keys:
                if k in expand:
                    filtered[k] = self._api_filter(k, raw_data[k])
                else:
                    filtered[k] = raw_data[k]
            return filtered
        elif category == "items":
            filtered = []
            for i in raw_data:
                filtered.append(self._api_filter("item", i))
            return filtered
        elif category == "item":
            filtered = {}
            keys = ["canUse", "consumable", "count", "displayName", "price"]
            for k in keys:
                filtered[k] = raw_data[k]
            return filtered
        elif category == "runes":
            filtered = {}
            for k in raw_data:
                filtered[k] = {
                    "displayName": raw_data[k]["displayName"],
                    "id": raw_data[k]["id"]
                }
            return filtered
        elif category == "summonerSpells":
            filtered = {}
            for k in raw_data:
                filtered[k] = {
                    "displayName": raw_data[k]["displayName"]
                }
            return filtered
        elif category == "gameStats":
            filtered = {}
            keys = ["gameMode", "gameTime"]
            for k in keys:
                filtered[k] = raw_data[k]
            return filtered
        else:
            print(f"UNCAUGHT CATEGORY: {category}")
            return None
