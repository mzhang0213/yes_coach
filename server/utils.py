import cv2 as cv
import numpy as np
import os
import pytesseract
from matplotlib import pyplot as plt
import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                              QLabel, QLineEdit, QPushButton, QVBoxLayout)
from PyQt6.QtCore import Qt, QRect, QRectF, QEventLoop
from PyQt6.QtGui import (QPainter, QPen, QColor, QBrush, QFont,
                          QLinearGradient, QRadialGradient, QPainterPath, QPixmap)
from mss import mss
import time
import platform
import threading
from queue import Queue

import logging

from server.resources.region_menu import RegionMenu
import requests


class MDebug:
    def __init__(self):
        self.info = []
        self.start = time.time()
        logging.basicConfig(level=logging.INFO)

    def log_msg(self, msg):
        self.info.append({"type":"message","message":str(msg), "time":time.time()-self.start})

    def log_img(self, img, name):
        self.info.append({"type":"image","name":str(name), "img":img, "time":time.time()-self.start})

    def log_error(self, msg):
        self.info.append({"type":"error","message":str(msg), "time":time.time()-self.start})

    def dump(self, write_file=False):
        ret = ""
        os.makedirs("./logs/", exist_ok=True)
        for msg in self.info:
            if msg["type"]=="message":
                fmt_msg = "INFO ("+str(msg["time"])+"): "+msg["message"]
                logging.info(fmt_msg)
                ret+=fmt_msg+"\n"
            elif msg["type"]=="image":
                cv.imwrite(msg["name"]+str(msg["time"]),msg["img"])
            elif msg["type"]=="error":
                fmt_msg = f"(ERROR {str(msg["time"])}) |  {msg["message"]}"
                logging.error(fmt_msg)
                ret+=fmt_msg+"\n"

        if write_file:
            with open(f"./logs/logs{round(time.time(), ndigits=5)}.txt", "w") as f:
                f.write(ret)

FEATURES = {
    #screen_feature: (tl,br)
    "gamestats":  ((0.7,  0.0), (1.0,  0.5 )),
    "hotbar":     ((0.0,  0.5), (1.0,  1.0 )),
    "map":        ((0.5,  0.5), (1.0,  1.0 )),
    "playerstats":((0.0,  0.5), (0.5,  1.0 )),
    "tab_menu":   ((0.05, 0.0), (0.95, 0.85)),  # full-screen overlay (held Tab)
}
BASE_RESOLUTION = (1512, 982) #my screen res FEATURES were captured at

# Relative sub-regions for each readable value within a feature crop.
# Format: name -> { value_name: ((rx1, ry1), (rx2, ry2)) }
# All coords are fractions of the crop's (width, height) — tune from captures.

def _tab_menu_values() -> dict[str, tuple]:
    """
    Generate relative cell positions for the LoL tab scoreboard grid.
    Layout: game_time header | 5 blue rows | 5 red rows
    Columns: name, kda, cs, gold  (x anchors shared across all rows)
    """
    # Column x-ranges within the tab crop
    cols = {
        "name": (0.18, 0.38),
        "kda":  (0.40, 0.52),
        "cs":   (0.52, 0.59),
        "gold": (0.60, 0.68),
    }
    # Row y-ranges: blue team rows then red team rows
    # Each team occupies roughly half the crop; header ~7% at top
    row_h = 0.088  # height of one player row
    blue_y0, red_y0 = 0.10, 0.58
    blue_rows = [(blue_y0 + i * row_h, blue_y0 + (i + 1) * row_h) for i in range(5)]
    red_rows  = [(red_y0  + i * row_h, red_y0  + (i + 1) * row_h) for i in range(5)]

    values: dict[str, tuple] = {
        "game_time": ((0.38, 0.00), (0.62, 0.07)),
    }
    for team, rows in (("blue", blue_rows), ("red", red_rows)):
        for i, (y1, y2) in enumerate(rows, 1):
            for stat, (x1, x2) in cols.items():
                values[f"{team}{i}_{stat}"] = ((x1, y1), (x2, y2))
    return values


