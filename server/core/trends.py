"""Trend seam — deriving coaching-relevant deltas over a snapshot window.

`TrendRules.compute` turns a window of state snapshots plus the raw event feed
into a small dict of deltas, so the coach sees *change* ("cs/min fell 7.2 ->
4.1") rather than raw history — this keeps per-call token cost flat. Games with
no trend concept return {}.
"""

from typing import Protocol


class TrendRules(Protocol):
    def compute(self, snapshots: list[dict], events: list) -> dict: ...
