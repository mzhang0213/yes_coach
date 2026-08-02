"""LOL adapter — the reference GameAdapter, self-registered on import."""

from server.core import registry
from server.games.lol.state import LolGameState, LOL_SCHEMA
from server.games.lol.coach_config import LOL_COACH_PROFILE
from server.games.lol.tabs import TAB_ACTIONS
from server.games.lol.ui_cards import LolUICards
from server.games.lol.checkpoints import LolCheckpointRules
from server.games.lol.trends import LolTrendRules
from server.games.lol.live_source import GameStatePoller
from server.games.lol.client_source import ClientPoller
from server.games.lol.vision_service import VisionService
from server.games.lol.lcu import find_lcu_credentials


class LolAdapter:
    name = "lol"
    display_name = "League of Legends"

    def is_active(self) -> bool:
        try:
            return find_lcu_credentials() is not None
        except Exception:
            return False

    def state_schema(self):
        return LOL_SCHEMA

    def new_state(self):
        return LolGameState()

    def coach_profile(self):
        return LOL_COACH_PROFILE

    def tab_actions(self):
        return TAB_ACTIONS

    def ui_cards(self):
        return LolUICards()

    def data_sources(self, session, services):
        vision = VisionService()
        live = GameStatePoller(
            session, store=services.store, coach=services.coach, vision=vision,
            checkpoint_rules=LolCheckpointRules(),
            trend_rules=LolTrendRules(session.game.riot_id))
        client = ClientPoller(session, coach=services.coach)
        return [live, client]

    def current_state(self, session) -> dict:
        return session.game.compressed_state()

    def current_extra(self, session) -> dict:
        return {"map": session.game.map_summary}


registry.register(LolAdapter())
