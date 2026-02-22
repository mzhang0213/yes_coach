import cv2 as cv
import numpy as np
import os
import pytesseract
from matplotlib import pyplot as plt

KEYS = ["gamestats", "hotbar", "items", "map", "playerstats"]

class GameState:

    def __init__(self, img):
        self.img = img #the frame of the game state to analyze
        self.key_images = {}
        #todo: rework this cuz shouldn't be duplicated for each game state
        keys_dir = os.path.join(os.path.dirname(__file__), 'keys')
        for key in KEYS:
            path = os.path.join(keys_dir, f"{key}.png")
            if os.path.exists(path):
                self.key_images[key] = cv.imread(path)

    def find_outliers_iqr(self, data: list) -> tuple[list, list]:
        """
        Find outliers using the Interquartile Range (IQR) method.

        :param data: List of numeric values
        :return: (filtered_data, indices)
        """
        data = np.array(data)
        if len(data) == 0:
            return [], []

        # Convert to numpy array
        arr_data = np.array(data)

        # Handle both scalar and coordinate data
        if arr_data.ndim == 1:  # 1D array (scalar values)
            Q1 = np.percentile(arr_data, 25)
            Q3 = np.percentile(arr_data, 75)
            IQR = Q3 - Q1
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR

            filtered_data = []
            indices = []
            for i, val in enumerate(arr_data):
                if lower_bound <= val <= upper_bound:
                    filtered_data.append(data[i])  # Use original data to preserve type
                    indices.append(i)
        else:  # 2D array (coordinates or multi-dimensional data)
            # Process each dimension separately
            filtered_data = []
            indices = []
            for i, coord in enumerate(arr_data):
                coord_valid = True
                for dim_idx in range(len(coord)):
                    dim_data = arr_data[:, dim_idx]
                    Q1 = np.percentile(dim_data, 25)
                    Q3 = np.percentile(dim_data, 75)
                    IQR = Q3 - Q1
                    lower_bound = Q1 - 1.5 * IQR
                    upper_bound = Q3 + 1.5 * IQR

                    if not (lower_bound <= coord[dim_idx] <= upper_bound):
                        coord_valid = False
                        break

                if coord_valid:
                    filtered_data.append(data[i])  # Use original data to preserve type
                    indices.append(i)

        return filtered_data, indices

    def get_box(self, target) -> tuple[tuple[int, int], tuple[int, int]]:
        """
        Retrieves the bounding box on the screen containing target (key image).
        :param target: target image as np.array image
        :return: bounding box - (top left coordinate, bottom right coordinate)
        """
        #Source: https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
        #(note minor edits made)
        assert self.img is not None, "this game state's img could not be read"
        assert target is not None, "target image is None"

        # Template matching works best in grayscale or with matched channels
        img = cv.cvtColor(self.img, cv.COLOR_BGR2GRAY)
        if len(target.shape) == 3:
            target = cv.cvtColor(target, cv.COLOR_BGR2GRAY)

        w, h = target.shape[::-1]

        # All the 6 methods for comparison in a list
        methods = ['TM_CCOEFF', 'TM_CCOEFF_NORMED', 'TM_CCORR',
                   'TM_CCORR_NORMED', 'TM_SQDIFF', 'TM_SQDIFF_NORMED']

        results = []

        for m in methods:
            method = getattr(cv, m)
            # Apply template Matching
            res = cv.matchTemplate(img,target,method)
            min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)

            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED]:
                top_left = int(min_loc[0]), int(min_loc[1])
            else:
                top_left = int(max_loc[0]), int(max_loc[1])
            bottom_right = int(top_left[0] + w), int(top_left[1] + h)

            curr_box = top_left,bottom_right
            results.append(curr_box)

            # cv.rectangle(img,top_left, bottom_right, 255, 2)

            # plt.subplot(121),plt.imshow(res,cmap = 'gray')
            # plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
            # plt.subplot(122),plt.imshow(img,cmap = 'gray')
            # plt.title('Detected Point'), plt.xticks([]), plt.yticks([])
            # plt.suptitle(meth)
            #
            # plt.show()

        # Extract x and y coordinates separately for outlier detection
        tl_x_coords = [r[0][0] for r in results]
        tl_y_coords = [r[0][1] for r in results]
        br_x_coords = [r[1][0] for r in results]
        br_y_coords = [r[1][1] for r in results]

        # Find outliers for each coordinate separately
        _, tl_x_outlier_indices = self.find_outliers_iqr(tl_x_coords)
        _, tl_y_outlier_indices = self.find_outliers_iqr(tl_y_coords)
        _, br_x_outlier_indices = self.find_outliers_iqr(br_x_coords)
        _, br_y_outlier_indices = self.find_outliers_iqr(br_y_coords)


        pruned = [] #this is just the results tuples pruned for outliers
        outlier_indicies = set(tl_x_outlier_indices + tl_y_outlier_indices +
                               br_x_outlier_indices + br_y_outlier_indices)
        for i in range(len(results)):
            if i not in outlier_indicies:
                pruned.append(results[i])

        if not pruned:
            #fallback if too few results
            return results[0] #TODO: always chooses the first matching

        # Calculate mean of pruned results
        final_tl = (round(np.mean([r[0][0] for r in pruned])),
                   int(np.mean([r[0][1] for r in pruned])))
        final_br = (int(np.mean([r[1][0] for r in pruned])),
                   int(np.mean([r[1][1] for r in pruned])))

        return final_tl, final_br


    # def get_boxes(self):
    #     return {
    #
    #     }

    def read_values(self):
        """
        Analyzes the current image and returns structured data based on detected keys.
        """
        data = {}

        for key_name in KEYS:
            if key_name not in self.key_images:
                continue

            target = self.key_images[key_name]
            tl, br = self.get_box(target)

            # Simple validation: if we found it, the content is at self.img[tl[1]:br[1], tl[0]:br[0]]
            # For gamestats, we can further subdivide
            if key_name == "gamestats":
                stats_roi = self.img[tl[1]:br[1], tl[0]:br[0]]
                h, w = stats_roi.shape[:2]

                # KDA: approx 250 to 400
                kda_roi = stats_roi[:, int(0.42*w):int(0.68*w)]
                # CS: approx 450 to 520
                cs_roi = stats_roi[:, int(0.76*w):int(0.88*w)]
                # Clock: approx 530 to 590
                clock_roi = stats_roi[:, int(0.9*w):w]
                # Score: approx 0 to 150
                score_roi = stats_roi[:, :int(0.25*w)]

                data["gamestats"] = {
                    "full_roi": stats_roi,
                    "sub_rois": {
                        "score": score_roi,
                        "kda": kda_roi,
                        "cs": cs_roi,
                        "clock": clock_roi
                    }
                }
            else:
                data[key_name] = self.img[tl[1]:br[1], tl[0]:br[0]]

        return data

    def export_state(self):
        return self.read_values()