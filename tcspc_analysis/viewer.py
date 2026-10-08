"""The PHU / TRES tab."""
import contextlib
import glob
import math
import os
import sys
import threading

import numpy as np

import matplotlib
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle
from matplotlib.ticker import EngFormatter, MaxNLocator

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .paths import user_dir
from .phu import read_phu
from .util import short_name, wavelength_to_rgb
from .origin import _origin_book1, _origin_fill_steady, _origin_fill_tres, _origin_sheet
from .model import TRESModel
from .theme import ACCENT, BG, INK, INK_DIM, INK_FAINT, LINE, PANEL, PIN, READOUT_BG, READOUT_FG, shade_wl_masks
from .dialogs.crop import CropDialog
from .dialogs.mask import MaskDialog
from .dialogs.kinetics import KineticsDialog
from .dialogs.global_analysis import GlobalAnalysisDialog

CMAPS = ["turbo", "viridis", "inferno", "magma", "plasma", "cividis", "gray"]
BIN_FACTORS = (1, 2, 4, 8, 16, 32, 64)      # time bins of the file summed into one


def bin_choices(res_ps):
    """The BIN choices for a file with ``res_ps`` per time bin: (label, factor)."""
    return [(f"{res_ps * k:g} ps", k) for k in BIN_FACTORS]


BIN_CHOICES = bin_choices(4.0)              # before a file is loaded (PicoHarp default)


