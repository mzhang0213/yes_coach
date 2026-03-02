from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QWidget
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
import sys

class Overlay(QMainWindow):
    def __init__(self):
        super().__init__()
        # Set flags for: No border, Always on Top, and Click-Through
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Create a central widget to enable painting
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        # Define some rectangles to draw using TL and BR points
        # Format: [(top_left_x, top_left_y, bottom_right_x, bottom_right_y, filled)]
        self.rectangles = [
            (50, 50, 200, 150, True),    # Rectangle 1: TL(50,50), BR(200,150), filled
            (300, 100, 500, 250, False),  # Rectangle 2: TL(300,100), BR(500,250), not filled
            (100, 200, 400, 300, True)   # Rectangle 3: TL(100,200), BR(400,300), filled
        ]
        
        # Define circles to draw
        # Format: [(center_x, center_y, radius, filled)]
        self.circles = [
            (150, 80, 40, True),   # Circle 1: Center(150,80), radius 40, filled
            (400, 180, 30, False), # Circle 2: Center(400,180), radius 30, not filled
            (250, 250, 50, True)   # Circle 3: Center(250,250), radius 50, filled
        ]
        
        # Define arrows to draw
        # Format: [(start_x, start_y, end_x, end_y)]
        self.arrows = [
            (10, 350, 100, 350),   # Arrow from (10,350) to (100,350)
            (150, 350, 150, 250),  # Arrow from (150,350) to (150,250)
            (200, 300, 250, 350)   # Arrow from (200,300) to (250,350)
        ]
        
        # Set a fixed size to ensure all shapes are visible
        self.resize(800, 600)
        self.show()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw each rectangle using TL and BR points
        for rect_coords in self.rectangles:
            top_left_x, top_left_y, bottom_right_x, bottom_right_y, filled = rect_coords
            
            # Calculate width and height from TL and BR points
            width = bottom_right_x - top_left_x
            height = bottom_right_y - top_left_y
            
            # Create QRect from top-left point and dimensions
            rect = QRect(top_left_x, top_left_y, width, height)
            
            # Set pen for drawing the rectangle
            painter.setPen(QPen(QColor(255, 0, 0), 3))  # Red border, 3px thick
            
            # Set brush based on fill option
            if filled:
                painter.setBrush(QBrush(QColor(255, 0, 0, 50)))  # Semi-transparent red fill
            else:
                painter.setBrush(QBrush())  # No fill
            
            # Draw the rectangle
            painter.drawRect(rect)
        
        # Draw each circle
        for circle_coords in self.circles:
            center_x, center_y, radius, filled = circle_coords
            
            # Set pen for drawing the circle
            painter.setPen(QPen(QColor(0, 255, 0), 3))  # Green border, 3px thick
            
            # Set brush based on fill option
            if filled:
                painter.setBrush(QBrush(QColor(0, 255, 0, 50)))  # Semi-transparent green fill
            else:
                painter.setBrush(QBrush())  # No fill
            
            # Draw the circle using drawEllipse
            painter.drawEllipse(int(center_x - radius), int(center_y - radius), 
                               int(radius * 2), int(radius * 2))
        
        # Draw each arrow
        for arrow_coords in self.arrows:
            start_x, start_y, end_x, end_y = arrow_coords
            
            # Draw the line
            painter.setPen(QPen(QColor(0, 0, 255), 3))  # Blue line, 3px thick
            painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))
            
            # Draw arrowhead
            self._draw_arrowhead(painter, start_x, start_y, end_x, end_y)
    
    def add_rectangle(self, top_left, bottom_right, filled=True):
        """Add a new rectangle given top-left and bottom-right points
        
        Args:
            top_left: tuple (x, y) representing top-left corner
            bottom_right: tuple (x, y) representing bottom-right corner
            filled: bool indicating whether to fill the rectangle
        """
        tl_x, tl_y = top_left
        br_x, br_y = bottom_right
        self.rectangles.append((tl_x, tl_y, br_x, br_y, filled))
        self.update()  # Trigger repaint
    
    def add_circle(self, center, radius, filled=True):
        """Add a new circle given center point and radius
        
        Args:
            center: tuple (x, y) representing center of the circle
            radius: int representing radius of the circle
            filled: bool indicating whether to fill the circle
        """
        center_x, center_y = center
        self.circles.append((center_x, center_y, radius, filled))
        self.update()  # Trigger repaint
    
    def add_arrow(self, start_point, end_point):
        """Add a new arrow given start and end points
        
        Args:
            start_point: tuple (x, y) representing start of the arrow
            end_point: tuple (x, y) representing end of the arrow
        """
        start_x, start_y = start_point
        end_x, end_y = end_point
        self.arrows.append((start_x, start_y, end_x, end_y))
        self.update()  # Trigger repaint
    
    def clearCanvas(self):
        """Clear all shapes from the canvas"""
        self.rectangles.clear()
        self.circles.clear()
        self.arrows.clear()
        self.update()  # Trigger repaint
    
    def hideCanvas(self):
        """Hide the canvas window"""
        self.hide()  # Hide the window
    
    def showCanvas(self):
        """Show the canvas window"""
        self.show()  # Show the window
    
    def _draw_arrowhead(self, painter, start_x, start_y, end_x, end_y):
        """Draw an arrowhead at the end point of the arrow
        
        Args:
            painter: QPainter object
            start_x, start_y: start coordinates of the arrow
            end_x, end_y: end coordinates of the arrow
        """
        import math
        
        # Calculate the angle of the line
        angle = math.atan2(end_y - start_y, end_x - start_x)
        
        # Size of the arrowhead
        arrowhead_length = 15
        
        # Calculate the points for the arrowhead
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        
        # Point 1 of the arrowhead (rotated -30 degrees from main line)
        angle1 = angle - math.pi / 6  # -30 degrees in radians
        x1 = end_x - arrowhead_length * math.cos(angle1)
        y1 = end_y - arrowhead_length * math.sin(angle1)
        
        # Point 2 of the arrowhead (rotated +30 degrees from main line)
        angle2 = angle + math.pi / 6  # +30 degrees in radians
        x2 = end_x - arrowhead_length * math.cos(angle2)
        y2 = end_y - arrowhead_length * math.sin(angle2)
        
        # Draw the arrowhead lines
        painter.drawLine(int(end_x), int(end_y), int(x1), int(y1))
        painter.drawLine(int(end_x), int(end_y), int(x2), int(y2))

app = QApplication(sys.argv)
window = Overlay()
sys.exit(app.exec())