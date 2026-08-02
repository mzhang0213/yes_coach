import sys

import cv2 as cv
from PyQt6.QtCore import QTimer

from server.utils import app, stop_screen_capture
from server.model import OverlayModel
from server.view import OverlayView, ButtonPlacer
from server.controller import OverlayController

model = OverlayModel()
view = OverlayView()
controller = OverlayController(model, view)

model.button_pos = ButtonPlacer().pick()

# QTimer fires tick() every 16ms (~60fps) on the main thread inside app.exec()
timer = QTimer()
timer.timeout.connect(controller.tick)
timer.start(16)

try:
    sys.exit(app.exec())
except KeyboardInterrupt:
    print("\nStopping...")
    stop_screen_capture()
    cv.destroyAllWindows()
