"""Checkpoint seam — deciding WHEN the coach should proactively speak.

`Checkpoint` is the generic carrier: it names the trigger, the schema the LLM
should answer with, and whether the decision is map-dependent enough to warrant
sending an image. `CheckpointRules` decides which checkpoints fire this cycle
and dedups so each fires once. The concrete triggers (objective timers, event
kinds, derived-metric thresholds) live in a game's rules implementation.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Checkpoint:
    key: str
    title: str
    schema_key: str = "situation"
    event_type: str | None = None
    want_image: bool = False


class CheckpointRules(Protocol):
    def check(self, state: dict, events: list, trends: dict) -> list[Checkpoint]:
        """Return checkpoints that fire for this cycle (deduped across cycles)."""
        ...

    def reset(self) -> None:
        """Clear per-game dedup state (call when a new game starts)."""
        ...
