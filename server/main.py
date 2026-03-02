import cv2 as cv
import numpy as np
from mss import mss
import time

from server.utils import GameState


def screen_capture_demo():
    """
    Screen capture using OpenCV with MSS (more efficient than VideoCapture(0))
    """
    with mss() as sct:
        monitor = sct.monitors[1] #just screen 1 ([0] is all displays)
        print(f"Capturing screen: {monitor}")
        
        while True:
            frame = np.array(sct.grab(monitor))
            
            frame = cv.cvtColor(frame, cv.COLOR_BGRA2BGR)
            
            cv.imshow('Screen Capture', frame)
            
            if cv.waitKey(1) & 0xFF == ord('q'):
                break
    
    cv.destroyAllWindows()

def live(intv:int):
    """
    Screen capture using OpenCV with MSS (more efficient than VideoCapture(0))
    """
    with mss() as sct:
        monitor = sct.monitors[1] #just screen 1 ([0] is all displays)
        print(f"Capturing screen: {monitor}")

        counter = 0
        while True:
            frame = np.array(sct.grab(monitor))

            frame = cv.cvtColor(frame, cv.COLOR_BGRA2BGR)

            cv.imshow('Screen Capture', frame)

            if counter%intv==0:
                #create game state across intervals
                gs = GameState(frame)

                cv.imshow('Screen Capture', frame)


            if cv.waitKey(1) & 0xFF == ord('q'):
                break

    cv.destroyAllWindows()




if __name__ == "__main__":
    print("OpenCV Screen Capture Demo")
    print("Press 'q' to quit")
    print("\nStarting screen capture...")


    # while True:
    #     cv.imshow("res", full)
    #
    #     if cv.waitKey(1) & 0xFF == ord('q'):
    #         break

