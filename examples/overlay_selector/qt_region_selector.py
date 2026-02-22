"""
Advanced Screen Region Selector with PyQt5 Overlay

This application creates a sophisticated transparent overlay that allows users to select
a region of the screen for capture. The overlay is non-interactive with the underlying
applications but allows the user to draw a selection rectangle.
"""

import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPainter, QPen, QColor, QBrush, QPixmap
from mss import mss
import threading


class SelectionOverlay(QWidget):
    def __init__(self, screen_geometry):
        super().__init__()
        self.screen_geometry = screen_geometry
        
        # Set up the overlay window
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        
        # Track mouse state
        self.drawing = False
        self.start_point = QPoint()
        self.end_point = QPoint()
        
        # Store the selected region
        self.selected_region = None
        
        # Set geometry to cover the entire screen
        self.setGeometry(screen_geometry)
        
        # Instructions label
        self.instruction_label = QLabel(self)
        self.instruction_label.setText("Click and drag to select a region to capture\nPress ESC to cancel")
        self.instruction_label.setStyleSheet("""
            color: white;
            background-color: rgba(0, 0, 0, 128);
            font-size: 16px;
            font-weight: bold;
            padding: 10px;
        """)
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.instruction_label.setGeometry(50, 50, 400, 80)
        
        self.show()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drawing = True
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.update()
    
    def mouseMoveEvent(self, event):
        if self.drawing:
            self.end_point = event.pos()
            self.update()
    
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            self.end_point = event.pos()
            
            # Calculate the selected region
            left = min(self.start_point.x(), self.end_point.x())
            top = min(self.start_point.y(), self.end_point.y())
            right = max(self.start_point.x(), self.end_point.x())
            bottom = max(self.start_point.y(), self.end_point.y())
            
            self.selected_region = {
                'left': left,
                'top': top,
                'width': right - left,
                'height': bottom - top
            }
            
            print(f"Selected region: {self.selected_region}")
            
            # Close the overlay
            self.close()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self.drawing:
            # Draw a semi-transparent overlay
            painter.setBrush(QColor(0, 0, 0, 100))
            painter.drawRect(self.rect())
            
            # Draw the selection rectangle
            left = min(self.start_point.x(), self.end_point.x())
            top = min(self.start_point.y(), self.end_point.y())
            width = abs(self.end_point.x() - self.start_point.x())
            height = abs(self.end_point.y() - self.start_point.y())
            
            rect = QRect(left, top, width, height)
            
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.setBrush(QBrush(QColor(255, 0, 0, 50)))
            painter.drawRect(rect)


class ScreenRegionSelectorApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.overlay = None
        self.selected_region = None
        self.sct = mss()
        
        # Get screen geometry
        screen = self.app.primaryScreen()
        self.screen_geometry = screen.geometry()
        
    def show_selection_overlay(self):
        """Show the selection overlay and wait for user input"""
        self.overlay = SelectionOverlay(self.screen_geometry)
        
        # Handle escape key
        self.app.keyReleaseEvent = self._handle_key_release
        
        # Run the event loop
        self.app.exec_()
        
        # Get the selected region
        if self.overlay:
            self.selected_region = self.overlay.selected_region
    
    def _handle_key_release(self, event):
        """Handle key release events"""
        if event.key() == Qt.Key_Escape:
            if self.overlay:
                self.overlay.close()
    
    def start_capture_with_region(self):
        """Start capturing the selected region"""
        if not self.selected_region:
            print("No region selected!")
            return
        
        print(f"Starting capture of region: {self.selected_region}")
        
        # Start capture in a separate thread
        capture_thread = threading.Thread(target=self.capture_loop)
        capture_thread.daemon = True
        capture_thread.start()
        
        # Keep the main thread alive
        try:
            capture_thread.join()
        except KeyboardInterrupt:
            print("Capture interrupted")
    
    def capture_loop(self):
        """Main capture loop"""
        try:
            while True:
                # Capture the selected region
                screenshot = self.sct.grab(self.selected_region)
                
                # Convert to numpy array and BGR format
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                # Display the captured region
                cv2.imshow('Selected Region Capture - Press Q to quit', frame)
                
                # Exit on 'q' key press
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        
        except KeyboardInterrupt:
            print("Capture interrupted")
        finally:
            cv2.destroyAllWindows()
    
    def run(self):
        """Run the entire selection and capture process"""
        print("Screen Region Selector")
        print("Instructions:")
        print("1. A transparent overlay will appear over your screen")
        print("2. Click and drag to select a region")
        print("3. The selected region will be captured in real-time")
        print("4. Press 'q' in the capture window to stop")
        print("5. Press 'ESC' during selection to cancel")
        print()
        
        print("Showing selection overlay...")
        self.show_selection_overlay()
        
        if self.selected_region:
            print(f"Region selected: {self.selected_region}")
            self.start_capture_with_region()
        else:
            print("No region was selected.")


def main():
    selector_app = ScreenRegionSelectorApp()
    selector_app.run()


if __name__ == "__main__":
    main()