import sys
import threading
import time
from typing import Any

import cv2 as cv
import numpy as np
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from server.utils import GameState, show_imgs, Overlay, SCREEN_SIZE, screen_capture, stop_screen_capture, \
    SCREEN_CAP, MLOG

# #this image harvesting needs to be continuous

overlay_queue = None
first=True
FRAME = None
DELAY_CAP = False

def process_frame(frame):
    global first, overlay_queue
    print(f"Processing frame at {time.strftime('%H:%M:%S')} - Shape: {frame.shape}")
    try:
        game_state = GameState(frame)
        if first:
            cv.imwrite("savetest.png", frame)
        print(f"frame: {frame.shape[::-1]}")
        boxes = game_state.get_boxes()
        print(f"Detected {len(boxes)} game elements")
        overlay_queue = {
            "img_w": frame.shape[1],
            "img_h": frame.shape[0],
            "boxes": boxes
        }
    except Exception as e:
        print(f"Error processing frame: {str(e)}")

def export_state_capture():
    global FRAME, overlay_queue
    print("capturing!")
    if FRAME is None:
        print("FRAME NOT DETECTED")
        return
    if overlay_queue is None:
        print("overlay_queue NOT DETECTED")
        return
    boxes = overlay_queue.get("boxes")
    for key in boxes:
        box = boxes[key]["full"]
        if not np.all(np.array(box) == 0):
            im_boxed = FRAME[box[0][1]:box[1][1], box[0][0]:box[1][0]]
            cv.imwrite(f"cap-box_{key}.png", im_boxed)
    cv.imwrite("cap-main_frame.png", FRAME)

DELAY_CAP = False
#tick is a periodic displayer and also detects wait key for both cv and pyqt
def tick():
    global overlay_queue, FRAME, DELAY_CAP
    """Called by QTimer on the main thread — safe for OpenCV GUI."""
    if not SCREEN_CAP.running:
        app.quit()
        return

    # Get the latest display frame
    frame = SCREEN_CAP.get_latest_display_frame()
    
    if frame is not None:
        FRAME = frame

    if overlay_queue is not None:
        img_w = overlay_queue["img_w"]
        img_h = overlay_queue["img_h"]
        boxes = overlay_queue["boxes"]

        window.clearCanvas()
        for key in boxes:
            box = boxes[key]["full"]
            scaled_tl, scaled_br = window.cvToQt(box[0], box[1], img_w, img_h)
            window.add_rectangle(scaled_tl, scaled_br, False)

    if frame is not None:
        cv.imshow('Live Screen Capture', frame)

    key = cv.waitKey(1)
    if key & 0xFF == ord('q'):
        print("'q' pressed, stopping...")
        MLOG.dump(write_file=True)
        stop_screen_capture()
        app.quit()
    if key & 0xFF == ord('c'):
        #capture
        export_state_capture()
        DELAY_CAP = False
    if key & 0xFF == ord('v'):
        #capture delay
        if not DELAY_CAP:
            print(" -- DELAY CAP INITIATED -- ")
            DELAY_CAP = True
            threading.Timer(3, export_state_capture).start()



app = QApplication.instance() or QApplication(sys.argv)
window = Overlay()

print("Starting screen capture...")
success = screen_capture(process_callback=process_frame, process_interval=1.0)

if not success:
    print("Failed to start screen capture")
    sys.exit(1)

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
'''
- do not run detections on bad screens - use iqr detection and high distribution
-
'''