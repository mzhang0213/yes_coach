import cv2 as cv
import os

from server.utils import FEATURES, get_screen_coords, GameState, SCREEN_SIZE, BASE_RESOLUTION, ensure_fit

img = cv.imread("./savetest.png")

key_images = {}
scale_x = SCREEN_SIZE[0] / BASE_RESOLUTION[0]
scale_y = SCREEN_SIZE[1] / BASE_RESOLUTION[1]

keys_dir = os.path.join(os.path.dirname(__file__), 'keys')
for key in FEATURES:
    path = os.path.join(keys_dir, f"{key}.png")
    if os.path.exists(path):
        key_images[key] = cv.imread(path)
        
for key_name in FEATURES:
    if key_name not in key_images:
        continue

    curr_feature = key_images[key_name]
    img_h,img_w = img.shape[:2]
    kh, kw = curr_feature.shape[:2]
    new_kw = max(1, int(kw * scale_x))
    new_kh = max(1, int(kh * scale_y))
    scaled_feature = cv.resize(curr_feature, (new_kw, new_kh))
    searcharea_tl,searcharea_br = get_screen_coords(img_w,img_h,FEATURES[key_name])
    searcharea_tl, searcharea_br = ensure_fit(
        searcharea_tl, searcharea_br, new_kw, new_kh, img_w, img_h
    )
    area1 = img.copy()
    area1 = area1[searcharea_tl[1]:searcharea_br[1],searcharea_tl[0]:searcharea_br[0]]
    cv.imwrite(f"searchzone{key_name}.png",area1)
    cv.imwrite(f"target{key_name}.png",scaled_feature)