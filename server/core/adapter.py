"""Game-adapter seam — bundles everything the overlay needs for one game.

An adapter wires a game's data sources, coach persona/schemas, hover-menu tabs,
and UI cards into the generic overlay. Adapters self-register (see
core.registry); `main.py` selects the active one and never imports a concrete
adapter.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TabAction:
    label: str            # tab button text (also the unfurled-menu label)
    question: str | None  # canned prompt, or None for live situational advice
    schema_key: str       # coach schema for the response


@dataclass
class Services:
    """Core singletons handed to an adapter so its data sources can orchestrate."""
    store: object = None
    coach: object = None


class GameAdapter(Protocol):
    name: str
    display_name: str

    def is_active(self) -> bool: ...
    def state_schema(self): ...                    # -> StateSchema
    def new_state(self): ...                        # fresh game-state object
    def coach_profile(self): ...                    # -> CoachProfile
    def tab_actions(self) -> list: ...              # -> list[TabAction]
    def ui_cards(self): ...                          # -> UICards
    def data_sources(self, session, services) -> list: ...   # -> list[DataSource]
    def current_state(self, session) -> dict: ...    # compact state for on-demand advice
    def current_extra(self, session) -> dict: ...    # extra context for on-demand advice
