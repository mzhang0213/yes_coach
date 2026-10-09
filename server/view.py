"""View layer — overlay rendering and input widgets.

Renders application state (CoachModel) onto a transparent, always-on-top
overlay, plus the auxiliary region-picker and prompt widgets. Pure
presentation: holds no game logic and never mutates the model.
"""
import math
import os
import time

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                             QLabel, QLineEdit, QPushButton, QVBoxLayout)
from PyQt6.QtCore import Qt, QRect, QRectF, QEventLoop
from PyQt6.QtGui import (QPainter, QPen, QColor, QBrush, QFont,
                         QLinearGradient, QRadialGradient, QPainterPath, QPixmap, QFontMetrics)

from server.utils import SCREEN_SIZE, app

# coach panel layout (screen pixels)
PANEL_W = 380
PANEL_PAD = 12
ICON_SIZE = 44     # round Gemini-logo button; doubles as the panel's top-left corner
ICON_INSET = 6     # logo's offset from the panel corner when open
ROW_H = 34
ROW_GAP = 6
DIVIDER_GAP = 14   # extra space where the thin rule sits between situational and pinned questions
FILL_STEP = 0.019  # hover-fill per frame (~0.85 s at 16 ms ticks)
TOAST_MARGIN = 16           # state toast: top-left corner offset
TOAST_PAD = 8
TOAST_LINE_H = 15
BUBBLE_D = 88               # tip bubbles (circles) beside the open panel
BUBBLE_GAP = 14             # panel edge → bubble area
# scattered slot offsets (dx out from the panel, dy down from its top) — spread out, not a list
BUBBLE_SLOTS = [(4, -8), (100, 92), (16, 200)]
# bubble colour per tip category — five spread-out hues around the colour wheel
BUBBLE_COLORS = {
    'death':     (255, 84, 104),   # coral red
    'objective': (255, 176, 46),   # amber
    'farm':      (64, 214, 120),   # green
    'economy':   (56, 168, 255),   # sky blue
    'macro':     (168, 92, 255),   # violet
}
MAX_BUBBLES = 3
BUBBLE_FILL_STEP = 0.04     # pops in ~0.4 s — faster than buttons
CARD_W = 280                # popped tip's detail card
CARD_LEAVE_FRAMES = 20      # card closes once the cursor has been off it this long (~0.3 s)


class ButtonPlacer(QWidget):
    """Dimmed full-screen overlay with a white crosshair. Click to place, ESC to cancel."""

    def __init__(self):
        super().__init__()
        self.mouse_pos = None
        self.selected_position = None
        self._loop = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.BlankCursor)

        screen = app.primaryScreen().geometry()
        self.setGeometry(screen)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # dim
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self.mouse_pos:
            mx, my = self.mouse_pos.x(), self.mouse_pos.y()
            arm = 8

            # white X crosshair
            pen = QPen(QColor(255, 255, 255), 2)
            painter.setPen(pen)
            painter.drawLine(mx - arm, my - arm, mx + arm, my + arm)
            painter.drawLine(mx - arm, my + arm, mx + arm, my - arm)

        # instruction label
        text = "Click to place button.  ESC to cancel."
        font = QFont('Arial', 13)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        pad = 10
        bx = (self.width() - tw) // 2 - pad
        by = 40
        painter.fillRect(bx, by, tw + pad * 2, th + pad * 2, QColor(255, 255, 255, 230))
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawRect(bx, by, tw + pad * 2, th + pad * 2)
        painter.setPen(Qt.GlobalColor.black)
        painter.drawText(bx + pad, by + pad + fm.ascent(), text)

        painter.end()

    def mouseMoveEvent(self, event):
        self.mouse_pos = event.pos()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected_position = {
                'x': event.pos().x() / SCREEN_SIZE[0],
                'y': event.pos().y() / SCREEN_SIZE[1],
            }
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        if self._loop and self._loop.isRunning():
            self._loop.quit()
        super().closeEvent(event)

    def pick(self) -> dict | None:
        """Block until click. Returns {'x': float, 'y': float} or None."""
        self._loop = QEventLoop()
        self.show()
        self._loop.exec()
        return self.selected_position


class PromptWindow(QWidget):
    """Small input window for custom user questions."""

    def __init__(self, callback=None):
        super().__init__()
        self.callback = callback
        self.setWindowTitle("Ask Coach")
        self.setFixedSize(350, 130)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        label = QLabel("Ask your question:")
        label.setFont(QFont('Arial', 12, QFont.Weight.Bold))
        layout.addWidget(label)

        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("e.g. Should I take dragon or push mid?")
        self.text_input.returnPressed.connect(self._submit)
        layout.addWidget(self.text_input)

        submit_btn = QPushButton("Ask!")
        submit_btn.clicked.connect(self._submit)
        layout.addWidget(submit_btn)

        self.setLayout(layout)

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )
        self.text_input.setFocus()

    def _submit(self):
        text = self.text_input.text().strip()
        if text and self.callback:
            self.callback(text)
        self.close()


