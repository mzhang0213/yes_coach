# Getting Started with OpenCV for Screen Capture

This project provides a complete setup for screen capture using OpenCV and MSS (Multiple Screen Shots). Below is everything you need to know to get started.

## Project Structure

```
opencv_screen_capture/
├── src/
│   ├── main.py                 # Basic screen capture implementation
│   ├── simple_capture.py       # Simple example with user choices
│   ├── screen_capture_advanced.py  # Advanced features with CLI options
│   └── complete_example.py     # Complete example with error handling
├── requirements.txt           # Dependencies
├── README.md                  # Documentation
├── setup.py                   # Package setup
└── .gitignore                 # Git ignore rules
```

## Installation

1. Navigate to the project directory:
   ```bash
   cd opencv_screen_capture
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or install manually:
   ```bash
   pip install opencv-python numpy mss pillow
   ```

## Key Components

### 1. MSS (Multiple Screen Shots)
- More efficient than OpenCV's VideoCapture for screen capture
- Cross-platform compatibility
- Better performance for screen capture tasks

### 2. Core Functions Available

- **Full screen capture**: Captures the entire primary monitor
- **Region capture**: Captures a specific rectangular region of the screen
- **Performance benchmarking**: Measures frames per second (FPS)
- **Screenshot saving**: Captures and saves a single screenshot to disk
- **Error handling**: Comprehensive error handling for permission issues

### 3. Usage Examples

#### Basic Screen Capture
```python
from mss import mss
import cv2
import numpy as np

with mss() as sct:
    monitor = sct.monitors[1]  # Primary monitor
    
    while True:
        # Capture the screen
        screenshot = sct.grab(monitor)
        
        # Convert to OpenCV format
        frame = np.array(screenshot)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        
        # Display the frame
        cv2.imshow('Screen Capture', frame)
        
        # Exit on 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cv2.destroyAllWindows()
```

#### Region Capture
```python
region = {
    "top": 100,
    "left": 100, 
    "width": 600,
    "height": 400
}

with mss() as sct:
    screenshot = sct.grab(region)
    frame = np.array(screenshot)
    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
```

## Running Examples

1. **Simple capture with menu**:
   ```bash
   python src/simple_capture.py
   ```

2. **Advanced capture with CLI options**:
   ```bash
   python src/screen_capture_advanced.py --help
   python src/screen_capture_advanced.py --show-fps
   python src/screen_capture_advanced.py --region 100 100 800 600
   ```

3. **Complete example with error handling**:
   ```bash
   python src/complete_example.py
   ```

## Platform-Specific Notes

### macOS
- You may need to grant "Screen Recording" permissions to your terminal application
- Go to System Preferences > Security & Privacy > Privacy > Screen Recording
- Make sure your terminal application is checked in the list

### Windows/Linux
- Generally no special permissions required for screen capture

## Performance Tips

1. **Use MSS instead of VideoCapture**: MSS is specifically designed for fast screen capture
2. **Capture only needed regions**: Smaller regions = better performance
3. **Add delays if needed**: Use `time.sleep()` to reduce CPU usage if capturing at full speed is too intensive
4. **Consider image processing**: Reduce resolution or apply filters to decrease processing load

## Troubleshooting

### Common Issues:
- **Permission errors on macOS**: Check screen recording permissions
- **Slow performance**: Try capturing smaller regions or adding small delays between captures
- **Import errors**: Ensure all dependencies are installed via `pip install -r requirements.txt`

## Next Steps

1. Experiment with different capture regions
2. Add image processing features using OpenCV
3. Implement screen recording to video files
4. Add computer vision algorithms to analyze the captured content

The foundation is now ready for any screen capture project you'd like to build!