FEATURE_VALUES: dict[str, dict[str, tuple]] = {

    # Top HUD bar: timer (center), team gold/kills (sides)
    "gamestats": {
        "timer":         ((0.38, 0.00), (0.62, 1.00)),  # game clock, center
        "blue_kills":    ((0.10, 0.00), (0.30, 1.00)),  # blue team kill count
        "red_kills":     ((0.70, 0.00), (0.90, 1.00)),  # red team kill count
        "blue_gold":     ((0.05, 0.00), (0.25, 1.00)),  # blue team total gold
        "red_gold":      ((0.75, 0.00), (0.95, 1.00)),  # red team total gold
    },

    # Bottom-left player HUD: health/mana bars, level badge, XP bar
    "playerstats": {
        "health":        ((0.08, 0.55), (0.55, 0.68)),  # HP number on health bar
        "mana":          ((0.08, 0.72), (0.55, 0.84)),  # MP number on mana bar
        "level":         ((0.00, 0.45), (0.10, 0.60)),  # champion level badge
        "xp_bar":        ((0.00, 0.88), (1.00, 1.00)),  # XP progress (numeric if shown)
    },

    # Bottom-center hotbar: summoner spell CDs, gold, CS, KDA
    "hotbar": {
        "gold":          ((0.42, 0.72), (0.58, 0.90)),  # current gold
        "cs":            ((0.28, 0.72), (0.42, 0.90)),  # creep score
        "kda":           ((0.38, 0.10), (0.62, 0.30)),  # K/D/A line
        "spell1_cd":     ((0.03, 0.30), (0.13, 0.55)),  # summoner spell 1 cooldown
        "spell2_cd":     ((0.03, 0.55), (0.13, 0.80)),  # summoner spell 2 cooldown
    },

    # Minimap: no OCR targets (visual only)
    "map": {},

    # Tab scoreboard: game_time + blue1..5 / red1..5 × {name, kda, cs, gold}
    "tab_menu": _tab_menu_values(),
}

app = QApplication.instance() or QApplication(sys.argv)
_screensize=app.primaryScreen().size()
SCREEN_SIZE = _screensize.width(),_screensize.height()
MLOG = MDebug()



DYDX = []

class ScreenCapture:
    def __init__(self):
        self.running = False
        self.capture_thread = None
        self.last_frame = None
        self.frame_lock = threading.Lock()
        self.process_callback = None
        self.process_interval = 1.0
        self.last_process_time = 0
        self.latest_display_frame = None
        self.latest_process_frame = None
        self.display_lock = threading.Lock()
        self.process_lock = threading.Lock()

    def start_capture(self, process_callback=None, process_interval=1.0):
        if self.running:
            print("Screen capture is already running.")
            return False

        self.process_callback = process_callback
        self.process_interval = process_interval
        self.running = True

        self.capture_thread = threading.Thread(target=self.capturing, daemon=True)
        self.capture_thread.start()
        print("Screen capture started in background.")
        return True

    def stop_capture(self):
        if not self.running:
            return False
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)
        cv.destroyAllWindows()  # Safe — called from main thread by caller
        print("Screen capture stopped.")
        return True

    def get_latest_display_frame(self):
        """Get latest frame for display (thread-safe)"""
        with self.display_lock:
            frame = self.latest_display_frame
            self.latest_display_frame = None
            return frame

    def capturing(self):
        frame_count = 0
        start_time = time.time()
        last_display_time = 0
        display_interval = 1.0 / 30  # ~30 FPS

        try:
            with mss() as sct:
                monitor = sct.monitors[1]
                print(f"\nStarting background screen capture...")
                print(f"Resolution: {monitor['width']} x {monitor['height']}")

                while self.running:
                    try:
                        screenshot = sct.grab(monitor)
                        frame = np.array(screenshot)
                        frame = cv.cvtColor(frame, cv.COLOR_BGRA2BGR)

                        with self.frame_lock:
                            self.last_frame = frame

                        current_time = time.time()

                        # Update display frame at ~30 FPS (main thread will consume)
                        if current_time - last_display_time > display_interval:
                            with self.display_lock:
                                self.latest_display_frame = frame
                            last_display_time = current_time

                        # Update process frame on interval
                        if self.process_callback and (current_time - self.last_process_time) >= self.process_interval:
                            with self.process_lock:
                                self.latest_process_frame = frame
                            self.last_process_time = current_time

                            # Run callback in a separate thread
                            threading.Thread(
                                target=self.callback,
                                args=(frame,),
                                daemon=True
                            ).start()

                        frame_count += 1
                        time.sleep(0.01)

                    except Exception as e:
                        print(f"Error during capture: {str(e)}")
                        time.sleep(0.1)
                        continue

        except Exception as e:
            print(f"Critical error in capture: {str(e)}")
            if "Permission denied" in str(e) or "screen recording" in str(e).lower():
                print("\nScreen Recording permission denied. Check System Settings > Privacy.")
        finally:
            self.running = False
            elapsed = time.time() - start_time
            print(f"\nCapture thread finished. Captured {frame_count} frames.")
            if elapsed > 0:
                print(f"Total time: {elapsed:.2f}s, Average FPS: {frame_count/elapsed:.2f}")

    def callback(self, frame):
        try:
            self.process_callback(frame)
        except Exception as e:
            print(f"Error in process callback: {str(e)}")

