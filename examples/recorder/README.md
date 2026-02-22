# Screen Recorder Module

This module provides functionality to record your screen and save it as video files using OpenCV and MSS.

## Available Recorders

### 1. Basic Recorder ([basic_recorder.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/recorder/basic_recorder.py))
- Simple screen recording functionality
- Records full screen or specific regions
- Basic file output with MP4 format
- Good for getting started

### 2. Standard Recorder ([screen_recorder.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/recorder/screen_recorder.py))
- More advanced recording options
- Configurable FPS and codecs
- Duration-based or manual stopping
- Preview window during recording

### 3. Advanced Recorder ([advanced_screen_recorder.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/recorder/advanced_screen_recorder.py))
- Quality settings (low, medium, high, ultra)
- Performance optimizations
- File size estimation
- More codec options

## How to Use

### Basic Recording:
```bash
cd opencv_screen_capture
python recorder/basic_recorder.py
```

### Standard Recording:
```bash
python recorder/screen_recorder.py
```

### Advanced Recording:
```bash
python recorder/advanced_screen_recorder.py
```

## Programmatic Usage

### Record Full Screen:
```python
from recorder.basic_recorder import record_screen_simple

# Record for 10 seconds
record_screen_simple(duration=10)
```

### Record Specific Region:
```python
from recorder.basic_recorder import record_region

# Record region (x=100, y=100, width=800, height=600) for 15 seconds
record_region(100, 100, 800, 600, duration=15)
```

### Advanced Recording:
```python
from recorder.advanced_screen_recorder import AdvancedScreenRecorder

# Create a high-quality recorder
recorder = AdvancedScreenRecorder(
    output_filename="my_recording.mp4",
    fps=30,
    quality='high'
)

# Record for 30 seconds
recorder.start_recording(duration=30)
```

## Output

All recordings are saved in the `recordings/` directory with automatically generated filenames based on timestamp, or with custom names you specify.

## Codecs

Commonly used codecs:
- `'mp4v'` - MPEG-4 (recommended for MP4 files)
- `'XVID'` - Xvid (good compatibility)
- `'MJPG'` - Motion JPEG (larger files, good quality)
- `'X264'` - H.264 (smaller files, requires more processing)

## Tips

1. **Performance**: Lower FPS and smaller regions will improve performance
2. **Storage**: Screen recordings can consume significant storage space
3. **Preview**: Showing the preview window may slightly reduce performance
4. **Permissions**: On macOS, ensure screen recording permissions are granted
5. **Quality vs Size**: Higher quality settings produce larger files
6. **Frame Rate**: All recorders now maintain consistent frame rates to prevent speed issues

The recordings will be saved as MP4 video files that can be played with any standard video player!