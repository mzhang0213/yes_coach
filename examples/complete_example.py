"""
Complete OpenCV Screen Capture Solution with Error Handling
"""
import cv2
import numpy as np
from mss import mss
import time
import sys
import platform
import os


def check_permissions():
    """
    Check if the application has necessary permissions on macOS
    """
    if platform.system() == "Darwin":  # macOS
        print("Platform: macOS")
        print("On macOS, you may need to grant Screen Recording permissions to your terminal app.")
        print("Go to System Preferences > Security & Privacy > Privacy > Screen Recording")
        print("and make sure your terminal application is checked.\n")
    elif platform.system() == "Windows":
        print("Platform: Windows")
    else:
        print(f"Platform: {platform.system()}")


def capture_with_error_handling():
    """
    Screen capture with comprehensive error handling
    """
    try:
        with mss() as sct:
            # Get monitor information
            monitors = sct.monitors
            print(f"Available monitors: {len(monitors) - 1}")  # monitors[0] is all monitors combined
            
            for i, monitor in enumerate(monitors):
                if i == 0:
                    print(f"Monitor {i} (Combined): {monitor}")
                else:
                    print(f"Monitor {i} (Primary)" if i == 1 else f"Monitor {i}): {monitor}")
            
            # Use primary monitor (index 1)
            monitor = sct.monitors[1]
            
            print(f"\nStarting screen capture for monitor 1...")
            print(f"Resolution: {monitor['width']} x {monitor['height']}")
            print("Press 'q' to quit\n")
            
            frame_count = 0
            start_time = time.time()
            
            while True:
                try:
                    # Capture the screen
                    screenshot = sct.grab(monitor)
                    
                    # Convert the screenshot to a numpy array (OpenCV format)
                    frame = np.array(screenshot)
                    
                    # Convert from BGRA to BGR (OpenCV format)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # Display the frame
                    cv2.imshow('Screen Capture - Press Q to Quit', frame)
                    
                    frame_count += 1
                    
                    # Print FPS every 60 frames
                    if frame_count % 60 == 0:
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed
                        print(f"FPS: {fps:.2f} (Frames: {frame_count}, Time: {elapsed:.2f}s)")
                    
                    # Exit on 'q' key press
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                        
                except Exception as e:
                    print(f"Error during capture: {str(e)}")
                    continue
            
    except Exception as e:
        print(f"Critical error: {str(e)}")
        if "Permission denied" in str(e) or "screen recording" in str(e).lower():
            print("\nThis error typically occurs due to missing permissions on macOS.")
            print("Please check your Screen Recording permissions as mentioned above.")
        return False
    
    finally:
        cv2.destroyAllWindows()
    
    print(f"\nCapture stopped. Processed {frame_count} frames.")
    elapsed = time.time() - start_time
    print(f"Total time: {elapsed:.2f}s, Average FPS: {frame_count/elapsed:.2f}")
    
    return True


def capture_region_with_error_handling(x=100, y=100, width=600, height=400):
    """
    Capture a specific region with error handling
    """
    try:
        with mss() as sct:
            # Define region to capture
            region = {
                "top": y,
                "left": x,
                "width": width,
                "height": height
            }
            
            print(f"Capturing region: ({x}, {y}, {width}, {height})")
            print("Press 'q' to quit\n")
            
            while True:
                try:
                    # Capture the specific region
                    screenshot = sct.grab(region)
                    
                    # Convert to numpy array and BGR format
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # Display the frame
                    cv2.imshow('Region Capture - Press Q to Quit', frame)
                    
                    # Exit on 'q' key press
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
                        
                except Exception as e:
                    print(f"Error during region capture: {str(e)}")
                    continue
            
    except Exception as e:
        print(f"Critical error in region capture: {str(e)}")
        return False
    
    finally:
        cv2.destroyAllWindows()
    
    return True


def save_screenshot_example():
    """
    Example of how to save screenshots instead of displaying them
    """
    try:
        with mss() as sct:
            monitor = sct.monitors[1]
            
            print("Taking a single screenshot...")
            screenshot = sct.grab(monitor)
            
            # Convert to numpy array
            frame = np.array(screenshot)
            
            # Convert from BGRA to BGR
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            
            # Create directory for screenshots if it doesn't exist
            os.makedirs("screenshots", exist_ok=True)
            
            # Save the screenshot
            timestamp = int(time.time())
            filename = f"screenshots/screenshot_{timestamp}.png"
            cv2.imwrite(filename, frame)
            
            print(f"Screenshot saved as {filename}")
            print(f"Image size: {frame.shape[1]}x{frame.shape[0]}")
    
    except Exception as e:
        print(f"Error saving screenshot: {str(e)}")
        return False
    
    return True


def main():
    print("OpenCV Screen Capture - Complete Example")
    print("="*50)
    
    check_permissions()
    
    print("\nChoose an option:")
    print("1. Full screen capture")
    print("2. Region capture (100,100,600,400)")
    print("3. Take single screenshot")
    print("4. All examples (one after another)")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == "1":
        capture_with_error_handling()
    elif choice == "2":
        capture_region_with_error_handling()
    elif choice == "3":
        save_screenshot_example()
    elif choice == "4":
        print("\nRunning full screen capture...")
        capture_with_error_handling()
        
        print("\nRunning region capture...")
        capture_region_with_error_handling()
        
        print("\nTaking single screenshot...")
        save_screenshot_example()
    else:
        print("Invalid choice. Running full screen capture by default.")
        capture_with_error_handling()


if __name__ == "__main__":
    main()