"""
Screen Region Selector with Transparent Overlay

This application creates a transparent overlay that allows users to select
a region of the screen for capture without interfering with underlying applications.
"""

import queue
import cv2
import numpy as np
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
from mss import mss
import sys


class ScreenRegionSelector:
    def __init__(self):
        self.root = None
        self.overlay = None
        self.selection_window = None
        self.is_selecting = False
        self.start_point = None
        self.current_point = None
        self.selected_region = None
        self.sct = mss()
        self.frame_queue = queue.Queue(maxsize=2)
        self.capture_window = None
        self.capture_label = None
        
        # Get screen dimensions
        self.screen_width = self.sct.monitors[0]['width']  # Combined monitor width
        self.screen_height = self.sct.monitors[0]['height']  # Combined monitor height
        
    def create_overlay(self):
        """Create a transparent overlay window covering the entire screen"""
        # Create transparent overlay window using tkinter
        self.overlay = tk.Toplevel()
        self.overlay.overrideredirect(True)  # Remove window decorations
        self.overlay.attributes('-alpha', 0.3)  # Set transparency
        self.overlay.configure(bg='white')
        
        # Position and size the overlay to cover the entire screen
        self.overlay.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        self.overlay.lift()
        self.overlay.wm_attributes("-topmost", True)
        
        # Bind mouse events for region selection
        self.overlay.bind("<Button-1>", self.on_mouse_down)
        self.overlay.bind("<B1-Motion>", self.on_mouse_drag)
        self.overlay.bind("<ButtonRelease-1>", self.on_mouse_up)
        
        # Add instruction label
        instruction_label = tk.Label(
            self.overlay,
            text="Click and drag to select a region to capture. Press ESC to cancel.",
            bg='yellow',
            fg='black',
            font=('Arial', 14, 'bold')
        )
        instruction_label.pack(pady=20)
        
        # Bring overlay to front periodically
        self.bring_to_front()
    
    def bring_to_front(self):
        """Ensure overlay stays on top"""
        if self.overlay and self.overlay.winfo_exists():
            self.overlay.lift()
            self.overlay.after(100, self.bring_to_front)  # Repeat every 100ms
    
    def on_mouse_down(self, event):
        """Handle mouse button press"""
        self.is_selecting = True
        self.start_point = (event.x, event.y)
        self.current_point = (event.x, event.y)
        
        # Create temporary selection rectangle
        if not self.selection_window:
            self.selection_window = tk.Canvas(
                self.overlay,
                highlightthickness=0,
                bg='white',
                bd=0
            )
            self.selection_window.place(x=0, y=0, width=self.screen_width, height=self.screen_height)
        
        # Draw initial rectangle
        self.draw_selection_rectangle()
    
    def on_mouse_drag(self, event):
        """Handle mouse dragging"""
        if self.is_selecting:
            self.current_point = (event.x, event.y)
            self.draw_selection_rectangle()
    
    def on_mouse_up(self, event):
        """Handle mouse button release"""
        if self.is_selecting:
            self.is_selecting = False
            self.current_point = (event.x, event.y)
            
            # Calculate selected region
            x1, y1 = self.start_point
            x2, y2 = self.current_point
            
            # Ensure proper coordinate ordering
            left = min(x1, x2)
            top = min(y1, y2)
            right = max(x1, x2)
            bottom = max(y1, y2)
            
            self.selected_region = {
                'left': left,
                'top': top,
                'width': right - left,
                'height': bottom - top
            }
            
            print(f"Selected region: {self.selected_region}")
            
            # Close overlay and proceed with capture
            self.cleanup()
            self.start_capture_with_selected_region()
    
    def draw_selection_rectangle(self):
        """Draw the selection rectangle on the canvas"""
        if self.selection_window:
            # Clear previous rectangle
            self.selection_window.delete("selection_rect")
            
            # Get current coordinates
            x1, y1 = self.start_point
            x2, y2 = self.current_point
            
            # Draw semi-transparent rectangle
            self.selection_window.create_rectangle(
                x1, y1, x2, y2,
                outline='red',
                width=2,
                fill='red',
                stipple='gray50',
                tags="selection_rect"
            )
    
    def cleanup(self):
        """Clean up overlay windows"""
        if self.overlay:
            self.overlay.destroy()
        if self.selection_window:
            self.selection_window.destroy()
        self.overlay = None
        self.selection_window = None
    
    def start_capture_with_selected_region(self):
        """Start screen capture with the selected region"""
        if not self.selected_region:
            print("No region selected!")
            return

        print(f"Starting capture of region: {self.selected_region}")

        # Create a tkinter window on the main thread for display
        self.capture_window = tk.Toplevel(self.root)
        self.capture_window.title("Selected Region Capture - Press Q to quit")
        self.capture_window.bind('<q>', lambda e: self._stop_capture())
        self.capture_window.bind('<Q>', lambda e: self._stop_capture())
        self.capture_window.protocol("WM_DELETE_WINDOW", self._stop_capture)
        self.capture_label = tk.Label(self.capture_window)
        self.capture_label.pack()

        # Start capture in a separate thread
        capture_thread = threading.Thread(target=self.capture_loop, daemon=True)
        capture_thread.start()

        # Poll the frame queue on the main thread
        self._poll_frames()

    def _stop_capture(self):
        """Stop capture and close windows"""
        # Signal the capture loop to stop by poisoning the queue
        try:
            self.frame_queue.put_nowait(None)
        except queue.Full:
            pass
        if self.capture_window:
            self.capture_window.destroy()
            self.capture_window = None
        self.root.quit()

    def _poll_frames(self):
        """Poll frame queue and update display — runs on main thread via root.after"""
        if self.capture_window is None:
            return
        try:
            frame = self.frame_queue.get_nowait()
            if frame is None:
                return  # sentinel: stop polling
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            imgtk = ImageTk.PhotoImage(image=img)
            self.capture_label.imgtk = imgtk  # keep reference
            self.capture_label.config(image=imgtk)
        except queue.Empty:
            pass
        self.root.after(16, self._poll_frames)  # ~60fps

    def capture_loop(self):
        """Main capture loop — runs in background thread, no GUI calls"""
        try:
            while True:
                screenshot = self.sct.grab(self.selected_region)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                try:
                    self.frame_queue.put(frame, timeout=0.1)
                except queue.Full:
                    pass  # drop frame if display can't keep up
        except Exception as e:
            print(f"Capture error: {e}")
    
    def start_selection(self):
        """Start the region selection process"""
        print("Creating overlay for region selection...")
        print(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
        
        # Create the main window (hidden)
        self.root = tk.Tk()
        self.root.withdraw()  # Hide main window
        
        # Create overlay
        self.create_overlay()
        
        # Handle escape key to cancel
        def on_escape(event):
            if self.overlay:
                self.cleanup()
                self.root.quit()
        
        self.root.bind('<Escape>', on_escape)
        
        try:
            self.root.mainloop()
        except tk.TclError:
            # Window might already be destroyed
            pass


def main():
    print("Screen Region Selector")
    print("Instructions:")
    print("1. A transparent overlay will appear over your screen")
    print("2. Click and drag to select a region")
    print("3. The selected region will be captured in real-time")
    print("4. Press 'q' in the capture window to stop")
    print("5. Press 'ESC' during selection to cancel")
    print()
    
    selector = ScreenRegionSelector()
    selector.start_selection()


if __name__ == "__main__":
    main()