class TRESViewer:
    def __init__(self, parent, initial_path=None):
        self.parent = parent                  # the tab frame widgets pack into
        self.win = parent.winfo_toplevel()    # the window, for title/cursor
        self.model = None
        self.cursor = None       # (wi, ti)
        self.pinned = False
        self.view = None         # (w_lo, w_hi, t_lo, t_hi) zoom, None = full
        self.clim = None         # (vmin, vmax) contrast, None = auto
        self._drag = None        # in-flight rubber-band drag
        self._bg = {}            # blitting backgrounds

        self._build_filebar()
        self._build_controls()
        self._build_figure()

        if initial_path:
            self.load(initial_path)
        else:
            self._show_placeholder()

    # -- chrome -----------------------------------------------------------
    def _build_filebar(self):
        bar = ttk.Frame(self.parent, padding=(10, 8))
        bar.pack(fill="x")

        ttk.Label(bar, text="TRES", font=("TkDefaultFont", 10, "bold"),
                  foreground=INK).pack(side="left", padx=(0, 12))
        ttk.Label(bar, text="FILE").pack(side="left", padx=(0, 6))

        self.var_path = tk.StringVar(value="No file loaded")
        entry = ttk.Entry(bar, textvariable=self.var_path, state="readonly",
                          font=("TkFixedFont", 9))
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._loading = False                 # a file is being read (load_async)
        self.btn_open = ttk.Button(bar, text="Open file...", command=self.open_dialog)
        self.btn_open.pack(side="left")
        ttk.Button(bar, text="Save map image...",
                   command=self.save_map_image).pack(side="left", padx=(6, 0))

        # -- combined data export: TRES map + steady state, always together --
        self._exporting = False               # an .opju export is driving Origin
        self.btn_export = ttk.Button(bar, text="Export data...",
                                     command=self.export_data)
        self.btn_export.pack(side="left", padx=(12, 4))
        self.var_out_csv = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="CSV",
                        variable=self.var_out_csv).pack(side="left")
        self.var_out_opju = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=".opju",
                        variable=self.var_out_opju).pack(side="left", padx=(4, 0))

        # -- a second row: the pop-up windows. On one row with the file
        #    controls the last buttons were squeezed out of a narrow window.
        bar = ttk.Frame(self.parent, padding=(10, 0, 10, 6))
        bar.pack(fill="x")
        self._bar2 = bar

        # -- preprocessing: crop + wavelength masks, each its own pop-up --
        ttk.Label(bar, text="PREP").pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Crop...", command=self.open_crop).pack(side="left")
        ttk.Button(bar, text="Mask λ...",
                   command=self.open_mask).pack(side="left", padx=(6, 0))
        self._crop_win = None
        self._mask_win = None

        # -- analysis tools, each in its own pop-up window --
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=(12, 8))
        ttk.Label(bar, text="ANALYSIS").pack(side="left", padx=(0, 6))
        ttk.Button(bar, text="Kinetics...",
                   command=self.open_kinetics).pack(side="left")
        ttk.Button(bar, text="Global analysis...",
                   command=self.open_global_analysis).pack(side="left", padx=(6, 0))
        # one live window of each kind, so a second click just raises it
        self._kinetics_win = None
        self._global_win = None

    def open_kinetics(self):
        """Open (or raise) the single-wavelength kinetics-fit window."""
        if not self.model:
            messagebox.showinfo("No data", "Load a .phu file first.", parent=self.win)
            return
        if self._kinetics_win is not None and self._kinetics_win.alive:
            self._kinetics_win.lift_and_refresh()
            return
        self._kinetics_win = KineticsDialog(self)

    def open_global_analysis(self):
        """Open (or raise) the global-analysis window."""
        if not self.model:
            messagebox.showinfo("No data", "Load a .phu file first.", parent=self.win)
            return
        if self._global_win is not None and self._global_win.alive:
            self._global_win.lift_and_refresh()
            return
        self._global_win = GlobalAnalysisDialog(self)

    def open_crop(self):
        """Open (or raise) the crop window (wavelength + time window)."""
        if not self.model:
            messagebox.showinfo("No data", "Load a .phu file first.", parent=self.win)
            return
        if self._crop_win is not None and self._crop_win.alive:
            self._crop_win.lift_and_refresh()
            return
        self._crop_win = CropDialog(self)

    def open_mask(self):
        """Open (or raise) the wavelength-mask window."""
        if not self.model:
            messagebox.showinfo("No data", "Load a .phu file first.", parent=self.win)
            return
        if self._mask_win is not None and self._mask_win.alive:
            self._mask_win.lift_and_refresh()
            return
        self._mask_win = MaskDialog(self)

    def _close_dialogs(self):
        """Drop every open Crop / Mask / Kinetics / Global-analysis window.

        Each is tied to the file that was loaded when it opened: the previews
        are that file's map, and a fit window keeps that file's time range, t0
        and result. Closing a Global-analysis window also stops its fit.
        """
        for w in (self._crop_win, self._mask_win, self._kinetics_win, self._global_win):
            if w is not None and w.alive:
                w._on_close()
        self._crop_win = self._mask_win = None
        self._kinetics_win = self._global_win = None

    def _tell_dialogs(self):
        """Let the open pop-up windows follow a change made in this window."""
        for w in (self._crop_win, self._mask_win, self._kinetics_win, self._global_win):
            if w is not None and w.alive:
                w.model_changed()

    def _build_controls(self):
        row = ttk.Frame(self.parent, padding=(10, 0, 10, 4))
        row.pack(fill="x")

        ttk.Label(row, text="COLORMAP").pack(side="left", padx=(0, 5))
        self.var_cmap = tk.StringVar(value="turbo")
        cb = ttk.Combobox(row, textvariable=self.var_cmap, values=CMAPS,
                          width=9, state="readonly")
        cb.pack(side="left", padx=(0, 16))
        cb.bind("<<ComboboxSelected>>", lambda e: self.redraw(full=True))

        ttk.Label(row, text="TIME SPAN").pack(side="left", padx=(0, 5))
        self.var_tmax = tk.StringVar(value="")   # filled from the file on open
        e = ttk.Entry(row, textvariable=self.var_tmax, width=8, font=("TkFixedFont", 9))
        e.pack(side="left")
        e.bind("<Return>", lambda ev: self.apply_params())
        e.bind("<FocusOut>", lambda ev: self.apply_params())
        ttk.Label(row, text="ps").pack(side="left", padx=(3, 16))

        ttk.Label(row, text="BIN").pack(side="left", padx=(0, 5))
        self.var_bin = tk.StringVar(value="16 ps")
        self._bins = dict(BIN_CHOICES)          # label -> rebin factor, for the loaded file
        cb2 = ttk.Combobox(row, textvariable=self.var_bin,
                           values=list(self._bins), width=7, state="readonly")
        cb2.pack(side="left", padx=(0, 16))
        cb2.bind("<<ComboboxSelected>>", lambda e: self.apply_params())
        self.cb_bin = cb2

        self.var_log = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="Log color", variable=self.var_log,
                        command=lambda: self.redraw(full=True)).pack(side="left", padx=(0, 12))

        self.var_t0 = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="t0 at IRF peak", variable=self.var_t0,
                        command=self.apply_params).pack(side="left", padx=(0, 12))

        # A .phu header carries no IRF flag and an IRF cannot be told apart from
        # the wavelength grid (it often sits on it), so whether curve 0 is an
        # IRF-only measurement is a manual choice - this checkbox. When on,
        # curve 0 is kept out of the map and only used to put t0 on its peak.
        self.var_irf = tk.BooleanVar(value=True)
        ttk.Checkbutton(row, text="First curve is IRF", variable=self.var_irf,
                        command=self.apply_params).pack(side="left")

        self.var_meta = tk.StringVar(value="")      # shown in the third row

        # -- second row: background subtraction, view resets, mouse legend --
        row2 = ttk.Frame(self.parent, padding=(10, 0, 10, 4))
        row2.pack(fill="x")

        self.var_bgsub = tk.BooleanVar(value=True)
        ttk.Checkbutton(row2, text="Subtract background", variable=self.var_bgsub,
                        command=self.apply_params).pack(side="left", padx=(0, 10))

        ttk.Label(row2, text="WINDOW").pack(side="left", padx=(0, 5))
        self.var_bg_lo = tk.StringVar(value="0")
        self.var_bg_hi = tk.StringVar(value="100")
        for var, pad in ((self.var_bg_lo, (0, 0)), (self.var_bg_hi, (0, 3))):
            ent = ttk.Entry(row2, textvariable=var, width=7, font=("TkFixedFont", 9))
            ent.pack(side="left", padx=pad)
            ent.bind("<Return>", lambda ev: self.apply_params())
            ent.bind("<FocusOut>", lambda ev: self.apply_params())
            if var is self.var_bg_lo:
                ttk.Label(row2, text="-").pack(side="left", padx=4)
        ttk.Label(row2, text="ps").pack(side="left", padx=(0, 10))

        self.var_bginfo = tk.StringVar(value="")    # its label ends the row, below

        ttk.Button(row2, text="Reset zoom", command=self.reset_view).pack(side="left")
        ttk.Button(row2, text="Auto contrast",
                   command=self.reset_contrast).pack(side="left", padx=(6, 0))

        ttk.Label(row2, text="OFFSET").pack(side="left", padx=(16, 5))
        self.var_offset = tk.StringVar(value="-50")   # default spectrograph calibration
        ent = ttk.Entry(row2, textvariable=self.var_offset, width=7, font=("TkFixedFont", 9))
        ent.pack(side="left")
        ent.bind("<Return>", lambda ev: self.apply_offset())
        ttk.Label(row2, text="nm").pack(side="left", padx=(3, 6))
        ttk.Button(row2, text="offset 적용",
                   command=self.apply_offset).pack(side="left")

        # packed last: in a narrow window this text is cut, not a button
        ttk.Label(row2, textvariable=self.var_bginfo, style="Val.TLabel",
                  foreground=PIN).pack(side="left", padx=(16, 0))

        # (the mouse legend was here; it did not fit and now sits beside the
        #  pop-up buttons, where there is room)
        ttk.Label(self._bar2,
                  text="map: drag = zoom | click = pin | right-click = reset      "
                       "colorbar: drag = contrast | right-click = auto"
                  ).pack(side="right")

        # -- third row: solvent subtraction on / off. The solvent itself is
        #    loaded and scaled in the Crop window; this only switches it, so
        #    the data can be compared with and without. A row of its own: the
        #    one above is already wider than the window.
        row3 = ttk.Frame(self.parent, padding=(10, 0, 10, 8))
        row3.pack(fill="x")

        self.var_solv = tk.BooleanVar(value=False)
        self.chk_solv = ttk.Checkbutton(row3, text="Subtract solvent",
                                        variable=self.var_solv,
                                        command=self.apply_params, state="disabled")
        self.chk_solv.pack(side="left", padx=(0, 10))
        self.var_solvinfo = tk.StringVar(value=self.NO_SOLVENT)
        ttk.Label(row3, textvariable=self.var_solvinfo, style="Val.TLabel",
                  foreground=PIN).pack(side="left")
        # the file's own numbers: the longest text of the window, on the row
        # with the most room
        ttk.Label(row3, textvariable=self.var_meta, style="Val.TLabel",
                  foreground=INK_FAINT).pack(side="right")

    NO_SOLVENT = "no solvent - load one in Crop..."

    def _sync_solvent_ui(self):
        """Mirror the model's solvent state into the checkbox and its label."""
        m = self.model
        if not m or m.solvent is None:
            self.var_solv.set(False)
            self.chk_solv.configure(state="disabled")
            self.var_solvinfo.set(self.NO_SOLVENT)
            return
        self.chk_solv.configure(state="normal")
        self.var_solv.set(m.solvent_sub)
        info = f'x{m.solvent_scale:g}  {short_name(m.solvent["path"])}'
        if m.solvent_active:
            info += f"  (clipped {m.clip_frac:.0%} of bins to 0)"
        self.var_solvinfo.set(info)

    # -- figure -----------------------------------------------------------
    def _build_figure(self):
        self.fig = Figure(figsize=(14, 7.4), dpi=100, facecolor=PANEL)
        gs = GridSpec(
            3, 3, figure=self.fig,
            width_ratios=[1.0, 3.6, 0.06], height_ratios=[3.0, 0.10, 1.35],
            left=0.055, right=0.955, top=0.955, bottom=0.075,
            wspace=0.045, hspace=0.06,
        )
        self.ax_hist = self.fig.add_subplot(gs[0, 0])
        self.ax_map = self.fig.add_subplot(gs[0, 1], sharey=self.ax_hist)
        self.cax = self.fig.add_subplot(gs[0, 2])
        self.ax_rib = self.fig.add_subplot(gs[1, 1], sharex=self.ax_map)
        self.ax_ss = self.fig.add_subplot(gs[2, 0])
        self.ax_spec = self.fig.add_subplot(gs[2, 1], sharex=self.ax_map)

        for ax in (self.ax_hist, self.ax_map, self.ax_ss, self.ax_spec, self.ax_rib):
            ax.set_facecolor(BG)
            for s in ax.spines.values():
                s.set_color(LINE)
            ax.tick_params(colors=INK_FAINT, labelsize=8, length=3)
            ax.xaxis.label.set_color(INK_FAINT)
            ax.yaxis.label.set_color(INK_FAINT)
            ax.title.set_color(INK_DIM)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("axes_leave_event", self.on_leave)
        self.canvas.mpl_connect("draw_event", self.on_draw)

    def _show_placeholder(self):
        for ax in (self.ax_hist, self.ax_ss, self.ax_spec, self.ax_rib, self.cax):
            ax.set_visible(False)
        self.ax_map.set_visible(True)
        self.ax_map.clear()
        self.ax_map.set_facecolor(BG)
        self.ax_map.set_xticks([])
        self.ax_map.set_yticks([])
        self.ax_map.text(
            0.5, 0.5,
            "No measurement loaded\n\nOpen a PicoHarp 300 .phu histogram file to draw the map.",
            ha="center", va="center", color=INK_FAINT, fontsize=11, linespacing=1.8,
            transform=self.ax_map.transAxes,
        )
        self.canvas.draw()

    # -- loading ----------------------------------------------------------
    def open_dialog(self):
        path = filedialog.askopenfilename(
            title="Open PicoQuant histogram file",
            filetypes=[("PicoQuant histogram", "*.phu"), ("All files", "*.*")],
        )
        if path:
            self.load_async(path)

    def load_async(self, path):
        """Open ``path`` without holding up the window: what the Open button does.

        The file is read on a worker thread - one that Windows first has to
        fetch (an online-only OneDrive file) can take a while - and the window
        says so meanwhile. Everything after the read happens back here on the
        main thread, exactly as in load().
        """
        if self._loading or self._exporting:
            return
        got = {}

        def read():
            try:
                got["phu"] = read_phu(path)
            except Exception as exc:        # noqa: BLE001 - shown in the box below
                got["error"] = exc

        worker = threading.Thread(target=read, daemon=True)
        worker.start()
        self._loading = True
        info = self.var_meta.get()
        self.btn_open.configure(state="disabled")
        self.win.config(cursor="watch")
        self.var_meta.set(f"Reading {os.path.basename(path)} ...")

        def poll():
            try:
                still_here = bool(self.win.winfo_exists())
            except tk.TclError:
                still_here = False
            if not still_here:              # the program was closed meanwhile
                return
            if worker.is_alive():
                self.win.after(50, poll)
                return
            self._loading = False
            self.btn_open.configure(state="normal")
            self.win.config(cursor="")
            self.var_meta.set(info)
            if "error" in got:
                messagebox.showerror("Could not read file", str(got["error"]), parent=self.win)
            else:
                self._show_loaded(got["phu"], path)

        poll()

    def load(self, path):
        """Open ``path`` and return when it is on screen."""
        try:
            phu = read_phu(path)
        except Exception as exc:
            messagebox.showerror("Could not read file", str(exc), parent=self.win)
            return
        self._show_loaded(phu, path)

    def _show_loaded(self, phu, path):
        # The new model is built completely before anything of the old file is
        # given up: a file that cannot be shown leaves the window as it was.
        old, old_tmax = self.model, self.var_tmax.get()
        old_bg = (self.var_bg_lo.get(), self.var_bg_hi.get())
        try:
            model = TRESModel(phu)
            # A .phu header has no IRF flag, so whether curve 0 is an IRF-only
            # measurement is the user's call via the "First curve is IRF" checkbox.
            model.first_is_irf = self.var_irf.get()
            model.t0_align = self.var_t0.get()
            # the choices are this file's bin widths; keep the width that was
            # selected (16 ps stays 16 ps on an 8 ps file), or the nearest one
            bins = dict(bin_choices(phu["res_ps"]))
            try:
                wanted = float(self.var_bin.get().split()[0])
            except (ValueError, IndexError):
                wanted = 4.0 * phu["res_ps"]
            bin_label = min(bins, key=lambda k: abs(bins[k] * phu["res_ps"] - wanted))
            model.rebin = bins[bin_label]
            model.bg_sub = self.var_bgsub.get()
            # the offset calibrates the spectrograph, not the file, so it carries over
            model.wl_offset = self._float_var(self.var_offset, 0.0)
            # open on everything that was actually recorded, empty tail trimmed
            model.t_max_ps = model.t_data_ps
            model.rebuild()
            self.model = model
            self._bins = bins
            self.cb_bin.configure(values=list(bins))
            self.var_bin.set(bin_label)
            self.var_tmax.set(f"{model.t_max_ps:.0f}")
            self._set_bg_window(model.t_lo, model.t_lo + 100.0)
        except Exception as exc:        # noqa: BLE001 - whatever the file trips over
            self.model = old
            self.var_tmax.set(old_tmax)
            self.var_bg_lo.set(old_bg[0]); self.var_bg_hi.set(old_bg[1])
            messagebox.showerror(
                "Could not read file",
                f"{os.path.basename(path)} was read but cannot be shown:\n"
                f"{type(exc).__name__}: {exc}", parent=self.win)
            return
        # the pop-up windows belong to the old file's data - drop them
        self._close_dialogs()
        # (a solvent belongs to the sample it was matched against, so the new
        # model starts without one and redraw() disables the checkbox again)

        self.cursor = None
        self.pinned = False
        self.view = None
        self.clim = None
        self.var_path.set(path)

        acq = f'{phu["acq_ms"] / 1000:g} s' if phu["acq_ms"] else "-"
        sync = f' | sync {phu["sync_rate"] / 1e6:.2f} MHz' if phu["sync_rate"] else ""
        self.var_meta.set(
            f'{phu["hw_type"]} SN {phu["serial"]} | {phu["ncurves"]} curves | '
            f'{phu["wls"][0]:.0f}-{phu["wls"][-1]:.0f} {phu["param_unit"]} | '
            f'{phu["nbins"]:,} bins @ {phu["res_ps"]:g} ps | acq {acq}/curve{sync}'
        )
        self.redraw(full=True)

    @staticmethod
    def _float_var(var, default):
        """Read a Tk entry as a finite float, rewriting it when it is not one."""
        try:
            value = float(var.get())
            if not math.isfinite(value):
                raise ValueError
            return value
        except ValueError:
            var.set(f"{default:g}")
            return default

    def _set_bg_window(self, lo_ps, hi_ps):
        """Move the background window and mirror it into the entry boxes."""
        m = self.model
        # t0 carries float noise far below one picosecond, which a round trip
        # through the entry box would otherwise accumulate; -0.0 prints as "-0"
        lo_ps, hi_ps = round(lo_ps, 1) + 0.0, round(hi_ps, 1) + 0.0
        m.bg_lo_ps, m.bg_hi_ps = lo_ps, hi_ps
        self.var_bg_lo.set(f"{lo_ps:g}")
        self.var_bg_hi.set(f"{hi_ps:g}")
        m.subtract_background()

    def _shown_settings(self):
        """The controls as apply_params() reads them."""
        m = self.model
        return (self.var_tmax.get().strip(), self.var_bin.get(),
                bool(self.var_irf.get()), bool(self.var_t0.get()),
                bool(self.var_bgsub.get()), self.var_bg_lo.get().strip(),
                self.var_bg_hi.get().strip(),
                bool(self.var_solv.get()) and m.solvent is not None)

    def _model_settings(self):
        """The same settings as the model holds them, written the way the
        controls show them - so a box that was not touched compares equal."""
        m = self.model
        label = next((k for k, v in self._bins.items() if v == m.rebin), None)
        return (f"{m.t_max_ps:.0f}", label, bool(m.first_is_irf),
                bool(m.t0_align), bool(m.bg_sub), f"{m.bg_lo_ps:g}",
                f"{m.bg_hi_ps:g}", bool(m.solvent_sub))

    def apply_params(self):
        if not self.model:
            return
        m = self.model
        # <FocusOut> lands here whenever the window loses the focus with the
        # caret in one of the boxes; with nothing changed there is nothing to
        # recompute, and no reason to throw a hand-picked contrast away
        before = self._model_settings()
        if self._shown_settings() == before:
            return
        try:
            tmax = float(self.var_tmax.get())
            if not tmax > 0:            # also catches nan
                raise ValueError
        except ValueError:
            tmax = m.t_data_ps          # unreadable entry falls back to the default
            self.var_tmax.set(f"{tmax:.0f}")

        t0_before = m.t0
        # where the cursor is, in wavelength and in delay from the start of
        # the record - its indices mean something else after the rebuild
        at = None
        if self.cursor:
            wi, ti = self.cursor
            at = (float(m.wls[wi]), float(m.times[ti] + m.t0))
        m.t_max_ps = min(tmax, m.t_full_ps)
        if tmax > m.t_max_ps:           # asked for more delay than was measured
            self.var_tmax.set(f"{m.t_max_ps:.0f}")
        m.rebin = self._bins[self.var_bin.get()]
        m.first_is_irf = self.var_irf.get()
        m.t0_align = self.var_t0.get()
        m.bg_sub = self.var_bgsub.get()
        m.bg_lo_ps = self._float_var(self.var_bg_lo, 0.0)
        m.bg_hi_ps = self._float_var(self.var_bg_hi, 100.0)
        m.solvent_sub = self.var_solv.get() and m.solvent is not None
        m.rebuild()

        # The window is quoted in display time, so moving t0 - by aligning to the
        # IRF peak, or by dropping the IRF curve - would slide it onto a different
        # part of the record: a pre-pulse baseline would land on the emission peak
        # and the subtraction would take the whole map negative. Shift the numbers
        # by the same amount so the window keeps covering the same real delays.
        shift = t0_before - m.t0
        if shift:
            self._set_bg_window(m.bg_lo_ps + shift, m.bg_hi_ps + shift)

        # counts per bin change with the rebin factor, the background, the
        # solvent and the IRF curve leaving the map, so a contrast picked for
        # the old scale is meaningless; a new time span or t0 leaves it valid
        after = self._model_settings()
        if before[1:3] + before[4:] != after[1:3] + after[4:]:
            self.clim = None
        self._clamp_view()

        if at:
            self.cursor = self._cell_near(at[0], at[1] - m.t0)
        self.redraw(full=True)
        self._tell_dialogs()

    def _cell_near(self, wl, t_ps):
        """The (wavelength, time) cell nearest to a point, clamped into the map."""
        m = self.model
        wi = int(np.argmin(np.abs(m.wls - wl)))
        ti = int(np.clip((t_ps + m.t0 - m.t_off_ps) // m.dt_ps, 0, m.n_t - 1))
        return wi, ti

    def _clamp_view(self):
        """Keep a zoom rectangle inside the axes after the model was rebuilt."""
        if not self.view:
            return
        m = self.model
        w_lo, w_hi = m.wl_edges
        x0, x1, y0, y1 = self.view
        x0, x1 = max(x0, w_lo), min(x1, w_hi)
        y0, y1 = max(y0, m.t_lo), min(y1, m.t_hi)
        self.view = (x0, x1, y0, y1) if (x1 > x0 and y1 > y0) else None

    def reset_view(self):
        self.view = None
        self.redraw(full=True)

    def reset_contrast(self):
        self.clim = None
        self.redraw(full=True)

    def apply_offset(self):
        """Shift every wavelength by the number of nm in the OFFSET box.

        The offset is absolute - it is always measured from the wavelengths
        stored in the file - so pressing the button twice does not shift twice.
        """
        if not self.model:
            return
        m = self.model
        new = self._float_var(self.var_offset, m.wl_offset)
        delta = new - m.wl_offset
        if delta == 0.0:
            return
        at = None
        if self.cursor:
            wi, ti = self.cursor
            at = (float(m.wls[wi]) + delta, float(m.times[ti]))
        m.wl_offset = new
        m.rebuild()          # the wavelengths come straight off the file each time
        # the cursor follows its curve; a crop quoted in nm may now keep other
        # curves (or fewer), so its old index can lie outside the map
        if at:
            self.cursor = self._cell_near(*at)

        # carry a zoom rectangle along, otherwise it would frame different lines
        if self.view:
            x0, x1, y0, y1 = self.view
            self.view = (x0 + delta, x1 + delta, y0, y1)
            self._clamp_view()
        self.redraw(full=True)
        self._tell_dialogs()

    # -- drawing ----------------------------------------------------------
    def _color_scale(self):
        """Colour mapping of the map: (norm, cmap, vmin, log).

        Shared with the export so a written PNG carries the colormap, the
        log/linear choice and any contrast dragged on the colorbar.
        """
        log = self.var_log.get()
        lo, hi = (self.clim if self.clim is not None
                  else ((1.0 if log else 0.0), self.model.vmax))
        if log:
            lo = max(lo, 1e-2)
            hi = max(hi, lo * 1.01)
            norm = LogNorm(vmin=lo, vmax=hi)
        else:
            hi = max(hi, lo + 1e-9)
            norm = Normalize(vmin=lo, vmax=hi)
        cmap = matplotlib.colormaps[self.var_cmap.get()].copy()
        cmap.set_bad(cmap(0.0))
        return norm, cmap, lo, log

    def redraw(self, full=False):
        if not self.model:
            return
        m = self.model
        # every change to the model ends in a redraw (controls, Crop, Mask,
        # offset, a new file), so this is where the solvent checkbox and its
        # clipped-share label are brought back in line with it
        self._sync_solvent_ui()
        for ax in (self.ax_hist, self.ax_ss, self.ax_spec, self.ax_rib, self.cax):
            ax.set_visible(True)

        for ax in (self.ax_hist, self.ax_map, self.ax_ss, self.ax_spec,
                   self.ax_rib, self.cax):
            ax.clear()
            ax.set_facecolor(BG)

        w_lo, w_hi = m.wl_edges
        norm, cmap, lo, log = self._color_scale()

        # ---- 2D map ----
        Z = np.ma.masked_less(m.E.T, lo) if log else m.E.T
        self.im = self.ax_map.imshow(
            Z, aspect="auto", origin="lower", cmap=cmap, norm=norm,
            extent=[w_lo, w_hi, m.t_lo, m.t_hi], interpolation="nearest",
        )
        # masked-out wavelength bands ride on top of the heatmap as hatched bars
        shade_wl_masks(self.ax_map, m.masks, w_lo, w_hi)
        # explicit limits so adding the rubber-band patch cannot autoscale them
        self.ax_map.set_xlim(w_lo, w_hi)
        self.ax_map.set_ylim(m.t_lo, m.t_hi)
        # the time axis is the Decay panel's, right beside it: labels of its
        # own would lie on top of that panel
        self.ax_map.tick_params(labelbottom=False, labelleft=False)
        # the IRF no longer has a panel of its own, so its numbers ride along here
        self.ax_map.set_title(
            "TRES map" + (f"     IRF {m.irf_wl:.0f} nm - FWHM {m.irf_fwhm_ps:.0f} ps"
                          if m.irf is not None else ""),
            fontsize=9, loc="left", pad=4)

        cb = self.fig.colorbar(self.im, cax=self.cax)
        cb.set_label("Counts" + (" (log)" if log else "")
                     + ("" if self.clim is None else "  [manual]"),
                     color=INK_FAINT, fontsize=8)
        cb.ax.tick_params(colors=INK_FAINT, labelsize=7.5)
        cb.outline.set_color(LINE)

        # ---- spectral ribbon ----
        grad = np.array([wavelength_to_rgb(w)
                         for w in np.linspace(w_lo, w_hi, 384)])[None, :, :]
        self.ax_rib.imshow(grad, aspect="auto", extent=[w_lo, w_hi, 0, 1],
                           interpolation="bilinear")
        self.ax_rib.set_yticks([])
        self.ax_rib.tick_params(labelbottom=False, length=0)

        # ---- decay histogram (left, time shared with the map) ----
        # The only static (grey) trace is the IRF, when the file has one. Its
        # raw scatter peak is many times brighter than the emission, so scale it
        # to the map's brightest count (m.vmax): it then shares the panel's count
        # scale with the live decay instead of running off the axis.
        if m.irf is not None and m.irf.max() > 0:
            irf_scaled = m.irf / m.irf.max() * m.vmax
            self.ax_hist.plot(np.maximum(irf_scaled, 0.7), m.times, color="#8a93a2",
                              lw=1.0, ls="--", alpha=0.65, label="IRF")
            self.ax_hist.legend(loc="upper right", fontsize=7, frameon=False,
                                handlelength=1.4, borderaxespad=0.3)
        (self.ln_decay,) = self.ax_hist.plot([], [], lw=1.4, color=ACCENT, animated=True)
        self.hl_hist = self.ax_hist.axhline(np.nan, color=INK_DIM, lw=0.8, ls=":",
                                            alpha=0.55, animated=True)
        self.ax_hist.set_xscale("log")
        self.ax_hist.set_xlim(1, m.vmax * 1.6)
        self.ax_hist.set_ylim(m.t_lo, m.t_hi)
        self.ax_hist.set_xlabel("Counts", fontsize=9)
        self.ax_hist.set_ylabel("Time (ps)", fontsize=9)
        self.ax_hist.set_title("Decay", fontsize=9, loc="left", pad=4)
        self.ax_hist.grid(alpha=0.12, lw=0.5, color=INK_FAINT)

        # ---- spectrum (bottom, wavelength shared with the map) ----
        # backdrop: the band shape of all delays together, scaled to the panel
        # (which is sized for one time bin) the way the IRF is in the Decay panel
        band = m.spec_total
        if np.isfinite(band).any() and np.nanmax(band) > 0:
            band = band / np.nanmax(band) * m.vmax
        self.ax_spec.fill_between(m.wls, np.maximum(band, 0.7), 0.7,
                                  color=INK_FAINT, alpha=0.16, lw=0)
        shade_wl_masks(self.ax_spec, m.masks, w_lo, w_hi)
        (self.ln_spec,) = self.ax_spec.plot([], [], lw=1.4, color=INK,
                                            marker="o", ms=2.6, animated=True)
        self.vl_spec = self.ax_spec.axvline(np.nan, color=INK_DIM, lw=0.8, ls=":",
                                            alpha=0.55, animated=True)
        self.ax_spec.set_yscale("log")
        self.ax_spec.set_ylim(0.7, m.vmax * 1.6)
        self.ax_spec.set_xlim(w_lo, w_hi)
        self.ax_spec.set_xlabel("Wavelength (nm)", fontsize=9)
        self.ax_spec.set_ylabel("Counts", fontsize=9)
        self.ax_spec.set_title("Spectrum", fontsize=9, loc="left", pad=4)
        self.ax_spec.grid(alpha=0.12, lw=0.5, color=INK_FAINT)

        # ---- background: shade the window, draw the spectrum that was removed ----
        if m.bg_spec is not None:
            b0, b1 = m.bg_window_ps
            self.ax_map.axhspan(b0, b1, color=PIN, alpha=0.10, lw=0)
            self.ax_hist.axhspan(b0, b1, color=PIN, alpha=0.14, lw=0)
            self.ax_spec.plot(m.wls, np.maximum(m.bg_spec, 0.7), color=PIN,
                              ls=":", lw=1.0, alpha=0.8)
            self.var_bginfo.set(
                f"bg {b0:,.0f}-{b1:,.0f} ps (mean {np.nanmean(m.bg_spec):,.1f} cts/bin)"
                + (f"  ** {m.neg_frac:.0%} of the map is negative - window is on signal?"
                   if m.neg_frac > 0.6 else ""))
        else:
            self.var_bginfo.set("bg off")

        # ---- steady-state spectrum: every delay of the record summed together ----
        # linear, unlike the slice below the map: this is the band shape a cw
        # spectrometer would have measured, and a log axis flattens it.
        ss = m.spec_total
        self.ax_ss.fill_between(m.wls, ss, 0.0, color=ACCENT, alpha=0.20, lw=0)
        self.ax_ss.plot(m.wls, ss, color=ACCENT, lw=1.2)
        shade_wl_masks(self.ax_ss, m.masks, w_lo, w_hi)
        self.ax_ss.set_xlim(w_lo, w_hi)
        # spec_total carries NaN gaps at masked wavelengths, so reduce nan-aware
        have_ss = bool(np.isfinite(ss).any())
        top = max(float(np.nanmax(ss)) if have_ss else 1.0, 1.0)
        ss_bot = float(np.nanmin(ss)) if have_ss else 0.0
        self.ax_ss.set_ylim(min(0.0, ss_bot * 1.08), top * 1.12)
        # summed counts run into the millions; "1.2M" keeps the panel readable
        self.ax_ss.yaxis.set_major_locator(MaxNLocator(5))
        self.ax_ss.yaxis.set_major_formatter(EngFormatter(places=0, sep=""))
        self.ax_ss.grid(alpha=0.12, lw=0.5, color=INK_FAINT)
        self.ax_ss.set_xlabel("Wavelength (nm)", fontsize=9)
        self.ax_ss.set_ylabel("Counts (all delays)", fontsize=9)
        # in-axes, not a title: the decay panel's x-label sits in that same band
        peak_txt = (f"{m.wls[int(np.nanargmax(ss))]:.0f} nm" if have_ss else "-")
        self.ax_ss.text(
            0.028, 0.955, f"Steady state - peak {peak_txt}",
            transform=self.ax_ss.transAxes, ha="left", va="top",
            fontsize=8.5, color=INK_DIM)

        # ---- crosshair + readout on the map ----
        self.vl_map = self.ax_map.axvline(np.nan, color="w", lw=0.9, ls="--",
                                          alpha=0.75, animated=True)
        self.hl_map = self.ax_map.axhline(np.nan, color="w", lw=0.9, ls="--",
                                          alpha=0.75, animated=True)
        # the read-out sits on top of the colormap image, so it keeps a dark
        # card with light text regardless of the (now light) UI theme
        self.txt = self.ax_map.text(
            0.988, 0.972, "", transform=self.ax_map.transAxes, ha="right", va="top",
            family="monospace", fontsize=8.5, color=READOUT_FG, animated=True,
            bbox=dict(boxstyle="round,pad=0.45", fc=READOUT_BG, ec=LINE, alpha=0.88),
        )

        # ---- rubber bands: zoom rectangle on the map, contrast span on the bar ----
        self.rect = Rectangle((0, 0), 0, 0, fc=ACCENT, alpha=0.16, ec=ACCENT,
                              lw=1.0, ls="--", animated=True, visible=False)
        self.ax_map.add_patch(self.rect)

        self.crect = Rectangle((0, 0), 1, 0, transform=self.cax.get_yaxis_transform(),
                               fc="none", ec="w", lw=1.2, animated=True, visible=False)
        self.cax.add_patch(self.crect)

        # clear() gave every label and title back matplotlib's default colour
        for ax in (self.ax_hist, self.ax_map, self.ax_ss, self.ax_spec, self.ax_rib):
            ax.xaxis.label.set_color(INK_FAINT)
            ax.yaxis.label.set_color(INK_FAINT)
            for title in (ax.title, ax._left_title, ax._right_title):
                title.set_color(INK_DIM)

        # ---- zoom: applied last, the shared axes follow ----
        x0, x1, y0, y1 = self.view if self.view else (w_lo, w_hi, m.t_lo, m.t_hi)
        self.ax_map.set_xlim(x0, x1)
        self.ax_map.set_ylim(y0, y1)

        self.canvas.draw()      # on_draw() puts the cursor artists back

    def on_draw(self, event):
        """Re-capture clean backgrounds after every full redraw (incl. resize)."""
        if not self.model:
            return
        self._bg = {
            "map": self.canvas.copy_from_bbox(self.ax_map.bbox),
            "hist": self.canvas.copy_from_bbox(self.ax_hist.bbox),
            "spec": self.canvas.copy_from_bbox(self.ax_spec.bbox),
            "cax": self.canvas.copy_from_bbox(self.cax.bbox),
        }
        # the crosshair and the live curves are animated artists: a draw does
        # not paint them, so put them back on the fresh backgrounds (a resize
        # or an uncovered window draws without going through redraw())
        self.update_cursor()

    def update_cursor(self):
        """Update the live slices by blitting - fast enough for every mouse move."""
        if not self.model or not self._bg:
            return
        m = self.model

        if self.cursor is None:
            self.ln_decay.set_data([], [])
            self.ln_spec.set_data([], [])
            for art in (self.vl_map, self.hl_map, self.vl_spec):
                art.set_xdata([np.nan, np.nan])
            self.hl_hist.set_ydata([np.nan, np.nan])
            self.txt.set_text("")
        else:
            wi, ti = self.cursor
            wl = m.wls[wi]
            t_ps = m.times[ti]
            val = m.E[wi, ti]
            col = wavelength_to_rgb(wl)

            decay = np.maximum(m.decay_at(wi), 0.7)
            self.ln_decay.set_data(decay, m.times)
            self.ln_decay.set_color(col)

            spec = np.maximum(m.spectrum_at(ti), 0.7)
            self.ln_spec.set_data(m.wls, spec)

            self.vl_map.set_xdata([wl, wl])
            self.hl_map.set_ydata([t_ps, t_ps])
            self.vl_spec.set_xdata([wl, wl])
            self.hl_hist.set_ydata([t_ps, t_ps])

            edge = PIN if self.pinned else "w"
            for art in (self.vl_map, self.hl_map):
                art.set_color(edge)

            self.txt.set_text(
                f"lambda   {wl:>8,.0f} nm\n"
                f"t        {t_ps:>8,.0f} ps\n"
                f"counts   {val:>8,.0f}"
                + ("\nPINNED - click to release" if self.pinned else "")
            )
            # the card under it is dark whatever the UI theme: light text
            self.txt.set_color(PIN if self.pinned else READOUT_FG)

        self.canvas.restore_region(self._bg["hist"])
        self.ax_hist.draw_artist(self.ln_decay)
        self.ax_hist.draw_artist(self.hl_hist)
        self.canvas.blit(self.ax_hist.bbox)

        self.canvas.restore_region(self._bg["spec"])
        self.ax_spec.draw_artist(self.ln_spec)
        self.ax_spec.draw_artist(self.vl_spec)
        self.canvas.blit(self.ax_spec.bbox)

        self.canvas.restore_region(self._bg["map"])
        self.ax_map.draw_artist(self.vl_map)
        self.ax_map.draw_artist(self.hl_map)
        self.ax_map.draw_artist(self.txt)
        self.canvas.blit(self.ax_map.bbox)

    # -- events -----------------------------------------------------------
    DRAG_PX = 5      # below this a press/release pair counts as a plain click

    def on_press(self, event):
        if not self.model or not self._bg:
            return
        if event.inaxes is self.ax_map:
            if event.button == 3:
                self.reset_view()
            elif event.button == 1 and event.xdata is not None:
                self._drag = dict(kind="zoom", x0=event.xdata, y0=event.ydata,
                                  px=event.x, py=event.y)
        elif event.inaxes is self.cax:
            if event.button == 3:
                self.reset_contrast()
            elif event.button == 1 and event.ydata is not None:
                self._drag = dict(kind="clim", y0=event.ydata, py=event.y)

    def on_motion(self, event):
        if not self.model:
            return
        if self._drag is not None:
            self._draw_rubber(event)
            return
        if self.pinned or event.inaxes is not self.ax_map:
            return
        if event.xdata is None or event.ydata is None:
            return
        hit = self.model.locate(event.xdata, event.ydata)
        if hit and hit != self.cursor:
            self.cursor = hit
            self.update_cursor()

    def on_release(self, event):
        drag, self._drag = self._drag, None
        if not self.model or drag is None:
            return

        if drag["kind"] == "zoom":
            moved = (abs(event.x - drag["px"]) > self.DRAG_PX or
                     abs(event.y - drag["py"]) > self.DRAG_PX)
            if moved and "x1" in drag:
                x0, x1 = sorted((drag["x0"], drag["x1"]))
                y0, y1 = sorted((drag["y0"], drag["y1"]))
                if x1 > x0 and y1 > y0:
                    self.view = (x0, x1, y0, y1)
                    self.redraw(full=True)
                    return
            if event.inaxes is self.ax_map:
                self._toggle_pin(event)
        elif abs(event.y - drag["py"]) > self.DRAG_PX and "y1" in drag:
            lo, hi = sorted((drag["y0"], drag["y1"]))
            if hi > lo:
                self.clim = (lo, hi)
                self.redraw(full=True)
                return

        self.rect.set_visible(False)
        self.crect.set_visible(False)
        self.update_cursor()

    def _draw_rubber(self, event):
        """Blit the drag rectangle over the clean background of its own axes."""
        d = self._drag
        if d["kind"] == "zoom":
            if event.inaxes is self.ax_map and event.xdata is not None:
                d["x1"], d["y1"] = event.xdata, event.ydata
            if "x1" not in d:
                return
            x0, x1 = sorted((d["x0"], d["x1"]))
            y0, y1 = sorted((d["y0"], d["y1"]))
            self.rect.set_bounds(x0, y0, x1 - x0, y1 - y0)
            self.rect.set_visible(True)
            self.canvas.restore_region(self._bg["map"])
            self.ax_map.draw_artist(self.rect)
            self.canvas.blit(self.ax_map.bbox)
        else:
            if event.inaxes is self.cax and event.ydata is not None:
                d["y1"] = event.ydata
            if "y1" not in d:
                return
            y0, y1 = sorted((d["y0"], d["y1"]))
            self.crect.set_bounds(0, y0, 1, y1 - y0)
            self.crect.set_visible(True)
            self.canvas.restore_region(self._bg["cax"])
            self.cax.draw_artist(self.crect)
            self.canvas.blit(self.cax.bbox)

    def _toggle_pin(self, event):
        if event.xdata is None or event.ydata is None:
            return
        hit = self.model.locate(event.xdata, event.ydata)
        if self.pinned:
            self.pinned = False
            if hit:
                self.cursor = hit
        elif hit:
            self.cursor = hit
            self.pinned = True
        self.update_cursor()

    def on_leave(self, event):
        if self._drag is not None:
            return
        if self.model and not self.pinned and event.inaxes is self.ax_map:
            self.cursor = None
            self.update_cursor()

    # -- export -----------------------------------------------------------
    def save_map_image(self):
        """Write the TRES map alone as a picture - not the surrounding panels.

        Carries the colormap and contrast on screen and covers exactly the
        region the map is showing, so a zoom crops the picture as well. For the
        numbers behind it, use "Export data".
        """
        if self._busy_reading():
            return
        if not self.model:
            messagebox.showinfo("Nothing to save", "Load a .phu file first.", parent=self.win)
            return

        base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        path = filedialog.asksaveasfilename(
            title="Save TRES map image", defaultextension=".png",
            initialfile=f"{base}_TRESmap.png",
            filetypes=[("PNG image", "*.png"), ("PDF document", "*.pdf"),
                       ("SVG image", "*.svg")],
        )
        if not path:
            return

        wls, times, Z = self._export_region()
        try:
            self._write_map_image(path, wls, times, Z)
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc), parent=self.win)
            return

        messagebox.showinfo(
            "Map image saved",
            f"{Z.shape[1]} wavelengths x {Z.shape[0]} time bins "
            f"({wls[0]:.0f}-{wls[-1]:.0f} nm, {times[0]:,.0f}-{times[-1]:,.0f} ps)"
            + ("  [current zoom]" if self.view else "") + "\n\n"
            f"image  {path}", parent=self.win)

    def _export_region(self):
        """The map as (wavelengths, times, Z[time, wavelength]), zoom applied."""
        m = self.model
        if self.view:
            x0, x1, y0, y1 = self.view
        else:
            (x0, x1), y0, y1 = m.wl_edges, m.t_lo, m.t_hi

        wi = np.nonzero((m.wls >= x0) & (m.wls <= x1))[0]
        ti = np.nonzero((m.times >= y0) & (m.times <= y1))[0]
        # a rectangle dragged narrower than one bin still has to export something
        if not len(wi):
            wi = np.array([int(np.argmin(np.abs(m.wls - (x0 + x1) / 2)))])
        if not len(ti):
            ti = np.array([int(np.argmin(np.abs(m.times - (y0 + y1) / 2)))])

        return m.wls[wi], m.times[ti], m.E[np.ix_(wi, ti)].T

    def _export_note(self):
        """One line of provenance, shared by the image and the data file."""
        m = self.model
        bits = [f"bin {m.dt_ps:g} ps"]
        if m.irf is not None:
            bits.append(f"IRF {m.irf_wl:.0f} nm - FWHM {m.irf_fwhm_ps:.0f} ps")
        if m.t0_align:
            bits.append("t0 at IRF peak")
        if m.bg_spec is not None:
            bits.append(f"bg subtracted {m.bg_window_ps[0]:,.0f}-{m.bg_window_ps[1]:,.0f} ps")
        else:
            bits.append("bg not subtracted")
        if m.wl_offset:
            bits.append(f"offset {m.wl_offset:+g} nm")
        if m.crop_wl is not None:
            bits.append(f"crop {min(m.crop_wl):g}-{max(m.crop_wl):g} nm")
        if m.t_min_ps > 0:
            bits.append(f"t from {m.t_min_ps:g} ps")
        if m.masks:
            bits.append("masked " +
                        ", ".join(f"{min(a, b):g}-{max(a, b):g}" for a, b in m.masks)
                        + " nm")
        if m.solvent_active:
            bits.append(f"solvent subtracted x{m.solvent_scale:g} "
                        f'({os.path.basename(m.solvent["path"])}), '
                        f"negatives clipped to 0 ({m.clip_frac:.0%} of bins)")
        return "  |  ".join(bits)

    def _extent_of(self, wls, times):
        """Pixel edges of the exported block, in data coordinates."""
        m = self.model
        dw = float(np.median(np.diff(wls))) if len(wls) > 1 else \
            (m.wl_edges[1] - m.wl_edges[0])
        return [wls[0] - dw / 2, wls[-1] + dw / 2,
                times[0] - m.dt_ps / 2, times[-1] + m.dt_ps / 2]

    def _write_map_image(self, path, wls, times, Z):
        """Render the map on its own figure - no decay, spectrum or ribbon."""
        norm, cmap, lo, log = self._color_scale()

        fig = Figure(figsize=(10.0, 6.4), dpi=100, facecolor=PANEL)
        ax = fig.add_axes([0.085, 0.095, 0.795, 0.800])
        cax = fig.add_axes([0.900, 0.095, 0.022, 0.800])
        for a in (ax, cax):
            a.set_facecolor(BG)
            for s in a.spines.values():
                s.set_color(LINE)
            a.tick_params(colors=INK_FAINT, labelsize=8, length=3)
            a.xaxis.label.set_color(INK_FAINT)
            a.yaxis.label.set_color(INK_FAINT)

        im = ax.imshow(
            np.ma.masked_less(Z, lo) if log else Z,
            aspect="auto", origin="lower", cmap=cmap, norm=norm,
            extent=self._extent_of(wls, times), interpolation="nearest",
        )
        ext = self._extent_of(wls, times)
        shade_wl_masks(ax, self.model.masks, ext[0], ext[1])
        ax.set_xlabel("Wavelength (nm)", fontsize=9.5)
        ax.set_ylabel("Time (ps)", fontsize=9.5)
        # two figure-level lines rather than a title, so the second one cannot
        # be pushed into the first by a long file name
        fig.text(0.085, 0.950, os.path.basename(self.model.phu["path"]),
                 color=INK, fontsize=10.5, ha="left", va="bottom")
        fig.text(0.085, 0.912, self._export_note(), color=INK_FAINT,
                 fontsize=8, ha="left", va="bottom")

        cb = fig.colorbar(im, cax=cax)
        cb.set_label("Counts" + (" (log)" if log else ""),
                     color=INK_FAINT, fontsize=8.5)
        cb.ax.tick_params(colors=INK_FAINT, labelsize=7.5)
        cb.outline.set_color(LINE)

        fig.savefig(path, dpi=200, facecolor=PANEL)

    def _write_map_csv(self, path, wls, times, Z, zoomed=False):
        """The same block as a matrix: one row per delay, one column per line.

        The commented preamble records how the numbers were produced; readers
        that cannot skip it (`pandas.read_csv(..., comment="#")` can) will find
        the table starting at the first line that does not begin with "#".
        """
        m = self.model
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("# TRES map\n")
            fh.write(f'# source: {m.phu["path"]}\n')
            fh.write(f"# {self._export_note()}\n")
            fh.write(f'# instrument: {m.phu["hw_type"]} SN {m.phu["serial"]}'
                     f' - {m.phu["res_ps"]:g} ps native resolution\n')
            if zoomed:
                fh.write("# region: current zoom\n")
            fh.write("# values: counts per time bin"
                     + (", background subtracted\n" if m.bg_spec is not None else "\n"))
            fh.write("# rows: delay in ps (first column) | "
                     "columns: wavelength in nm (first row)\n")
            fh.write("time_ps\\wavelength_nm," + ",".join(f"{w:g}" for w in wls) + "\n")
            np.savetxt(fh, np.column_stack([times, Z]), delimiter=",", fmt="%.6g")

    # -- combined data export: TRES map + steady state, CSV and/or .opju ----
    def _default_data_dir(self):
        """The default home for exported data: the project's Data\\ folder,
        or Documents\\TCSPC_analysis\\Data for a frozen build (see user_dir)."""
        return os.path.join(user_dir(), "Data")

    def _map_arrays_full(self):
        """The whole map as (wavelengths, times, Z[time, wavelength]); no zoom.

        The data export archives the complete record, so unlike the image it
        ignores the current zoom.
        """
        m = self.model
        return m.wls.copy(), m.times.copy(), m.E.T.copy()

    def _steady_arrays(self):
        """Steady-state spectrum as (wavelengths, summed counts, normalised)."""
        m = self.model
        ss = m.spec_total.copy()   # NaN at masked wavelengths (a gap, kept)
        peak = float(np.nanmax(np.abs(ss))) if np.isfinite(ss).any() else 0.0
        norm = ss / peak if peak > 0 else np.zeros_like(ss)
        return m.wls.copy(), ss, norm

    @contextlib.contextmanager
    def _origin_busy(self, owner=None):
        """Around the part of an export that drives Origin.

        Origin is started and fed on the main thread, which can take many
        seconds. Meanwhile no second export may start (the buttons, here and in
        the analysis windows, come back to export_data / export_analysis, which
        return at once), and the window - and ``owner``, the analysis window
        that asked - shows a busy cursor and a line saying what is going on.
        Only pending redraws are flushed (update_idletasks): update() would
        also run whatever else is queued, in the middle of the export.
        """
        wins = [self.win] + ([owner] if owner not in (None, self.win) else [])
        info = self.var_meta.get()
        self._exporting = True
        try:
            self.btn_export.configure(state="disabled")
            self.var_meta.set("Writing the .opju - Origin is being started, "
                              "this can take a while ...")
            for w in wins:
                try:
                    w.config(cursor="watch")
                except tk.TclError:     # the analysis window was closed meanwhile
                    pass
            self.win.update_idletasks()
            yield
        finally:
            self._exporting = False
            self.btn_export.configure(state="normal")
            self.var_meta.set(info)
            for w in wins:
                try:
                    w.config(cursor="")
                except tk.TclError:         # the analysis window was closed
                    pass

    def _busy_reading(self):
        """True (with a note to the user) while Open is reading a file: what
        is on screen is about to be replaced, and a save dialog opened now
        would still be up when it is - the old name over the new data."""
        if self._loading:
            messagebox.showinfo(
                "Reading a file",
                "A file is being opened. Try again when it is on screen.", parent=self.win)
        return self._loading

    def export_data(self):
        """Export the TRES map and the steady-state spectrum, always together.

        The "CSV" and ".opju" tickboxes pick the output; at least one is
        required. Both datasets go out in full - the whole record, not the
        current zoom - so the archive does not depend on how the map is framed.
        """
        if self._exporting or self._busy_reading():
            return
        if not self.model:
            messagebox.showinfo("Nothing to export", "Load a .phu file first.", parent=self.win)
            return
        want_csv = self.var_out_csv.get()
        want_opju = self.var_out_opju.get()
        if not (want_csv or want_opju):
            messagebox.showwarning(
                "No output selected",
                "Tick at least one of CSV / .opju before exporting.", parent=self.win)
            return

        phu_base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        stem = phu_base                       # names the CSV files and the opju tabs
        data_dir = self._default_data_dir()

        # -- where the CSVs go (asked first so the opju name can follow it) --
        tres_csv = steady_csv = None
        if want_csv:
            try:
                os.makedirs(data_dir, exist_ok=True)
            except Exception:
                data_dir = ""
            chosen = filedialog.asksaveasfilename(
                title="Export data as CSV - choose a base name",
                defaultextension=".csv", initialdir=data_dir or None,
                initialfile=f"{phu_base}.csv",
                filetypes=[("CSV data", "*.csv"), ("All files", "*.*")],
                confirmoverwrite=False,     # that name is not written: see below
            )
            if not chosen:
                return
            stem = self._strip_export_suffix(
                os.path.splitext(os.path.basename(chosen))[0]) or phu_base
            folder = os.path.dirname(chosen) or data_dir or "."
            tres_csv = os.path.join(folder, f"{stem}_TRESmap.csv")
            steady_csv = os.path.join(folder, f"{stem}_steadystate.csv")
            if not self._confirm_replace([tres_csv, steady_csv], self.win):
                return

        # -- which opju to write into --
        opju_path = None
        if want_opju:
            opju_path = self._ask_opju_path(stem)
            if not opju_path:
                return

        # -- do the work --
        written = []
        on_disk = []        # for the error box, should a later step fail
        try:
            if want_csv:
                wls, times, Z = self._map_arrays_full()
                self._write_map_csv(tres_csv, wls, times, Z, zoomed=False)
                on_disk.append(tres_csv)
                self._write_steady_state_csv(steady_csv)
                on_disk.append(steady_csv)
                written.append(f"CSV\n    {tres_csv}\n    {steady_csv}")
            if want_opju:
                with self._origin_busy():
                    tabs = self._write_opju(opju_path, stem)
                written.append(f".opju  {opju_path}\n    tabs: "
                               + ", ".join(tabs))
        except Exception as exc:
            messagebox.showerror("Export failed", self._failure_text(exc, on_disk), parent=self.win)
            return

        messagebox.showinfo("Export complete", "\n\n".join(written), parent=self.win)

    @staticmethod
    def _confirm_replace(paths, parent=None):
        """Ask before writing over files that exist. The file dialog can only
        ask about the base name typed into it, which is not one of the files
        that get written ({base}_TRESmap.csv, {base}_kinetics.csv, ...)."""
        have = [p for p in paths if os.path.exists(p)]
        if not have:
            return True
        return messagebox.askyesno(
            "Replace existing files?",
            "These files already exist:\n\n" + "\n".join(have)
            + "\n\nReplace them?", parent=parent)

    @staticmethod
    def _failure_text(exc, on_disk):
        """The error box of an export: what went wrong, and - an export is
        several files - which of them were written before that."""
        text = str(exc)
        if on_disk:
            text += ("\n\nWritten before the failure:\n"
                     + "\n".join(f"    {p}" for p in on_disk))
        return text

    @staticmethod
    def _strip_export_suffix(name):
        """Drop a trailing _TRESmap / _steadystate so both files share a stem."""
        for suf in ("_TRESmap", "_steadystate", "_TRES", "_steady"):
            if name.lower().endswith(suf.lower()):
                return name[: -len(suf)]
        return name

    def _ask_opju_path(self, stem):
        """Pick an existing .opju in the Data folder, or a new name to create.

        Defaults to the project Data\\ folder. When it already holds .opju
        files the dialog opens there so one can be selected (it is opened and
        the data appended); otherwise a new file name is suggested. Overwrite
        confirmation is off - selecting an existing project means "add to it".
        """
        data_dir = self._default_data_dir()
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception:
            data_dir = ""
        has_existing = bool(glob.glob(os.path.join(data_dir, "*.opju"))) if data_dir else False
        title = ("Pick an existing .opju to add to, or type a new name"
                 if has_existing else "New .opju file")
        path = filedialog.asksaveasfilename(
            title=title, defaultextension=".opju",
            initialdir=data_dir or None,
            initialfile=("" if has_existing else f"{stem}.opju"),
            filetypes=[("Origin project", "*.opju"), ("All files", "*.*")],
            confirmoverwrite=False,   # existing project is opened & appended, not clobbered
        )
        if not path:
            return None
        if not path.lower().endswith(".opju"):
            path += ".opju"
        return os.path.normpath(path)

    @staticmethod
    def _install_hint(packages):
        """How to get missing packages: a pip line for this Python, or - in the
        .exe, where nothing can be installed - what to do instead."""
        if getattr(sys, "frozen", False):
            return ("This build of the program does not contain them, and "
                    "nothing can be added to it. Export as CSV instead, or run "
                    "the program from source (see SETUP.md).")
        return (f'Install into {sys.executable}:\n'
                f'  "{sys.executable}" -m pip install {packages}')

    @staticmethod
    def _require_pandas():
        """Lazy pandas import with a friendly install hint (opju needs it)."""
        try:
            import pandas as pd
            return pd
        except ImportError as exc:
            raise RuntimeError(
                "Writing .opju needs pandas.\n"
                + TRESViewer._install_hint("pandas")) from exc

    def _opju_write_tabs(self, opju_path, tabs):
        """Open (or create) opju_path, ensure a 'Book1' workbook, fill each tab.

        `tabs` is a list of (tab_name, fill_fn); fill_fn(ws) writes one
        worksheet (via the _origin_fill_* helpers). An existing project is
        opened and the tabs added / overwritten; a new one is created when the
        file is absent. Origin (originpro + pywin32) is only reached here, so a
        machine without it can still run everything else. Returns the tab names.
        """
        try:
            import pythoncom            # pywin32
            import originpro as op      # launches Origin on first use
        except ImportError as exc:
            raise RuntimeError(
                "Writing .opju needs OriginLab Origin plus the originpro and "
                "pywin32 packages.\n"
                + self._install_hint("originpro pywin32")) from exc

        folder = os.path.dirname(opju_path)
        exists = os.path.exists(opju_path)
        try:
            pythoncom.CoInitialize()
            com_started = True
        except Exception:
            com_started = False         # e.g. already initialised in another mode
        written = []
        try:
            if not exists and folder and not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)      # its own error, not Origin's
            try:
                if exists:
                    if not op.open(opju_path):
                        raise RuntimeError(f"Could not open the project: {opju_path}")
                else:
                    op.new()
                wb = _origin_book1(op)
            except RuntimeError:
                raise
            except Exception as exc:
                # originpro only fails here, on its first real call, when there
                # is no Origin to talk to - with a bare COM error
                raise RuntimeError(
                    "Origin could not be started or did not answer. The .opju "
                    "export needs OriginLab Origin installed on this PC; CSV "
                    "export works without it.\n\n"
                    f"Details: {type(exc).__name__}: {exc}") from exc

            for tab_name, fill_fn in tabs:
                ws, _ = _origin_sheet(wb, tab_name, fresh=not exists)
                fill_fn(ws)
                written.append(tab_name)

            if not op.save(opju_path):
                raise RuntimeError(
                    f"Could not save the project: {opju_path}\n"
                    "(is it open in Origin, or the folder read-only?)")
        finally:
            try:
                op.exit()
            except Exception:
                pass
            if com_started:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
        return written

    def _write_opju(self, opju_path, stem):
        """Write the map and spectrum into opju_path as two Book1 worksheets.

        Reuses the "Book1 + one tab per dataset" layout of csv_to_opju.py via
        _opju_write_tabs. Returns the two worksheet names.
        """
        pd = self._require_pandas()
        wls, times, Z = self._map_arrays_full()
        _, ss, norm = self._steady_arrays()
        tres_tab = f"{stem}_TRESmap"
        steady_tab = f"{stem}_steadystate"

        # column headers carry the wavelengths; _origin_fill_tres turns them
        # into per-column comments, matching the csv_to_opju layout
        tres_df = pd.DataFrame(Z, columns=[f"{w:g}" for w in wls])
        tres_df.insert(0, "time_ps", times)
        steady_df = pd.DataFrame({"Wavelength": wls, "Counts": ss, "Nor.": norm})

        return tuple(self._opju_write_tabs(opju_path, [
            (tres_tab, lambda ws: _origin_fill_tres(ws, tres_df, tres_tab)),
            (steady_tab, lambda ws: _origin_fill_steady(ws, steady_df, steady_tab)),
        ]))

    def export_analysis(self, default_base, parts, owner=None):
        """CSV / .opju export for an analysis window, driven by the main tickboxes.

        Kinetics and Global-analysis results go out through exactly the same
        path as "Export data...": tick "CSV" on the main window to get CSV
        files, tick ".opju" to add worksheet tabs to Book1 of an Origin
        project (the one already holding the TRES map, if picked).

        `parts` is a list of dicts, one per table:
            {"suffix": str,          # names the file / tab: {stem}_{suffix}
             "csv":   fn(path),      # writes that CSV
             "fill":  fn(ws)}        # fills that opju worksheet
        `owner` is the window that asked, for the busy cursor.
        """
        if self._exporting or self._busy_reading():
            return
        want_csv = self.var_out_csv.get()
        want_opju = self.var_out_opju.get()
        if not (want_csv or want_opju):
            messagebox.showwarning(
                "No output selected",
                "Tick CSV and/or .opju on the main window before exporting.", parent=(owner or self.win))
            return

        data_dir = self._default_data_dir()
        stem = default_base

        # -- every name is asked first, so cancelling one writes nothing --
        files = []
        if want_csv:
            try:
                os.makedirs(data_dir, exist_ok=True)
            except Exception:
                data_dir = ""
            chosen = filedialog.asksaveasfilename(
                title="Export results as CSV - choose a base name",
                defaultextension=".csv", initialdir=data_dir or None,
                initialfile=f"{default_base}.csv",
                filetypes=[("CSV data", "*.csv"), ("All files", "*.*")],
                confirmoverwrite=False)
            if not chosen:
                return
            base = os.path.splitext(os.path.basename(chosen))[0]
            # drop a trailing _{suffix} the picker might have kept, so all
            # parts share one stem
            for p in parts:
                suf = "_" + p["suffix"].lower()
                if base.lower().endswith(suf):
                    base = base[: -len(suf)]
                    break
            stem = base or default_base
            folder = os.path.dirname(chosen) or data_dir or "."
            files = [os.path.join(folder, f"{stem}_{p['suffix']}.csv") for p in parts]
            if not self._confirm_replace(files, owner or self.win):
                return
        opju_path = None
        if want_opju:
            opju_path = self._ask_opju_path(stem)
            if not opju_path:
                return

        written = []
        on_disk = []        # for the error box, should a later step fail
        try:
            # -- CSV: one file per part, {stem}_{suffix}.csv --
            if want_csv:
                for p, fp in zip(parts, files):
                    p["csv"](fp)
                    on_disk.append(fp)
                written.append("CSV\n    " + "\n    ".join(files))

            # -- .opju: one worksheet tab per part, in Book1 --
            if want_opju:
                with self._origin_busy(owner):
                    tabs = self._opju_write_tabs(
                        opju_path,
                        [(f"{stem}_{p['suffix']}", p["fill"]) for p in parts])
                written.append(f".opju  {opju_path}\n    tabs: " + ", ".join(tabs))
        except Exception as exc:
            messagebox.showerror("Export failed", self._failure_text(exc, on_disk), parent=(owner or self.win))
            return

        messagebox.showinfo("Export complete", "\n\n".join(written), parent=(owner or self.win))

    def _write_steady_state_csv(self, path):
        """One row per wavelength: summed counts, and the same normalised to 1.

        Same commented preamble as the map file, so both carry the settings
        the numbers were produced under and both are readable with
        `pandas.read_csv(..., comment="#")`.
        """
        m = self.model
        ss = m.spec_total
        peak = float(np.nanmax(np.abs(ss))) if np.isfinite(ss).any() else 0.0
        norm = ss / peak if peak > 0 else np.zeros_like(ss)

        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("# steady-state fluorescence spectrum\n")
            fh.write(f'# source: {m.phu["path"]}\n')
            fh.write(f"# {self._export_note()}\n")
            fh.write(f'# instrument: {m.phu["hw_type"]} SN {m.phu["serial"]}'
                     f' - {m.phu["res_ps"]:g} ps native resolution\n')
            # t_lo is -t0, which is -0.0 when t0 is off and would print as "-0"
            fh.write(f"# values: counts summed over all {m.n_t} time bins of the "
                     f"displayed record ({m.t_lo + 0.0:,.0f} to {m.t_hi:,.0f} ps)"
                     + (", background subtracted\n" if m.bg_spec is not None else "\n"))
            fh.write("# counts_norm: counts_sum divided by its peak\n")
            fh.write("wavelength_nm,counts_sum,counts_norm\n")
            np.savetxt(fh, np.column_stack([m.wls, ss, norm]),
                       delimiter=",", fmt=("%g", "%.6g", "%.6g"))
