import requests
import urllib3

###RIOT API INTEGRATION

BASE = "https://127.0.0.1:2999/liveclientdata"

# the Live Client API uses a self-signed cert on localhost, hence verify=False below
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def make_get_req(path: str, params: dict = None) -> dict | list | str:
    # short timeout: this runs on the GUI thread, and a loading / paused game can hang the socket
    resp = requests.get(f"{BASE}{path}", params=params, verify=False, timeout=1)
    resp.raise_for_status()
    return resp.json()

def get_all_game_data() -> dict:
    return make_get_req("/allgamedata")

def get_active_player() -> dict:
    return make_get_req("/activeplayer")
def get_active_player_name() -> str:
    return make_get_req("/activeplayername")
def get_active_player_abilities() -> dict:
    return make_get_req("/activeplayerabilities")
def get_active_player_runes() -> dict:
    return make_get_req("/activeplayerrunes")

def get_player_list() -> list:
    return make_get_req("/playerlist")

def get_player_scores(riot_id: str) -> dict:
    return make_get_req("/playerscores", params={"riotId": riot_id})
def get_player_summoner_spells(riot_id: str) -> dict:
    return make_get_req("/playersummonerspells", params={"riotId": riot_id})
def get_player_main_runes(riot_id: str) -> dict:
    return make_get_req("/playermainrunes", params={"riotId": riot_id})
def get_player_items(riot_id: str) -> list:
    return make_get_req("/playeritems", params={"riotId": riot_id})

def get_event_data() -> dict:
    return make_get_req("/eventdata")
def get_game_stats() -> dict:
    return make_get_req("/gamestats")


### LEAGUE CLIENT (LCU) — champ select / game phase, before the Live Client API exists
# The client writes a lockfile "name:pid:port:password:protocol" while it runs; requests use
# basic auth riot:<password> against https://127.0.0.1:<port> (self-signed cert).

import json
import os
import sys

LOCKFILE_PATHS = {
    "darwin": "/Applications/League of Legends.app/Contents/LoL/lockfile",
    "win32": r"C:\Riot Games\League of Legends\lockfile",
}


def _lcu_auth() -> tuple[str, tuple[str, str]] | None:
    """(base url, auth) from the lockfile, or None if the client isn't running.
    LEAGUE_LOCKFILE overrides the path for non-default installs."""
    path = os.environ.get("LEAGUE_LOCKFILE") or LOCKFILE_PATHS.get(sys.platform, "")
    try:
        with open(path) as f:
            _, _, port, password, protocol = f.read().strip().split(":")
    except (OSError, ValueError):
        return None
    return f"{protocol}://127.0.0.1:{port}", ("riot", password)


def lcu_get(path: str):
    """GET a client endpoint; None if the client isn't running or the resource doesn't exist
    (e.g. no champ select session)."""
    auth = _lcu_auth()
    if auth is None:
        return None
    base, creds = auth
    resp = requests.get(base + path, auth=creds, verify=False, timeout=2)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def get_gameflow_phase() -> str | None:
    """"None" | "Lobby" | "Matchmaking" | "ReadyCheck" | "ChampSelect" | "InProgress" |
    "EndOfGame" | …, or None if the client isn't running."""
    return lcu_get("/lol-gameflow/v1/gameflow-phase")


def get_champ_select_session() -> dict | None:
    return lcu_get("/lol-champ-select/v1/session")


def get_player_profile() -> dict | None:
    """The local player's level of play + experience: {"solo", "flex": "SILVER III" | None,
    "account_level", "mastery": {champion id: points}}, or None if the client isn't running."""
    ranked = lcu_get("/lol-ranked/v1/current-ranked-stats")
    if ranked is None:
        return None
    summoner = lcu_get("/lol-summoner/v1/current-summoner") or {}
    mastery = lcu_get("/lol-champion-mastery/v1/local-player/champion-mastery") or []

    def rank(queue):
        q = ranked.get("queueMap", {}).get(queue) or {}
        tier = q.get("tier")
        if not tier or tier in ("NONE", "NA", ""):
            return None
        division = q.get("division")
        return f"{tier} {division}" if division and division not in ("NA", "") else tier

    return {"solo": rank("RANKED_SOLO_5x5"), "flex": rank("RANKED_FLEX_SR"),
            "account_level": summoner.get("summonerLevel"),
            "mastery": {str(m["championId"]): m.get("championPoints", 0) for m in mastery}}


### DATA DRAGON — static champion / summoner spell / rune data, cached per patch

DDRAGON = "https://ddragon.leagueoflegends.com"
_STATIC_CACHE = os.path.join(os.path.dirname(__file__), "league", "ddragon_cache.json")


def load_static_data() -> dict:
    """{"version", "champions": {id: {"name", "tags", "attack", "magic"}}, "spells": {id: name},
    "runes": {tree: [[keystones], [row], [row], [row]]}}. Fetches the latest patch's files once
    and caches them; falls back to the cache when offline."""
    cached = None
    try:
        with open(_STATIC_CACHE) as f:
            cached = json.load(f)
    except (OSError, ValueError):
        pass
    try:
        version = requests.get(f"{DDRAGON}/api/versions.json", timeout=5).json()[0]
    except Exception:
        if cached:
            return cached
        raise
    if cached and cached.get("version") == version:
        return cached

    base = f"{DDRAGON}/cdn/{version}/data/en_US"
    champs = requests.get(f"{base}/champion.json", timeout=10).json()["data"].values()
    spells = requests.get(f"{base}/summoner.json", timeout=10).json()["data"].values()
    trees = requests.get(f"{base}/runesReforged.json", timeout=10).json()
    data = {
        "version": version,
        "champions": {c["key"]: {"name": c["name"], "tags": c["tags"],
                                 "attack": c["info"]["attack"], "magic": c["info"]["magic"]}
                      for c in champs},
        "spells": {s["key"]: s["name"] for s in spells if "CLASSIC" in s.get("modes", [])},
        "runes": {t["name"]: [[r["name"] for r in slot["runes"]] for slot in t["slots"]] for t in trees},
    }
    with open(_STATIC_CACHE, "w") as f:
        json.dump(data, f)
    return data
