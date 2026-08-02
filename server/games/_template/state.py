"""Template game state — declare your compact coaching-state fields once."""

from server.core.schema import Field, StateSchema

# The fields your coach sees each turn. Keep them short (token cost) and stable.
TEMPLATE_SCHEMA = StateSchema(
    fields=(
        Field("t", int),      # a monotonic clock/turn used for ordering & windows
        # Field("score", int),
        # Field("hp", int),
    ),
    identity_key=None,        # e.g. "character" — a label for per-match metadata
)


def build_state(raw) -> dict:
    """Strip a raw signal frame to the compact dict declared in TEMPLATE_SCHEMA."""
    return {"t": 0}


class TemplateGameState:
    """Mutable per-session game state, written by your data source(s) and read by
    your UI cards. Opaque to the generic overlay core."""

    def __init__(self):
        self.latest = {}

    def compressed_state(self) -> dict:
        return build_state(self.latest)
