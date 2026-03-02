from transparent_overlay import Overlay
import time

# Initialize a persistent, click-through overlay
with Overlay() as overlay:
    # Draw text at (x, y)
    overlay.draw_text(100, 100, "System Monitor: Active", color=(0, 255, 0, 255), font_size=30)
    # Draw a rectangle (x, y, width, height, color)
    overlay.draw_rect(90, 90, 350, 50, (0, 0, 0, 100))

    overlay.signal_render()
    time.sleep(10) # Stays on screen for 10 seconds