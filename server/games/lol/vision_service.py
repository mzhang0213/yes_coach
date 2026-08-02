"""Minimap computer vision — the "map state" the Riot API can't expose.

Two paths, both cheap:

  * `summarize()` runs every poll. It crops the minimap, masks champion blips by
    colour (enemies red, allies blue/green) and emits a ONE-LINE TEXT summary
    (e.g. "enemies_visible:3/5 near_dragon:y"). Zero token cost — this string is
    merged into the LLM prompt.
  * `minimap_image()` returns a cropped, downscaled minimap as a PIL image for the
    RARE case where a decision checkpoint wants Gemini to actually look at the map.

Frames come from the shared ScreenCapture in utils.py (already running for the
overlay). Everything is wrapped so a missing frame / no screen-recording
permission degrades to an empty summary rather than crashing the poll loop.
"""

import cv2 as cv
import numpy as np

from server.utils import SCREEN_CAP, FEATURES

# HSV colour gates for minimap champion icons.
_RED1 = ((0, 120, 120), (10, 255, 255))
_RED2 = ((170, 120, 120), (180, 255, 255))
_BLUE = ((90, 120, 120), (130, 255, 255))
_GREEN = ((40, 80, 80), (85, 255, 255))   # self / allies render greenish

_MIN_BLOB_AREA = 6   # px; filters noise/pings
_MAX_BLOB_AREA = 400  # px; filters large coloured UI regions, not icons

# Objective pits as fractions of the minimap crop (Summoner's Rift, blue-corner
# minimap orientation: dragon bottom-right, baron top-left).
_DRAGON_PIT = ((0.55, 0.55), (1.0, 1.0))
_BARON_PIT = ((0.0, 0.0), (0.45, 0.45))


def _latest_frame() -> np.ndarray | None:
    with SCREEN_CAP.frame_lock:
        return None if SCREEN_CAP.last_frame is None else SCREEN_CAP.last_frame.copy()


def _crop_minimap(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    (x1, y1), (x2, y2) = FEATURES["map"]
    return frame[int(y1 * h):int(y2 * h), int(x1 * w):int(x2 * w)]


def _mask(hsv: np.ndarray, *ranges) -> np.ndarray:
    out = None
    for lo, hi in ranges:
        m = cv.inRange(hsv, np.array(lo), np.array(hi))
        out = m if out is None else cv.bitwise_or(out, m)
    return out


def _blob_centroids(mask: np.ndarray) -> list[tuple[int, int]]:
    contours, _ = cv.findContours(mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    centroids = []
    for c in contours:
        area = cv.contourArea(c)
        if _MIN_BLOB_AREA <= area <= _MAX_BLOB_AREA:
            M = cv.moments(c)
            if M["m00"]:
                centroids.append((M["m10"] / M["m00"], M["m01"] / M["m00"]))
    return centroids


def _in_region(pt, region, w, h) -> bool:
    (rx1, ry1), (rx2, ry2) = region
    x, y = pt
    return rx1 * w <= x <= rx2 * w and ry1 * h <= y <= ry2 * h


class VisionService:
    """Stateless wrapper around the shared screen-capture frame buffer."""

    def summarize(self) -> str:
        """One-line minimap summary, or "" if no frame is available."""
        frame = _latest_frame()
        if frame is None:
            return ""
        try:
            mm = _crop_minimap(frame)
            if mm.size == 0:
                return ""
            h, w = mm.shape[:2]
            hsv = cv.cvtColor(mm, cv.COLOR_BGR2HSV)

            enemies = _blob_centroids(_mask(hsv, _RED1, _RED2))
            allies = _blob_centroids(_mask(hsv, _BLUE, _GREEN))

            n_enemy = min(len(enemies), 5)
            n_ally = min(len(allies), 5)
            near_dragon = any(_in_region(p, _DRAGON_PIT, w, h) for p in enemies)
            near_baron = any(_in_region(p, _BARON_PIT, w, h) for p in enemies)

            parts = [f"enemies_visible:{n_enemy}/5", f"allies_visible:{n_ally}/5"]
            if near_dragon:
                parts.append("enemy_near_dragon:y")
            if near_baron:
                parts.append("enemy_near_baron:y")
            return " ".join(parts)
        except Exception:
            return ""

    def minimap_image(self, max_dim: int = 256):
        """Cropped, downscaled minimap as a PIL image for rare multimodal calls.

        Returns None if no frame or PIL is unavailable.
        """
        frame = _latest_frame()
        if frame is None:
            return None
        try:
            from PIL import Image
        except Exception:
            return None
        try:
            mm = _crop_minimap(frame)
            if mm.size == 0:
                return None
            h, w = mm.shape[:2]
            scale = max_dim / max(h, w)
            if scale < 1:
                mm = cv.resize(mm, (int(w * scale), int(h * scale)))
            rgb = cv.cvtColor(mm, cv.COLOR_BGR2RGB)
            return Image.fromarray(rgb)
        except Exception:
            return None
