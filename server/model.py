"""Model layer — generic overlay UI state.

`OverlayUIState` holds the presentation/interaction state the view renders and
the controller mutates: the hover-fill state machine, coach results, and the
session lifecycle flags. It has no game knowledge. `GameSession` pairs it with a
game-specific state object the adapter owns; core never introspects `.game`.
"""

from dataclasses import dataclass


class OverlayModel:
    # State machine: idle → filling → unfurled → closing → cooldown → idle
    #   idle:     main button only
    #   filling:  hovering main button, bloom rising
    #   unfurled: side tabs visible
    #   closing:  re-hover bloom on main button, tabs frozen, completes → cooldown
    #   cooldown: wait for cursor to leave main button before allowing re-trigger
    def __init__(self, tab_labels=None):
        self.button_pos = None
        self.compl = 0.0
        self.user_question = None

        self.state = 'idle'
        self.has_left = False  # user moved cursor off all buttons since unfurl

        tab_labels = list(tab_labels or [])
        self.left_texts = tab_labels
        self.left_compls = [0.0] * len(tab_labels)
        self.right_compl = 0.0
        self.action_compl = 0.0   # generic hover-fill for an adapter action button

        # Session lifecycle (written by data sources).
        self.in_game = False       # True while the live game feed is reachable
        self.phase = "NotRunning"  # data-source phase label (e.g. LCU gameflow)

        # Coach results (surfaced proactively by the UI).
        self.checkpoints = []
        self.pending_suggestion = None  # {title, advice} awaiting the player
        self.last_advice = None         # most recent coach response (any source)


@dataclass
class GameSession:
    model: OverlayModel
    game: object   # adapter-owned game state; opaque to core
