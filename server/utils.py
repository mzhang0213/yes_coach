import cv2 as cv
import numpy as np
from matplotlib import pyplot as plt

KEYS = ["gamestats", "hotbar", "items", "map", "playerstats"]

class GameState:

    def __init__(self, img):
        self.img = img #the frame of the game state to analyze

    #def get [box]

    import numpy as np

    def find_outliers_iqr(self, data: list[int]):
        """
        Find outliers using the Interquartile Range (IQR) method.
        
        :param data: List of numeric values
        :param k: Multiplier for IQR (typically 1.5 for standard outlier detection)
        :return: Array of non-outlier values
        """
        # Convert to numpy array if it isn't already
        data = np.array(data)
        
        Q1 = np.percentile(data, 25)
        Q3 = np.percentile(data, 75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        res = [], []

        for i in range(len(data)):
            if lower_bound <= data[i] <= upper_bound:
                res[0].append(data[i])
                res[1].append(i)

        return res



    def get_box(self, target) -> tuple[int,int]:
        """
        Retrieves the bounding box on the screen containing target (key image).
        For example, if I wanted to get_box(map), pass in map as np.array image

        :param target: target image as np.array image
        :return: bounding box - (top left coordinate, bottom right coordinate)
        :rtype: tuple(int,int)
        """
        #Source: https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
        #(note minor edits made)
        assert self.img is not None, "file could not be read, check with os.path.exists()"
        assert target is not None, "file could not be read, check with os.path.exists()"
        w, h = target.shape[::-1]

        # All the 6 methods for comparison in a list
        methods = ['TM_CCOEFF', 'TM_CCOEFF_NORMED', 'TM_CCORR',
                   'TM_CCORR_NORMED', 'TM_SQDIFF', 'TM_SQDIFF_NORMED']

        results = []

        for meth in methods:
            img = self.img.copy()
            method = getattr(cv, meth)

            # Apply template Matching
            res = cv.matchTemplate(img,target,method)
            min_val, max_val, min_loc, max_loc = cv.minMaxLoc(res)

            # If the method is TM_SQDIFF or TM_SQDIFF_NORMED, take minimum
            if method in [cv.TM_SQDIFF, cv.TM_SQDIFF_NORMED]:
                top_left = min_loc
            else:
                top_left = max_loc
            bottom_right = (top_left[0] + w, top_left[1] + h)

            results.append((top_left,bottom_right))

            cv.rectangle(img,top_left, bottom_right, 255, 2)

            # plt.subplot(121),plt.imshow(res,cmap = 'gray')
            # plt.title('Matching Result'), plt.xticks([]), plt.yticks([])
            # plt.subplot(122),plt.imshow(img,cmap = 'gray')
            # plt.title('Detected Point'), plt.xticks([]), plt.yticks([])
            # plt.suptitle(meth)
            #
            # plt.show()

        tl_outliers = self.find_outliers_iqr(results[0])
        br_outliers = self.find_outliers_iqr(results[1])

        pruned = []
        for i in range(len(results)):
            if not i == tl_outliers[1][i] and not i == br_outliers[1][i]:
                pruned.append(results[i])

        return np.mean(pruned[0]), np.mean(pruned[1])

    # def get_boxes(self):
    #     return {
    #
    #     }

    def read_values(self):
        return 0

    def export_state(self):
        return 0