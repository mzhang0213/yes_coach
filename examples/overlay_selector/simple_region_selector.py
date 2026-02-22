"""
Simple Screen Region Selector with OpenCV Drawing

This version uses OpenCV's mouse callback functionality to allow users to select
a region directly on screen without needing additional UI frameworks.
"""

import cv2
import numpy as np
from mss import mss
import time


class SimpleRegionSelector:
    def __init__(self):
        self.drawing = False
        self.start_point = (-1, -1)
        self.end_point = (-1, -1)
        self.selected_region = None
        self.sct = mss()
        
        # Get screen dimensions
        self.screen_size = self.sct.monitors[1]  # Primary monitor
        self.width = self.screen_size['width']
        self.height = self.screen_size['height']
        
        # Create a blank image to draw on
        self.blank_image = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Show instructions
        cv2.putText(self.blank_image, 
                   "Select region: Click and drag to select area to capture", 
                   (50, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 
                   1, 
                   (255, 255, 255), 
                   2)
        cv2.putText(self.blank_image, 
                   "Press 'c' to confirm selection, 'r' to reset, 'q' to quit", 
                   (50, 100), 
                   cv2.FONT_HERSHEY_SIMPLEX, 
                   0.7, 
                   (255, 255, 255), 
                   2)

    def mouse_callback(self, event, x, y, flags, param):
        """Mouse callback function"""
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start_point = (x, y)
            self.end_point = (x, y)
        
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                self.end_point = (x, y)
        
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            self.end_point = (x, y)

    def draw_rectangle(self, image):
        """Draw the selection rectangle on the image"""
        if self.start_point != (-1, -1) and self.end_point != (-1, -1):
            cv2.rectangle(image, self.start_point, self.end_point, (0, 255, 0), 2)
            
            # Draw coordinates text
            x1, y1 = self.start_point
            x2, y2 = self.end_point
            width = abs(x2 - x1)
            height = abs(y2 - y1)
            
            cv2.putText(image, 
                       f"Selected: {width}x{height}", 
                       (min(x1, x2), min(y1, y2) - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, 
                       (0, 255, 0), 
                       2)

    def select_region(self):
        """Display the selection interface and get user selection"""
        cv2.namedWindow('Screen Region Selector', cv2.WINDOW_NORMAL)
        cv2.setMouseCallback('Screen Region Selector', self.mouse_callback)
        
        # Make window fullscreen
        cv2.setWindowProperty('Screen Region Selector', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        
        print("Screen Region Selector Active")
        print("Instructions:")
        print("- Click and drag to select a region")
        print("- Press 'c' to confirm selection")
        print("- Press 'r' to reset selection")
        print("- Press 'q' to quit")
        
        while True:
            # Create a copy of the blank image to draw on
            display_img = self.blank_image.copy()
            
            # Draw the current selection rectangle
            self.draw_rectangle(display_img)
            
            cv2.imshow('Screen Region Selector', display_img)
            
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('q'):
                cv2.destroyAllWindows()
                return None
            elif key == ord('r'):  # Reset selection
                self.start_point = (-1, -1)
                self.end_point = (-1, -1)
            elif key == ord('c'):  # Confirm selection
                if self.start_point != (-1, -1) and self.end_point != (-1, -1):
                    # Calculate the selected region
                    x1, y1 = self.start_point
                    x2, y2 = self.end_point
                    
                    left = min(x1, x2)
                    top = min(y1, y2)
                    right = max(x1, x2)
                    bottom = max(y1, y2)
                    
                    self.selected_region = {
                        'left': left,
                        'top': top,
                        'width': right - left,
                        'height': bottom - top
                    }
                    
                    cv2.destroyAllWindows()
                    return self.selected_region

    def capture_region(self, region):
        """Capture and display the selected region"""
        print(f"Starting capture of region: {region}")
        
        # Create a named window for the capture
        cv2.namedWindow('Selected Region Capture', cv2.WINDOW_AUTOSIZE)
        
        try:
            while True:
                # Capture the selected region
                screenshot = self.sct.grab(region)
                
                # Convert to numpy array and BGR format
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                # Display the captured region
                cv2.imshow('Selected Region Capture', frame)
                
                # Exit on 'q' key press
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        except KeyboardInterrupt:
            print("Capture interrupted")
        finally:
            cv2.destroyAllWindows()


def main():
    print("Simple Screen Region Selector")
    print("="*40)
    
    selector = SimpleRegionSelector()
    
    # Get the selected region
    region = selector.select_region()
    
    if region:
        print(f"Region selected: {region}")
        print("Starting capture...")
        selector.capture_region(region)
    else:
        print("No region selected or operation cancelled.")


if __name__ == "__main__":
    main()