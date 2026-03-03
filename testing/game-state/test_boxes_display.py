import cv2 as cv

from server.utils import GameState, show_imgs


img = cv.imread("./savetest.png")

gs = GameState(img)
data = gs.get_boxes()

ret = []
for k in data:
    og = img.copy()
    stats = data[k]
    cv.rectangle(og, stats["full"][0], stats["full"][1], (0,0,255), thickness=10) #bgr
    ret.append(og)

show_imgs(ret)