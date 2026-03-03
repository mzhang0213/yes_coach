import sys
import time

import cv2 as cv
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from server.utils import GameState, show_imgs, Overlay, SCREEN_SIZE, screen_capture, stop_screen_capture, \
    SCREEN_CAP


# #this image harvesting needs to be continuous
# sys.exit(app.exec())
first=True
def process_frame(frame):
    global first
    print(f"Processing frame at {time.strftime('%H:%M:%S')} - Shape: {frame.shape}")
    try:
        game_state = GameState(frame)
        if first:
            cv.imwrite("savetest.png", frame)
        print(f"frame: {frame.shape[::-1]}")
        boxes = game_state.get_boxes()
        print(f"Detected {len(boxes)} game elements")
        if first:
            qt_app = QApplication(sys.argv)
            window = Overlay()
            img_width, img_height = frame.shape[1], frame.shape[0]
            window_width, window_height = SCREEN_SIZE

            for d in boxes:
                box = boxes[d]["full"]
                scaled_tl,scaled_br = window.cvToQt(box[0],box[1],img_width,img_height)
                window.add_rectangle(scaled_tl, scaled_br, False)

            show_imgs([boxes])
            sys.exit(qt_app.exec())

            first=False
    except Exception as e:
        print(f"Error processing frame: {str(e)}")

#tick is used to detect wait key for both cv and pyqt
def tick():
    """Called by QTimer on the main thread — safe for OpenCV GUI."""
    if not SCREEN_CAP.running:
        app.quit()
        return

    # Drain the display queue and show the latest frame
    frame = None
    while not SCREEN_CAP.display_queue.empty():
        try:
            frame = SCREEN_CAP.display_queue.get_nowait()
        except Exception:
            break

    if frame is not None:
        cv.imshow('Live Screen Capture', frame)

    key = cv.waitKey(1)
    if key & 0xFF == ord('q'):
        print("'q' pressed, stopping...")
        stop_screen_capture()
        app.quit()


app = QApplication.instance() or QApplication(sys.argv)

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