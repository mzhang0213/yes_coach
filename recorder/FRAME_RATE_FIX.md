# Frame Rate Correction Guide

## The Problem
Videos were appearing "sped up" because there was a mismatch between the actual frame capture rate and the frame rate specified when creating the video file.

## The Solution
The issue was fixed by implementing a timing mechanism that ensures frames are captured at consistent intervals based on the target FPS.

### Key Changes Made:

1. **Frame Interval Calculation**:
   ```python
   frame_interval = 1.0 / target_fps  # Time between frames in seconds
   ```

2. **Consistent Timing Loop**:
   ```python
   last_frame_time = time.time()
   while recording:
       current_time = time.time()
       
       if current_time - last_frame_time >= frame_interval:
           # Capture and save frame
           screenshot = sct.grab(region)
           frame = np.array(screenshot)
           frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
           out.write(frame)
           
           last_frame_time = current_time  # Update time for next frame
       else:
           # Brief sleep to prevent excessive CPU usage
           time.sleep(0.001)
   ```

### Benefits:
- Videos now play back at the correct speed
- Maintains the specified FPS in the output file
- Consistent timing prevents speed variations
- Prevents frame drops that could cause timing issues

### Files Updated:
- [recorder/basic_recorder.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/recorder/basic_recorder.py) - Basic recorder with frame rate control
- [recorder/screen_recorder.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/recorder/screen_recorder.py) - Standard recorder with frame rate control
- [recorder/advanced_screen_recorder.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/recorder/advanced_screen_recorder.py) - Advanced recorder with frame rate control
- [recorder/corrected_recorder.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/recorder/corrected_recorder.py) - Dedicated corrected recorder example

All recorders now maintain proper timing to ensure videos play back at the correct speed!