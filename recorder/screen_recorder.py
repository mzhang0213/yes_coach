"""
Screen Recorder using OpenCV and MSS

This module provides functionality to record screen captures and save them as video files.
"""

import cv2
import numpy as np
from mss import mss
import time
import os
from datetime import datetime


class ScreenRecorder:
    def __init__(self, output_filename=None, fps=30, codec='mp4v'):
        """
        Initialize the screen recorder
        
        Args:
            output_filename: Name of the output video file (will be created in 'recordings' folder)
            fps: Frames per second for the output video
            codec: FourCC codec code (e.g., 'mp4v', 'XVID', 'MJPG')
        """
        self.fps = fps
        self.codec = codec
        
        # Create recordings directory if it doesn't exist
        os.makedirs('recordings', exist_ok=True)
        
        # Generate filename if not provided
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"screen_recording_{timestamp}.mp4"
        
        self.output_path = os.path.join('recordings', output_filename)
        
        # Initialize MSS for screen capture
        self.sct = mss()
        self.monitor = self.sct.monitors[1]  # Primary monitor
        
        # Initialize video writer (will be set up when recording starts)
        self.out = None
        self.frame_size = None
        
    def start_recording(self, duration=None, region=None):
        """
        Start recording the screen
        
        Args:
            duration: Recording duration in seconds (None for indefinite recording)
            region: Optional region to record {'top': int, 'left': int, 'width': int, 'height': int}
        """
        print(f"Starting screen recording...")
        print(f"Output file: {self.output_path}")
        
        # Use specified region or full screen
        capture_region = region if region else self.monitor
        
        # Capture first frame to determine frame size
        first_frame = self.sct.grab(capture_region)
        frame_np = np.array(first_frame)
        frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_BGRA2BGR)
        
        # Set up video writer with proper frame dimensions
        height, width, channels = frame_bgr.shape
        self.frame_size = (width, height)
        
        # Calculate frame interval for consistent timing
        self.frame_interval = 1.0 / self.fps  # Time between frames in seconds
        
        fourcc = cv2.VideoWriter_fourcc(*self.codec)
        self.out = cv2.VideoWriter(self.output_path, fourcc, self.fps, self.frame_size)
        
        print(f"Recording at {width}x{height}, {self.fps} FPS, codec: {self.codec}")
        
        # Start timing if duration is specified
        start_time = time.time()
        
        try:
            last_frame_time = time.time()
            while True:
                current_time = time.time()
                
                # Maintain consistent frame interval
                if current_time - last_frame_time >= self.frame_interval:
                    # Capture screen
                    screenshot = self.sct.grab(capture_region)
                    
                    # Convert to numpy array and BGR format
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # Write frame to video file
                    self.out.write(frame)
                    
                    # Update frame time
                    last_frame_time = current_time
                    
                    # Check if duration has been reached
                    if duration and (time.time() - start_time) >= duration:
                        break
                    
                    # Optional: Show preview (comment out if you don't want the preview window)
                    cv2.imshow('Screen Recorder Preview - Press Q to stop early', frame)
                    
                    # Allow early termination with 'q' key
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("Recording stopped early by user")
                        break
                else:
                    # Small sleep to prevent excessive CPU usage
                    time.sleep(0.001)
                    
        except KeyboardInterrupt:
            print("Recording interrupted by user")
        
        finally:
            self.stop_recording()
    
    def stop_recording(self):
        """Stop recording and clean up resources"""
        if self.out:
            self.out.release()
        
        cv2.destroyAllWindows()
        
        # Get file size
        if os.path.exists(self.output_path):
            size_mb = os.path.getsize(self.output_path) / (1024 * 1024)
            print(f"Recording saved: {self.output_path}")
            print(f"File size: {size_mb:.2f} MB")
        else:
            print("Recording may have been interrupted before file was created")


def record_full_screen(output_filename=None, duration=10, fps=30):
    """
    Record the full screen for a specified duration
    
    Args:
        output_filename: Name of the output file
        duration: Recording duration in seconds
        fps: Frames per second
    """
    recorder = ScreenRecorder(output_filename=output_filename, fps=fps)
    recorder.start_recording(duration=duration)


def record_region(x, y, width, height, output_filename=None, duration=10, fps=30):
    """
    Record a specific region of the screen
    
    Args:
        x, y: Top-left corner coordinates
        width, height: Dimensions of the region
        output_filename: Name of the output file
        duration: Recording duration in seconds
        fps: Frames per second
    """
    region = {
        "top": y,
        "left": x,
        "width": width,
        "height": height
    }
    
    recorder = ScreenRecorder(output_filename=output_filename, fps=fps)
    recorder.start_recording(duration=duration, region=region)


def record_until_stopped(output_filename=None, fps=30):
    """
    Record continuously until user stops (presses 'q' or Ctrl+C)
    
    Args:
        output_filename: Name of the output file
        fps: Frames per second
    """
    recorder = ScreenRecorder(output_filename=output_filename, fps=fps)
    recorder.start_recording()


def main():
    print("OpenCV Screen Recorder")
    print("=" * 40)
    print("Options:")
    print("1. Record full screen for N seconds")
    print("2. Record specific region for N seconds")
    print("3. Record until stopped manually")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        fps = int(input("Enter FPS (default 30): ") or "30")
        filename = input("Enter output filename (optional, will auto-generate if empty): ").strip()
        if not filename:
            filename = None
        
        record_full_screen(output_filename=filename, duration=duration, fps=fps)
        
    elif choice == "2":
        x = int(input("Enter X coordinate (default 100): ") or "100")
        y = int(input("Enter Y coordinate (default 100): ") or "100")
        width = int(input("Enter width (default 800): ") or "800")
        height = int(input("Enter height (default 600): ") or "600")
        duration = int(input("Enter recording duration in seconds (default 10): ") or "100")
        fps = int(input("Enter FPS (default 30): ") or "30")
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        
        record_region(x, y, width, height, output_filename=filename, duration=duration, fps=fps)
        
    elif choice == "3":
        fps = int(input("Enter FPS (default 30): ") or "30")
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        
        print("Recording until stopped. Press 'q' in the preview window or Ctrl+C to stop.")
        record_until_stopped(output_filename=filename, fps=fps)
        
    else:
        print("Invalid choice. Recording full screen for 10 seconds as default.")
        record_full_screen(duration=10)


if __name__ == "__main__":
    main()