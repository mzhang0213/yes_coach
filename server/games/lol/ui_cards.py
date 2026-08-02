"""LOL overlay cards — champ-select rune card + ban/pick advice + phase labels.

Composes the generic Overlay primitives into LOL-specific pre-game cards and
returns the rune card's ActionZone (the hover-fill 'Apply runes' button, which
writes the page to the client via LCU). All LOL/LCU knowledge lives here, not in
the view.
"""

import threading

from server.core.ui_cards import ActionZone
from server.games.lol.lcu import apply_rune_page
from server.utils import SCREEN_SIZE

# LCU gameflow phase → human-readable status pill text.
_PHASE_LABELS = {
    "NotRunning":      "League not running",
    "None":            "In client",
    "Lobby":           "In lobby",
    "Matchmaking":     "In queue",
    "ReadyCheck":      "Match found!",
    "ChampSelect":     "Champ select — coaching",
    "InProgress":      "Loading into game…",
    "Reconnect":       "Reconnecting…",
    "WaitingForStats": "Loading stats…",
    "PreEndOfGame":    "Game ending",
    "EndOfGame":       "Post-game",
}


class LolUICards:
    def phase_label(self, phase: str) -> str:
        return _PHASE_LABELS.get(phase, "No game detected")

    def draw_pregame(self, overlay, session) -> list:
        if session.model.phase != "ChampSelect":
            return []
        g = session.game
        # Rune card (with hover-fill Apply button) takes precedence once a
        # loadout exists; otherwise show ban/pick advice text.
        if g.rune_recommendation:
            box = self._draw_rune_card(
                overlay, g.rune_recommendation, session.model.button_pos,
                apply_compl=session.model.action_compl, applied=g.runes_applied)
            return [ActionZone(
                box=box, fill_key="action_compl",
                on_complete=lambda: self._apply_runes(session),
                guard=lambda: not session.game.runes_applied)]
        if g.pregame_suggestion:
            self._draw_pregame_advice(overlay, session.model.button_pos, g.pregame_suggestion)
        return []

    def draw_ingame(self, overlay, session) -> list:
        return []

    # ── apply-runes action (LCU write-back) ──────────────────────────────────

    def _apply_runes(self, session):
        rec = session.game.rune_recommendation or {}
        payload = rec.get("payload")
        if not payload or not payload.get("selectedPerkIds"):
            print("No resolvable rune page to apply.")
            return

        def worker():
            try:
                apply_rune_page(payload)
                session.game.runes_applied = True
                print("Runes applied to client.")
            except Exception as e:
                print(f"Apply runes failed: {e}")

        threading.Thread(target=worker, daemon=True).start()

    # ── card drawing (uses the generic Overlay primitives) ───────────────────

    def _draw_pregame_advice(self, overlay, button_pos: dict, suggestion: dict):
        """Stack the coach's ban/pick advice as text boxes just below the pill.

        Schema-agnostic: renders the title then one line per non-empty advice
        field (lists are joined), so it works for both the ban and pick schemas.
        """
        advice = suggestion.get("advice") or {}
        title = suggestion.get("title") or "Coach"
        x = int(SCREEN_SIZE[0] * button_pos['x']) - 150
        y = int(SCREEN_SIZE[1] * button_pos['y']) + 34

        _, th = overlay.add_small_text_box(x, y, title, color=(60, 120, 200), font_size=11)
        y += th + 4
        for key, val in advice.items():
            if val in (None, "", []):
                continue
            if isinstance(val, (list, tuple)):
                val = ", ".join(str(v) for v in val)
            _, th = overlay.add_small_text_box(x, y, f"{key}: {val}",
                                               color=(40, 40, 40), font_size=9)
            y += th + 3

    def _draw_rune_card(self, overlay, rec: dict, button_pos: dict,
                        apply_compl: float = 0.0, applied: bool = False) -> tuple:
        """Annotated rune card: circles mark each recommended rune, an arrow +
        label highlights the keystone's rationale, and a hover-fill 'Apply runes'
        button writes the page. Returns the apply button's box."""
        x = int(SCREEN_SIZE[0] * button_pos['x']) - 175
        y = int(SCREEN_SIZE[1] * button_pos['y']) + 34

        _, th = overlay.add_small_text_box(x, y, "RECOMMENDED RUNES", color=(120, 75, 220), font_size=11)
        y += th + 4

        def rune_row(text, color, marker_filled, marker_r):
            nonlocal y
            _, h = overlay.add_small_text_box(x + 16, y, text, color=color, font_size=9)
            overlay.add_circle((x + 6, y + h // 2), marker_r, filled=marker_filled)
            y += h + 3
            return h

        # Primary tree + keystone (hollow ring marker), with an arrow→reason label.
        if rec.get("primary_style"):
            _, th = overlay.add_small_text_box(x, y, f"[{rec['primary_style']}]", color=(55, 115, 230), font_size=10)
            y += th + 2
        if rec.get("keystone"):
            ky = y
            kh = rune_row(rec["keystone"], (20, 20, 20), False, 8)
            if rec.get("reason"):
                overlay.add_arrow((x + 230, ky + kh // 2), (x + 18, ky + kh // 2))
                overlay.add_small_text_box(x + 236, ky, rec["reason"], color=(150, 90, 0), font_size=9)
        for r in rec.get("primary_runes") or []:
            rune_row(r, (60, 60, 60), True, 4)

        # Secondary tree
        if rec.get("secondary_style"):
            _, th = overlay.add_small_text_box(x, y, f"[{rec['secondary_style']}]", color=(55, 115, 230), font_size=10)
            y += th + 2
        for r in rec.get("secondary_runes") or []:
            rune_row(r, (60, 60, 60), True, 4)

        if rec.get("shards"):
            _, th = overlay.add_small_text_box(x, y, "Shards: " + ", ".join(rec["shards"]),
                                               color=(80, 80, 80), font_size=9)
            y += th + 2
        if rec.get("summoner_spells"):
            _, th = overlay.add_small_text_box(x, y, "Spells: " + ", ".join(rec["summoner_spells"]),
                                               color=(80, 80, 80), font_size=9)
            y += th + 4

        # Apply button (hover-fill). Turns into a confirmation once applied.
        label = "Runes applied ✓" if applied else "Apply runes"
        bg = (90, 90, 90) if applied else (38, 148, 73)
        box = overlay.draw_tab_button(x + 75, y + 17, 150, 34, text=label, bg=bg,
                                      completion=0.0 if applied else apply_compl)
        return (*box[0], *box[1])
