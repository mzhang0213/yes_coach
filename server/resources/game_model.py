from dataclasses import dataclass

from server.resources.checkpoint import Checkpoint

@dataclass
class PlayerType:
    player_id:str
    player_name:str
    alive:bool
    #stats - hp, mana, etc (per game model)
    #todo: add more generics abt players

@dataclass
class StatsType: #since this is generic, make everything str
    score:str
    time:str

class GameState:
    active_player:PlayerType
    players:list[PlayerType]
    game_stats:StatsType

class GameModel:
    quick_actions:list[str]
    actions:list # log of button presses: [{"button": str, "time": float}, ...]
    checkpoints:list[Checkpoint]
    state_history:list[GameState]

    def __init__(self, checkpoints:list[Checkpoint], actions:list[str]):
        # self.user_question = None
        self.quick_actions = actions
        self.actions = []
        self.state_history = []
        self.checkpoints = checkpoints
        # written by the controller/coach worker, polled by the view each frame
        self.status = None
        self.advice = None