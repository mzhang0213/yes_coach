# OpenCV Screen Capture

This project demonstrates screen capturing using OpenCV with the MSS library for efficient screen capture.

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

Or install them individually:
```bash
pip install opencv-python numpy mss pillow
```

## Usage

Run the main script:
```bash
python src/main.py
```

The application will:
- Capture your primary screen in real-time
- Display the captured frames in a window
- Press 'q' to quit the application

## Features

- Real-time screen capture using MSS (which is more efficient than traditional approaches)
- OpenCV for frame processing and display
- Configurable capture regions (modify in code)

## Features

- Real-time screen capture using MSS (which is more efficient than traditional approaches)
- OpenCV for frame processing and display
- Configurable capture regions (modify in code)
- Screen region selector with interactive overlay

## Notes

- MSS (Multiple Screen Shots) is used for efficient screen capture
- On macOS, you may need to grant screen recording permissions to your terminal application
- The capture runs at full speed - you can add `time.sleep()` to control frame rate if needed

## Advanced Features

The project also includes advanced screen region selection and recording capabilities:

### Screen Region Selection
1. **Interactive Region Selection**: Use `overlay_selector/simple_region_selector.py` to visually select areas of the screen to capture
2. **Multiple UI Options**: Choose from OpenCV-based, Tkinter, or PyQt5 implementations
3. **Non-Interference**: The overlay doesn't affect underlying applications

To try the region selector:
```bash
python overlay_selector/simple_region_selector.py
```

### Screen Recording
1. **Save Captures as Videos**: Record screen activity and save as MP4 files
2. **Multiple Recording Options**: Basic, standard, and advanced recording modes
3. **Configurable Settings**: FPS, quality, codecs, and durations

To try the recorder:
```bash
python recorder/basic_recorder.py
```

**Note**: The recorders now maintain consistent frame rates to prevent videos from playing back too fast.