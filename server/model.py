"""Model layer — application state for the coach overlay.

Holds the game data the view renders from and the controller mutates, plus a
log of which UI buttons were pressed and when. Button positions, animations and
hover state live in the view — the model only cares that a press happened. No
PyQt, no drawing, no input handling — just state.
"""
import time

from server.resources.game_model import GameModel


class OverlayModel:
    def __init__(self, game:GameModel):
        self.game = game

    # def update_players(self, raw_data):
    #     #update the players
    #     return
    #
    # def update_events(self, raw_data):
    #     #update the events 直接
    #     self.events = raw_data

    def record_press(self, button: str):
        """Record that a UI button crossed its activation threshold, timestamped."""
        self.presses.append({"button": button, "time": time.time()})

    def update_quick_actions(self, new_actions:list[str]):
        self.quick_actions = new_actions

    def update_game_stats(self, raw_data):
        #update the game stats
        self.game_stats = self._api_filter("gameStats", raw_data)

    def _api_filter(self, category: str, raw_data):
        #NOTES: more data is available for the active player, but not necessarily utilized
        #TODO: impl more data for active player
        expand = {"players", "player", "items", "item", "runes", "summonerSpells"}
        if category == "players":
            filtered = []
            for p in raw_data:
                filtered.append(self._api_filter("player", p))
            return filtered
        elif category == "player":
            filtered = {}
            keys = ["championName", "items", "level", "position", "respawnTimer", "runes", "scores", "summonerSpells", "team"] #no summ name or riot id
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

    #ai interfacing
    # def run_query(self, prompt:str):

    #checkpoint interfacing
