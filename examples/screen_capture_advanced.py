import cv2
import numpy as np
from mss import mss
import time
import argparse


class ScreenCapture:
    def __init__(self, monitor_index=1, show_fps=True):
        self.monitor_index = monitor_index
        self.show_fps = show_fps
        self.sct = mss()
        
        # Get monitor information
        self.monitor = self.sct.monitors[self.monitor_index]
        print(f"Monitor {self.monitor_index}: {self.monitor}")
    
    def capture_screen(self):
        """Main capture loop"""
        fps_counter = 0
        fps_start_time = time.time()
        
        while True:
            start_time = time.time()
            
            # Capture the screen
            screenshot = self.sct.grab(self.monitor)
            
            # Convert the screenshot to a numpy array (OpenCV format)
            frame = np.array(screenshot)
            
            # Convert from BGRA to BGR (OpenCV format)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            if self.show_fps:
                # Calculate FPS
                fps_counter += 1
                if fps_counter % 10 == 0:
                    fps_end_time = time.time()
                    fps = 10 / (fps_end_time - fps_start_time)
                    fps_start_time = fps_end_time
                    cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            
            # Display the frame
            cv2.imshow('Screen Capture', frame)
            
            # Calculate processing time
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Print frame time occasionally
            if fps_counter % 30 == 0:
                print(f"Frame processing time: {processing_time*1000:.2f} ms")
            
            # Press 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    def capture_region(self, x, y, width, height):
        """Capture a specific region of the screen"""
        region = {
            "top": self.monitor["top"] + y,
            "left": self.monitor["left"] + x,
            "width": width,
            "height": height
        }
        
        screenshot = self.sct.grab(region)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        
        return frame
    
    def capture_custom_region(self, top, left, width, height):
        """Capture a custom region (absolute coordinates)"""
        region = {
            "top": top,
            "left": left,
            "width": width,
            "height": height
        }
        
        screenshot = self.sct.grab(region)
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        
        return frame
    
    def __del__(self):
        cv2.destroyAllWindows()
        if hasattr(self, 'sct'):
            self.sct.close()


def main():
    parser = argparse.ArgumentParser(description='Screen Capture with OpenCV')
    parser.add_argument('--monitor', type=int, default=1, help='Monitor index (default: 1 for primary)')
    parser.add_argument('--region', nargs=4, type=int, metavar=('X', 'Y', 'WIDTH', 'HEIGHT'),
                       help='Capture specific region (x, y, width, height)')
    parser.add_argument('--show-fps', action='store_true', help='Show FPS counter')
    
    args = parser.parse_args()
    
    print("OpenCV Screen Capture")
    print("Press 'q' to quit")
    print("="*30)
    
    # Initialize screen capture
    capturer = ScreenCapture(monitor_index=args.monitor, show_fps=args.show_fps)
    
    if args.region:
        # Capture only the specified region
        x, y, w, h = args.region
        print(f"Capturing region: ({x}, {y}, {w}, {h})")
        
        while True:
            frame = capturer.capture_region(x, y, w, h)
            cv2.imshow('Screen Region Capture', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    else:
        # Capture full screen
        print("Capturing full screen...")
        capturer.capture_screen()
    
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()