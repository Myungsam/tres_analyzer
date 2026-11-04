"""Colours, the ttk theme and the plot helpers every window shares."""
import os
import sys

import numpy as np

import matplotlib
from matplotlib.colors import LogNorm, Normalize

import tkinter as tk
from tkinter import font as tkfont
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
PANEL = "#f0f0f0"      # widget / figure panels (the Windows dialog grey)
MASK_FILL = "#eef1f6"  # wash under the hatch of a masked band (PANEL up to 1.6)
INK = "#161d28"        # primary text
INK_DIM = "#3f4a5a"    # secondary text / titles
INK_FAINT = "#5b6675"  # tick labels, faint traces, grid
LINE = "#c2cad6"       # borders, spines, grid lines
ACCENT = "#1668c4"     # live decay / fit lines, highlights
PIN = "#c8860a"        # background window + pinned overlays
MASKED = "#b0364a"     # hatched bars over masked-out wavelength regions
GOOD = "#2e9e5c"       # GPU available / "on" states in the FLIM panel
WARN = "#b3261e"       # a warning in an info line
BTN = "#e1e1e1"        # button / combobox face (Windows grey)
BTN_ACTIVE = "#d4d4d4" # button hover
BTN_BORDER = "#adadad" # button outline
BTN_DISABLED_FG = "#8c8c8c"  # text of a button that cannot be pressed
READOUT_FG = "#eef4ff" # map cursor read-out text (always light on its dark box)
READOUT_BG = "#10151d" # map cursor read-out box (dark, reads over any colormap)

# Buttons that do something beyond the window carry a role colour, always with
# white text at a contrast of at least 4.5:1 (WCAG AA), hover and press included.
ROLE_ANALYSIS = "#6f35a5"   # opens an analysis window (Kinetics, Global analysis)
ROLE_EXPORT = "#1a5fb4"     # writes files
ROLE_OPJU = "#b35400"       # writes files and drives Origin (".opju" ticked)
ROLE_RUN = "#1e7b34"        # starts a fit
ROLE_STOP = "#b3261e"       # stops it
ROLE_FG = "#ffffff"


def _shade(colour, factor):
    """``colour`` with each channel times ``factor`` (below 1: darker)."""
    return "#" + "".join(f"{min(255, int(round(int(colour[i:i + 2], 16) * factor))):02x}"
                         for i in (1, 3, 5))


# colour -> (face, hover, pressed); darker shades only raise the contrast
ROLE_SHADES = {c: (c, _shade(c, 0.88), _shade(c, 0.76))
               for c in (ROLE_ANALYSIS, ROLE_EXPORT, ROLE_OPJU, ROLE_RUN, ROLE_STOP)}
# role name -> colour; the ttk style of a role is "<role>.TButton"
ROLES = {"Analysis": ROLE_ANALYSIS, "Export": ROLE_EXPORT, "Opju": ROLE_OPJU,
         "Run": ROLE_RUN, "Stop": ROLE_STOP}

# Named fonts (made by apply_theme). Widgets and styles name them by these
# strings. A font given as a tuple of "TkDefaultFont" and a size is not the
# named font: Tk reads it as a family called "TkDefaultFont", which it does
# not have, and on a Korean Windows falls back to Gulim.
UI_FONT = "TcspcUI"             # Segoe UI 9: labels, buttons, boxes
UI_FONT_BOLD = "TcspcUIBold"    # Segoe UI 10 bold: captions
UI_FONT_TAB = "TcspcUITab"      # Segoe UI 10: the tab bar
FIXED_FONT = "TcspcFixed"       # Consolas 9: numbers, paths, result text
_FONTS = {UI_FONT: {"family": "Segoe UI", "size": 9},
          UI_FONT_BOLD: {"family": "Segoe UI", "size": 10, "weight": "bold"},
          UI_FONT_TAB: {"family": "Segoe UI", "size": 10},
          FIXED_FONT: {"family": "Consolas", "size": 9}}


def shade_wl_masks(ax, masks, wl_lo, wl_hi):
    """Draw masked-out wavelength regions as hatched vertical bars.

    Shared by the main map and the Crop / Mask dialog previews so a masked
    band looks the same everywhere. ``masks`` is a list of (wl1, wl2) nm.
    """
    for a, b in masks:
        lo, hi = max(min(a, b), wl_lo), min(max(a, b), wl_hi)
        if hi > lo:
            ax.axvspan(lo, hi, facecolor=MASK_FILL, alpha=0.55, lw=0, zorder=4)
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


