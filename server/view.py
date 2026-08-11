"""View layer — overlay rendering and input widgets.

Renders application state (CoachModel) onto a transparent, always-on-top
overlay, plus the auxiliary region-picker and prompt widgets. Pure
presentation: holds no game logic and never mutates the model.
"""
import os

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget,
                             QLabel, QLineEdit, QPushButton, QVBoxLayout)
from PyQt6.QtCore import Qt, QRect, QRectF, QEventLoop
from PyQt6.QtGui import (QPainter, QPen, QColor, QBrush, QFont,
                         QLinearGradient, QRadialGradient, QPainterPath, QPixmap)

from server.utils import SCREEN_SIZE, app


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

        # ── interaction state (the view owns button positions + animations) ──
        # idle → filling → unfurled → closing → cooldown → idle
        self.button_pos = None
        self.state = 'idle'
        self.has_left = False  # cursor left all buttons since unfurl
        self.compl = 0.0  # main-button hover-fill
        self.left_compls = [0.0, 0.0, 0.0, 0.0, 0.0]
        self.right_compl = 0.0

        # load notebook icon once
        icon_path = os.path.join(os.path.dirname(__file__), 'notebook_icon.png')
        self.notebook_icon = QPixmap(icon_path) if os.path.exists(icon_path) else None

        self.resize(SCREEN_SIZE[0], SCREEN_SIZE[1])
        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)


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

    def render(self, model) -> dict | None:
        """Draw the current frame from the view's own interaction state.

        Draws the main button (always) and, when unfurled/closing, the side
        tabs — reading fill/state from self and the tab labels (quick_actions)
        from the model. Returns the on-screen geometry the controller needs for
        hit-testing, or None if there is nothing to draw yet.
        """
        self.clearCanvas()
        if not self.button_pos:
            return None

        # always draw main button
        (bx1, by1), (bx2, by2) = self.draw_gemini_button(
            "Ask Coach!!", x=self.button_pos['x'], y=self.button_pos['y'],
            completion=self.compl,
        )

        # checkpoint status — re-emitted every frame since clearCanvas() wiped it
        if model.game.status:
            self.draw_status(model.game.status)

        left_boxes = []
        right_box = None

        if self.state in ('unfurled', 'closing'):
            main_w = bx2 - bx1
            main_h = by2 - by1
            main_cy = (by1 + by2) // 2

            # tab sizing
            tab_h = int(main_h * 0.82)
            tab_w = int(main_w * 0.65)
            tab_w_right = tab_h  # square for icon-only
            gap = 10
            tab_gap = 5

            frozen = self.state == 'closing'

            # ── left action tabs (fanned around the left perimeter) ──
            # 5 fixed slots on a left-facing arc: the middle slot bulges out
            # furthest, top/bottom sit near the button edge. Actions fill the
            # slots top-down, one by one.
            import math
            n_slots = len(self.left_compls)
            total_left_h = n_slots * tab_h + (n_slots - 1) * tab_gap
            left_top = main_cy - total_left_h // 2
            left_base_cx = bx1 - gap - tab_w // 2  # x of the top/bottom slots
            bulge = int(tab_w * 0.9)               # leftward push at the middle slot

            for i in range(min(len(model.game.quick_actions), n_slots)):
                frac = i / (n_slots - 1)           # 0 (top) .. 1 (bottom)
                ty = left_top + i * (tab_h + tab_gap) + tab_h // 2
                tx = left_base_cx - int(bulge * math.sin(frac * math.pi))
                box = self.draw_tab_button(
                    tx, ty, tab_w, tab_h,
                    text=model.game.quick_actions[i], bg=(50, 100, 190),
                    completion=0.0 if frozen else self.left_compls[i],
                )
                left_boxes.append((*box[0], *box[1]))

            # ── right tab ──
            right_cx = bx2 + gap + tab_w_right // 2
            rbox = self.draw_tab_button(
                right_cx, main_cy, tab_w_right, tab_h,
                icon=self.notebook_icon, bg=(180, 180, 180),
                completion=0.0 if frozen else self.right_compl,
            )
            right_box = (*rbox[0], *rbox[1])

        return {'main': (bx1, by1, bx2, by2), 'left': left_boxes, 'right': right_box}

    def advance(self, hover: dict) -> str | None:
        """Advance button-fill animations and the interaction state machine one frame.

        State: idle → filling → unfurled → closing → cooldown → idle
            idle:     main button only
            filling:  hovering main button, bloom rising
            unfurled: side tabs visible
            closing:  re-hover bloom on main button, tabs frozen, completes → cooldown
            cooldown: wait for cursor to leave main button before allowing re-trigger

        Args:
            hover: {'main': bool, 'left': list[bool], 'right': bool} — which buttons
                   the cursor is over this frame (from the controller's hit-test).
        Returns:
            The id of a button that just crossed its activation threshold this frame
            ('left:0'..'left:2' or 'right'), or None. Main-button open/close are
            internal transitions and report no press.
        """
        on_main = hover['main']
        press = None

        # ── idle ──────────────────────────────────────────────
        if self.state == 'idle':
            if on_main:
                self.state = 'filling'
                self.compl = 0.019

        # ── filling ───────────────────────────────────────────
        elif self.state == 'filling':
            if on_main:
                if int(self.compl * 100) / 100 >= 0.98:
                    self.state = 'unfurled'
                    self.compl = 1.0
                    self.has_left = False
                elif self.compl <= 1.0:
                    self.compl += 0.019
            else:
                self.state = 'idle'
                self.compl = 0.0

        # ── unfurled ──────────────────────────────────────────
        elif self.state == 'unfurled':
            self.compl = 0.0

            # ── hover logic ──
            on_any = on_main
            for i, over in enumerate(hover['left']):
                if over:
                    on_any = True
                    if int(self.left_compls[i] * 100) / 100 >= 0.98:
                        press = f'left:{i}'
                        self.left_compls[i] = 0.0
                    elif self.left_compls[i] <= 1.0:
                        self.left_compls[i] += 0.019
                else:
                    self.left_compls[i] = 0.0

            if hover['right']:
                on_any = True
                if int(self.right_compl * 100) / 100 >= 0.98:
                    press = 'right'
                    self.right_compl = 0.0
                elif self.right_compl <= 1.0:
                    self.right_compl += 0.019
            else:
                self.right_compl = 0.0

            if not on_any:
                self.has_left = True

            # re-hover on OG after leaving → start close animation
            if self.has_left and on_main:
                self.state = 'closing'
                self.compl = 0.0
                self.left_compls = [0.0, 0.0, 0.0, 0.0, 0.0]
                self.right_compl = 0.0

        # ── closing ──────────────────────────────────────────
        elif self.state == 'closing':
            # bloom on main button to confirm close
            if on_main:
                if int(self.compl * 100) / 100 >= 0.98:
                    self.state = 'cooldown'
                    self.compl = 0.0
                    self.has_left = False
                elif self.compl <= 1.0:
                    self.compl += 0.019
            else:
                # moved off main → cancel close, back to unfurled
                self.state = 'unfurled'
                self.compl = 1.0

        # ── cooldown ─────────────────────────────────────────
        elif self.state == 'cooldown':
            # wait for cursor to leave main button before re-enabling
            if not on_main:
                self.state = 'idle'

        return press

    def clearCanvas(self):
        """Clear all shapes from the canvas"""
        self.rectangles.clear()
        self.circles.clear()
        self.arrows.clear()
        self.text_boxes.clear()
        self.gemini_buttons.clear()
        self.tab_buttons.clear()
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
