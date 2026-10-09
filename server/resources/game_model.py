import itertools
from dataclasses import dataclass

from server.resources.checkpoint import Checkpoint

TIP_COOLDOWN_S = 180.0  # game s before a tip kind can come back after it was popped / cleared / expired


@dataclass
class Tip:
    """A quick pointer offered as a bubble: headline on the bubble, detail when popped.
    detail starts as rule-written text; a coach worker may replace it (detail_by="coach")."""
    id: int
    kind: str         # dedupe/cooldown key, e.g. "cs_low", "death@480", "cp:baron taken"
    headline: str
    detail: str
    priority: int     # higher first: objective timers > death review > economy
    created: float    # game s
    expires: float    # game s
    category: str = "macro"  # bubble colour: death | objective | farm | economy | macro
    detail_by: str = "rules"

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
        # tips (bubbles while the panel is open); kind → game s it may return
        self.tips: list[Tip] = []
        self.tip_cooldowns: dict[str, float] = {}
        self.tip_log: list[dict] = []   # popped tips: {"t", "kind", "headline"}
        self.open_tip: Tip | None = None  # popped tip whose detail card is showing
        self._tip_ids = itertools.count(1)
        # coach panel (rendered by the view while open):
        # suggestions None = analyzing; question set + answer None = answering
        self.suggestions: list[str] | None = None
        self.pinned_questions: list[str] = []  # always offered, after a divider, at the end of suggestions
        self.question: str | None = None
        self.answer: str | None = None
        # live game state as the coach sees it, refreshed by a controller worker;
        # None = Riot API unreachable (no game running)
        self.live_state: dict | None = None

    # ── tips ──
    def offer_tip(self, kind: str, headline: str, detail: str, priority: int,
                  now: float, ttl: float, category: str = "macro") -> Tip | None:
        """Add a tip unless one of that kind is already up or cooling down.
        Returns the new Tip (so the caller can have the coach refine its detail)."""
        if any(t.kind == kind for t in self.tips) or now < self.tip_cooldowns.get(kind, float('-inf')):
            return None
        tip = Tip(next(self._tip_ids), kind, headline, detail, priority, now, now + ttl, category)
        self.tips.append(tip)
        return tip

    def _retire_tip(self, tip: Tip, now: float):
        self.tips.remove(tip)
        self.tip_cooldowns[tip.kind] = now + TIP_COOLDOWN_S

    def clear_tip(self, kind: str, now: float):
        """The condition behind a tip no longer holds — take it down."""
        for tip in [t for t in self.tips if t.kind == kind]:
            self._retire_tip(tip, now)

    def expire_tips(self, now: float):
        for tip in [t for t in self.tips if now >= t.expires]:
            self._retire_tip(tip, now)

    def pop_tip(self, tip_id: int, now: float) -> Tip | None:
        """Player popped a bubble: show its detail card, log it, start its cooldown."""
        tip = next((t for t in self.tips if t.id == tip_id), None)
        if tip:
            self._retire_tip(tip, now)
            self.tip_log.append({"t": round(now), "kind": tip.kind, "headline": tip.headline})
            self.open_tip = tip
        return tip

    def tips_on_offer(self) -> list[Tip]:
        """Live tips, most important (then newest) first."""
        return sorted(self.tips, key=lambda t: (-t.priority, -t.created))

    def state_lines(self) -> list[str]:
        """Readable lines for the overlay's state toast (first line is the header)."""
        return []