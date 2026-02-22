"""
Simple OpenCV Screen Capture Example
"""
import cv2
import numpy as np
from mss import mss
import time


def simple_screen_capture():
    """
    Simplest possible screen capture using OpenCV and MSS
    """
    # Initialize MSS (Multi-Screen Shot)
    with mss() as sct:
        # Get the primary monitor dimensions
        monitor = sct.monitors[1]  # Index 1 is primary monitor, 0 is all monitors combined
        
        print(f"Capturing screen: {monitor['width']}x{monitor['height']}")
        
        while True:
            # Capture the screen
            img = sct.grab(monitor)
            
            # Convert to numpy array
            frame = np.array(img)

            # Convert from BGRA to BGR (OpenCV format)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            frame = frame / np.linalg.norm(frame)

            # Display the frame
            cv2.imshow('Screen Capture - Press Q to Quit', frame)
            
            # Exit on 'q' key press
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    # Clean up
    cv2.destroyAllWindows()


def capture_specific_region():
    """
    Example of capturing a specific region of the screen
    """
    with mss() as sct:
        # Define a specific region to capture (x, y, width, height)
        region = {
            "top": 100,      # Y coordinate of the top-left corner
            "left": 100,     # X coordinate of the top-left corner
            "width": 600,    # Width of the region
            "height": 400    # Height of the region
        }
        
        print(f"Capturing region: {region}")
        
        while True:
            # Capture the specific region
            img = sct.grab(region)
            
            # Convert to numpy array and BGR format
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            # Display the frame
            cv2.imshow('Region Capture - Press Q to Quit', frame)
            
            # Exit on 'q' key press
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    cv2.destroyAllWindows()


def benchmark_performance():
    """
    Benchmark the capture performance
    """
    with mss() as sct:
        monitor = sct.monitors[1]
        
        print("Benchmarking screen capture performance...")
        print(f"Resolution: {monitor['width']}x{monitor['height']}")
        
        # Capture a few frames to measure performance
        frame_count = 0
        start_time = time.time()
        
        while frame_count < 100:
            img = sct.grab(monitor)
            frame = np.array(img)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            frame_count += 1
            
            # Show progress
            if frame_count % 20 == 0:
                elapsed = time.time() - start_time
                avg_fps = frame_count / elapsed
                print(f"Captured {frame_count}/100 frames, avg FPS: {avg_fps:.2f}")
        
        total_time = time.time() - start_time
        avg_fps = frame_count / total_time
        
        print(f"\nBenchmark Results:")
        print(f"Total frames: {frame_count}")
        print(f"Total time: {total_time:.2f}s")
        print(f"Average FPS: {avg_fps:.2f}")


if __name__ == "__main__":
    print("OpenCV Screen Capture Examples")
    print("1. Simple full screen capture")
    print("2. Specific region capture")
    print("3. Performance benchmark")
    
    choice = input("\nEnter your choice (1-3, or Enter for default 1): ").strip()
    
    if choice == "1" or choice == "":
        simple_screen_capture()
    elif choice == "2":
        capture_specific_region()
    elif choice == "3":
        benchmark_performance()
    else:
        print("Invalid choice. Running simple screen capture by default.")
        simple_screen_capture()