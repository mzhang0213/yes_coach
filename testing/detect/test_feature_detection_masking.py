import cv2 as cv
import numpy as np

from server.utils import show_imgs

img = cv.imread("test1.png")
map = cv.imread("map.png")


show_imgs([img])
