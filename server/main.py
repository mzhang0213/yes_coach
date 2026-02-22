import cv2 as cv
import numpy as np
from mss import mss
import time

from server.utils import GameState


def screen_capture_opencv():
    """
    Screen capture using OpenCV with MSS (more efficient than VideoCapture(0))
    """
    with mss() as sct:
        monitor = sct.monitors[1] #just screen 1 ([0] is all displays)
        print(f"Capturing screen: {monitor}")
        
        while True:
            frame = np.array(sct.grab(monitor))
            
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            cv2.imshow('Screen Capture', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    cv2.destroyAllWindows()




if __name__ == "__main__":
    # print("OpenCV Screen Capture Demo")
    # print("Press 'q' to quit")
    # print("\nStarting screen capture...")
    # screen_capture_opencv()
    control = cv.imread("./keys/test_control.png")
    test = cv.imread("./keys/test_control.png")

    gs_control = GameState(control)
    gs_test = GameState(test)
    control_data = gs_control.read_values()
    full = control_data["gamestats"]["full_roi"]

    while True:
        cv.imshow("res", full)

        if cv.waitKey(1) & 0xFF == ord('q'):
            break

