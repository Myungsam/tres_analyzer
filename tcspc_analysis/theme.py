"""Colours, the ttk theme and the plot helpers every window shares."""
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
