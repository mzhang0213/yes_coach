import cv2 as cv
import numpy as np
import os
import pytesseract
from matplotlib import pyplot as plt
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QWidget
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
import sys
from PyQt6.QtWidgets import QMainWindow, QWidget
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
from mss import mss
import time
import platform
import threading
from queue import Queue

class MDebug:
    def __init__(self):
        self.info = []

    def log_msg(self, msg):
        self.info.append({"msg":msg})

    def log_img(self, img, name):
        self.info.append({"name":name, "img":img})


FEATURES = {
    #screen_feature: (tl,br)
    "gamestats":((0.75,0),(1,0.2)),
    "hotbar":((0,0.5),(1,1)),
    "items":((0.5,0.75),(0.9,1)),
    "map":((0.5,0.5),(1,1)),
    "playerstats":((0,0.5),(0.5,1))
}
app = QApplication.instance() or QApplication(sys.argv)
_screensize=app.primaryScreen().size()
SCREEN_SIZE = _screensize.width(),_screensize.height()
# KEYS = [
#     {
#         "name":"gamestats",
#         "box":((0.75,0),(1,0.2))
#     },
#     {
#         "name":"hotbar",
#         "box":((0,0.5),(1,1))
#     },
#     {
#         "name":"items",
#         "box":((0.5,0.75),(0.9,1))
#     },
#     {
#         "name":"map",
#         "box":((0.5,0.5),(1,1))
#     },
#     {
#         "name":"playerstats",
#         "box":((0,0.5),(0.5,1))
#     }
# ]

def show_imgs(_img):
    """
    show cv images, auto use quit with Q
    BLOCKS INPUT AND EXECUTION
    :param _img: LIST OF IMAGES
    """
    while True:
        for i,_ in enumerate(_img):
            cv.imshow(f'img{str(i)}', _)

        if cv.waitKey(1) & 0xFF == ord('q'):
            break

def find_outliers_iqr(data: list) -> tuple[list, list]:
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

def get_screen_coords(w:int, h:int, scale:tuple[tuple[float,float],tuple[float,float]])-> tuple[tuple[int, int], tuple[int, int]]:
    return (int(scale[0][0]*w),int(scale[0][1]*h)),(int(scale[1][0]*w),int(scale[1][1]*h))

class GameState:

    def __init__(self, img):
        self.img = img #the frame of the game state to analyze
        self.key_images = {}
        #todo: rework this cuz shouldn't be duplicated for each game state
        keys_dir = os.path.join(os.path.dirname(__file__), 'keys')
        for key in FEATURES:
            path = os.path.join(keys_dir, f"{key}.png")
            if os.path.exists(path):
                self.key_images[key] = cv.imread(path)

    def get_box(self, target, tl:tuple[int,int], br:tuple[int,int]) -> tuple[tuple[int, int], tuple[int, int]]:
        """
        Retrieves the bounding box on the screen containing target (key image).
        :param br:
        :param tl:
        :param target: target image as np.array image
        :return: bounding box - (top left coordinate, bottom right coordinate)
        """
        #Source: https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html
        #(note minor edits made)
        assert self.img is not None, "this game state's img could not be read"
        assert target is not None, "target image is None"
        if tl == (-1, -1):
            tl = (0,0)
        if br == (-1, -1):
            br = tuple(self.img.shape[::-1])

        # Store original coordinates offset
        offset_x, offset_y = tl[0], tl[1]

        # Template matching works best in grayscale or with matched channels
        img = self.img[tl[1]:br[1],tl[0]:br[0]]
        img = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
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

            # Adjust coordinates back to original image space
            top_left = (top_left[0] + offset_x, top_left[1] + offset_y)
            bottom_right = (bottom_right[0] + offset_x, bottom_right[1] + offset_y)

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
        _, tl_x_outlier_indices = find_outliers_iqr(tl_x_coords)
        _, tl_y_outlier_indices = find_outliers_iqr(tl_y_coords)
        _, br_x_outlier_indices = find_outliers_iqr(br_x_coords)
        _, br_y_outlier_indices = find_outliers_iqr(br_y_coords)


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

    def get_boxes(self):
        """
        Analyzes the current game screen and returns structured data based on detected keys.
        """
        data = {}

        for key_name in FEATURES:
            if key_name not in self.key_images:
                continue

            curr_feature = self.key_images[key_name]
            img_h,img_w = self.img.shape[:2]
            feature_tl,feature_br = get_screen_coords(img_w,img_h,FEATURES[key_name])
            tl, br = self.get_box(curr_feature, feature_tl, feature_br)
            feature = self.img[tl[1]:br[1], tl[0]:br[0]]
            fh,fw = feature.shape[:2]

            if key_name == "gamestats":
                # KDA: approx 250 to 400
                kda_box = (int(0.42 * fw),(0.68 * fw)),(0,fh)
                # CS: approx 450 to 520
                cs_box = (int(0.76 * fw),int(0.88 * fw)),(0,fh)
                # Clock: approx 530 to 590
                clock_box = (int(0.9 * fw),fw),(0,fh)
                # Score: approx 0 to 150
                score_box = (0,int(0.25 * fw)),(0,fh)

                data["gamestats"] = {
                    "full": (tl,br),
                    "sections": {
                        "score": score_box,
                        "kda": kda_box,
                        "cs": cs_box,
                        "clock": clock_box
                    }
                }
            else:
                data[key_name] = {
                    "full": (tl,br)
                }

        return data

    def extract_box(self,tl:tuple[int,int],br:tuple[int,int]):
        return self.img[tl[1]:br[1],tl[0]:br[0]]

    def display_boxes(self):
        boxes = self.get_boxes()
        for key in FEATURES:
            og = self.img.copy()
            cv.rectangle(og, boxes[key]["full"][0], boxes[key]["full"][1], (0,255,0))
            cv.imshow(key, og)

    def export_state(self):
        return self.get_boxes()

