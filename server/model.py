"""Model layer — application state for the coach overlay.

Holds the data the view renders from and the controller mutates. No PyQt,
no drawing, no input handling — just state.
"""


class CoachModel:
    # State: idle → filling → unfurled → closing → cooldown → idle
    #   idle:     main button only
    #   filling:  hovering main button, bloom rising
    #   unfurled: side tabs visible
    #   closing:  re-hover bloom on main button, tabs frozen, completes → cooldown
    #   cooldown: wait for cursor to leave main button before allowing re-trigger
    def __init__(self):
        self.button_pos = None
        self.compl = 0.0
        self.user_question = None

        self.state = 'idle'
        self.has_left = False  # user moved cursor off all buttons since unfurl

        self.left_texts = ["Suggest plays", "Team comp", "Build path"]
        self.left_compls = [0.0, 0.0, 0.0]
        self.right_compl = 0.0


        #actual game state

        self.active_player = {}

        self.players = []

        self.game_stats = {}

        self.events = []

        self.checkpoints = [
            {
                "title":"",
                "indicator": {

                }
            }
        ]

    def update_players(self, raw_data):
        #update the players
        return

    def update_events(self, raw_data):
        #update the events 直接
        self.events = raw_data

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