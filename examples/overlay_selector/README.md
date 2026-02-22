# Screen Region Selector with Overlay

This directory contains multiple implementations for selecting screen regions with overlays for capture.

## Available Implementations

### 1. Simple Region Selector ([simple_region_selector.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/overlay_selector/simple_region_selector.py))
- Uses OpenCV's built-in mouse callbacks
- Shows a full-screen overlay where you can click and drag to select a region
- Press 'c' to confirm selection, 'r' to reset, 'q' to quit
- Simplest implementation requiring only existing dependencies

### 2. Tkinter Overlay ([region_selector.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/overlay_selector/region_selector.py))
- Uses Tkinter to create a transparent overlay
- Allows drawing selection rectangles with live preview
- More complex but provides better visual feedback

### 3. PyQt5 Overlay ([qt_region_selector.py](file:///Users/mzhang/Documents/0b_cs_projects/yes_coach/opencv_screen_capture/overlay_selector/qt_region_selector.py))
- Uses PyQt5 for professional-grade overlay
- Provides smooth, responsive selection experience
- Requires PyQt5 installation

## How to Use

### For Simple Region Selector (Recommended):
```bash
cd opencv_screen_capture
python overlay_selector/simple_region_selector.py
```

### For PyQt5 Version:
```bash
cd opencv_screen_capture
python overlay_selector/qt_region_selector.py
```

### For Tkinter Version:
```bash
cd opencv_screen_capture
python overlay_selector/region_selector.py
```

## Features

- **Non-Interactive Overlay**: The overlay doesn't interfere with underlying applications
- **Visual Feedback**: Shows the selected region in real-time
- **Flexible Selection**: Click and drag to select any rectangular area
- **Live Capture**: Immediately starts capturing the selected region
- **Easy Controls**: Simple keyboard shortcuts for operation

## Requirements

All versions require the base dependencies from the main project:
- opencv-python
- numpy
- mss
- pillow

The PyQt5 version additionally requires:
- PyQt5

Install all dependencies with:
```bash
pip install -r requirements.txt
```

## Use Cases

- Gaming streams focusing on specific game areas
- Tutorial creation highlighting specific UI elements
- Monitoring specific application windows
- Creating custom screen recording regions
- Computer vision applications focusing on specific screen areas

Try the simple_region_selector.py first as it provides the core functionality with the simplest setup!