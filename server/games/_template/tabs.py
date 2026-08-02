"""Template hover-menu tabs — the left-tab coaching intents."""

from server.core.adapter import TabAction

TAB_ACTIONS = [
    TabAction("Suggest play", None, "situation"),
    TabAction("Explain", "Explain the current situation and my best options.", "question"),
]