class Overlay(QMainWindow):
    def __init__(self):
        super().__init__()
        # Set flags for: No border, Always on Top, and Click-Through
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Create a central widget to enable painting
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Format: [(top_left_x, top_left_y, bottom_right_x, bottom_right_y, filled)]
        # self.rectangles = [
        #     (50, 50, 200, 150, True),    # Rectangle 1: TL(50,50), BR(200,150), filled
        #     (300, 100, 500, 250, False),  # Rectangle 2: TL(300,100), BR(500,250), not filled
        #     (100, 200, 400, 300, True)   # Rectangle 3: TL(100,200), BR(400,300), filled
        # ]
        #
        # # Format: [(center_x, center_y, radius, filled)]
        # self.circles = [
        #     (150, 80, 40, True),   # Circle 1: Center(150,80), radius 40, filled
        #     (400, 180, 30, False), # Circle 2: Center(400,180), radius 30, not filled
        #     (250, 250, 50, True)   # Circle 3: Center(250,250), radius 50, filled
        # ]
        #
        # # Format: [(start_x, start_y, end_x, end_y)]
        # self.arrows = [
        #     (10, 350, 100, 350),   # Arrow from (10,350) to (100,350)
        #     (150, 350, 150, 250),  # Arrow from (150,350) to (150,250)
        #     (200, 300, 250, 350)   # Arrow from (200,300) to (250,350)
        # ]
        self.rectangles = []
        self.circles = []
        self.arrows = []

        self.resize(SCREEN_SIZE[0], SCREEN_SIZE[1])
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw each rectangle using TL and BR points
        for rect_coords in self.rectangles:
            top_left_x, top_left_y, bottom_right_x, bottom_right_y, filled = rect_coords

            # Calculate width and height from TL and BR points
            width = bottom_right_x - top_left_x
            height = bottom_right_y - top_left_y

            # Create QRect from top-left point and dimensions
            rect = QRect(top_left_x, top_left_y, width, height)

            # Set pen for drawing the rectangle
            painter.setPen(QPen(QColor(255, 0, 0), 3))  # Red border, 3px thick

            # Set brush based on fill option
            if filled:
                painter.setBrush(QBrush(QColor(255, 0, 0, 50)))  # Semi-transparent red fill
            else:
                painter.setBrush(QBrush())  # No fill

            # Draw the rectangle
            painter.drawRect(rect)

        # Draw each circle
        for circle_coords in self.circles:
            center_x, center_y, radius, filled = circle_coords

            # Set pen for drawing the circle
            painter.setPen(QPen(QColor(0, 255, 0), 3))  # Green border, 3px thick

            # Set brush based on fill option
            if filled:
                painter.setBrush(QBrush(QColor(0, 255, 0, 50)))  # Semi-transparent green fill
            else:
                painter.setBrush(QBrush())  # No fill

            # Draw the circle using drawEllipse
            painter.drawEllipse(int(center_x - radius), int(center_y - radius),
                                int(radius * 2), int(radius * 2))

        # Draw each arrow
        for arrow_coords in self.arrows:
            start_x, start_y, end_x, end_y = arrow_coords

            # Draw the line
            painter.setPen(QPen(QColor(0, 0, 255), 3))  # Blue line, 3px thick
            painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))

            # Draw arrowhead
            self.draw_arrowhead(painter, start_x, start_y, end_x, end_y)

    def draw_arrowhead(self, painter, start_x, start_y, end_x, end_y):
        """Draw an arrowhead at the end point of the arrow

        Args:
            painter: QPainter object
            start_x, start_y: start coordinates of the arrow
            end_x, end_y: end coordinates of the arrow
        """
        import math

        # Calculate the angle of the line
        angle = math.atan2(end_y - start_y, end_x - start_x)

        # Size of the arrowhead
        arrowhead_length = 15

        # Point 1 of the arrowhead (rotated -30 degrees from main line)
        angle1 = angle - math.pi / 6  # -30 degrees in radians
        x1 = end_x - arrowhead_length * math.cos(angle1)
        y1 = end_y - arrowhead_length * math.sin(angle1)

        # Point 2 of the arrowhead (rotated +30 degrees from main line)
        angle2 = angle + math.pi / 6  # +30 degrees in radians
        x2 = end_x - arrowhead_length * math.cos(angle2)
        y2 = end_y - arrowhead_length * math.sin(angle2)

        # Draw the arrowhead lines
        painter.drawLine(int(end_x), int(end_y), int(x1), int(y1))
        painter.drawLine(int(end_x), int(end_y), int(x2), int(y2))

    def add_rectangle(self, top_left, bottom_right, filled=True):
        """Add a new rectangle given top-left and bottom-right points

        Args:
            top_left: tuple (x, y) representing top-left corner
            bottom_right: tuple (x, y) representing bottom-right corner
            filled: bool indicating whether to fill the rectangle
        """
        tl_x, tl_y = top_left
        br_x, br_y = bottom_right
        self.rectangles.append((tl_x, tl_y, br_x, br_y, filled))
        self.update()  # Trigger repaint

    def add_circle(self, center, radius, filled=True):
        """Add a new circle given center point and radius

        Args:
            center: tuple (x, y) representing center of the circle
            radius: int representing radius of the circle
            filled: bool indicating whether to fill the circle
        """
        center_x, center_y = center
        self.circles.append((center_x, center_y, radius, filled))
        self.update()  # Trigger repaint

    def add_arrow(self, start_point, end_point):
        """Add a new arrow given start and end points

        Args:
            start_point: tuple (x, y) representing start of the arrow
            end_point: tuple (x, y) representing end of the arrow
        """
        start_x, start_y = start_point
        end_x, end_y = end_point
        self.arrows.append((start_x, start_y, end_x, end_y))
        self.update()  # Trigger repaint

    def clearCanvas(self):
        """Clear all shapes from the canvas"""
        self.rectangles.clear()
        self.circles.clear()
        self.arrows.clear()
        self.update()  # Trigger repaint

    def hideCanvas(self):
        """Hide the canvas window"""
        self.hide()  # Hide the window

    def showCanvas(self):
        """Show the canvas window"""
        self.show()  # Show the window

    def cvToQt(self, tl:tuple[int,int], br:tuple[int,int], img_w:int, img_h:int)->tuple[tuple[int,int],tuple[int,int]]:
        return (
            int((tl[0] / img_w) * SCREEN_SIZE[0]),
            int((tl[1] / img_h) * SCREEN_SIZE[1])
        ), (
            int((br[0] / img_w) * SCREEN_SIZE[0]),
            int((br[1] / img_h) * SCREEN_SIZE[1])
        )

