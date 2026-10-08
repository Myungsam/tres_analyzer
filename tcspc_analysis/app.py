"""The application window with its two tabs."""
import os
import sys

import tkinter as tk
from tkinter import messagebox, ttk

from .theme import apply_theme
from .flim import FLIMViewer
from .viewer import TRESViewer
from .freezelog import FreezeLog


def initial_window_size(screen_w, screen_h):
    """The window's size at start: 1440 x 920, or what the screen has room for
    (a laptop, or a display scaled to 125 / 150 %)."""
    return (max(600, min(1440, screen_w - 40)), max(400, min(920, screen_h - 100)))


def main():
    path = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            path = arg
            break
    if path and not os.path.exists(path):
        print(f"File not found: {path}", file=sys.stderr)
        # the windowed .exe has no console: without a box a mistyped or moved
        # path would just close the program
        box = tk.Tk()
        box.withdraw()
        messagebox.showerror("File not found", f"There is no such file:\n{path}",
                             parent=box)
        box.destroy()
        sys.exit(1)
    # a .ptu belongs to the other tab
    ptu = path if path and path.lower().endswith(".ptu") else None
    if ptu:
        path = None

    root = tk.Tk()
    root.title("PicoHarp 300 post-processing - PHU/TRES + PTU/FLIM")
    w, h = initial_window_size(root.winfo_screenwidth(), root.winfo_screenheight())
    root.geometry(f"{w}x{h}")
    root.minsize(min(980, w), min(660, h))
    apply_theme(root)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    phu_tab = ttk.Frame(nb)
    ptu_tab = ttk.Frame(nb)
    nb.add(phu_tab, text="PHU  ·  TRES")
    nb.add(ptu_tab, text="PTU  ·  FLIM")

    # before the viewers, so a file that hangs on opening is caught as well
    tres = None
    log = FreezeLog(root, lambda: os.path.basename(tres.var_path.get()) if tres else "")
    tres = TRESViewer(phu_tab, path)
    flim = FLIMViewer(ptu_tab)
    if ptu:
        flim.path_var.set(ptu)
        nb.select(ptu_tab)

    root.mainloop()
    log.close()
