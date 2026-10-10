# Response schema templates — one per use-case.
# Each schema is sent inline with the prompt so the model knows exactly
# what shape to return. Keeping them small minimises per-turn token cost.

SCHEMAS: dict[str, dict] = {

    "situation": {
        "priority": "what to focus on RIGHT NOW (short phrase)",
        "action":   "specific next action (one sentence)",
        "warning":  "threat or risk to watch, or null",
    },

    # Player asked an explicit question (typed or picked from suggestions)
    "question": {
        "action": "the one thing to do, imperative, max 12 words (who / where / when)",
        "why":    "one sentence naming the specific numbers, champions or timers behind it",
    },

    # Guess why the player opened the coach and offer questions to ask
    "suggest": {
        "questions": ["up to 5 short questions (max 6 words each) the player would ask, in their own voice "
                      "('How's my CS?', 'Do we have lane prio?'), neutral and open, never stating a "
                      "problem or verdict ('Why is your CS so low?') — the diagnosis belongs in the answer. "
                      "Each must be specific to this moment and have a concrete answer in the state/context; "
                      "not the generic 'What should I do / where should I be / what should I buy' "
                      "(always offered separately). Every question on a DIFFERENT topic: never a narrower version of "
                      "another (not 'Why did I die?' plus 'Was I overextended?' — pick one). Fewer is better than filler"],
    },

    # Detail for a tip bubble (headline + rule-written facts given in the question)
    "tip": {
        "action": "the one thing to do now, imperative, max 12 words",
        "why":    "one sentence with the specific numbers / champions / timers from state and context",
    },

    # Champ select: comp reads + loadout. Runes/summoners must come from the options in context.
    "draft": {
        "reads": [{"headline": "2-4 word team comp read",
                   "action": "what to do about it, imperative, max 12 words",
                   "why": "one sentence naming the champions involved", "side": "ally | enemy"}],
        "runes": {"primary_tree": "rune tree", "keystone": "keystone (row 0 of primary_tree)",
                  "primary": ["3 runes from primary_tree, one each from rows 1-3"],
                  "secondary_tree": "a different tree", "secondary": ["2 runes from secondary_tree, different rows 1-3"]},
        "summoners": ["2 summoner spells"],
        "why": "one sentence: why this loadout against this enemy comp",
    },

    # Triggered by a game event (kill, death, dragon, baron, tower)
    "event": {
        "event_type": "kill | death | dragon | baron | tower | other",
        "reaction":   "how to respond to this event (one sentence)",
        "adjustment": "what to change in your play going forward (one sentence)",
    },

    # Called once at game end for a session summary
    "post_game": {
        "summary":     "2-3 sentence overview of how the game went",
        "top_mistake": "single biggest mistake to fix",
        "focus_next":  "one concrete thing to practise next game",
    },
}
