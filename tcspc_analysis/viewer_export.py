"""The TRES tab's exports: picture, CSV, Origin project."""
import contextlib
import glob
import os
import sys

import numpy as np

from matplotlib.figure import Figure

import tkinter as tk
from tkinter import filedialog, messagebox

from .paths import user_dir
from .origin import _origin_book1, _origin_fill_steady, _origin_fill_tres, _origin_sheet
from .model import wavelength_grid
from .theme import BG, INK, INK_FAINT, LINE, PANEL, shade_wl_masks


# Numbers in the map and steady-state CSV: eight digits, like the fit exports.
# (Six lost up to 4 ps in the time column of a long record and 4e-6 of a count.)
CSV_NUMBER = "%.8g"


def _name_fonts():
    """Font families for a file name drawn into a picture: matplotlib's own
    font, then one with Hangul where this computer has one (the default font
    draws empty boxes for it)."""
    from matplotlib import font_manager
    out = ["DejaVu Sans"]
    for name in ("Malgun Gothic", "NanumGothic", "Noto Sans CJK KR", "AppleGothic"):
        try:
            font_manager.findfont(name, fallback_to_default=False)
        except Exception:
            continue
        out.append(name)
        break
    return out


class _Export:
    """Everything the TRES tab writes: the map picture, the map and
    steady-state CSV, the Origin project, and the path the fit windows'
    exports take. Part of TRESViewer (viewer.py).
    """

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
            messagebox.showinfo("No file loaded", "Load a .phu file first.", parent=self.win)
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
                        f'({os.path.basename(m.solvent["path"])})')
        return "  |  ".join(bits)

    def _extent_of(self, wls, times):
        """Pixel edges of the exported block, in data coordinates."""
        m = self.model
        dw = wavelength_grid(wls)[2] if len(wls) > 1 else \
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

        col, n_cols, _ = wavelength_grid(wls)
        if n_cols != len(wls):              # unevenly spaced: empty columns between
            wide = np.full((Z.shape[0], n_cols), np.nan)
            wide[:, col] = Z
            Z = wide
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
                 color=INK, fontsize=10.5, ha="left", va="bottom",
                 fontfamily=_name_fonts())  # a file name may be in Hangul
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
            np.savetxt(fh, np.column_stack([times, Z]), delimiter=",", fmt=CSV_NUMBER)

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

    def export_data(self):
        """Export the TRES map and the steady-state spectrum, always together.

        The "CSV" and ".opju" tickboxes pick the output; at least one is
        required. Both datasets go out in full - the whole record, not the
        current zoom - so the archive does not depend on how the map is framed.
        """
        if self._exporting or self._busy_reading():
            return
        if not self.model:
            messagebox.showinfo("No file loaded", "Load a .phu file first.", parent=self.win)
            return
        want_csv = self.var_out_csv.get()
        want_opju = self.var_out_opju.get()
        if not (want_csv or want_opju):
            messagebox.showwarning(
                "No output selected",
                "Tick at least one of CSV / .opju before exporting.", parent=self.win)
            return

        phu_base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        # names the CSV files and the opju tabs - the same with and without CSV
        stem = self._strip_export_suffix(phu_base) or phu_base
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
        """Drop a trailing _TRESmap / _steadystate - the name of a file this
        export wrote, picked as the base name - so both files share a stem.
        Nothing shorter: a record called sample_TRES.phu keeps its name."""
        for suf in ("_TRESmap", "_steadystate"):
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
        wls, times, Z = self._map_arrays_full()
        _, ss, norm = self._steady_arrays()
        tres_tab = f"{stem}_TRESmap"
        steady_tab = f"{stem}_steadystate"

        # the wavelengths become per-column comments, matching the csv_to_opju
        # layout
        return tuple(self._opju_write_tabs(opju_path, [
            (tres_tab, lambda ws: _origin_fill_tres(ws, times, Z, wls)),
            (steady_tab, lambda ws: _origin_fill_steady(ws, wls, ss, norm, steady_tab)),
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
                "Tick at least one of CSV / .opju before exporting.", parent=(owner or self.win))
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
                       delimiter=",", fmt=("%g", CSV_NUMBER, CSV_NUMBER))
