import requests

###RIOT API INTEGRATION

BASE = "https://127.0.0.1:2999/liveclientdata"


def make_get_req(path: str, params: dict = None) -> dict | list | str:
    resp = requests.get(f"{BASE}{path}", params=params, verify=False)
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
