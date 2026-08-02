"""Template UI cards — pill-only is valid; return [] for no action zones.

Draw game-specific cards with the generic Overlay primitives (add_text_box,
add_circle, add_arrow, draw_tab_button, ...) and return any ActionZones — the
hover-fill hitboxes the controller drives and fires on completion.
"""


class TemplateUICards:
    def phase_label(self, phase: str) -> str:
        return "Running" if phase == "InProgress" else "Not running"

    def draw_pregame(self, overlay, session) -> list:
        # e.g. draft/loadout cards; return ActionZones for hover-fill buttons.
        return []

    def draw_ingame(self, overlay, session) -> list:
        return []