class OverlayView(QMainWindow):

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

        # Format: [(top_left_x, top_left_y, bottom_right_x, bottom_right_y, filled)]
        # self.rectangles = [
        #     (50, 50, 200, 150, True),    # Rectangle 1: TL(50,50), BR(200,150), filled
        #     (300, 100, 500, 250, False),  # Rectangle 2: TL(300,100), BR(500,250), not filled
        #     (100, 200, 400, 300, True)   # Rectangle 3: TL(100,200), BR(400,300), filled
        # ]
        #
        # # Format: [(center_x, center_y, radius, filled)]
        # self.circles = [
        #     (150, 80, 40, True),   # Circle 1: Center(150,80), radius 40, filled
        #     (400, 180, 30, False), # Circle 2: Center(400,180), radius 30, not filled
        #     (250, 250, 50, True)   # Circle 3: Center(250,250), radius 50, filled
        # ]
        #
        # # Format: [(start_x, start_y, end_x, end_y)]
        # self.arrows = [
        #     (10, 350, 100, 350),   # Arrow from (10,350) to (100,350)
        #     (150, 350, 150, 250),  # Arrow from (150,350) to (150,250)
        #     (200, 300, 250, 350)   # Arrow from (200,300) to (250,350)
        # ]
        self.rectangles = []
        self.circles = []
        self.arrows = []
        self.text_boxes = []
        self.gemini_buttons = []
        self.tab_buttons = []
        self.panels = []
        self.labels = []
        self.rows = []
        self.spinners = []
        self.icon_buttons = []

        # ── interaction state (the view owns button positions + animations) ──
        # idle → open → cooldown → idle. What the open panel shows (analyzing /
        # suggestions / answering / answer) is derived from model data in render().
        self.button_pos = None
        self.state = 'idle'
        self.fills = {}  # hover-fill per target name ('open', 'close', 'suggest:0', …)
        self._close_armed = False  # re-hovering the logo closes only after the cursor left it once
        self.tip_slots: dict[int, int] = {}  # tip id → bubble slot, so bubbles never shift under the cursor
        self.card_slot = 0                   # slot the open detail card grew from
        self._card_away = 0                  # frames the cursor has been off the card
        self.bubbles = []
        self.cards = []
        self.dividers = []

        # load notebook icon once
        icon_path = os.path.join(os.path.dirname(__file__), 'notebook_icon.png')
        self.notebook_icon = QPixmap(icon_path) if os.path.exists(icon_path) else None
        gemini_path = os.path.join(os.path.dirname(__file__), 'gemini_icon.png')
        self.gemini_icon = QPixmap(gemini_path) if os.path.exists(gemini_path) else None

        self.resize(SCREEN_SIZE[0], SCREEN_SIZE[1])
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for panel in self.panels:
            self._paint_panel(painter, panel)
        for row in self.rows:
            self._paint_row(painter, row)
        painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        for x1, y1, x2 in self.dividers:
            painter.drawLine(x1, y1, x2, y1)
        for label in self.labels:
            self._paint_label(painter, label)
        for spinner in self.spinners:
            self._paint_spinner(painter, spinner)
        for icon_btn in self.icon_buttons:
            self._paint_icon_button(painter, icon_btn)
        for bubble in self.bubbles:
            self._paint_bubble(painter, bubble)
        for card in self.cards:
            self._paint_card(painter, card)

        for i,box in enumerate(self.text_boxes):
            x, y, text, color, font_size = box
            font = QFont('Arial', font_size)
            font.setBold(font_size >= 12)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(text)
            th = fm.height()
            pad = 10
            bx = x
            by = y
            bw = tw + pad * 2
            bh = th + pad * 2
            painter.fillRect(bx, by, bw, bh, QColor(255, 255, 255, 255))
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawRect(bx, by, bw, bh)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(bx + pad, by + pad + fm.ascent(), text)

        # Draw each rectangle using TL and BR points
        for rect_coords in self.rectangles:
            top_left_x, top_left_y, bottom_right_x, bottom_right_y, filled, color = rect_coords
            r, g, b = color

            width = bottom_right_x - top_left_x
            height = bottom_right_y - top_left_y
            rect = QRect(top_left_x, top_left_y, width, height)

            painter.setPen(QPen(QColor(r, g, b), 3))
            if filled:
                painter.setBrush(QBrush(QColor(r, g, b, 50)))
            else:
                painter.setBrush(QBrush())

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

        # Draw gemini buttons
        for btn in self.gemini_buttons:
            self._paint_gemini_button(painter, btn)

        # Draw tab buttons
        for tab in self.tab_buttons:
            self._paint_tab_button(painter, tab)

        # Draw each arrow
        for arrow_coords in self.arrows:
            start_x, start_y, end_x, end_y = arrow_coords

            # Draw the line
            painter.setPen(QPen(QColor(0, 0, 255), 3))  # Blue line, 3px thick
            painter.drawLine(int(start_x), int(start_y), int(end_x), int(end_y))

            # Draw arrowhead
            self.draw_arrowhead(painter, start_x, start_y, end_x, end_y)

    def draw_arrowhead(self, painter, start_x, start_y, end_x, end_y):
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

    def add_rectangle(self, top_left:tuple[int,int], bottom_right:tuple[int,int], filled=True, color=(255, 0, 0)):
        """Add a new rectangle given top-left and bottom-right points

        Args:
            top_left: tuple (x, y) representing top-left corner
            bottom_right: tuple (x, y) representing bottom-right corner
            filled: bool indicating whether to fill the rectangle
            color: tuple (r, g, b) border/fill color
        """
        tl_x, tl_y = top_left
        br_x, br_y = bottom_right
        self.rectangles.append((tl_x, tl_y, br_x, br_y, filled, color))
        self.update()  # Trigger repaint

    @staticmethod
    def _measure_text_box(text: str, font_size: int, pad: int = 10) -> tuple[int, int]:
        from PyQt6.QtGui import QFontMetrics
        font = QFont('Arial', font_size)
        font.setBold(font_size >= 12)
        fm = QFontMetrics(font)
        return fm.horizontalAdvance(text) + pad * 2, fm.height() + pad * 2

    def add_text_box(self, x: int, y: int, text: str, color=(255, 0, 0)):
        self.text_boxes.append((x, y, text, color, 13))
        self.update()
        return self._measure_text_box(text, 13)

    def add_small_text_box(self, x: int, y: int, text: str, color=(80, 80, 80), font_size: int = 9):
        self.text_boxes.append((x, y, text, color, font_size))
        self.update()
        return self._measure_text_box(text, font_size)

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

    def draw_button(self, completion: float, text: str,
                    x: float = 0.775, y: float = 0.15,
                    color: tuple = (38, 148, 73), progress_color: tuple = (55, 222, 108)):
        tl_x = int(SCREEN_SIZE[0] * x)
        tl_y = int(SCREEN_SIZE[1] * y)
        tb_w, tb_h = self.add_text_box(tl_x, tl_y, text, color)
        br_x = tl_x + tb_w
        br_y = tl_y + tb_h
        prog_x = tl_x + int(tb_w * completion)
        self.add_rectangle((tl_x, tl_y), (prog_x, br_y), True, progress_color)
        return (tl_x, tl_y), (br_x, br_y)

    def _paint_gemini_button(self, painter: QPainter, btn: dict):
        """Render a single Gemini-styled button with gradient, rounded rect, icon, and text."""
        x, y, w, h = btn['x'], btn['y'], btn['w'], btn['h']
        completion = btn.get('completion', 0.0)
        radius = h // 2  # pill shape

        # --- main button body ---
        btn_rect = QRectF(x, y, w, h)
        btn_path = QPainterPath()
        btn_path.addRoundedRect(btn_rect, radius, radius)

        grad = QLinearGradient(btn_rect.topLeft(), btn_rect.topRight())
        grad.setColorAt(0.0, QColor(55, 115, 230))    # vibrant blue
        grad.setColorAt(0.35, QColor(120, 75, 220))    # purple
        grad.setColorAt(0.65, QColor(190, 60, 220))    # magenta-purple
        grad.setColorAt(1.0, QColor(235, 90, 140))     # pink-coral

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(btn_path)

        # --- completion fill (radial bloom from center, clipped to pill) ---
        if completion > 0.0:
            painter.save()
            painter.setClipPath(btn_path)
            import math
            cx = x + w / 2
            cy = y + h / 2
            max_r = math.hypot(w / 2, h / 2)
            r = max_r * min(completion, 1.0)
            bloom = QRadialGradient(cx, cy, r)
            bloom.setColorAt(0.0, QColor(255, 255, 255, 90))
            bloom.setColorAt(0.6, QColor(200, 170, 255, 70))
            bloom.setColorAt(1.0, QColor(200, 170, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bloom))
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
            painter.restore()

        # thin bright border for crispness
        border_grad = QLinearGradient(btn_rect.topLeft(), btn_rect.topRight())
        border_grad.setColorAt(0.0, QColor(100, 160, 255, 160))
        border_grad.setColorAt(0.5, QColor(180, 120, 255, 160))
        border_grad.setColorAt(1.0, QColor(255, 120, 180, 160))
        painter.setPen(QPen(QBrush(border_grad), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(btn_path)

        # --- icon ---
        icon_size = int(h * 0.55)
        icon_x = x + int(h * 0.35)
        icon_y = y + (h - icon_size) // 2
        if btn.get('icon'):
            painter.drawPixmap(int(icon_x), int(icon_y), icon_size, icon_size, btn['icon'])

        # --- text ---
        text_x = icon_x + icon_size + int(h * 0.2)
        font = QFont('Arial', max(int(h * 0.32), 11))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        text_rect = QRectF(text_x, y, w - (text_x - x) - int(h * 0.3), h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, btn['text'])

    def draw_gemini_button(self, text: str = "Ask Coach!!",
                           x: float = 0.775, y: float = 0.15,
                           completion: float = 0.0):
        """Add a Gemini-styled rounded button to the overlay.

        Args:
            text: button label
            x: center x as fraction of screen width
            y: center y as fraction of screen height
            completion: 0.0–1.0 hover-fill progress
        Returns:
            (tl, br) bounding box in screen pixels
        """
        import os
        icon_path = os.path.join(os.path.dirname(__file__), 'gemini_icon.png')
        icon = QPixmap(icon_path) if os.path.exists(icon_path) else None

        font = QFont('Arial', 14)
        font.setBold(True)
        from PyQt6.QtGui import QFontMetrics
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(text)

        btn_h = 44
        icon_space = int(btn_h * 0.55) + int(btn_h * 0.55)  # icon + padding
        btn_w = int(btn_h * 0.35) + icon_space + text_w + int(btn_h * 0.3)

        px = int(SCREEN_SIZE[0] * x) - btn_w // 2
        py = int(SCREEN_SIZE[1] * y) - btn_h // 2

        self.gemini_buttons.append({
            'x': px, 'y': py, 'w': btn_w, 'h': btn_h,
            'text': text, 'icon': icon,
            'completion': completion,
        })
        self.update()
        return (px, py), (px + btn_w, py + btn_h)

    def _paint_tab_button(self, painter: QPainter, tab: dict):
        """Render a small tab button with solid bg, optional text/icon, and radial bloom."""
        import math
        x, y, w, h = tab['x'], tab['y'], tab['w'], tab['h']
        completion = tab.get('completion', 0.0)
        bg = tab.get('bg', (60, 120, 200))
        radius = h // 2

        btn_rect = QRectF(x, y, w, h)
        btn_path = QPainterPath()
        btn_path.addRoundedRect(btn_rect, radius, radius)

        # solid bg
        r, g, b = bg
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(r, g, b)))
        painter.drawPath(btn_path)

        # radial bloom
        if completion > 0.0:
            painter.save()
            painter.setClipPath(btn_path)
            cx = x + w / 2
            cy = y + h / 2
            max_r = math.hypot(w / 2, h / 2)
            br = max_r * min(completion, 1.0)
            bloom = QRadialGradient(cx, cy, br)
            bloom.setColorAt(0.0, QColor(255, 255, 255, 100))
            bloom.setColorAt(0.6, QColor(255, 255, 255, 50))
            bloom.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(bloom))
            painter.drawEllipse(QRectF(cx - br, cy - br, br * 2, br * 2))
            painter.restore()

        # subtle border
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(btn_path)

        # icon (centered)
        if tab.get('icon'):
            icon_size = int(h * 0.55)
            if tab.get('text'):
                # icon left, text right
                ix = x + int(h * 0.3)
            else:
                # icon centered
                ix = x + (w - icon_size) / 2
            iy = y + (h - icon_size) / 2
            painter.drawPixmap(int(ix), int(iy), icon_size, icon_size, tab['icon'])

        # text
        if tab.get('text'):
            font = QFont('Arial', max(int(h * 0.30), 10))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            if tab.get('icon'):
                icon_size = int(h * 0.55)
                tx = x + int(h * 0.3) + icon_size + int(h * 0.15)
                text_rect = QRectF(tx, y, w - (tx - x) - int(h * 0.2), h)
                align = Qt.AlignmentFlag.AlignVCenter
            else:
                text_rect = btn_rect
                align = Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter
            painter.drawText(text_rect, align, tab['text'])

    def draw_tab_button(self, cx: int, cy: int, w: int, h: int,
                        text: str | None = None, icon: QPixmap | None = None,
                        bg: tuple = (60, 120, 200),
                        completion: float = 0.0):
        """Add a tab button centered at (cx, cy) in screen pixels.

        Returns:
            (tl, br) bounding box in screen pixels
        """
        px = cx - w // 2
        py = cy - h // 2
        self.tab_buttons.append({
            'x': px, 'y': py, 'w': w, 'h': h,
            'text': text, 'icon': icon, 'bg': bg,
            'completion': completion,
        })
        self.update()
        return (px, py), (px + w, py + h)

    def draw_status(self, text: str, color: tuple = (200, 120, 0), x: float = 0.775, y: float = 0.05):
        px = int(SCREEN_SIZE[0] * x)
        py = int(SCREEN_SIZE[1] * y)
        self.add_small_text_box(px, py, text, color=color, font_size=10)

    def draw_transaction_table(self, transactions: list[dict], x: float = 0.10, y: float = 0.30,
                               hover_zones: dict | None = None):
        """Draw extracted transactions as a table on the overlay.

        Args:
            transactions: list of dicts with keys: date, company, amount
            x: left edge as fraction of screen width
            y: top edge as fraction of screen height
            hover_zones: dict of (row, col) -> completion float for hover highlights.
                         col -1 = X button. cols 0/1/2 = date/company/amount.

        Returns:
            list of hitboxes: [(x1, y1, x2, y2, row_idx, col_idx), ...]
            col_idx -1 = X delete button, 0 = date, 1 = company, 2 = amount
        """
        if not transactions:
            return []

        if hover_zones is None:
            hover_zones = {}

        px = int(SCREEN_SIZE[0] * x)
        py = int(SCREEN_SIZE[1] * y)
        x_btn_w = 25  # width of X button column
        col_widths = [120, 180, 80]  # date, company, amount
        row_h = 35
        header_color = (40, 40, 40)
        row_color = (60, 60, 60)
        hitboxes = []

        # Header row (offset right to account for X column)
        headers = ["Date", "Company", "Amount"]
        cx = px + x_btn_w
        for j, hdr in enumerate(headers):
            self.add_small_text_box(cx, py, hdr, color=header_color, font_size=10)
            cx += col_widths[j]

        # Data rows
        keys = ["date", "company", "amount"]
        for i, txn in enumerate(transactions):
            ry = py + (i + 1) * row_h

            # X delete button
            x_compl = hover_zones.get((i, -1), 0.0)
            x_color = (200, 50, 50) if x_compl > 0 else (150, 150, 150)
            self.add_small_text_box(px, ry, "X", color=x_color, font_size=9)
            x_w, x_h = self._measure_text_box("X", 9)
            if x_compl > 0:
                prog_x = px + int(x_w * x_compl)
                self.add_rectangle((px, ry), (prog_x, ry + x_h), True, (200, 50, 50))
            hitboxes.append((px, ry, px + x_w, ry + x_h, i, -1))

            # Data cells
            cx = px + x_btn_w
            vals = [
                txn.get("date") or "—",
                txn.get("company") or "—",
                txn.get("amount") or "—",
                ]
            for j, val in enumerate(vals):
                cell_compl = hover_zones.get((i, j), 0.0)
                cell_color = (30, 90, 160) if cell_compl > 0 else row_color
                self.add_small_text_box(cx, ry, val, color=cell_color, font_size=9)
                cw, ch = self._measure_text_box(val, 9)
                if cell_compl > 0:
                    prog_x = cx + int(cw * cell_compl)
                    self.add_rectangle((cx, ry), (prog_x, ry + ch), True, (30, 90, 160))
                hitboxes.append((cx, ry, cx + cw, ry + ch, i, j))
                cx += col_widths[j]

        return hitboxes

    def draw_loading_icon(self):
        #draws an icon showing prompt currently loading / in progress
        #this should sit right under the gemini button
        return

    def draw_updater_icon(self, icon_status: str):
        #draws an icon showing the status of the continuous updater

        return

    @staticmethod
    def _font(size: int, bold: bool = False) -> QFont:
        font = QFont('Arial', size)
        font.setBold(bold)
        return font

    @classmethod
    def _wrapped_height(cls, text: str, w: int, size: int, bold: bool = False) -> int:
        fm = QFontMetrics(cls._font(size, bold))
        return fm.boundingRect(QRect(0, 0, w, 10000), Qt.TextFlag.TextWordWrap.value, text).height()

    def _paint_panel(self, painter: QPainter, d: dict):
        radius = d.get('radius', 12)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.setBrush(QBrush(QColor(18, 18, 26, 230)))
        painter.drawRoundedRect(QRectF(d['x'], d['y'], d['w'], d['h']), radius, radius)

    def _paint_label(self, painter: QPainter, d: dict):
        painter.setFont(self._font(d['size'], d.get('bold', False)))
        painter.setPen(QColor(*d.get('color', (255, 255, 255))))
        align = Qt.AlignmentFlag.AlignVCenter if d.get('vcenter') else Qt.AlignmentFlag.AlignTop
        painter.drawText(QRectF(d['x'], d['y'], d['w'], d['h']),
                         Qt.TextFlag.TextWordWrap.value | align.value, d['text'])

    def _paint_row(self, painter: QPainter, d: dict):
        """A full-width suggestion row; hover-fill sweeps left → right."""
        x, y, w, h = d['x'], d['y'], d['w'], d['h']
        path = QPainterPath()
        path.addRoundedRect(QRectF(x, y, w, h), 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(255, 255, 255, 22)))
        painter.drawPath(path)

        if d['completion'] > 0.0:
            painter.save()
            painter.setClipPath(path)
            grad = QLinearGradient(x, y, x + w, y)
            grad.setColorAt(0.0, QColor(55, 115, 230, 170))
            grad.setColorAt(0.5, QColor(150, 70, 220, 170))
            grad.setColorAt(1.0, QColor(235, 90, 140, 170))
            painter.setBrush(QBrush(grad))
            painter.drawRect(QRectF(x, y, w * min(d['completion'], 1.0), h))
            painter.restore()

        font = self._font(11, True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        text = QFontMetrics(font).elidedText(d['text'], Qt.TextElideMode.ElideRight, w - 24)
        painter.drawText(QRectF(x + 12, y, w - 24, h), Qt.AlignmentFlag.AlignVCenter, text)

    def _paint_spinner(self, painter: QPainter, d: dict):
        cx, cy, r = d['cx'], d['cy'], d['r']
        start = int(time.monotonic() * 360) % 360
        pen = QPen(QColor(180, 140, 255), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(QRectF(cx - r, cy - r, 2 * r, 2 * r), -start * 16, 270 * 16)

    def _paint_icon_button(self, painter: QPainter, d: dict):
        """Round Gemini-logo button: Gemini-gradient disc, bright rim, radial bloom on hover-fill."""
        x, y, size = d['x'], d['y'], d['size']
        rect = QRectF(x, y, size, size)
        path = QPainterPath()
        path.addEllipse(rect)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())  # same stops as the old pill
        grad.setColorAt(0.0, QColor(55, 115, 230))
        grad.setColorAt(0.35, QColor(120, 75, 220))
        grad.setColorAt(0.65, QColor(190, 60, 220))
        grad.setColorAt(1.0, QColor(235, 90, 140))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)

        if d['completion'] > 0.0:
            painter.save()
            painter.setClipPath(path)
            cx, cy = x + size / 2, y + size / 2
            r = math.hypot(size / 2, size / 2) * min(d['completion'], 1.0)
            bloom = QRadialGradient(cx, cy, r)
            bloom.setColorAt(0.0, QColor(255, 255, 255, 90))
            bloom.setColorAt(0.6, QColor(200, 170, 255, 70))
            bloom.setColorAt(1.0, QColor(200, 170, 255, 0))
            painter.setBrush(QBrush(bloom))
            painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
            painter.restore()

        rim = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim.setColorAt(0.0, QColor(100, 160, 255, 160))
        rim.setColorAt(0.5, QColor(180, 120, 255, 160))
        rim.setColorAt(1.0, QColor(255, 120, 180, 160))
        painter.setPen(QPen(QBrush(rim), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect.adjusted(1, 1, -1, -1))

        if self.gemini_icon:
            icon = int(size * 0.58)
            painter.drawPixmap(int(x + (size - icon) / 2), int(y + (size - icon) / 2), icon, icon, self.gemini_icon)

    def _paint_bubble(self, painter: QPainter, d: dict):
        """Glossy filled bubble, no border: colour body lit from the top-left, a soft
        sheen at the rim, a specular highlight. Hover-fill swells and brightens it
        until it pops."""
        c = min(d['completion'], 1.0)
        size = d['size'] * (1 + 0.08 * c)                 # swells as it fills
        x = d['x'] - (size - d['size']) / 2
        y = d['y'] - (size - d['size']) / 2
        r = size / 2
        cx, cy = x + r, y + r
        rgb = d['color']

        def mix(f):  # f > 0 → toward white, f < 0 → toward black
            return QColor(*[int(v + (255 - v) * f) if f > 0 else int(v * (1 + f)) for v in rgb])

        painter.setPen(Qt.PenStyle.NoPen)
        body = QRadialGradient(cx - 0.3 * r, cy - 0.35 * r, 1.25 * r)
        body.setColorAt(0.0, mix(0.45 + 0.3 * c))
        body.setColorAt(0.55, mix(0.08 * c))
        body.setColorAt(1.0, mix(-0.35))
        painter.setBrush(QBrush(body))
        painter.drawEllipse(QRectF(x, y, size, size))

        sheen = QRadialGradient(cx, cy, r)                 # bright film at the edge, no stroke
        sheen.setColorAt(0.78, QColor(255, 255, 255, 0))
        sheen.setColorAt(0.97, QColor(255, 255, 255, 70))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(sheen))
        painter.drawEllipse(QRectF(x, y, size, size))

        painter.save()                                     # specular highlight, tilted
        painter.translate(x + 0.32 * size, y + 0.22 * size)
        painter.rotate(-35)
        hw, hh = 0.36 * size, 0.2 * size
        spec = QRadialGradient(0, 0, hw / 2)
        spec.setColorAt(0.0, QColor(255, 255, 255, 210))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(spec))
        painter.drawEllipse(QRectF(-hw / 2, -hh / 2, hw, hh))
        painter.restore()
        painter.setBrush(QBrush(QColor(255, 255, 255, 90)))  # small glint, lower right
        painter.drawEllipse(QRectF(x + 0.7 * size, y + 0.7 * size, 0.08 * size, 0.08 * size))

        inset = size * 0.14
        rect = QRectF(x + inset, y + size * 0.22, size - 2 * inset, size * 0.56)
        flags = (Qt.TextFlag.TextWordWrap.value | Qt.AlignmentFlag.AlignHCenter.value
                 | Qt.AlignmentFlag.AlignVCenter.value)
        painter.setFont(self._font(10, True))
        painter.setPen(QColor(0, 0, 0, 120))               # shadow keeps white text readable on light hues
        painter.drawText(rect.translated(0, 1), flags, d['text'])
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, flags, d['text'])

    def _paint_card(self, painter: QPainter, d: dict):
        """Popped tip: headline + detail on a panel with the gradient rim."""
        x, y, w, h = d['x'], d['y'], d['w'], d['h']
        rect = QRectF(x, y, w, h)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(18, 18, 26, 240)))
        painter.drawRoundedRect(rect, 12, 12)
        rim = QLinearGradient(x, y, x + w, y + h)
        rim.setColorAt(0.0, QColor(100, 160, 255, 190))
        rim.setColorAt(0.5, QColor(180, 120, 255, 190))
        rim.setColorAt(1.0, QColor(255, 120, 180, 190))
        painter.setPen(QPen(QBrush(rim), 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.75, 0.75, -0.75, -0.75), 12, 12)
        inner = w - 2 * PANEL_PAD
        wrap = Qt.TextFlag.TextWordWrap.value
        painter.setFont(self._font(11, True))
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(QRectF(x + PANEL_PAD, y + PANEL_PAD, inner, d['head_h']), wrap, d['headline'])
        painter.setFont(self._font(10))
        painter.setPen(QColor(220, 220, 232))
        painter.drawText(QRectF(x + PANEL_PAD, y + PANEL_PAD + d['head_h'] + 6, inner, h), wrap, d['detail'])

    def _panel_button(self, name: str, cx: int, cy: int, w: int = 26,
                      text: str | None = None, icon: QPixmap | None = None) -> tuple:
        tl, br = self.draw_tab_button(cx, cy, w, 26, text=text, icon=icon, bg=(70, 70, 88),
                                      completion=self.fills.get(name, 0.0))
        return (*tl, *br)

    def render(self, model) -> dict | None:
        """Draw the current frame from the view's interaction state + model data.

        Closed: just the round Gemini-logo button. Open: a panel with the logo in its
        top-left corner (re-hover it to close); what it shows depends on the model —
            game.suggestions is None          → analyzing (spinner + Cancel)
            game.question is None             → suggestion list
            game.question, game.answer None   → answering (question + spinner + Cancel)
            game.question, game.answer        → answer
        While open, tip bubbles float beside the panel; a popped tip (game.open_tip)
        shows as a detail card where its bubble was.
        Returns hit-test geometry: {'main': logo box, 'buttons': {name: box}, 'rows': [box],
        'tips': {tip id: box}, 'card': box | None}, or None if there is nothing to draw yet.
        """
        self.clearCanvas()
        if not self.button_pos:
            return None
        game = model.game
        geom = {'main': None, 'buttons': {}, 'rows': [], 'tips': {}, 'card': None}
        self._render_state_toast(game)

        cx = int(SCREEN_SIZE[0] * self.button_pos['x'])
        cy = int(SCREEN_SIZE[1] * self.button_pos['y'])
        ix, iy = cx - ICON_SIZE // 2, cy - ICON_SIZE // 2
        geom['main'] = (ix, iy, ix + ICON_SIZE, iy + ICON_SIZE)

        if self.state == 'open':
            px, py, ph = self._render_panel(game, ix, iy, geom)
            self._render_tips(game, px, py, ph, geom)
        else:
            self.tip_slots = {}
            self.icon_buttons.append({'x': ix, 'y': iy, 'size': ICON_SIZE,
                                      'completion': self.fills.get('open', 0.0)})
        return geom

    def _render_state_toast(self, game):
        """Persistent top-left box: the game state the client reads from the Riot API."""
        lines = game.state_lines()
        if not lines:
            return
        fm_head, fm = QFontMetrics(self._font(10, True)), QFontMetrics(self._font(10))
        w = max([fm_head.horizontalAdvance(lines[0])] + [fm.horizontalAdvance(l) for l in lines[1:]])
        w += 2 * TOAST_PAD
        x, y = TOAST_MARGIN, TOAST_MARGIN
        self.panels.append({'x': x, 'y': y, 'w': w, 'h': len(lines) * TOAST_LINE_H + 2 * TOAST_PAD - 2,
                            'radius': 8})
        for i, line in enumerate(lines):
            self.labels.append({'x': x + TOAST_PAD, 'y': y + TOAST_PAD + i * TOAST_LINE_H, 'w': w, 'h': TOAST_LINE_H,
                                'text': line, 'size': 10, 'bold': i == 0,
                                'color': (170, 170, 190) if i == 0 else (235, 235, 245)})

    def _render_panel(self, game, ix: int, iy: int, geom: dict):
        """Panel opening right/down from the logo, which sits in its top-left
        corner: analyzing, suggestions, a pending question, or the answer."""
        inner = PANEL_W - 2 * PANEL_PAD
        if game.suggestions is None:
            mode, title, body_h = 'analyzing', 'Analyzing…', 0
        elif game.question is None:
            mode, title = 'suggest', 'Ask about…'
            # thin rule before the pinned questions, if there are situational ones above them
            split = len(game.suggestions) - len(game.pinned_questions)
            split = split if 0 < split < len(game.suggestions) else None
            body_h = max(len(game.suggestions) * (ROW_H + ROW_GAP) - ROW_GAP, 0) + (DIVIDER_GAP if split else 0)
        else:
            mode = 'answering' if game.answer is None else 'answer'
            title = 'Coach'
            q_h = self._wrapped_height(game.question, inner, 12, True)
            a_h = self._wrapped_height(game.answer, inner, 11) if mode == 'answer' else 20
            body_h = q_h + 8 + a_h
        header_h = ICON_INSET + ICON_SIZE
        h = header_h + (8 + body_h if body_h else ICON_INSET) + (PANEL_PAD if body_h else 0)

        # logo stays put; the panel is only nudged if it would run off-screen
        x = max(10, min(ix - ICON_INSET, SCREEN_SIZE[0] - PANEL_W - 10))
        y = max(10, min(iy - ICON_INSET, SCREEN_SIZE[1] - h - 10))
        self.panels.append({'x': x, 'y': y, 'w': PANEL_W, 'h': h})
        lx, ly = x + ICON_INSET, y + ICON_INSET
        self.icon_buttons.append({'x': lx, 'y': ly, 'size': ICON_SIZE, 'completion': self.fills.get('close', 0.0)})
        geom['main'] = (lx, ly, lx + ICON_SIZE, ly + ICON_SIZE)  # re-hover the logo to close

        # header: [logo] title ............ buttons
        hcy = y + ICON_INSET + ICON_SIZE // 2
        tx = x + ICON_INSET + ICON_SIZE + 10
        if mode == 'analyzing':
            self.spinners.append({'cx': tx + 8, 'cy': hcy, 'r': 7})
            tx += 24
        self.labels.append({'x': tx, 'y': hcy - 13, 'w': x + PANEL_W - tx, 'h': 26, 'text': title,
                            'size': 12 if mode == 'analyzing' else 10, 'bold': True,
                            'color': (255, 255, 255) if mode == 'analyzing' else (170, 170, 190),
                            'vcenter': True})
        buttons = []
        if mode == 'suggest':
            buttons.append(('prompt', 26, None if self.notebook_icon else '✎', self.notebook_icon))
        elif mode in ('answering', 'analyzing'):
            buttons.append(('cancel', 70, 'Cancel', None))
        else:  # answer is in → move on to the next question
            buttons.append(('next', 26, '→', None))
        bx = x + PANEL_W - PANEL_PAD
        for name, w, text, icon in buttons:
            bx -= w
            geom['buttons'][name] = self._panel_button(name, bx + w // 2, hcy, w=w, text=text, icon=icon)
            bx -= 6

        top = y + header_h + 8
        if mode == 'analyzing':
            return x, y, h
        if mode == 'suggest':
            for i, q in enumerate(game.suggestions):
                ry = top + i * (ROW_H + ROW_GAP) + (DIVIDER_GAP if split and i >= split else 0)
                if i == split:
                    ly = ry - ROW_GAP // 2 - DIVIDER_GAP // 2
                    self.dividers.append((x + PANEL_PAD + 8, ly, x + PANEL_W - PANEL_PAD - 8))
                self.rows.append({'x': x + PANEL_PAD, 'y': ry, 'w': inner, 'h': ROW_H, 'text': q,
                                  'completion': self.fills.get(f'suggest:{i}', 0.0)})
                geom['rows'].append((x + PANEL_PAD, ry, x + PANEL_PAD + inner, ry + ROW_H))
            return x, y, h

        self.labels.append({'x': x + PANEL_PAD, 'y': top, 'w': inner, 'h': q_h,
                            'text': game.question, 'size': 12, 'bold': True})
        ay = top + q_h + 8
        if mode == 'answering':
            self.spinners.append({'cx': x + PANEL_PAD + 9, 'cy': ay + 10, 'r': 7})
            self.labels.append({'x': x + PANEL_PAD + 26, 'y': ay, 'w': inner - 26, 'h': 20,
                                'text': 'Thinking…', 'size': 11, 'color': (180, 180, 195), 'vcenter': True})
        else:
            self.labels.append({'x': x + PANEL_PAD, 'y': ay, 'w': inner, 'h': a_h,
                                'text': game.answer, 'size': 11})
        return x, y, h

    def _render_tips(self, game, px: int, py: int, ph: int, geom: dict):
        """Tip bubbles stacked beside the panel (right side, or left if no room),
        bobbing gently. Each tip keeps its slot while it lives; new tips fill free
        slots in priority order. The popped tip's card grows from its slot and
        hides the bubbles until it closes."""
        live = {t.id: t for t in game.tips_on_offer()}
        self.tip_slots = {tid: slot for tid, slot in self.tip_slots.items() if tid in live}
        free = [s for s in range(MAX_BUBBLES) if s not in self.tip_slots.values()]
        for tid in live:
            if not free:
                break
            if tid not in self.tip_slots:
                self.tip_slots[tid] = free.pop(0)

        # side is chosen with room for a card too, so bubbles don't jump sides when one pops
        widest = max(max(dx for dx, _ in BUBBLE_SLOTS) + BUBBLE_D, CARD_W)
        right = px + PANEL_W + BUBBLE_GAP + widest <= SCREEN_SIZE[0] - 10
        t = time.monotonic()

        def slot_y(slot):
            return py + BUBBLE_SLOTS[slot][1]

        # while a card is open the bubbles step aside (they'd sit under it and pop by accident)
        for tid, slot in ([] if game.open_tip else self.tip_slots.items()):
            dx = BUBBLE_SLOTS[slot][0]
            bx = px + PANEL_W + BUBBLE_GAP + dx if right else px - BUBBLE_GAP - BUBBLE_D - dx
            bx = int(bx + 3 * math.sin(t * 1.3 + slot * 2.1))               # drift
            by = int(slot_y(slot) + 5 * math.sin(t * 2.0 + slot * 1.7))     # float
            self.bubbles.append({'x': bx, 'y': by, 'size': BUBBLE_D, 'text': live[tid].headline,
                                 'color': BUBBLE_COLORS.get(live[tid].category, BUBBLE_COLORS['macro']),
                                 'completion': self.fills.get(f'tip:{tid}', 0.0)})
            geom['tips'][tid] = (bx, by, bx + BUBBLE_D, by + BUBBLE_D)

        tip = game.open_tip
        if tip:
            inner = CARD_W - 2 * PANEL_PAD
            head_h = self._wrapped_height(tip.headline, inner, 11, True)
            body_h = self._wrapped_height(tip.detail, inner, 10)
            h = PANEL_PAD + head_h + 6 + body_h + PANEL_PAD
            cx = px + PANEL_W + BUBBLE_GAP if right else max(10, px - BUBBLE_GAP - CARD_W)
            cy = max(10, min(slot_y(self.card_slot), SCREEN_SIZE[1] - h - 10))
            self.cards.append({'x': cx, 'y': cy, 'w': CARD_W, 'h': h, 'headline': tip.headline,
                               'detail': tip.detail, 'head_h': head_h})
            geom['card'] = (cx, cy, cx + CARD_W, cy + h)

    def advance(self, hover: dict) -> str | None:
        """Advance hover-fills and the interaction state machine one frame.

        State: idle → open → cooldown → idle
            idle:     pill only; hover-filling it opens the panel
            open:     panel targets (buttons / suggestion rows) fill on hover; re-hovering
                      the logo (once the cursor has left it) closes
            cooldown: after close, wait for the cursor to leave the logo

        Args:
            hover: {'main': bool, 'buttons': {name: bool}, 'rows': [bool]} — what the
                   cursor is over this frame (from the controller's hit-test).
        Returns:
            The target that just finished filling — 'open', 'close', 'cancel',
            'prompt', 'next' or 'suggest:<i>' — or None.
        """
        if self.state == 'cooldown':
            self.fills = {}
            if not hover['main']:
                self.state = 'idle'
            return None

        if self.state == 'idle':
            targets = {'open': hover['main']}
        else:
            if not hover['main']:
                self._close_armed = True
            targets = {'close': hover['main'] and self._close_armed, **hover['buttons']}
            targets.update({f'suggest:{i}': over for i, over in enumerate(hover['rows'])})
            targets.update({f'tip:{tid}': over for tid, over in hover['tips'].items()})

        press = None
        fills = {}
        for name, over in targets.items():
            step = BUBBLE_FILL_STEP if name.startswith('tip:') else FILL_STEP
            fill = self.fills.get(name, 0.0) + step if over else 0.0
            if fill >= 0.98:
                press, fill = name, 0.0
            fills[name] = fill
        self.fills = fills  # targets that vanished this frame drop their fill

        if press == 'open':
            self.state = 'open'
            self._close_armed = False
        elif press == 'close':
            self.state = 'cooldown'
        elif press and press.startswith('tip:'):
            self.card_slot = self.tip_slots.pop(int(press.split(':')[1]), 0)
            self._card_away = 0   # cursor starts on the card (it grows from the bubble)
        elif press is None and self.state == 'open' and self.cards:
            # detail card: close once the cursor has been off it for a moment
            self._card_away = 0 if hover['card'] else self._card_away + 1
            if self._card_away >= CARD_LEAVE_FRAMES:
                press = 'tip_close'
        return press

    def clearCanvas(self):
        """Clear all shapes from the canvas"""
        self.rectangles.clear()
        self.circles.clear()
        self.arrows.clear()
        self.text_boxes.clear()
        self.gemini_buttons.clear()
        self.tab_buttons.clear()
        self.panels.clear()
        self.labels.clear()
        self.rows.clear()
        self.spinners.clear()
        self.icon_buttons.clear()
        self.bubbles.clear()
        self.cards.clear()
        self.dividers.clear()
        self.update()  # Trigger repaint

    def hideCanvas(self):
        """Hide the canvas window"""
        self.hide()  # Hide the window

    def showCanvas(self):
        """Show the canvas window"""
        self.show()  # Show the window

    def cvToQt(self, tl:tuple[int,int], br:tuple[int,int], img_w:int, img_h:int)->tuple[tuple[int,int],tuple[int,int]]:
        return (
            int((tl[0] / img_w) * SCREEN_SIZE[0]),
            int((tl[1] / img_h) * SCREEN_SIZE[1])
        ), (
            int((br[0] / img_w) * SCREEN_SIZE[0]),
            int((br[1] / img_h) * SCREEN_SIZE[1])
        )
