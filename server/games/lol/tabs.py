"""LOL hover-menu tabs — the left-tab coaching intents."""

from server.core.adapter import TabAction

TAB_ACTIONS = [
    TabAction("Suggest plays", None, "situation"),
    TabAction("Team comp", "Analyze both team comps and how I should play around them.", "question"),
    TabAction("Build path", "What should I build next given the current game state?", "question"),
]
