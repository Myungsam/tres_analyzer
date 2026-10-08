"""The application window with its two tabs."""
import os
import sys

import tkinter as tk
from tkinter import ttk

from .theme import apply_theme
from .flim import FLIMViewer
from .viewer import TRESViewer
from .freezelog import FreezeLog


def main():
    path = None
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            path = arg
            break
    if path and not os.path.exists(path):
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    root = tk.Tk()
    root.title("PicoHarp 300 post-processing - PHU/TRES + PTU/FLIM")
    root.geometry("1440x920")
    root.minsize(980, 660)
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
    FLIMViewer(ptu_tab)

    root.mainloop()
    log.close()
