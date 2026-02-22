"""
Basic Screen Recording Example

Simple example showing how to record your screen and save it as a video file.
"""

import cv2
import numpy as np
from mss import mss
import time
import os
from datetime import datetime


def record_screen_simple(duration=10, filename=None):
    """
    Simple function to record the screen for a given duration
    
    Args:
        duration: Recording time in seconds
        filename: Output filename (auto-generated if None)
    """
    # Create recordings directory
    os.makedirs('recordings', exist_ok=True)
    
    # Generate filename if not provided
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.mp4"
    
    output_path = os.path.join('recordings', filename)
    
    # Initialize screen capture
    with mss() as sct:
        # Get primary monitor dimensions
        monitor = sct.monitors[1]
        
        # Capture first frame to get dimensions
        first_frame = sct.grab(monitor)
        frame_np = np.array(first_frame)
        frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_BGRA2BGR)
        
        # Get frame dimensions
        height, width, channels = frame_bgr.shape
        frame_size = (width, height)
        
        print(f"Recording screen: {width}x{height}")
        print(f"Duration: {duration} seconds")
        print(f"Output file: {output_path}")
        
        # Calculate frame interval for consistent timing
        target_fps = 20.0  # Target FPS
        frame_interval = 1.0 / target_fps  # Time between frames in seconds
        
        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # or 'XVID', 'MJPG', 'X264'
        out = cv2.VideoWriter(output_path, fourcc, target_fps, frame_size)  # Consistent FPS
        
        # Start recording
        start_time = time.time()
        frame_count = 0
        
        print("Recording started... Press Ctrl+C to stop early")
        
        try:
            last_frame_time = time.time()
            while time.time() - start_time < duration:
                current_time = time.time()
                
                # Maintain consistent frame interval
                if current_time - last_frame_time >= frame_interval:
                    # Capture screen
                    screenshot = sct.grab(monitor)
                    
                    # Convert to numpy array and BGR format
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # Write the frame
                    out.write(frame)
                    
                    # Update frame time
                    last_frame_time = current_time
                    frame_count += 1
                    
                    # Optional: show preview (remove if you don't want the window)
                    cv2.imshow('Recording Preview - Press Q to stop', frame)
                    
                    # Check if user wants to quit early
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("Recording stopped early by user")
                        break
                else:
                    # Small sleep to prevent excessive CPU usage
                    time.sleep(0.001)
        
        except KeyboardInterrupt:
            print("Recording interrupted by user")
        
        finally:
            # Release everything
            out.release()
            cv2.destroyAllWindows()
            
            # Report results
            actual_duration = time.time() - start_time
            actual_fps = frame_count / actual_duration if actual_duration > 0 else 0
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)  # Size in MB
                print(f"\nRecording complete!")
                print(f"Saved to: {output_path}")
                print(f"Actual duration: {actual_duration:.2f} seconds")
                print(f"Frames captured: {frame_count}")
                print(f"Average FPS: {actual_fps:.2f}")
                print(f"File size: {file_size:.2f} MB")
            else:
                print("Recording may have been interrupted")


def record_region(x, y, width, height, duration=10, filename=None):
    """
    Record a specific region of the screen
    
    Args:
        x, y: Top-left corner coordinates
        width, height: Dimensions of the region
        duration: Recording time in seconds
        filename: Output filename
    """
    # Create recordings directory
    os.makedirs('recordings', exist_ok=True)
    
    # Generate filename if not provided
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"region_recording_{timestamp}.mp4"
    
    output_path = os.path.join('recordings', filename)
    
    # Define the region to capture
    region = {
        "top": y,
        "left": x,
        "width": width,
        "height": height
    }
    
    # Initialize screen capture
    with mss() as sct:
        # Capture first frame to get dimensions
        first_frame = sct.grab(region)
        frame_np = np.array(first_frame)
        frame_bgr = cv2.cvtColor(frame_np, cv2.COLOR_BGRA2BGR)
        
        # Get frame dimensions
        height, width, channels = frame_bgr.shape
        frame_size = (width, height)
        
        print(f"Recording region: {width}x{height}")
        print(f"Location: ({x}, {y})")
        print(f"Duration: {duration} seconds")
        print(f"Output file: {output_path}")
        
        # Calculate frame interval for consistent timing
        target_fps = 20.0  # Target FPS
        frame_interval = 1.0 / target_fps  # Time between frames in seconds
        
        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, target_fps, frame_size)  # Consistent FPS
        
        # Start recording
        start_time = time.time()
        
        print("Recording region started... Press Ctrl+C to stop early")
        
        try:
            last_frame_time = time.time()
            while time.time() - start_time < duration:
                current_time = time.time()
                
                # Maintain consistent frame interval
                if current_time - last_frame_time >= frame_interval:
                    # Capture the specified region
                    screenshot = sct.grab(region)
                    
                    # Convert to numpy array and BGR format
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # Write the frame
                    out.write(frame)
                    
                    # Update frame time
                    last_frame_time = current_time
                    
                    # Optional: show preview
                    cv2.imshow('Region Recording - Press Q to stop', frame)
                    
                    # Check if user wants to quit early
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        print("Recording stopped early by user")
                        break
                else:
                    # Small sleep to prevent excessive CPU usage
                    time.sleep(0.001)
        
        except KeyboardInterrupt:
            print("Recording interrupted by user")
        
        finally:
            # Release everything
            out.release()
            cv2.destroyAllWindows()
            
            # Report results
            actual_duration = time.time() - start_time
            
            if os.path.exists(output_path):
                file_size = os.path.getsize(output_path) / (1024 * 1024)  # Size in MB
                print(f"\nRegion recording complete!")
                print(f"Saved to: {output_path}")
                print(f"Duration: {actual_duration:.2f} seconds")
                print(f"File size: {file_size:.2f} MB")
            else:
                print("Recording may have been interrupted")


if __name__ == "__main__":
    print("Basic Screen Recorder Example")
    print("=" * 40)
    
    print("\n1. Record full screen")
    print("2. Record specific region")
    
    choice = input("\nEnter choice (1 or 2): ").strip()
    
    if choice == "1":
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        filename = input("Enter output filename (optional): ").strip() or None
        record_screen_simple(duration=duration, filename=filename)
    
    elif choice == "2":
        x = int(input("Enter X coordinate (default 100): ") or "100")
        y = int(input("Enter Y coordinate (default 100): ") or "100")
        width = int(input("Enter width (default 600): ") or "600")
        height = int(input("Enter height (default 400): ") or "400")
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        filename = input("Enter output filename (optional): ").strip() or None
        
        record_region(x, y, width, height, duration=duration, filename=filename)
    
    else:
        print("Invalid choice. Recording full screen for 5 seconds as example.")
        record_screen_simple(duration=5)