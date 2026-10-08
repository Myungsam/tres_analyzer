"""The PHU / TRES tab: its controls, the file it shows and the windows it opens.

The figure and what the mouse does on it are in viewer_figure.py, everything
that is written to disk or to Origin in viewer_export.py; TRESViewer inherits
both.
"""
import math
import os
import threading

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .phu import read_phu
from .util import short_name
from .model import TRESModel
from .theme import INK, INK_FAINT, PIN
from .viewer_figure import _MapFigure
from .viewer_export import _Export
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


class TRESViewer(_MapFigure, _Export):
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

    def _open(self, attr, make):
        """Open the window kept in ``attr`` - or raise it when it is open."""
        if not self.model:
            messagebox.showinfo("No file loaded", "Load a .phu file first.", parent=self.win)
            return
        win = getattr(self, attr)
        if win is not None and win.alive:
            win.lift_and_refresh()
            return
        setattr(self, attr, make(self))

    def open_kinetics(self):
        """Open (or raise) the single-wavelength kinetics-fit window."""
        self._open("_kinetics_win", KineticsDialog)

    def open_global_analysis(self):
        """Open (or raise) the global-analysis window."""
        self._open("_global_win", GlobalAnalysisDialog)

    def open_crop(self):
        """Open (or raise) the crop window (wavelength + time window)."""
        self._open("_crop_win", CropDialog)

    def open_mask(self):
        """Open (or raise) the wavelength-mask window."""
        self._open("_mask_win", MaskDialog)

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
        cb.bind("<<ComboboxSelected>>", lambda e: self._on_colormap())

        ttk.Label(row, text="TIME END").pack(side="left", padx=(0, 5))
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
                        command=self._on_log_color).pack(side="left", padx=(0, 12))

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

        ttk.Label(row2, text="BG WINDOW").pack(side="left", padx=(0, 5))
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
        ttk.Button(row2, text="Apply offset",
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
            info += f"  ({m.neg_frac:.0%} of bins below 0)"
        self.var_solvinfo.set(info)

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
            model = TRESModel(phu, build=False)     # built once, below, with the settings
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
        # The crop range and the masks are quoted in the nm on show. They go
        # along with the axis, so that they keep the curves they were put on:
        # a mask on a scatter line stays on that line.
        if m.crop_wl is not None:
            m.crop_wl = (m.crop_wl[0] + delta, m.crop_wl[1] + delta)
        m.masks = [(a + delta, b + delta) for a, b in m.masks]
        m.wl_offset = new
        m.rebuild()          # the wavelengths come straight off the file each time
        # the cursor follows its curve
        if at:
            self.cursor = self._cell_near(*at)

        # carry a zoom rectangle along, otherwise it would frame different lines
        if self.view:
            x0, x1, y0, y1 = self.view
            self.view = (x0 + delta, x1 + delta, y0, y1)
            self._clamp_view()
        self.redraw(full=True)
        self._tell_dialogs()

    def _busy_reading(self):
        """True (with a note to the user) while Open is reading a file: what
        is on screen is about to be replaced, and a save dialog opened now
        would still be up when it is - the old name over the new data."""
        if self._loading:
            messagebox.showinfo(
                "Reading a file",
                "A file is being opened. Try again when it is on screen.", parent=self.win)
        return self._loading
