"""
Region Menu

Arrow-key navigable menu for assigning screen regions to named options.
Navigate with ↑↓, press Enter to select a region, ESC to quit.
"""

import tkinter as tk

try:
    from region_picker import ScreenRegionPicker
except ImportError:
    from testing.picker.region_picker import ScreenRegionPicker


class RegionMenu:
    def __init__(self, options: list[str]):
        self.options = options
        self.cursor = 0
        self.regions: dict[str, dict] = {}
        self.root = None

    def _build_window(self):
        self.root = tk.Tk()
        self.root.title("Region Menu")
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)

        self.root.bind('<Up>', self._on_up)
        self.root.bind('<Down>', self._on_down)
        self.root.bind('<Return>', self._on_enter)
        self.root.bind('<Escape>', lambda e: self.root.quit())

        self._render()

        # Center on screen
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _render(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        tk.Label(
            self.root,
            text="Assign screen regions",
            font=('Arial', 13, 'bold'),
            padx=20, pady=10,
        ).pack(fill='x')

        tk.Frame(self.root, height=1, bg='#cccccc').pack(fill='x')

        for i, opt in enumerate(self.options):
            selected = i == self.cursor
            region = self.regions.get(opt)
            status = f"{region['width']}x{region['height']}" if region else "not set"
            arrow = '▶' if selected else '  '

            row = tk.Frame(self.root, bg='#ddeeff' if selected else self.root.cget('bg'))
            row.pack(fill='x')

            tk.Label(
                row,
                text=f" {arrow}  {opt}",
                font=('Courier', 12, 'bold' if selected else 'normal'),
                anchor='w',
                bg=row.cget('bg'),
                padx=12, pady=6,
            ).pack(side='left')

            tk.Label(
                row,
                text=status,
                font=('Courier', 11),
                fg='#228822' if region else '#999999',
                anchor='e',
                bg=row.cget('bg'),
                padx=12,
            ).pack(side='right')

        tk.Frame(self.root, height=1, bg='#cccccc').pack(fill='x')

        tk.Label(
            self.root,
            text="↑↓ navigate    Enter assign region    ESC quit",
            font=('Arial', 9),
            fg='#888888',
            pady=6,
        ).pack()

    def _on_up(self, event):
        self.cursor = (self.cursor - 1) % len(self.options)
        self._render()

    def _on_down(self, event):
        self.cursor = (self.cursor + 1) % len(self.options)
        self._render()

    def _on_enter(self, event):
        opt = self.options[self.cursor]
        self.root.withdraw()
        region = ScreenRegionPicker().pick()
        if region:
            self.regions[opt] = region
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        self._render()

    def run(self) -> dict[str, dict]:
        """Show the menu and return the assigned regions on exit."""
        self._build_window()
        self.root.mainloop()
        return self.regions


if __name__ == "__main__":
    regions = RegionMenu(["Hotbar", "Map", "Player Stats", "Minimap"]).run()
    print("Assigned regions:")
    for name, region in regions.items():
        print(f"  {name}: {region}")