SCREEN_CAP = ScreenCapture()

def screen_capture(process_callback=None, process_interval=1.0):
    """
    Starts screen capture in background with optional processing callback
    """
    return SCREEN_CAP.start_capture(process_callback, process_interval)

def stop_screen_capture():
    """
    Stops the background screen capture
    """
    return SCREEN_CAP.stop_capture()

def get_latest_frame():
    """
    Gets the latest captured frame
    """
    return SCREEN_CAP.get_latest_frame()



def setup_screen(overlay_agent: "Overlay") -> dict:
    """
    Init screen cap areas by letting user pick regions via menu, then draw them on the overlay.
    :param overlay_agent: the PyQt Overlay window
    :return: dict of name -> {left, top, width, height}
    """
    regions = RegionMenu(list(FEATURES.keys())).run()

    # Draw each selected region on the overlay in its assigned color
    overlay_agent.clearCanvas()
    for region in regions.values():
        tl = (region['left'], region['top'])
        br = (region['left'] + region['width'], region['top'] + region['height'])
        overlay_agent.add_rectangle(tl, br, False, color=region.get('color', (255, 0, 0)))

    return regions




#READ VALUES

def get_value_crop(feature_crop: np.ndarray, feature_name: str, value_name: str) -> np.ndarray | None:
    """Return the sub-crop for a named value within a feature crop, ready for OCR.

    Args:
        feature_crop: the already-cropped feature image (BGR numpy array)
        feature_name: key in FEATURE_VALUES  e.g. "gamestats"
        value_name:   key within that feature e.g. "timer"
    Returns:
        cropped numpy array, or None if the name isn't found / crop is empty
    """
    spec = FEATURE_VALUES.get(feature_name, {}).get(value_name)
    if spec is None:
        return None
    h, w = feature_crop.shape[:2]
    (rx1, ry1), (rx2, ry2) = spec
    crop = feature_crop[int(ry1 * h):int(ry2 * h), int(rx1 * w):int(rx2 * w)]
    return crop if crop.size > 0 else None


def read_value(feature_crop: np.ndarray, feature_name: str, value_name: str,
               digits_only: bool = False) -> str:
    """OCR a named value from a feature crop.

    Args:
        feature_crop: the already-cropped feature image
        feature_name: key in FEATURE_VALUES
        value_name:   key within that feature
        digits_only:  if True, restrict tesseract to digits (for numeric-only fields)
    Returns:
        stripped OCR string, or "" on failure
    """
    crop = get_value_crop(feature_crop, feature_name, value_name)
    if crop is None:
        return ""
    gray = cv.cvtColor(crop, cv.COLOR_BGR2GRAY)
    config = '--psm 7 --oem 3' + (' -c tessedit_char_whitelist=0123456789:/' if digits_only else '')
    try:
        return pytesseract.image_to_string(gray, config=config).strip()
    except Exception:
        return ""


def read_all_values(feature_crop: np.ndarray, feature_name: str,
                    digits_only: bool = False) -> dict[str, str]:
    """OCR every defined value for a feature at once.

    Returns:
        dict of value_name -> OCR string
    """
    return {
        name: read_value(feature_crop, feature_name, name, digits_only=digits_only)
        for name in FEATURE_VALUES.get(feature_name, {})
    }


