import cv2 as cv
import numpy as np

from server.utils import show_imgs

img = cv.imread("test1.png")
map = cv.imread("map.png")
canny = img.copy()
canny = cv.Canny(canny, 100, 200)
lines = img.copy()
contours, _ = cv.findContours(canny, cv.RETR_TREE, cv.CHAIN_APPROX_SIMPLE)
cv.drawContours(lines,contours,-1,(0,255,0),2)


all_objs = [] #all contours
all_objs_areas = [] # areas of all contours
pos_objs = [] # biggest contours
for c in contours:
    closed = cv.convexHull(c)
    closed_area = cv.contourArea(closed)
    #for now, use 10e4; problems in future may arise where its necessary to access the top 5 or so biggest contours
    if closed_area > 1e4:
        all_objs.append(closed)
        all_objs_areas.append(closed_area)
    #    pos_objs.append(closed)
    #time.sleep(10/1000)
swaps=list(range(len(all_objs_areas)))
swaps.sort(key=lambda ind: all_objs_areas[ind], reverse=True)
for i in range(min(50,len(all_objs))):
    pos_objs.append(all_objs[swaps[i]])

final_lines = img.copy()
cv.drawContours(final_lines, pos_objs, -1, (0,255,0), 2)


show_imgs([img, canny, lines, final_lines])