DYDX = []

class ScreenCapture:
    def __init__(self):
        self.running = False
        self.capture_thread = None
        self.last_frame = None
        self.frame_lock = threading.Lock()
        self.process_callback = None
        self.process_interval = 1.0
        self.last_process_time = 0
        self.process_queue = Queue(maxsize=1)  # For processing callback
        self.display_queue = Queue(maxsize=1)  # For main-thread display

    def start_capture(self, process_callback=None, process_interval=1.0):
        if self.running:
            print("Screen capture is already running.")
            return False

        self.process_callback = process_callback
        self.process_interval = process_interval
        self.running = True

        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        print("Screen capture started in background.")
        return True

    def stop_capture(self):
        if not self.running:
            return False
        self.running = False
        if self.capture_thread and self.capture_thread.is_alive():
            self.capture_thread.join(timeout=2)
        cv.destroyAllWindows()  # Safe — called from main thread by caller
        print("Screen capture stopped.")
        return True

    def get_latest_frame(self):
        with self.frame_lock:
            return self.last_frame

    def pump_display(self):
        """
        Call this repeatedly from the MAIN THREAD to show frames and handle GUI events.
        Returns False if 'q' was pressed (signal to stop), True otherwise.
        """
        if not self.display_queue.empty():
            try:
                frame = self.display_queue.get_nowait()
                cv.imshow('Live Screen Capture', frame)
            except Exception:
                pass

        key = cv.waitKey(1)
        if key & 0xFF == ord('q'):
            print("'q' pressed, stopping capture...")
            self.running = False
            return False
        return True

    def _capture_loop(self):
        frame_count = 0
        start_time = time.time()
        last_display_time = 0
        display_interval = 1.0 / 30  # ~30 FPS

        try:
            with mss() as sct:
                monitor = sct.monitors[1]
                print(f"\nStarting background screen capture...")
                print(f"Resolution: {monitor['width']} x {monitor['height']}")

                while self.running:
                    try:
                        screenshot = sct.grab(monitor)
                        frame = np.array(screenshot)
                        frame = cv.cvtColor(frame, cv.COLOR_BGRA2BGR)

                        with self.frame_lock:
                            self.last_frame = frame

                        current_time = time.time()

                        # Push to display queue at ~30 FPS (main thread will consume)
                        if current_time - last_display_time > display_interval:
                            if not self.display_queue.empty():
                                try:
                                    self.display_queue.get_nowait()
                                except Exception:
                                    pass
                            self.display_queue.put(frame)
                            last_display_time = current_time

                        # Push to process queue on interval
                        if self.process_callback and (current_time - self.last_process_time) >= self.process_interval:
                            if not self.process_queue.empty():
                                try:
                                    self.process_queue.get_nowait()
                                except Exception:
                                    pass
                            self.process_queue.put(frame)
                            self.last_process_time = current_time

                            # Run callback in a separate thread so it doesn't block capture
                            latest = self.process_queue.get()
                            threading.Thread(
                                target=self._run_callback,
                                args=(latest,),
                                daemon=True
                            ).start()

                        frame_count += 1
                        time.sleep(0.01)

                    except Exception as e:
                        print(f"Error during capture: {str(e)}")
                        time.sleep(0.1)
                        continue

        except Exception as e:
            print(f"Critical error in capture: {str(e)}")
            if "Permission denied" in str(e) or "screen recording" in str(e).lower():
                print("\nScreen Recording permission denied. Check System Settings > Privacy.")
        finally:
            self.running = False
            elapsed = time.time() - start_time
            print(f"\nCapture thread finished. Captured {frame_count} frames.")
            if elapsed > 0:
                print(f"Total time: {elapsed:.2f}s, Average FPS: {frame_count/elapsed:.2f}")

    def _run_callback(self, frame):
        try:
            self.process_callback(frame)
        except Exception as e:
            print(f"Error in process callback: {str(e)}")


# Global instance for easy use
screen_capture_instance = ScreenCapture()

def screen_capture(process_callback=None, process_interval=1.0):
    """
    Starts screen capture in background with optional processing callback
    """
    return screen_capture_instance.start_capture(process_callback, process_interval)

def stop_screen_capture():
    """
    Stops the background screen capture
    """
    return screen_capture_instance.stop_capture()

def get_latest_frame():
    """
    Gets the latest captured frame
    """
    return screen_capture_instance.get_latest_frame()