import sys

import cv2 as cv
from PyQt6.QtWidgets import QApplication

from server.utils import GameState, show_imgs, Overlay, SCREEN_SIZE

img = cv.imread("./server/keys/test_1.png")

gs = GameState(img)
data = gs.get_boxes()

# ret = []
# for k in data:
#     og = img.copy()
#     stats = data[k]
#     cv.rectangle(og, stats["full"][0], stats["full"][1], (0,0,255), thickness=10) #bgr
#     ret.append(og)
# show_imgs(ret)

app = QApplication(sys.argv)
window = Overlay()
img_width, img_height = img.shape[1], img.shape[0]
window_width, window_height = SCREEN_SIZE

for d in data:
    box = data[d]["full"]
    scaled_tl,scaled_br = window.cvToQt(box[0],box[1],img_width,img_height)
    window.add_rectangle(scaled_tl, scaled_br, False)

show_imgs([img])
sys.exit(app.exec())
