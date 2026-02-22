"""
Advanced Screen Recorder with Quality Controls

This module provides advanced screen recording with quality controls, 
performance optimizations, and various recording options.
"""

import cv2
import numpy as np
from mss import mss
import time
import os
from datetime import datetime
import threading
from queue import Queue


class AdvancedScreenRecorder:
    def __init__(self, output_filename=None, fps=30, codec='mp4v', quality='medium'):
        """
        Initialize the advanced screen recorder
        
        Args:
            output_filename: Name of the output video file
            fps: Frames per second for the output video
            codec: FourCC codec code (e.g., 'mp4v', 'XVID', 'MJPG')
            quality: Quality setting ('low', 'medium', 'high', 'ultra')
        """
        self.fps = fps
        self.codec = codec
        self.quality = quality
        
        # Quality settings mapping
        quality_settings = {
            'low': {'compression': 50, 'buffer_size': 10},
            'medium': {'compression': 75, 'buffer_size': 20},
            'high': {'compression': 90, 'buffer_size': 30},
            'ultra': {'compression': 100, 'buffer_size': 50}
        }
        
        self.quality_params = quality_settings.get(quality, quality_settings['medium'])
        
        # Create recordings directory
        os.makedirs('recordings', exist_ok=True)
        
        # Generate filename if not provided
        if output_filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"advanced_recording_{timestamp}.mp4"
        
        self.output_path = os.path.join('recordings', output_filename)
        
        # Initialize MSS for screen capture
        self.sct = mss()
        self.monitor = self.sct.monitors[1]  # Primary monitor
        
        # Frame buffer for performance
        self.frame_queue = Queue(maxsize=self.quality_params['buffer_size'])
        
        # Recording state
        self.recording = False
        self.out = None
        self.frame_size = None
        
    def calculate_compression_params(self):
        """Calculate compression parameters based on quality"""
        # Different codecs may require different parameters
        if self.codec.lower() in ['jpeg', 'jpg', 'jpe']:
            # JPEG compression level (0-100, higher is better quality)
            return [int(cv2.IMWRITE_JPEG_QUALITY), self.quality_params['compression']]
        elif self.codec.lower() == 'png':
            # PNG compression level (0-9, lower is better quality)
            png_level = max(0, 9 - (self.quality_params['compression'] // 12))
            return [int(cv2.IMWRITE_PNG_COMPRESSION), png_level]
        else:
            return []
    
    def start_recording(self, duration=None, region=None, show_preview=True):
        """
        Start recording the screen with advanced options
        
        Args:
            duration: Recording duration in seconds (None for indefinite recording)
            region: Optional region to record {'top': int, 'left': int, 'width': int, 'height': int}
            show_preview: Whether to show a preview window during recording
        """
        print(f"Starting advanced screen recording...")
        print(f"Output file: {self.output_path}")
        print(f"Quality: {self.quality} (FPS: {self.fps}, Codec: {self.codec})")
        
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
        print(f"Estimated file size: ~{(width * height * 3 * self.fps * (duration or 60) / (1024*1024*8)):.2f} MB per minute")
        
        # Start timing if duration is specified
        start_time = time.time()
        self.recording = True
        
        try:
            last_frame_time = time.time()
            while self.recording:
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
                    
                    # Show preview if enabled
                    if show_preview:
                        cv2.imshow('Advanced Screen Recorder - Press Q to stop', frame)
                        
                        # Check for quit command
                        if cv2.waitKey(1) & 0xFF == ord('q'):
                            print("Recording stopped early by user")
                            break
                else:
                    # Small sleep to prevent excessive CPU usage
                    time.sleep(0.001)
                
                # Check if duration has been reached
                if duration and (time.time() - start_time) >= duration:
                    print(f"Recording duration of {duration} seconds reached")
                    break
                    
        except KeyboardInterrupt:
            print("Recording interrupted by user")
        
        finally:
            self.stop_recording()
    
    def stop_recording(self):
        """Stop recording and clean up resources"""
        self.recording = False
        
        if self.out:
            self.out.release()
        
        cv2.destroyAllWindows()
        
        # Get file size and info
        if os.path.exists(self.output_path):
            size_bytes = os.path.getsize(self.output_path)
            size_mb = size_bytes / (1024 * 1024)
            print(f"\nRecording saved: {self.output_path}")
            print(f"File size: {size_mb:.2f} MB ({size_bytes:,} bytes)")
            
            # Provide basic stats
            duration_estimate = size_mb * 8 / (self.frame_size[0] * self.frame_size[1] * 3 * self.fps / (1024*1024))
            print(f"Estimated duration: {duration_estimate:.1f} seconds")
        else:
            print("Recording may have been interrupted before file was created")
    
    def record_with_audio_placeholder(self, duration=None, region=None):
        """
        Placeholder method for future implementation with audio recording
        Note: This would require additional libraries like sounddevice or pyaudio
        """
        print("Audio recording feature would be implemented here")
        print("This requires additional audio capture libraries")
        # This would integrate with libraries like:
        # - sounddevice for audio input
        # - moviepy for combining video and audio
        # - pydub for audio processing
        self.start_recording(duration, region)


def quick_record(duration=10, output_filename=None):
    """
    Quick function to record screen for specified duration
    
    Args:
        duration: Recording duration in seconds
        output_filename: Output filename (auto-generated if None)
    """
    recorder = AdvancedScreenRecorder(output_filename=output_filename, fps=30, quality='medium')
    recorder.start_recording(duration=duration)


def record_region_quick(x, y, width, height, duration=10, output_filename=None):
    """
    Quick function to record a specific region
    
    Args:
        x, y: Top-left corner coordinates
        width, height: Dimensions of the region
        duration: Recording duration in seconds
        output_filename: Output filename (auto-generated if None)
    """
    region = {
        "top": y,
        "left": x,
        "width": width,
        "height": height
    }
    
    recorder = AdvancedScreenRecorder(output_filename=output_filename, fps=30, quality='medium')
    recorder.start_recording(duration=duration, region=region)


def main():
    print("Advanced OpenCV Screen Recorder")
    print("=" * 50)
    print("Features:")
    print("- Adjustable quality settings (low, medium, high, ultra)")
    print("- Various codec options")
    print("- Customizable regions")
    print("- File size estimation")
    print("- Performance optimizations")
    print()
    
    print("Options:")
    print("1. Quick record (full screen)")
    print("2. Record specific region")
    print("3. Advanced recording with options")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        
        print(f"Recording for {duration} seconds...")
        quick_record(duration=duration, output_filename=filename)
        
    elif choice == "2":
        x = int(input("Enter X coordinate (default 100): ") or "100")
        y = int(input("Enter Y coordinate (default 100): ") or "100")
        width = int(input("Enter width (default 800): ") or "800")
        height = int(input("Enter height (default 600): ") or "600")
        duration = int(input("Enter recording duration in seconds (default 10): ") or "10")
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        
        print(f"Recording region ({x}, {y}, {width}, {height}) for {duration} seconds...")
        record_region_quick(x, y, width, height, duration=duration, output_filename=filename)
        
    elif choice == "3":
        duration = int(input("Enter recording duration in seconds (0 for indefinite): ") or "0")
        if duration <= 0:
            duration = None
        
        x = input("Enter X coordinate (or Enter for full screen): ").strip()
        y = input("Enter Y coordinate (or Enter for full screen): ").strip()
        width = input("Enter width (or Enter for full screen): ").strip()
        height = input("Enter height (or Enter for full screen): ").strip()
        
        region = None
        if x and y and width and height:
            region = {
                "top": int(y),
                "left": int(x),
                "width": int(width),
                "height": int(height)
            }
        
        fps = int(input("Enter FPS (default 30): ") or "30")
        quality = input("Enter quality (low/medium/high/ultra, default medium): ").strip() or "medium"
        codec = input("Enter codec (mp4v/XVID/MJPG, default mp4v): ").strip() or "mp4v"
        filename = input("Enter output filename (optional): ").strip()
        if not filename:
            filename = None
        
        show_preview = input("Show preview? (y/n, default y): ").strip().lower()
        show_preview = show_preview != 'n'
        
        recorder = AdvancedScreenRecorder(
            output_filename=filename,
            fps=fps,
            codec=codec,
            quality=quality
        )
        
        print("Starting advanced recording...")
        recorder.start_recording(
            duration=duration,
            region=region,
            show_preview=show_preview
        )
        
    else:
        print("Invalid choice. Running quick record for 10 seconds.")
        quick_record(duration=10)


if __name__ == "__main__":
    main()