# Response schema templates — one per use-case.
# Each schema is sent inline with the prompt so the model knows exactly
# what shape to return. Keeping them small minimises per-turn token cost.

SCHEMAS: dict[str, dict] = {

    "situation": {
        "priority": "what to focus on RIGHT NOW (short phrase)",
        "action":   "specific next action (one sentence)",
        "warning":  "threat or risk to watch, or null",
    },

    # Player typed an explicit question (or a checkpoint phrased as one)
    "question": {
        "answer":    "direct answer to the question (one or two sentences)",
        "follow_up": "related thing to consider, or null",
    },

    # Triggered by a game event (kill, death, dragon, baron, tower)
    "event": {
        "event_type": "kill | death | dragon | baron | tower | other",
        "reaction":   "how to respond to this event (one sentence)",
        "adjustment": "what to change in your play going forward (one sentence)",
    },

    # Champ select — the player's ban turn
    "ban": {
        "target":       "champion to ban (single name)",
        "reason":       "why ban them, tied to your team/role (one sentence)",
        "alternatives": "1-2 other reasonable bans (list of names)",
    },

    # Champ select — the player's pick turn
    "pick": {
        "pick":         "champion to pick for your role (single name)",
        "reason":       "why this pick vs the current draft (one sentence)",
        "counters":     "enemy champs this pick struggles into, or null (list)",
        "alternatives": "1-2 other strong picks (list of names)",
    },

    # Champ select — player's champion is locked: recommend runes + summoner spells.
    # Use exact in-client names (e.g. "Conqueror", "Precision", "Adaptive Force").
    "loadout": {
        "primary_style":   "primary rune tree name (e.g. Precision)",
        "keystone":        "keystone rune name",
        "primary_runes":   "the 3 minor runes in the primary tree, slot order (list of names)",
        "secondary_style": "secondary rune tree name",
        "secondary_runes": "the 2 runes from the secondary tree (list of names)",
        "shards":          "the 3 stat shards, offense/flex/defense order (list of names)",
        "summoner_spells": "the two summoner spells (list of names)",
        "reason":          "one sentence: why this setup vs the enemy comp",
    },

    # Called once at game end for a session summary
    "post_game": {
        "summary":     "2-3 sentence overview of how the game went",
        "top_mistake": "single biggest mistake to fix",
        "focus_next":  "one concrete thing to practise next game",
    },
}
