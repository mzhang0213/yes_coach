"""Template adapter — copy this folder to games/<yourgame>/ and fill in the seams.

Underscore-prefixed folders are skipped by registry.discover(), so this template
never auto-registers. Once copied & renamed, the module-level register(...) call
wires your adapter in (or select it explicitly with YESCOACH_GAME=<yourgame>).
"""

from server.core import registry
from server.games._template.state import TemplateGameState, TEMPLATE_SCHEMA
from server.games._template.coach_config import TEMPLATE_COACH_PROFILE
from server.games._template.tabs import TAB_ACTIONS
from server.games._template.ui_cards import TemplateUICards
from server.games._template.source import TemplateSource


class TemplateAdapter:
    name = "_template"           # rename to your game key (also the YESCOACH_GAME value)
    display_name = "Template Game"

    def is_active(self) -> bool:
        return False             # detect whether your game is running (client/process/window)

    def state_schema(self):
        return TEMPLATE_SCHEMA

    def new_state(self):
        return TemplateGameState()

    def coach_profile(self):
        return TEMPLATE_COACH_PROFILE

    def tab_actions(self):
        return TAB_ACTIONS

    def ui_cards(self):
        return TemplateUICards()

    def data_sources(self, session, services):
        return [TemplateSource(session, store=services.store, coach=services.coach)]

    def current_state(self, session) -> dict:
        return session.game.compressed_state()

    def current_extra(self, session) -> dict:
        return {}


registry.register(TemplateAdapter())
