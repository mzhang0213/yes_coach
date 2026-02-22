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

## Notes

- MSS (Multiple Screen Shots) is used for efficient screen capture
- On macOS, you may need to grant screen recording permissions to your terminal application
- The capture runs at full speed - you can add `time.sleep()` to control frame rate if needed