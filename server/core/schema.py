"""State-schema seam — a game's compact coaching-state field declaration.

`GameState` is a plain dict (JSON-friendly, and exactly what the coach already
consumes). `StateSchema` is the single, once-per-game declaration of that
dict's fields — it documents the state shape and names the game-identity field.

It is deliberately NOT used to generate SQL columns: the SnapshotStore persists
state as a JSON blob, so adding a game never touches the DB schema.
"""

from dataclasses import dataclass
from typing import Any

GameState = dict[str, Any]


@dataclass(frozen=True)
class Field:
    key: str
    type: type = int


@dataclass(frozen=True)
class StateSchema:
    fields: tuple[Field, ...]
    identity_key: str | None = None   # generic stand-in for LOL's 'champion' label

    def keys(self) -> list[str]:
        return [f.key for f in self.fields]
