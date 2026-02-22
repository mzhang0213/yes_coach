import cv2
import numpy as np
from mss import mss
import time


def screen_capture_opencv():
    """
    Screen capture using OpenCV with MSS (more efficient than VideoCapture(0))
    """
    # Define the region of the screen to capture (full screen by default)
    with mss() as sct:
        # Get the monitor information
        monitor = sct.monitors[1]  # Primary monitor
        
        print(f"Capturing screen: {monitor}")
        
        while True:
            # Capture the screen
            screenshot = sct.grab(monitor)
            
            # Convert the screenshot to a numpy array (OpenCV format)
            frame = np.array(screenshot)
            
            # Convert from BGRA to BGR (OpenCV format)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            # Display the frame
            cv2.imshow('Screen Capture', frame)
            
            # Press 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    cv2.destroyAllWindows()


def screen_capture_basic():
    """
    Basic screen capture using VideoCapture (not recommended for screen capture)
    This is just for demonstration - it won't actually capture the screen
    """
    # This approach doesn't work for actual screen capture on most systems
    # It's shown here for educational purposes only
    cap = cv2.VideoCapture(0)
    
    while True:
        ret, frame = cap.read()
        
        if ret:
            cv2.imshow('Camera Feed (not screen)', frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    print("OpenCV Screen Capture Demo")
    print("Press 'q' to quit")
    print("\nStarting screen capture...")
    screen_capture_opencv()