"""LOL coach profile — the persona + output schemas injected into the engine."""

import os

from server.core.coach import CoachProfile
from server.games.lol.prompts.schemas import SCHEMAS

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")


def _load_system_prompt() -> str:
    with open(os.path.join(_PROMPTS_DIR, "context.txt")) as f:
        return f.read().strip()


LOL_COACH_PROFILE = CoachProfile(system_prompt=_load_system_prompt(), schemas=SCHEMAS)
