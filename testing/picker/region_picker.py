"""
Screen Region Picker

Displays a transparent overlay and lets the user click-drag to select a region.
Returns the selected region as screen coordinates dict: {left, top, width, height}.
"""

import tkinter as tk
from mss import mss


class ScreenRegionPicker:
    def __init__(self):
        self.root = None
        self.overlay = None
        self.canvas = None
        self.text_label = None
        self.is_selecting = False
        self.start_point = None
        self.current_point = None
        self.selected_region = None

        sct = mss()
        self.screen_width = sct.monitors[0]['width']
        self.screen_height = sct.monitors[0]['height']

    def _create_overlay(self):
        self.overlay = tk.Toplevel()
        self.overlay.overrideredirect(True)
        self.overlay.attributes('-alpha', 0.3)
        self.overlay.configure(bg='white')
        self.overlay.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        self.overlay.lift()
        self.overlay.wm_attributes("-topmost", True)

        self.overlay.bind("<Button-1>", self._on_mouse_down)
        self.overlay.bind("<B1-Motion>", self._on_mouse_drag)
        self.overlay.bind("<ButtonRelease-1>", self._on_mouse_up)

        self._draw_text("Click and drag to select a region. ESC to cancel.")
        self._keep_on_top()

    def _draw_text(self, text: str):
        """Draw text near the top-center of the screen with a white-filled black-bordered box."""
        self.text_label = tk.Label(
            self.overlay,
            text=text,
            bg='white',
            fg='black',
            font=('Arial', 13, 'bold'),
            padx=12,
            pady=8,
            relief='solid',
            bd=1,
        )
        self.text_label.place(anchor='n', x=self.screen_width // 2, y=40)

    def _keep_on_top(self):
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.lift()
            self.overlay.after(100, self._keep_on_top)

    def _on_mouse_down(self, event):
        self.is_selecting = True
        self.start_point = (event.x, event.y)
        self.current_point = (event.x, event.y)

        if not self.canvas:
            self.canvas = tk.Canvas(
                self.overlay,
                highlightthickness=0,
                bg='white',
                bd=0
            )
            self.canvas.place(x=0, y=0, width=self.screen_width, height=self.screen_height)
            if self.text_label:
                self.text_label.lift()

        self._draw_rect()

    def _on_mouse_drag(self, event):
        if self.is_selecting:
            self.current_point = (event.x, event.y)
            self._draw_rect()

    def _on_mouse_up(self, event):
        if self.is_selecting:
            self.is_selecting = False
            self.current_point = (event.x, event.y)

            x1, y1 = self.start_point
            x2, y2 = self.current_point
            self.selected_region = {
                'left': min(x1, x2),
                'top': min(y1, y2),
                'width': abs(x2 - x1),
                'height': abs(y2 - y1),
            }

            self._cleanup()
            self.root.quit()

    def _draw_rect(self):
        if self.canvas:
            self.canvas.delete("sel")
            x1, y1 = self.start_point
            x2, y2 = self.current_point
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline='red', width=2, fill='red', stipple='gray50',
                tags="sel"
            )

    def _cleanup(self):
        if self.overlay:
            self.overlay.destroy()
        self.overlay = None
        self.canvas = None

    def pick(self) -> dict | None:
        """Show the overlay and block until the user selects a region.
        Returns {left, top, width, height} in screen coordinates, or None if cancelled.
        """
        self.root = tk.Tk()
        self.root.withdraw()

        self._create_overlay()

        def on_escape(event):
            self._cleanup()
            self.root.quit()

        self.root.bind('<Escape>', on_escape)

        try:
            self.root.mainloop()
        except tk.TclError:
            pass

        return self.selected_region




if __name__ == "__main__":
    region = ScreenRegionPicker().pick()
    if region:
        print(f"Selected: {region}")
    else:
        print("Cancelled.")
