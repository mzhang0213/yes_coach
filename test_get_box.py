import cv2 as cv

from server.utils import GameState


def show_img(_img):
    while True:
        for i,_ in enumerate(_img):
            cv.imshow(f'img{str(i)}', _)

        if cv.waitKey(1) & 0xFF == ord('q'):
            break

img = cv.imread("./server/keys/test_1.png")
target = cv.imread("./server/keys/gamestats.png")
target = cv.cvtColor(target, cv.COLOR_BGR2GRAY)

h,w = img.shape[:2]

gs = GameState(img)
tl,br = gs.get_box(target,(int(w*0.75),0), (w,int(h*0.2)))
og = img.copy()
cv.rectangle(img, tl, br, (0,255,0))
cv.rectangle(og, (int(w*0.75),0), (w,int(h*0.2)), (0,255,0))
show_img([img,og])

'''
TODOS:
-map the rest of the boxes and features
-map the subsections
-integrate ocr

-continuous transmission while game is running
-python overlay
-determine final json req/res formats
'''