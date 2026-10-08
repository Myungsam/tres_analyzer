"""Colours, the ttk theme and the plot helpers every window shares."""
import os
import sys

import numpy as np

import matplotlib
from matplotlib.colors import LogNorm, Normalize

import tkinter as tk
from tkinter import ttk


# ==========================================================================
# 4. Viewer
# ==========================================================================
# Light theme. BG is the plot/field white, PANEL the light-grey card behind
# the widgets and figures; INK/INK_DIM/INK_FAINT are the text ramp from near-
# black to a muted grey; ACCENT/PIN/GOOD are the signal colours, chosen dark
# enough to read on white. Everything downstream refers to these names, so the
# whole program (both tabs + the analysis windows) follows a change here.
BG = "#ffffff"         # plot backgrounds and entry fields
PANEL = "#eef1f6"      # widget / figure panels
INK = "#161d28"        # primary text
INK_DIM = "#3f4a5a"    # secondary text / titles
INK_FAINT = "#5b6675"  # tick labels, faint traces, grid
LINE = "#c2cad6"       # borders, spines, grid lines
ACCENT = "#1668c4"     # live decay / fit lines, highlights
PIN = "#c8860a"        # background window + pinned overlays
MASKED = "#b0364a"     # hatched bars over masked-out wavelength regions
GOOD = "#2e9e5c"       # GPU available / "on" states in the FLIM panel
BTN = "#e3e8ef"        # button / combobox face
BTN_ACTIVE = "#d3dae4" # button hover
READOUT_FG = "#eef4ff" # map cursor read-out text (always light on its dark box)
READOUT_BG = "#10151d" # map cursor read-out box (dark, reads over any colormap)


def shade_wl_masks(ax, masks, wl_lo, wl_hi):
    """Draw masked-out wavelength regions as hatched vertical bars.

    Shared by the main map and the Crop / Mask dialog previews so a masked
    band looks the same everywhere. ``masks`` is a list of (wl1, wl2) nm.
    """
    for a, b in masks:
        lo, hi = max(min(a, b), wl_lo), min(max(a, b), wl_hi)
        if hi > lo:
            ax.axvspan(lo, hi, facecolor=PANEL, alpha=0.55, lw=0, zorder=4)
            ax.axvspan(lo, hi, facecolor="none", edgecolor=MASKED, lw=0.9,
                       hatch="///", zorder=5)


def style_plot_ax(ax):
    """Apply the shared light-theme look to a stand-alone dialog axis."""
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color(LINE)
    ax.tick_params(colors=INK_FAINT, labelsize=8, length=3)
    ax.xaxis.label.set_color(INK_FAINT)
    ax.yaxis.label.set_color(INK_FAINT)
    ax.title.set_color(INK_DIM)


def preview_norm_cmap(vmax, log, cmap_name):
    """(Z-transform, norm, cmap) for a raw-count heatmap in the dialogs."""
    cmap = matplotlib.colormaps[cmap_name].copy()
    cmap.set_bad(cmap(0.0))
    if log:
        norm = LogNorm(vmin=1.0, vmax=max(vmax, 1.02))
        transform = lambda E: np.ma.masked_less(E, 1.0)
    else:
        norm = Normalize(vmin=0.0, vmax=max(vmax, 1e-9))
        transform = lambda E: E
    return transform, norm, cmap


def dpi_aware():
    """Tell Windows that this program draws at the display's own resolution.

    Without it Windows draws the window at 96 dpi and stretches the picture on
    a display set to 125 or 150 %: everything is the right size, and blurred.
    With it Tk gets the real resolution and scales its fonts (and matplotlib
    its figures) itself; ui_scale() does the same for the sizes this program
    gives in pixels. "System aware", not per monitor: Tk does not rescale a
    window that is dragged to a display with another setting.
    Must run before the first window is made. TCSPC_DPI_AWARE=0 in the
    environment switches it off (the old, stretched picture).
    """
    if os.environ.get("TCSPC_DPI_AWARE", "1") == "0" or sys.platform != "win32":
        return False
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)      # Windows 8.1 and later
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()           # Vista / 7
        return True
    except Exception:                   # noqa: BLE001 - already set, or not allowed: go on as before
        return False


def ui_scale(widget):
    """How many real pixels one "pixel at 100 %" is on this display: 1.0 at
    100 %, 1.5 at 150 % (and 1.0 whatever the display says while the program
    is not dpi_aware(): Windows then does the stretching)."""
    try:
        # Windows' settings are steps of 25 %; Tk reports 96.02 for 96 dpi
        return max(1.0, round(float(widget.winfo_fpixels("1i")) / 96.0, 2))
    except Exception:                   # noqa: BLE001
        return 1.0


def px(widget, n):
    """``n`` pixels at 100 % as pixels of this display."""
    return int(round(n * ui_scale(widget)))


def scaled_geometry(widget, geometry):
    """A "WxH" geometry given for 100 % as one for this display, no larger
    than the screen has room for."""
    w, h = (int(v) for v in geometry.lower().split("x"))
    return (f"{min(px(widget, w), widget.winfo_screenwidth() - px(widget, 40))}"
            f"x{min(px(widget, h), widget.winfo_screenheight() - px(widget, 100))}")


def apply_theme(root):
    """Configure the shared ttk light theme, once, for the whole window.

    ttk styles are per-interpreter, so this covers both tabs; the extra
    Notebook / Labelframe / Progressbar entries are what the FLIM tab needs on
    top of the widgets the TRES tab already used.
    """
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure(".", background=PANEL, foreground=INK, fieldbackground=BG)
    st.configure("TFrame", background=PANEL)
    st.configure("TLabel", background=PANEL, foreground=INK_FAINT, font=("TkDefaultFont", 9))
    st.configure("Val.TLabel", foreground=INK, font=("TkFixedFont", 9))
    st.configure("TButton", background=BTN, foreground=INK, borderwidth=1)
    st.map("TButton", background=[("active", BTN_ACTIVE)])
    st.configure("TCheckbutton", background=PANEL, foreground=INK_DIM)
    st.map("TCheckbutton", background=[("active", PANEL)])
    st.configure("TCombobox", fieldbackground=BG, background=BTN, foreground=INK)
    st.configure("TEntry", fieldbackground=BG, foreground=INK, insertcolor=INK)
    # -- extras for the FLIM tab and the tab bar --
    st.configure("TLabelframe", background=PANEL, bordercolor=LINE)
    st.configure("TLabelframe.Label", background=PANEL, foreground=INK_DIM)
    st.configure("TNotebook", background=PANEL, bordercolor=LINE, tabmargins=(6, 6, 6, 0))
    st.configure("TNotebook.Tab", background=PANEL, foreground=INK_DIM,
                 padding=(18, 7), font=("TkDefaultFont", 10))
    st.map("TNotebook.Tab",
           background=[("selected", BG)], foreground=[("selected", INK)])
    st.configure("TProgressbar", background=ACCENT, troughcolor="#dfe4ec", bordercolor=LINE)
    st.configure("TSeparator", background=LINE)
    root.configure(bg=PANEL)


# Back-compat alias: the theme went light, but keep the old name callable so
# nothing that imported it breaks.
apply_dark_theme = apply_theme
