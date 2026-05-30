import os
import sys
import time

import cv2 as cv
import pyautogui
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from server.utils import Overlay, ButtonPlacer, stop_screen_capture, PromptWindow

BUTTON_POS = None
COMPL = 0.0
PROMPT_WINDOW = None
USER_QUESTION = None

# State: idle → filling → unfurled → closing → cooldown → idle
#   idle:     main button only
#   filling:  hovering main button, bloom rising
#   unfurled: side tabs visible
#   closing:  re-hover bloom on main button, tabs frozen, completes → cooldown
#   cooldown: wait for cursor to leave main button before allowing re-trigger
STATE = 'idle'
HAS_LEFT = False  # user has moved cursor off all buttons at least once since unfurl

LEFT_TEXTS = ["Suggest plays", "Team comp", "Build path"]
LEFT_COMPLS = [0.0, 0.0, 0.0]
RIGHT_COMPL = 0.0

NOTEBOOK_ICON = None


def run_prompt():
    return


def show_prompt_window():
    global PROMPT_WINDOW, USER_QUESTION
    if PROMPT_WINDOW and PROMPT_WINDOW.isVisible():
        return

    def on_submit(text):
        global USER_QUESTION
        USER_QUESTION = text
        print(f"User question: {text}")
        # TODO: pass to gemini coach

    PROMPT_WINDOW = PromptWindow(callback=on_submit)
    PROMPT_WINDOW.show()


def _in_box(x, y, box):
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def tick():
    global COMPL, STATE, HAS_LEFT, LEFT_COMPLS, RIGHT_COMPL

    window.clearCanvas()
    if not BUTTON_POS:
        return

    # always draw main button
    (bx1, by1), (bx2, by2) = window.draw_gemini_button(
        "Ask Coach!!", x=BUTTON_POS['x'], y=BUTTON_POS['y'],
        completion=COMPL,
    )

    mx, my = pyautogui.position()
    on_main = _in_box(mx, my, (bx1, by1, bx2, by2))

    # ── idle ──────────────────────────────────────────────
    if STATE == 'idle':
        if on_main:
            STATE = 'filling'
            COMPL = 0.019

    # ── filling ───────────────────────────────────────────
    elif STATE == 'filling':
        if on_main:
            if int(COMPL * 100) / 100 >= 0.98:
                STATE = 'unfurled'
                COMPL = 1.0
                HAS_LEFT = False
            elif COMPL <= 1.0:
                COMPL += 0.019
        else:
            STATE = 'idle'
            COMPL = 0.0

    # ── unfurled ──────────────────────────────────────────
    elif STATE == 'unfurled':
        COMPL = 0.0
        main_w = bx2 - bx1
        main_h = by2 - by1
        main_cy = (by1 + by2) // 2

        # tab sizing
        tab_h = int(main_h * 0.82)
        tab_w = int(main_w * 0.65)
        tab_w_right = tab_h  # square for icon-only
        gap = 10
        tab_gap = 5

        # ── left tabs (stacked, centered vertically on main button) ──
        total_left_h = 3 * tab_h + 2 * tab_gap
        left_top = main_cy - total_left_h // 2
        left_cx = bx1 - gap - tab_w // 2

        left_boxes = []
        for i in range(3):
            ty = left_top + i * (tab_h + tab_gap) + tab_h // 2
            box = window.draw_tab_button(
                left_cx, ty, tab_w, tab_h,
                text=LEFT_TEXTS[i], bg=(50, 100, 190),
                completion=LEFT_COMPLS[i],
            )
            left_boxes.append((*box[0], *box[1]))

        # ── right tab ──
        right_cx = bx2 + gap + tab_w_right // 2
        rbox = window.draw_tab_button(
            right_cx, main_cy, tab_w_right, tab_h,
            icon=NOTEBOOK_ICON, bg=(180, 180, 180),
            completion=RIGHT_COMPL,
        )
        right_box = (*rbox[0], *rbox[1])

        # ── hover logic ──
        on_any = on_main
        for i, lb in enumerate(left_boxes):
            if _in_box(mx, my, lb):
                on_any = True
                if int(LEFT_COMPLS[i] * 100) / 100 >= 0.98:
                    # TODO: trigger left tab action
                    LEFT_COMPLS[i] = 0.0
                elif LEFT_COMPLS[i] <= 1.0:
                    LEFT_COMPLS[i] += 0.019
            else:
                LEFT_COMPLS[i] = 0.0

        if _in_box(mx, my, right_box):
            on_any = True
            if int(RIGHT_COMPL * 100) / 100 >= 0.98:
                RIGHT_COMPL = 0.0
                show_prompt_window()
            elif RIGHT_COMPL <= 1.0:
                RIGHT_COMPL += 0.019
        else:
            RIGHT_COMPL = 0.0

        if not on_any:
            HAS_LEFT = True

        # re-hover on OG after leaving → start close animation
        if HAS_LEFT and on_main:
            STATE = 'closing'
            COMPL = 0.0
            LEFT_COMPLS = [0.0, 0.0, 0.0]
            RIGHT_COMPL = 0.0

    # ── closing ──────────────────────────────────────────
    elif STATE == 'closing':
        # draw side tabs frozen (no interaction) while close animation plays
        main_w = bx2 - bx1
        main_h = by2 - by1
        main_cy = (by1 + by2) // 2

        tab_h = int(main_h * 0.82)
        tab_w = int(main_w * 0.65)
        tab_w_right = tab_h
        gap = 10
        tab_gap = 5

        total_left_h = 3 * tab_h + 2 * tab_gap
        left_top = main_cy - total_left_h // 2
        left_cx = bx1 - gap - tab_w // 2

        for i in range(3):
            ty = left_top + i * (tab_h + tab_gap) + tab_h // 2
            window.draw_tab_button(
                left_cx, ty, tab_w, tab_h,
                text=LEFT_TEXTS[i], bg=(50, 100, 190),
                completion=0.0,
            )

        right_cx = bx2 + gap + tab_w_right // 2
        window.draw_tab_button(
            right_cx, main_cy, tab_w_right, tab_h,
            icon=NOTEBOOK_ICON, bg=(180, 180, 180),
            completion=0.0,
        )

        # bloom on main button to confirm close
        if on_main:
            if int(COMPL * 100) / 100 >= 0.98:
                STATE = 'cooldown'
                COMPL = 0.0
                HAS_LEFT = False
            elif COMPL <= 1.0:
                COMPL += 0.019
        else:
            # moved off main → cancel close, back to unfurled
            STATE = 'unfurled'
            COMPL = 1.0

    # ── cooldown ─────────────────────────────────────────
    elif STATE == 'cooldown':
        # wait for cursor to leave main button before re-enabling
        if not on_main:
            STATE = 'idle'


app = QApplication.instance() or QApplication(sys.argv)
window = Overlay()

# load notebook icon once
_icon_path = os.path.join(os.path.dirname(__file__), 'notebook_icon.png')
if os.path.exists(_icon_path):
    NOTEBOOK_ICON = QPixmap(_icon_path)

BUTTON_POS = ButtonPlacer().pick()

# QTimer fires tick() every 16ms (~60fps) on the main thread inside app.exec()
timer = QTimer()
timer.timeout.connect(tick)
timer.start(16)

try:
    sys.exit(app.exec())
except KeyboardInterrupt:
    print("\nStopping...")
    stop_screen_capture()
    cv.destroyAllWindows()