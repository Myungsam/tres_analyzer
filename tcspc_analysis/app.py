"""The application window with its two tabs."""
import os
import sys

import tkinter as tk
from tkinter import messagebox, ttk

from .theme import apply_theme, dpi_aware, ui_scale
from .flim import FLIMViewer
from .viewer import TRESViewer
from .freezelog import FreezeLog
from .paths import program_dir
from .version import APP_VERSION


def initial_window_size(screen_w, screen_h, scale=1.0):
    """The window's size at start: 1440 x 920 at 100 %, or what the screen has
    room for (a laptop, or a display scaled to 125 / 150 %). ``scale`` is
    ui_scale(): the screen size is in real pixels, the numbers here are for
    100 %."""
    def s(n):
        return int(round(n * scale))
    return (max(s(600), min(s(1440), screen_w - s(40))), max(s(400), min(s(920), screen_h - s(100))))


def main():
    dpi_aware()                 # before any window, the "file not found" box included
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
    root.title("PicoHarp 300 post-processing - PHU/TRES + PTU/FLIM"
               f"   |   TCSPC_analysis {APP_VERSION}")
    # the program's icon for this window and every window it opens: the file
    # beside the launcher or, in the .exe, the one built into the .exe
    icon = (sys.executable if getattr(sys, "frozen", False)
            else os.path.join(program_dir(), "TCSPC_analysis.ico"))
    if os.path.exists(icon):
        try:
            root.iconbitmap(default=icon)
        except tk.TclError:
            pass
    scale = ui_scale(root)
    w, h = initial_window_size(root.winfo_screenwidth(), root.winfo_screenheight(), scale)
    root.geometry(f"{w}x{h}")
    root.minsize(min(int(round(980 * scale)), w), min(int(round(660 * scale)), h))
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
