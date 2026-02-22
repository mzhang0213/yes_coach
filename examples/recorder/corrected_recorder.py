"""
Corrected Screen Recorder with Proper Frame Rate Control

This version ensures that the recorded video plays back at the correct speed
by maintaining consistent frame rates between capture and output.
"""

import cv2
import numpy as np
from mss import mss
import time
import os
from datetime import datetime


class CorrectedScreenRecorder:
    def __init__(self, output_filename=None, fps=30, codec='mp4v'):
        """
        Initialize the screen recorder with proper frame rate control
        
        Args:
            output_filename: Name of the output video file
            fps: Frames per second for both capture and output
            codec: FourCC codec code (e.g., 'mp4v', 'XVID', 'MJPG')
        """
        self.target_fps = fps
        self.codec = codec
        self.frame_interval = 1.0 / fps  # Time between frames in seconds
        
        # Create recordings directory if it doesn't exist
        os.makedirs('recordings', exist_ok=True)
        
        # Generate filename if not provided
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"corrected_recording_{timestamp}_{fps}fps.mp4"
        
        self.output_path = os.path.join('recordings', output_filename)
        
        # Initialize MSS for screen capture
        self.sct = mss()
        self.monitor = self.sct.monitors[1]  # Primary monitor
        
        # Initialize video writer (will be set up when recording starts)
        self.out = None
        self.frame_size = None
        
    def start_recording(self, duration=None, region=None):
        """
        Start recording the screen with accurate frame rate
        
        Args:
            duration: Recording duration in seconds (None for indefinite recording)
            region: Optional region to record {'top': int, 'left': int, 'width': int, 'height': int}
        """
        print(f"Starting corrected screen recording...")
        print(f"Output file: {self.output_path}")
        print(f"Target FPS: {self.target_fps}")
        
        # Use specified region or full screen
        capture_region = region if region else self.monitor
        
        # Capture first frame to determine frame size
        first_frame = self.sct.grab(capture_region)
        frame_np = np.array(first_frame)
        frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_BGRA2BGR)
        
        # Set up video writer with proper frame dimensions
        height, width, channels = frame_bgr.shape
        self.frame_size = (width, height)
        
        fourcc = cv2.VideoWriter_fourcc(*self.codec)
        self.out = cv2.VideoWriter(self.output_path, fourcc, self.target_fps, self.frame_size)
        
        print(f"Recording at {width}x{height}, {self.target_fps} FPS, codec: {self.codec}")
        
        # Start timing if duration is specified
        start_time = time.time()
        last_frame_time = time.time()
        
        frame_count = 0
        
        try:
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
                    frame_count += 1
                    
                    # Show preview
                    cv2.imshow('Corrected Screen Recorder - Press Q to stop', frame)
                    
                    # Check if duration has been reached
                    if duration and (time.time() - start_time) >= duration:
                        break
                    
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
            elapsed_time = time.time() - start_time
            actual_fps = frame_count / elapsed_time if elapsed_time > 0 else 0
            print(f"Recorded {frame_count} frames in {elapsed_time:.2f} seconds")
            print(f"Actual FPS: {actual_fps:.2f}")
    
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


def record_at_fps(fps=30, duration=10, output_filename=None):
    """
    Record screen at a specific frame rate to ensure correct playback speed
    
    Args:
        fps: Frames per second for the recording
        duration: Recording duration in seconds
        output_filename: Name of the output file
    """
    recorder = CorrectedScreenRecorder(output_filename=output_filename, fps=fps)
    recorder.start_recording(duration=duration)


def main():
    print("Corrected Screen Recorder - Fixed Frame Rate Issue")
    print("=" * 55)
    print("This version maintains consistent frame rates to prevent speed issues.")
    print()
    
    print("Options:")
    print("1. Record at 30 FPS (standard)")
    print("2. Record at 60 FPS (smooth motion)")
    print("3. Record at custom FPS")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        record_at_fps(fps=30, duration=duration, output_filename=filename)
        
    elif choice == "2":
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        record_at_fps(fps=60, duration=duration, output_filename=filename)
        
    elif choice == "3":
        fps = int(input("Enter desired FPS (e.g., 15, 30, 60): ") or "30")
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        record_at_fps(fps=fps, duration=duration, output_filename=filename)
        
    else:
        print("Invalid choice. Recording at 30 FPS for 10 seconds as default.")
        record_at_fps(fps=30, duration=10)


if __name__ == "__main__":
    main()