def _named_fonts(root):
    """Make the program's named fonts, once per Tk root, and point Tk's own
    default fonts at Segoe UI 9. Sizes are in points (positive), so they follow
    the display's scaling. The Font objects are kept on the root: a Font that
    is garbage collected deletes its named font."""
    keep = root.__dict__.setdefault("_tcspc_fonts", [])
    have = set(tkfont.names(root))
    for name, spec in _FONTS.items():
        if name not in have:
            keep.append(tkfont.Font(root=root, name=name, **spec))
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        if name in have:
            tkfont.nametofont(name, root=root).configure(family="Segoe UI", size=9)


def apply_theme(root):
    """Configure the shared ttk light theme, once, for the whole window.

    ttk styles are per-interpreter, so this covers both tabs; the extra
    Notebook / Labelframe / Progressbar entries are what the FLIM tab needs on
    top of the widgets the TRES tab already used. Calling it again (another
    window of the same root) makes no second set of fonts.
    """
    _named_fonts(root)
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    st.configure(".", background=PANEL, foreground=INK, fieldbackground=BG, font=UI_FONT)
    st.configure("TFrame", background=PANEL)
    st.configure("TLabel", background=PANEL, foreground=INK_FAINT, font=UI_FONT)
    st.configure("Val.TLabel", foreground=INK, font=FIXED_FONT)
    st.configure("TButton", background=BTN, foreground=INK, borderwidth=1, bordercolor=BTN_BORDER,
                 lightcolor=BTN, darkcolor=BTN, focuscolor=INK_FAINT)
    st.map("TButton", background=[("disabled", BTN), ("pressed", BTN_ACTIVE), ("active", BTN_ACTIVE)],
           lightcolor=[("pressed", BTN_ACTIVE), ("active", BTN_ACTIVE)],
           darkcolor=[("pressed", BTN_ACTIVE), ("active", BTN_ACTIVE)],
           foreground=[("disabled", BTN_DISABLED_FG)])
    # one style per role: white text on the role colour, grey when disabled
    for role, colour in ROLES.items():
        face, hover, pressed = ROLE_SHADES[colour]
        name = f"{role}.TButton"
        st.configure(name, background=face, foreground=ROLE_FG, bordercolor=pressed,
                     lightcolor=face, darkcolor=face)
        states = [("disabled", BTN), ("pressed", pressed), ("active", hover)]
        st.map(name, background=states, lightcolor=states, darkcolor=states,
               bordercolor=[("disabled", BTN_BORDER)],
               foreground=[("disabled", BTN_DISABLED_FG)])
    st.configure("TCheckbutton", background=PANEL, foreground=INK_DIM)
    st.map("TCheckbutton", background=[("active", PANEL)])
    st.configure("TCombobox", fieldbackground=BG, background=BTN, foreground=INK)
    st.configure("TEntry", fieldbackground=BG, foreground=INK, insertcolor=INK)
    st.configure("TSpinbox", fieldbackground=BG, background=BTN, foreground=INK,
                 insertcolor=INK, arrowcolor=INK_DIM, arrowsize=10)
    # -- groups, the status bar, the tab bar and the FLIM tab --
    st.configure("TLabelframe", background=PANEL, bordercolor=LINE)
    st.configure("TLabelframe.Label", background=PANEL, foreground=INK_DIM, font=UI_FONT)
    st.configure("Status.TFrame", background=PANEL)
    st.configure("Status.TLabel", background=PANEL, foreground=INK_FAINT, font=UI_FONT)
    st.configure("TNotebook", background=PANEL, bordercolor=LINE, tabmargins=(6, 6, 6, 0))
    st.configure("TNotebook.Tab", background=PANEL, foreground=INK_DIM,
                 padding=(18, 7), font=UI_FONT_TAB)
    st.map("TNotebook.Tab",
           background=[("selected", BG)], foreground=[("selected", INK)])
    st.configure("TProgressbar", background=ACCENT, troughcolor="#dfe4ec", bordercolor=LINE)
    st.configure("TSeparator", background=LINE)
    root.configure(bg=PANEL)


# Back-compat alias: the theme went light, but keep the old name callable so
# nothing that imported it breaks.
apply_dark_theme = apply_theme
