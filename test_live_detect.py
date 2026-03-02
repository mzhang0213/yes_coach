import sys
import time

import cv2 as cv
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from server.utils import GameState, show_imgs, Overlay, SCREEN_SIZE, screen_capture, stop_screen_capture, \
    screen_capture_instance


# #this image harvesting needs to be continuous
# img = cv.imread("./server/keys/test_1.png")
#
# gs = GameState(img)
# data = gs.get_boxes()
#
# # ret = []
# # for k in data:
# #     og = img.copy()
# #     stats = data[k]
# #     cv.rectangle(og, stats["full"][0], stats["full"][1], (0,0,255), thickness=10) #bgr
# #     ret.append(og)
# # show_imgs(ret)
#
# app = QApplication(sys.argv)
# window = Overlay()
# img_width, img_height = img.shape[1], img.shape[0]
# window_width, window_height = SCREEN_SIZE
#
# for d in data:
#     box = data[d]["full"]
#     scaled_tl,scaled_br = window.cvToQt(box[0],box[1],img_width,img_height)
#     window.add_rectangle(scaled_tl, scaled_br, False)
#
# show_imgs([img])
# sys.exit(app.exec())

def process_frame(frame):
    print(f"Processing frame at {time.strftime('%H:%M:%S')} - Shape: {frame.shape}")
    try:
        game_state = GameState(frame)
        boxes = game_state.get_boxes()
        print(f"Detected {len(boxes)} game elements")
    except Exception as e:
        print(f"Error processing frame: {str(e)}")


def tick():
    """Called by QTimer on the main thread — safe for OpenCV GUI."""
    if not screen_capture_instance.running:
        app.quit()
        return

    # Drain the display queue and show the latest frame
    frame = None
    while not screen_capture_instance.display_queue.empty():
        try:
            frame = screen_capture_instance.display_queue.get_nowait()
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