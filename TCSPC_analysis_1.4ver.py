#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PicoHarp 300 post-processing - two tools in one window, one per file format

A tab bar at the top switches between:

    PHU  -  TRES : time-resolved emission spectroscopy from a .phu histogram
                   (the viewer described below)
    PTU  -  FLIM : fluorescence-lifetime imaging from a .ptu TTTR record
                   (intensity image + lifetime map + per-pixel decay)

The two tabs are independent - each opens its own file and does its own thing -
so this file simply hosts both under a single window and a shared dark theme.
The rest of this docstring describes the PHU/TRES tab.

TRES Viewer - PicoQuant PicoHarp 300 (.phu) time-resolved emission spectroscopy

Layout
    [ file path + Open ]
    [ controls                                     ]
    [ decay histogram      | TRES 2D map | color ]
    [                      | spectral ribbon     ]
    [ steady-state spectrum| spectrum            ]

The first curve can be treated as an IRF-only measurement: with the "First
curve is IRF" checkbox on, it is kept out of the map and only used to put t0
on its peak. A .phu header carries no IRF flag and an IRF cannot be told apart
from the wavelength grid (it often sits on it), so this is a manual choice.
When the checkbox is on, the IRF is the grey trace in the left decay panel,
scaled so its peak matches the map's brightest count.

The bottom-left panel is the steady-state fluorescence spectrum: every time
bin of the displayed record summed together, i.e. what a cw spectrometer would
have recorded. The bottom-right panel is still the spectrum at the cursor
delay only.

OFFSET shifts the whole wavelength axis by the number of nm in the box, for
spectrograph calibration. It is absolute - always measured from the values
stored in the file - so pressing the button twice does not shift twice. The
box starts at -50 nm (the usual calibration for this setup); type 0 for the
raw wavelengths in the file.

Two preprocessing tools live under "PREP", each in its own pop-up:
    Crop    keep only a rectangular (wavelength, time) window. The whole map is
            drawn once as a preview; drag two corners or type the bounds and the
            kept box updates live. Apply re-slices the pristine file, so the
            crop can be widened again (or Reset to full) without reloading. Its
            upper time edge is the same value as the main TIME SPAN box.
            The same window subtracts a solvent: "Load solvent..." takes a
            pure-solvent .phu measured on the same grid (same curves,
            wavelengths, resolution and bin count - anything else is refused),
            and SCALE (slider 0-2, or type a larger value) sets how much of it
            is taken off, bin for bin: sample - scale x solvent. The heatmap and
            the steady-state panel under it (sample, scaled solvent, subtracted)
            follow the scale as a preview; Apply hands it to the main window,
            where the "Subtract solvent" checkbox switches it on and off. While
            it is on, negatives left after the background are clipped to 0 -
            the share of clipped bins is shown, since clipping lifts weak
            signals. Opening another sample drops the solvent.
            Moving the pointer over the heatmap draws the spectrum of that one
            time bin in bold over the (faded) steady-state lines, on the
            right-hand scale: sample, scaled solvent and their difference, in
            raw counts and unclipped. Double-click pins the time, double-click
            again releases it; single clicks still set the crop box.
            To look closer, the wheel zooms the heatmap about the pointer (Ctrl:
            time only, Shift: wavelength only), a right-button drag moves it
            and "Fit" shows all of it again. "Log color" and "Log time" switch
            the colour and the time axis between linear and log; "Auto color"
            takes the colour range from the part in view instead of the whole
            map. These only change the picture, not the crop, and are
            forgotten when the window closes.
    Mask λ  set one or more wavelength bands to NaN so they drop out of the map,
            the summed spectra and the fits, shown as a hatched gap. Click the
            preview to pick From / To, Add region, and Remove / Clear from the
            list. Masks apply inside the current crop.
Both feed the whole pipeline through the model, so the map, the spectra, the
CSV / .opju export and the Kinetics / Global-analysis fits all follow along.
Opening another file closes all four pop-up windows (Crop, Mask, Kinetics,
Global analysis): each shows the file it was opened on, so export a fit you
want to keep first.

If the window stops answering for more than 5 seconds, or a step fails
without a message, where the program was at that moment is noted in
TCSPC_analysis_freeze.log next to the program - code locations and the name
of the open file, no measured data. Slow but healthy steps (starting Origin
for an .opju export) show up there too.

Move the pointer over the map to update the decay (at the cursor wavelength)
and the spectrum (at the cursor delay) in real time. Click to pin a position.

"Save map image" writes the 2D map on its own - none of the surrounding
panels - as a picture (PNG/PDF/SVG). It carries the colormap and contrast on
screen and covers whatever the map is showing, so zoom in first to save a
region.

"Export data" writes the TRES map and the steady-state spectrum together -
never one without the other. Tick "CSV", ".opju", or both:
    CSV    two files next to each other, {name}_TRESmap.csv (a matrix of one
           row per delay, one column per wavelength) and {name}_steadystate.csv
           (one row per wavelength: summed counts and the same normalised).
    .opju  an Origin project, by default in the project's Data\\ folder. If one
           already exists there you can pick it and the data is added to it as
           two worksheets; otherwise a new project is created. Needs Origin +
           originpro + pywin32 installed. The map and spectrum are written in
           full - the whole record, not the current zoom.

Analysis (top bar, each opens its own window)
    Kinetics...        fit the decay at one wavelength (or an averaged band) to
                       a sum of IRF-convolved exponentials - number of
                       components, per-component fixed/stretched flags, IRF t0
                       and FWHM, and a fit window; shows data + fit + residual.
    Global analysis... one VARPRO fit of the whole map to a shared set of
                       exponentials; shows the data / fit / residual maps, the
                       DADS and (sequential) EADS spectra, and the kinetics at
                       a chosen wavelength. Runs in a background thread with a
                       Stop button. Both tools need SciPy (pip install scipy).
    Each window's "Export results" button obeys the same "CSV" / ".opju"
    tickboxes as "Export data" above: CSV writes {stem}_kinetics.csv, or
    {stem}_DADS.csv + {stem}_EADS.csv; .opju adds the matching worksheet tabs
    to Book1 of the chosen Origin project - the same one holding the TRES map.

Mouse
    map       drag        zoom into the rectangle
              click       pin / release the cursor
              right-click reset the zoom
    colorbar  drag        set the contrast range
              right-click auto contrast

A background spectrum - the mean over a time window, by default the first
0-100 ps of the record - is subtracted from every time bin. Untick "Subtract
background" or type your own window to change it. The window is quoted on the
displayed time axis and is re-quoted automatically when t0 moves, so it always
keeps covering the same real delays.

Usage
    python TCSPC_analysis_1.4ver.py [file.phu]

An optional .phu path is loaded straight into the PHU/TRES tab; the PTU/FLIM
tab is opened from its own "Open file..." button.

Requires: numpy, matplotlib, tkinter (tkinter ships with most CPython builds;
on Debian/Ubuntu install it with `sudo apt install python3-tk`)
Optional: pandas + originpro + pywin32 for the TRES ".opju" export;
          tensorflow (2.10 on Windows/CUDA 11.2) for FLIM GPU acceleration -
          without it the FLIM tab still runs on the CPU.
"""

import faulthandler
import glob
import os
import queue
import re
import struct
import sys
import threading
import time
import traceback
import warnings

import numpy as np

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.colors import LogNorm, Normalize
from matplotlib.figure import Figure
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Rectangle
from matplotlib.ticker import EngFormatter, LogFormatterSciNotation, MaxNLocator

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


# ==========================================================================
# 1. PicoQuant .phu (PQHISTO) reader
# ==========================================================================
TY_EMPTY8       = 0xFFFF0008
TY_BOOL8        = 0x00000008
TY_INT8         = 0x10000008
TY_BITSET64     = 0x11000008
TY_COLOR8       = 0x12000008
TY_FLOAT8       = 0x20000008
TY_TDATETIME    = 0x21000008
TY_FLOAT8ARRAY  = 0x2001FFFF
TY_ANSISTRING   = 0x4001FFFF
TY_WIDESTRING   = 0x4002FFFF
TY_BINARYBLOB   = 0xFFFFFFFF


def read_phu(path):
    """Parse a .phu file into a dict of metadata plus a (ncurves, nbins) array."""
    with open(path, "rb") as fh:
        data = fh.read()

    magic = data[:8].split(b"\x00")[0].decode("ascii", "replace")
    if magic != "PQHISTO":
        raise ValueError(f'Not a PicoQuant histogram file (magic "{magic}").')
    version = data[8:16].split(b"\x00")[0].decode("ascii", "replace")

    pos, tags = 16, []
    while pos + 48 <= len(data):
        ident = data[pos:pos + 32].split(b"\x00")[0].decode("ascii", "replace")
        idx = struct.unpack_from("<i", data, pos + 32)[0]
        typ = struct.unpack_from("<I", data, pos + 36)[0]
        raw = data[pos + 40:pos + 48]
        pos += 48

        if typ in (TY_INT8, TY_BITSET64, TY_COLOR8):
            val = struct.unpack("<q", raw)[0]
        elif typ == TY_BOOL8:
            val = bool(struct.unpack("<q", raw)[0])
        elif typ in (TY_FLOAT8, TY_TDATETIME):
            val = struct.unpack("<d", raw)[0]
        elif typ == TY_EMPTY8:
            val = None
        elif typ == TY_FLOAT8ARRAY:
            n = struct.unpack("<q", raw)[0]
            val = np.frombuffer(data[pos:pos + n], "<f8")
            pos += n
        elif typ == TY_ANSISTRING:
            n = struct.unpack("<q", raw)[0]
            val = data[pos:pos + n].split(b"\x00")[0].decode("ascii", "replace")
            pos += n
        elif typ == TY_WIDESTRING:
            n = struct.unpack("<q", raw)[0]
            val = data[pos:pos + n].split(b"\x00\x00")[0].decode("utf-16-le", "replace")
            pos += n
        elif typ == TY_BINARYBLOB:
            n = struct.unpack("<q", raw)[0]
            val = None
            pos += n
        else:
            val = None

        tags.append((ident, idx, val))
        if ident == "Header_End":
            break

    def one(name):
        for ident, _, val in tags:
            if ident == name:
                return val
        return None

    def many(name):
        return {i: v for ident, i, v in tags if ident == name}

    ncurves = one("HistoResult_NumberOfCurves")
    if not ncurves:
        raise ValueError("No histogram curves found in this file.")

    nbins = many("HistResDscr_HistogramBins")[0]
    offsets = many("HistResDscr_DataOffset")
    res_ps = many("HistResDscr_MDescResolution")[0] * 1e12
    wl_map = many("ParValue0")
    integrals = many("HistResDscr_IntegralCount")

    counts = np.zeros((ncurves, nbins), dtype=np.uint32)
    for i in range(ncurves):
        off = offsets[i]
        if off is None or off + 4 * nbins > len(data):
            raise ValueError(f"Curve {i} data lies outside the file.")
        counts[i] = np.frombuffer(data[off:off + 4 * nbins], dtype="<u4")

    wls = np.array([wl_map.get(i, i) for i in range(ncurves)], dtype=float)

    return dict(
        path=path, version=version, ncurves=ncurves, nbins=nbins,
        res_ps=res_ps, counts=counts, wls=wls,
        integrals=np.array([integrals.get(i, 0) for i in range(ncurves)]),
        param_name=one("MeasDesc_Param_Name") or "Index",
        param_unit=one("MeasDesc_Param_Unit") or "",
        hw_type=one("HW_Type") or "", serial=one("HW_SerialNo") or "",
        acq_ms=one("MeasDesc_AcquisitionTime"),
        sync_rate=many("HistResDscr_SyncRate").get(0),
        comment=one("File_Comment") or "",
    )


# ==========================================================================
# 2. Helpers
# ==========================================================================
def wavelength_to_rgb(wl):
    """Approximate visible-spectrum colour of a wavelength, for the axis ribbon."""
    r = g = b = 0.0
    if 380 <= wl < 440:
        r, b = -(wl - 440) / 60.0, 1.0
    elif wl < 490:
        g, b = (wl - 440) / 50.0, 1.0
    elif wl < 510:
        g, b = 1.0, -(wl - 510) / 20.0
    elif wl < 580:
        r, g = (wl - 510) / 70.0, 1.0
    elif wl < 645:
        r, g = 1.0, -(wl - 645) / 65.0
    elif wl <= 830:
        r = 1.0

    f = 1.0
    if 380 <= wl < 420:
        f = 0.25 + 0.75 * (wl - 380) / 40.0
    elif 700 < wl <= 830:
        f = 0.25 + 0.75 * (830 - wl) / 130.0

    gamma = 0.85
    return tuple(float(np.clip(max(c, 0.0) * f, 0, 1) ** gamma) for c in (r, g, b))


def fwhm_of(trace, res_ps):
    """Peak position (ps) and FWHM (ps) of a histogram, at native resolution."""
    pk = int(np.argmax(trace))
    half = trace[pk] / 2.0
    lo = pk
    while lo > 0 and trace[lo] > half:
        lo -= 1
    hi = pk
    while hi < len(trace) - 1 and trace[hi] > half:
        hi += 1
    return pk * res_ps, (hi - lo) * res_ps


def solvent_mismatch(sample, solvent):
    """Compare a solvent .phu against the sample it is to be subtracted from.

    Returns (errors, notes), two lists of messages. The subtraction is bin for
    bin, with no resampling, so any error - a different number of curves,
    wavelength list, time resolution or bin count - means the solvent has to be
    refused. A note (a different acquisition time) is only reported: the scale
    factor can make up for it.
    """
    errors, notes = [], []
    if solvent["ncurves"] != sample["ncurves"]:
        errors.append(f'number of curves: {solvent["ncurves"]} (solvent) vs '
                      f'{sample["ncurves"]} (sample)')
    # only comparable once the counts agree - allclose cannot broadcast otherwise
    elif not np.allclose(solvent["wls"], sample["wls"], rtol=0.0, atol=1e-6):
        errors.append("wavelength list differs from the sample")
    if solvent["nbins"] != sample["nbins"]:
        errors.append(f'time bins: {solvent["nbins"]:,} (solvent) vs '
                      f'{sample["nbins"]:,} (sample)')
    if not np.isclose(solvent["res_ps"], sample["res_ps"], rtol=1e-9, atol=0.0):
        errors.append(f'time resolution: {solvent["res_ps"]:g} ps (solvent) vs '
                      f'{sample["res_ps"]:g} ps (sample)')

    acq_v, acq_s = solvent.get("acq_ms"), sample.get("acq_ms")
    if acq_v and acq_s and acq_v != acq_s:
        notes.append(f"acquisition time per curve: {acq_v / 1000:g} s (solvent) vs "
                     f"{acq_s / 1000:g} s (sample)")
    return errors, notes


def short_name(path, limit=24):
    """File name of ``path``, cut to ``limit`` characters for a status label."""
    name = os.path.basename(path)
    return name if len(name) <= limit else name[:limit - 3] + "..."


# ==========================================================================
# 2b. Origin (.opju) writing
# ==========================================================================
# These four helpers mirror TRES_data_processing/csv_to_opju.py so a project
# written here matches the ones written there: a workbook whose short name is
# "Book1", one worksheet (tab) per dataset, named after the dataset. They only
# touch the `op` (originpro) / `ws` (worksheet) objects, never import anything,
# so importing this module never pulls Origin in - that happens lazily, only
# when the user actually asks for a .opju, inside TRESViewer._write_opju.
def _origin_book1(op):
    """The workbook with short name 'Book1', created if the project has none."""
    wb = op.find_book("w", "Book1")
    if wb is not None:
        return wb
    wb = op.new_book("w")
    try:
        if wb.name != "Book1":
            wb.name = "Book1"
    except Exception:
        pass
    return wb


def _origin_sheet(wb, sheet_name):
    """Find the worksheet called sheet_name in wb, or add it. -> (sheet, created)."""
    for sh in wb:
        if sh.name == sheet_name:
            return sh, False                       # exists -> overwrite target
    sheets = list(wb)
    # a brand-new project's single empty "Sheet1" is renamed rather than kept
    if len(sheets) == 1 and sheets[0].name.lower().startswith("sheet"):
        try:
            sheets[0].name = sheet_name
            return sheets[0], True
        except Exception:
            pass
    return wb.add_sheet(sheet_name), True


def _origin_fill_tres(ws, df, tab_name):
    """TRES map into a worksheet: col A = time (ps), one column per wavelength."""
    ncols = df.shape[1]
    cols = list(df.columns)
    ws.clear()
    ws.from_df(df)
    ws.cols = ncols
    ws.set_label(0, "time", "L"); ws.set_label(0, "ps", "U"); ws.set_label(0, "", "C")
    for j in range(1, ncols):
        ws.set_label(j, "", "L")
        ws.set_label(j, "", "U")
        ws.set_label(j, str(cols[j]).strip(), "C")   # wavelength kept as a comment


def _origin_fill_steady(ws, df, tab_name):
    """Steady-state spectrum into a worksheet: Wavelength / Counts / Nor. (3 cols)."""
    data = df.iloc[:, :3].reset_index(drop=True)
    ws.clear()
    ws.from_df(data)
    ws.cols = 3
    ws.set_label(0, "Wavelength", "L"); ws.set_label(0, "nm", "U");    ws.set_label(0, "", "C")
    ws.set_label(1, "Counts", "L");     ws.set_label(1, "nm", "U");    ws.set_label(1, tab_name, "C")
    ws.set_label(2, "Nor.", "L");       ws.set_label(2, "a. u.", "U"); ws.set_label(2, tab_name, "C")


def _origin_fill_table(ws, df, col_specs):
    """Generic: put df into ws, then label each column (Long name, Units, Comment).

    col_specs is a list of (long_name, unit, comment) aligned with df.columns.
    Used by the Kinetics / Global-analysis exports, whose tables do not fit the
    fixed TRES-map / steady-state shapes above.
    """
    ws.clear()
    ws.from_df(df)
    ws.cols = df.shape[1]
    for j, (lname, unit, comment) in enumerate(col_specs):
        ws.set_label(j, lname, "L")
        ws.set_label(j, unit, "U")
        ws.set_label(j, comment, "C")


# ==========================================================================
# 2c. FLIM PTU (T3 TTTR) processing - the PTU tab
# ==========================================================================
# Ported from FLIM_Post_Process/flim_viewer.py. PicoHarp 300 T3 records are
# 32-bit: channel (31..28), dtime (27..16, the 12-bit lifetime bin), nsync
# (15..0). channel 1 is a photon; channel 15 is a "special" whose low dtime
# nibble is a marker - overflow (0), pixel clock (1) or line end (2) - that
# drives the scan position. The state machine below turns the record stream
# into a per-pixel decay cube, exactly as the standalone viewer did.
NX_DEFAULT = 99          # X pixels (pixel-clock based)
NY_DEFAULT = 100         # Y lines
NBINS_DEFAULT = 4096     # dtime is 12-bit -> at most 4096 bins

# TensorFlow is optional and, where installed, slow to import (it pulls CUDA),
# so it is never imported at start-up. detect_gpu() runs once in a background
# thread the first time the FLIM tab needs it and fills these in; the tab polls
# _GPU_DONE and refreshes its panel when the answer arrives.
tf = None
GPU_AVAILABLE = False
GPU_NAME = "detecting..."
TF_VERSION = "?"
_GPU_DONE = threading.Event()
_GPU_STARTED = threading.Event()


def detect_gpu():
    """Import TensorFlow (if present) and record whether a GPU is usable.

    Safe to call from a worker thread; sets globals and _GPU_DONE when done.
    Missing TensorFlow is not an error - the FLIM tab just stays on the CPU.
    """
    global tf, GPU_AVAILABLE, GPU_NAME, TF_VERSION
    try:
        import tensorflow as _tf
        tf = _tf
        TF_VERSION = getattr(tf, "__version__", "?")
        try:
            gpus = tf.config.list_physical_devices("GPU")
        except Exception:
            gpus = []
        if gpus:
            try:
                details = tf.config.experimental.get_device_details(gpus[0])
                GPU_NAME = details.get("device_name", gpus[0].name)
            except Exception:
                GPU_NAME = gpus[0].name
            try:                                   # don't grab all of VRAM
                for g in gpus:
                    tf.config.experimental.set_memory_growth(g, True)
            except Exception:
                pass
            GPU_AVAILABLE = True
        else:
            GPU_NAME = "none"
    except ImportError:
        tf = None
        TF_VERSION = "not installed"
        GPU_NAME = "none"
    finally:
        _GPU_DONE.set()


def start_gpu_detection():
    """Kick off detect_gpu() in a background thread, at most once."""
    if not _GPU_STARTED.is_set():
        _GPU_STARTED.set()
        threading.Thread(target=detect_gpu, daemon=True).start()


def load_ptu_records(filepath):
    """Read a .ptu as a little-endian uint32 record array, skipping any header.

    Files saved as raw TTTR start straight at the records; a standard PQTTTR
    header, if present, is skipped up to just past its Header_End tag.
    """
    with open(filepath, "rb") as f:
        raw = f.read()
    if raw[:6] == b"PQTTTR":
        idx = raw.find(b"Header_End")
        if idx != -1:
            raw = raw[idx + 48:]                   # past the 48-byte Header_End tag
    n = (len(raw) // 4) * 4
    return np.frombuffer(raw[:n], dtype="<u4")


def process_records_cpu(records, nx=NX_DEFAULT, ny=NY_DEFAULT,
                        n_bins=NBINS_DEFAULT, progress_cb=None):
    """State machine over the records -> decay cube hist[nx, ny, n_bins]."""
    hist = np.zeros((nx, ny, n_bins), dtype=np.uint32)
    x_pixel = 0
    y_line = 0
    direction = True          # True = forward, False = reverse
    line_active = False

    total = len(records)
    step = max(1, total // 100)

    for i in range(total):
        rec = int(records[i])
        ch = (rec >> 28) & 0xF
        dt = (rec >> 16) & 0x0FFF
        if ch == 15:                              # special record - a marker
            m = dt & 0x0F
            if m == 1:                            # pixel clock -> advance x
                if not line_active:
                    line_active = True
                    x_pixel = 0 if direction else (nx - 1)
                else:
                    x_pixel += 1 if direction else -1
            elif m == 2:                          # line end -> advance y, flip
                y_line += 1
                direction = not direction
                line_active = False
            # m == 0 is an overflow; nsync is unused here so nothing to do
        elif ch == 1:                             # photon
            if 0 <= x_pixel < nx and 0 <= y_line < ny and 0 <= dt < n_bins:
                hist[x_pixel, y_line, dt] += 1
        if progress_cb is not None and (i % step == 0):
            progress_cb(i / total)

    if progress_cb is not None:
        progress_cb(1.0)
    return hist


def process_records_gpu(records, nx=NX_DEFAULT, ny=NY_DEFAULT,
                        n_bins=NBINS_DEFAULT, progress_cb=None):
    """Same result as the CPU path, with the histogram accumulated on the GPU.

    The scan position depends on record order, so the per-photon (x, y, dtime)
    indices are still found on the CPU; only the large bincount is offloaded.
    """
    ch_all = (records >> 28) & 0xF
    dt_all = (records >> 16) & 0x0FFF

    x_pixel = 0
    y_line = 0
    direction = True
    line_active = False
    photon_x, photon_y, photon_d = [], [], []

    total = len(records)
    step = max(1, total // 100)

    for i in range(total):
        ch = int(ch_all[i])
        dt = int(dt_all[i])
        if ch == 15:
            m = dt & 0x0F
            if m == 1:
                if not line_active:
                    line_active = True
                    x_pixel = 0 if direction else (nx - 1)
                else:
                    x_pixel += 1 if direction else -1
            elif m == 2:
                y_line += 1
                direction = not direction
                line_active = False
        elif ch == 1:
            if 0 <= x_pixel < nx and 0 <= y_line < ny and 0 <= dt < n_bins:
                photon_x.append(x_pixel)
                photon_y.append(y_line)
                photon_d.append(dt)
        if progress_cb is not None and (i % step == 0):
            progress_cb(0.5 * i / total)

    total_bins = nx * ny * n_bins
    with tf.device("/GPU:0"):
        px = tf.constant(photon_x, dtype=tf.int64)
        py = tf.constant(photon_y, dtype=tf.int64)
        pd = tf.constant(photon_d, dtype=tf.int64)
        flat_idx = (px * ny + py) * n_bins + pd
        counts = tf.math.bincount(tf.cast(flat_idx, tf.int32),
                                  minlength=total_bins, maxlength=total_bins,
                                  dtype=tf.int32)
        hist = tf.reshape(counts, (nx, ny, n_bins)).numpy().astype(np.uint32)

    if progress_cb is not None:
        progress_cb(1.0)
    return hist


def compute_intensity(hist):
    """Intensity image: photons per pixel (sum over the dtime axis)."""
    return hist.sum(axis=2)


def compute_lifetime_map(hist, min_photons=10):
    """Lifetime map: mean arrival bin minus the global peak bin.

    Pixels with fewer than min_photons are left NaN so they drop out of the
    image rather than showing meaningless noise.
    """
    nx, ny, n_bins = hist.shape
    bins = np.arange(n_bins)
    total_decay = hist.sum(axis=(0, 1))
    peak_bin = int(np.argmax(total_decay)) if total_decay.sum() > 0 else 0

    totals = hist.sum(axis=2)
    weighted = (hist * bins[None, None, :]).sum(axis=2)
    with np.errstate(divide="ignore", invalid="ignore"):
        mean_t = np.where(totals > 0, weighted / np.maximum(totals, 1), 0.0)
    lifetime = np.where(totals >= min_photons, mean_t - peak_bin, np.nan)
    return lifetime, peak_bin


# ==========================================================================
# 2d. Kinetics + Global-analysis kernels (ported from TA_Analyzer_rev5/ta_core)
# ==========================================================================
# These are the numerical heart of the two analysis windows: an IRF-convolved
# multi-exponential model, a single-trace fit (Kinetics) and a VARPRO global
# fit over the whole map (Global analysis).  They are lifted almost verbatim
# from ta_core.py but made self-contained - scipy is imported lazily so the
# viewer still starts (and the FLIM tab still runs) on a machine without it;
# the TensorFlow "backend" of the original global fit is dropped for plain
# NumPy.  Time is in ps here, matching TRESModel.times.
_erfc = _erfcx = _minimize = _least_squares = None


def _ensure_scipy():
    """Load scipy on first use; raise a friendly error if it is missing."""
    global _erfc, _erfcx, _minimize, _least_squares
    if _erfc is None:
        try:
            from scipy.special import erfc, erfcx
            from scipy.optimize import minimize, least_squares
        except ImportError as exc:      # pragma: no cover - depends on env
            raise RuntimeError(
                "The Kinetics and Global-analysis tools need SciPy.\n"
                "Install it with:  pip install scipy") from exc
        _erfc, _erfcx = erfc, erfcx
        _minimize, _least_squares = minimize, least_squares


def exp_irf_conv(t, tau, t0, fwhm):
    """Exponential decay convolved with a Gaussian IRF (given as FWHM).

    Evaluated piecewise to dodge overflow: the asymptotic form far past t0,
    the full erfcx formula near t0, ~0 far before it. tau = +inf gives the
    step response, used for the constant (tau = infinity) offset term.
    """
    _ensure_scipy()                         # erfc / erfcx come from here
    sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
    t_arr = np.asarray(t, float).ravel()
    dt = t_arr - t0
    c = np.zeros_like(dt)

    if np.isinf(tau):
        with np.errstate(invalid="ignore"):
            c = 0.5 * _erfc(-dt / (sigma * np.sqrt(2.0)))
        c[~np.isfinite(c)] = 0.0
        return c

    thresh = 5.0 * sigma + sigma ** 2 / tau
    near = np.abs(dt) <= thresh
    far_pos = dt > thresh

    if np.any(far_pos):
        dtf = dt[far_pos]
        c[far_pos] = np.exp(sigma ** 2 / (2.0 * tau ** 2) - dtf / tau)

    if np.any(near):
        dtn = dt[near]
        B = (sigma / tau - dtn / sigma) / np.sqrt(2.0)
        with np.errstate(invalid="ignore", over="ignore"):
            c[near] = 0.5 * np.exp(-dtn ** 2 / (2.0 * sigma ** 2)) * _erfcx(B)

    c[~np.isfinite(c)] = 0.0
    return c


def stretched_irf_conv(t, tau, beta, t0, fwhm, mode="numerical"):
    """Stretched exp exp(-((t-t0)/tau)^beta), optional Gaussian-IRF convolution.

    mode='skip' ignores the IRF (caller masks data within ~3 sigma of t0);
    mode='numerical' convolves on a fine uniform grid.
    """
    t = np.asarray(t, float).ravel()
    dt = t - t0
    out = np.zeros_like(dt)
    if (not np.isfinite(tau)) or tau <= 0 or \
       (not np.isfinite(beta)) or beta <= 0:
        return out

    def bare(x):
        with np.errstate(invalid="ignore"):
            xx = np.maximum(x, 0.0)
            return np.exp(-(xx / tau) ** beta) * (x >= 0).astype(float)

    mode = mode.lower()
    if mode == "skip":
        out = bare(dt)
    elif mode == "numerical":
        sigma = fwhm / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        if not np.isfinite(sigma) or sigma <= 0:
            return bare(dt)
        step = min(0.2 * sigma, 0.05 * tau)
        if not np.isfinite(step) or step <= 0:
            step = 0.01
        t_lo = float(t.min()) - 5.0 * sigma
        t_hi = float(t.max()) + 5.0 * sigma
        n_grid = int(np.ceil((t_hi - t_lo) / step)) + 1
        if n_grid > 200_000:
            step = (t_hi - t_lo) / 200_000.0
            n_grid = 200_001
        t_grid = t_lo + np.arange(n_grid) * step
        f_grid = bare(t_grid - t0)
        n_k = int(np.ceil(5.0 * sigma / step))
        kx = np.arange(-n_k, n_k + 1) * step
        irf = np.exp(-kx ** 2 / (2.0 * sigma ** 2))
        irf /= irf.sum()
        c_grid = np.convolve(f_grid, irf, mode="same")
        out = np.interp(t, t_grid, c_grid, left=0.0, right=0.0)
    else:
        raise ValueError(f"stretched_irf_conv: unknown mode {mode!r}")

    out[~np.isfinite(out)] = 0.0
    return out


def build_ga_basis(t, tau_vec, t0, fwhm, has_inf):
    """(N_t x k) basis of IRF-convolved plain exponentials."""
    tau_vec = np.asarray(tau_vec, float).ravel()
    k = len(tau_vec) + (1 if has_inf else 0)
    t_arr = np.asarray(t, float).ravel()
    C = np.zeros((len(t_arr), k))
    for j, tau in enumerate(tau_vec):
        C[:, j] = exp_irf_conv(t_arr, tau, t0, fwhm)
    if has_inf:
        C[:, -1] = exp_irf_conv(t_arr, np.inf, t0, fwhm)
    return C


def _nm_fatol(data):
    """Nelder-Mead's stop tolerance on the loss, for a fit of ``data``.

    The loss is a sum of squared residuals, so its size follows the data: about
    1e-6 for absorbance changes, 1e8 and more for photon counts. A fixed 1e-10
    is then far below the rounding noise of the loss itself; the simplex could
    only stop when all its corners happened to give the very same number, and
    otherwise ran on to maxiter with nothing left to gain (seconds per fit,
    and which of the two happened changed with the numpy / scipy build).
    A 1e-12th of the data's own sum of squares is still well beyond the
    precision of any fitted parameter, and never tighter than the old 1e-10
    for small-valued data. Only finite values count, as in the loss.
    """
    data = np.asarray(data, float)
    data = data[np.isfinite(data)]
    return max(1e-10, 1e-12 * float(np.sum(np.square(data))))


def _lsqminnorm(A, B):
    """Minimum-norm least-squares solve (numpy.linalg.lstsq wrapper)."""
    X, *_ = np.linalg.lstsq(A, B, rcond=None)
    return X


class GlobalAnalysisStopped(Exception):
    """Raised inside the GA objective when stop_check() reports a cancel."""


def fit_global_analysis(D, t, tau_init, t0_init, fwhm_init,
                        tau_fixed, t0_fixed, fwhm_fixed, has_inf,
                        beta_init=None, beta_fixed=None, stretch_on=None,
                        irf_mode="numerical", stop_check=None, method="trf"):
    """VARPRO global fit of D (M wavelengths x N delays) to a shared set of
    IRF-convolved (optionally stretched) exponentials.

    Non-linear params (tau, beta, t0, FWHM) are optimised (TRF or Nelder-Mead);
    the per-wavelength amplitudes A are solved by linear least-squares inside
    every objective call.  stop_check(), if given, is polled each iteration and
    raising GlobalAnalysisStopped aborts cleanly.  Returns a dict with keys
    tau, beta, stretch_on, t0, fwhm, A (M x k), fit (M x N), info.
    """
    _ensure_scipy()
    tau_init = np.asarray(tau_init, float).ravel()
    tau_fixed = np.asarray(tau_fixed, bool).ravel()
    t_arr = np.asarray(t, float).ravel()
    D = np.asarray(D, float)
    M, N = D.shape

    n_nl = len(tau_init)
    if beta_init is None:
        beta_init = np.ones(n_nl)
    if stretch_on is None:
        stretch_on = np.zeros(n_nl, dtype=bool)
    if beta_fixed is None:
        beta_fixed = np.zeros(n_nl, dtype=bool)
    beta_init = np.asarray(beta_init, float).ravel()
    stretch_on = np.asarray(stretch_on, bool).ravel()
    beta_fixed = np.asarray(beta_fixed, bool).ravel()
    if (beta_init.size != n_nl or stretch_on.size != n_nl
            or beta_fixed.size != n_nl):
        raise ValueError("beta_init / stretch_on / beta_fixed length "
                         "must match tau_init")
    any_stretched = bool(stretch_on.any())

    tau_cur = tau_init.copy()
    beta_cur = beta_init.copy()
    t0_cur = float(t0_init)
    fwhm_cur = float(fwhm_init)
    idx_free_tau = np.where(~tau_fixed)[0]
    n_free_tau = len(idx_free_tau)
    idx_free_beta = np.where(stretch_on & ~beta_fixed)[0]
    n_free_beta = len(idx_free_beta)

    x0_list = []
    if n_free_tau > 0:
        x0_list.extend(np.log(tau_init[idx_free_tau]).tolist())
    if n_free_beta > 0:
        x0_list.extend(np.log(np.maximum(beta_init[idx_free_beta], 1e-3)).tolist())
    if not t0_fixed:
        x0_list.append(float(t0_init))
    if not fwhm_fixed:
        x0_list.append(float(np.log(fwhm_init)))
    x0 = np.array(x0_list, float)

    skip_mask_active = any_stretched and irf_mode.lower() == "skip"

    def build_basis_local(tau_v, beta_v, t0_v, fwhm_v):
        if not any_stretched:
            return build_ga_basis(t_arr, tau_v, t0_v, fwhm_v, has_inf)
        n_cols = n_nl + (1 if has_inf else 0)
        C = np.zeros((N, n_cols))
        for j in range(n_nl):
            if stretch_on[j]:
                C[:, j] = stretched_irf_conv(
                    t_arr, tau_v[j], beta_v[j], t0_v, fwhm_v, irf_mode)
            else:
                C[:, j] = exp_irf_conv(t_arr, tau_v[j], t0_v, fwhm_v)
        if has_inf:
            C[:, -1] = exp_irf_conv(t_arr, np.inf, t0_v, fwhm_v)
        return C

    def objective(x):
        nonlocal tau_cur, beta_cur, t0_cur, fwhm_cur
        if stop_check is not None and stop_check():
            raise GlobalAnalysisStopped()
        idx = 0
        for j in range(n_free_tau):
            tau_cur[idx_free_tau[j]] = np.exp(x[idx]); idx += 1
        for j in range(n_free_beta):
            beta_cur[idx_free_beta[j]] = np.exp(x[idx]); idx += 1
        if not t0_fixed:
            t0_cur = float(x[idx]); idx += 1
        if not fwhm_fixed:
            fwhm_cur = float(np.exp(x[idx])); idx += 1

        sigma_cur = fwhm_cur / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        t_span = t_arr.max() - t_arr.min()
        if (np.any(tau_cur < sigma_cur / 4.0) or
                np.any(tau_cur > 100.0 * t_span) or
                fwhm_cur <= 0 or fwhm_cur > t_span or
                (any_stretched and (np.any(beta_cur[stretch_on] <= 0)
                                    or np.any(beta_cur[stretch_on] > 2)))):
            k_cols = n_nl + (1 if has_inf else 0)
            return 1e30, np.zeros((M, k_cols)), np.zeros((M, N))

        C = build_basis_local(tau_cur, beta_cur, t0_cur, fwhm_cur)
        col_norms = np.sqrt(np.nansum(C ** 2, axis=0))
        if np.any(col_norms < 1e-12) or not np.all(np.isfinite(C)):
            return 1e30, np.zeros((M, C.shape[1])), np.zeros((M, N))

        col_mask = np.ones(N, dtype=bool)
        if skip_mask_active:
            col_mask = t_arr > (t0_cur + 3.0 * sigma_cur)
            if int(col_mask.sum()) <= C.shape[1]:
                col_mask = np.ones(N, dtype=bool)

        k_cols = C.shape[1]
        As = np.zeros((M, k_cols))
        fit_M = np.zeros((M, N))
        if np.all(np.isfinite(D)):
            Cs = C[col_mask, :]
            Ds = D[:, col_mask]
            try:
                At = _lsqminnorm(Cs, Ds.T)         # (k x M)
            except GlobalAnalysisStopped:
                raise
            except Exception:
                return 1e30, As, fit_M
            if not np.all(np.isfinite(At)) or np.max(np.abs(At)) > 1e10:
                return 1e30, As, fit_M
            As = At.T
            fit_M = As @ C.T
        else:
            for ii in range(M):
                row = D[ii, :]
                mm = np.isfinite(row) & col_mask
                if np.count_nonzero(mm) <= k_cols:
                    continue
                try:
                    ai = _lsqminnorm(C[mm, :], row[mm])
                except GlobalAnalysisStopped:
                    raise
                except Exception:
                    continue
                if not np.all(np.isfinite(ai)) or np.max(np.abs(ai)) > 1e8:
                    continue
                As[ii, :] = ai
                fit_M[ii, :] = (ai.reshape(1, -1) @ C.T).ravel()

        R = D - fit_M
        if skip_mask_active:
            R = R[:, col_mask]
        mfin = np.isfinite(R)
        loss = float(np.sum(R[mfin] ** 2)) if np.any(mfin) else 1e30
        return loss, As, fit_M

    method_lc = str(method).lower()
    if method_lc in ("trf", "levenberg-marquardt", "lm", "least_squares"):
        method_used = "trf"
    elif method_lc in ("nm", "nelder-mead", "neldermead", "nelder_mead"):
        method_used = "nm"
    else:
        raise ValueError(f"fit_global_analysis: unknown method {method!r}")

    if x0.size == 0:
        loss, A_out, fit_out = objective(np.array([]))
        iters = 0
        n_fev = 1
        init_loss = loss
    elif method_used == "trf":
        init_loss, _, _ = objective(x0)

        def _residuals(x):
            _, _, fit_M = objective(x)
            R = D - fit_M
            R = np.where(np.isfinite(R), R, 0.0)
            if skip_mask_active:
                cm = t_arr > (t0_cur + 3.0 * fwhm_cur / (2.0
                              * np.sqrt(2.0 * np.log(2.0))))
                if cm.any() and cm.sum() < N:
                    R[:, ~cm] = 0.0
            return R.ravel()

        res = _least_squares(_residuals, x0, method="trf",
                             xtol=1e-8, ftol=1e-10, gtol=1e-8, max_nfev=5000)
        loss, A_out, fit_out = objective(res.x)
        iters = int(getattr(res, "nfev", 0))
        n_fev = int(getattr(res, "nfev", 0))
    else:
        init_loss, _, _ = objective(x0)
        res = _minimize(lambda x: objective(x)[0], x0, method="Nelder-Mead",
                        options={"xatol": 1e-8, "fatol": _nm_fatol(D),
                                 "maxiter": 5000, "maxfev": 20000,
                                 "disp": False})
        loss, A_out, fit_out = objective(res.x)
        iters = int(res.nit)
        n_fev = int(getattr(res, "nfev", iters))

    info = {
        "rss": loss, "iters": iters, "nfev": n_fev, "method": method_used,
        "rms": float(np.sqrt(loss / D.size)),
        "initialLoss": init_loss,
        "initialRMS": float(np.sqrt(init_loss / D.size)),
        "irf_mode": irf_mode if any_stretched else "closed-form",
    }
    return {
        "tau": tau_cur.copy(), "beta": beta_cur.copy(),
        "stretch_on": stretch_on.copy(), "t0": t0_cur, "fwhm": fwhm_cur,
        "A": A_out, "fit": fit_out, "info": info,
    }


def compute_eads_from_dads(DADS, tau_vec, has_inf):
    """Convert parallel DADS to sequential EADS (1 -> 2 -> ... -> N).

    Species are ordered by ascending tau. Returns (EADS, tau_sorted, Bmat).
    """
    tau_vec = np.asarray(tau_vec, float).ravel()
    sort_idx = np.argsort(tau_vec)
    tau_sorted = tau_vec[sort_idx]
    n_decay = len(tau_sorted)

    if has_inf:
        k_vec = np.concatenate([1.0 / tau_sorted, [0.0]])
        perm = np.concatenate([sort_idx, [n_decay]])
    else:
        k_vec = 1.0 / tau_sorted
        perm = sort_idx

    n = len(k_vec)
    Bmat = np.zeros((n, n))
    for ii in range(n):
        prod_k = 1.0 if ii == 0 else float(np.prod(k_vec[:ii]))
        for jj in range(ii + 1):
            denom = 1.0
            for mm in range(ii + 1):
                if mm != jj:
                    denom *= (k_vec[mm] - k_vec[jj])
            Bmat[ii, jj] = prod_k / denom

    DADS_perm = DADS[:, perm]
    try:
        EADS = np.linalg.solve(Bmat.T, DADS_perm.T).T
        if not np.all(np.isfinite(EADS)):
            raise np.linalg.LinAlgError("non-finite")
    except np.linalg.LinAlgError:
        EADS = DADS_perm @ np.linalg.pinv(Bmat)
    return EADS, tau_sorted, Bmat


def fit_single_trace(t, y, *, tau_init, tau_fixed,
                     beta_init=None, beta_fixed=None, stretch_on=None,
                     t0_init=0.0, t0_fixed=True,
                     fwhm_init=0.15, fwhm_fixed=True,
                     has_inf=False, irf_mode="skip"):
    """Fit one kinetic trace y(t) to a sum of (possibly stretched) exponentials
    convolved with a Gaussian IRF.  Linear amplitudes solved by VARPRO, the
    non-linear params by Nelder-Mead over a log parameterisation.  Returns a
    dict with keys tau, beta, t0, fwhm, A, fit, residual, info.
    """
    _ensure_scipy()
    t = np.asarray(t, float).ravel()
    y = np.asarray(y, float).ravel()
    if t.shape != y.shape:
        raise ValueError(f"shape mismatch: t {t.shape} vs y {y.shape}")

    n_nl = int(len(tau_init))
    tau_init = np.asarray(tau_init, float).ravel()
    tau_fixed = np.asarray(tau_fixed, bool).ravel()
    if beta_init is None:
        beta_init = np.ones(n_nl)
    if beta_fixed is None:
        beta_fixed = np.zeros(n_nl, dtype=bool)
    if stretch_on is None:
        stretch_on = np.zeros(n_nl, dtype=bool)
    beta_init = np.asarray(beta_init, float).ravel()
    beta_fixed = np.asarray(beta_fixed, bool).ravel()
    stretch_on = np.asarray(stretch_on, bool).ravel()

    mask = np.isfinite(y)
    if irf_mode.lower() == "skip" and stretch_on.any():
        sig = fwhm_init / (2.0 * np.sqrt(2.0 * np.log(2.0)))
        mask = mask & (t > t0_init + 3.0 * sig)

    n_min = n_nl + (1 if has_inf else 0) + 1
    if int(mask.sum()) < n_min:
        raise ValueError(
            f"Not enough data points for the fit "
            f"(need >= {n_min}, have {int(mask.sum())} after masking).")

    free_tau_idx = np.where(~tau_fixed)[0]
    free_beta_idx = np.where(stretch_on & ~beta_fixed)[0]

    x0 = []
    if free_tau_idx.size:
        x0.extend(np.log(np.maximum(tau_init[free_tau_idx], 1e-12)))
    if free_beta_idx.size:
        x0.extend(np.log(np.maximum(beta_init[free_beta_idx], 1e-3)))
    if not t0_fixed:
        x0.append(float(t0_init))
    if not fwhm_fixed:
        x0.append(float(np.log(max(fwhm_init, 1e-12))))
    x0 = np.asarray(x0, float)

    cur = {"tau": tau_init.copy(), "beta": beta_init.copy(),
           "t0": float(t0_init), "fwhm": float(fwhm_init)}
    t_span = float(t.max() - t.min()) if t.size else 1.0
    n_cols = n_nl + (1 if has_inf else 0)

    def unpack(x):
        i = 0
        if free_tau_idx.size:
            cur["tau"][free_tau_idx] = np.exp(x[i:i + free_tau_idx.size])
            i += free_tau_idx.size
        if free_beta_idx.size:
            cur["beta"][free_beta_idx] = np.exp(x[i:i + free_beta_idx.size])
            i += free_beta_idx.size
        if not t0_fixed:
            cur["t0"] = float(x[i]); i += 1
        if not fwhm_fixed:
            cur["fwhm"] = float(np.exp(x[i])); i += 1

        if (not np.all(np.isfinite(cur["tau"])) or np.any(cur["tau"] <= 0)
                or not np.all(np.isfinite(cur["beta"]))
                or np.any(cur["beta"] <= 0) or np.any(cur["beta"] > 2)
                or not np.isfinite(cur["fwhm"]) or cur["fwhm"] <= 0
                or cur["fwhm"] > t_span):
            return (np.zeros(n_cols), np.zeros_like(t))

        Mb = np.zeros((t.size, n_cols))
        for j in range(n_nl):
            if stretch_on[j]:
                Mb[:, j] = stretched_irf_conv(
                    t, cur["tau"][j], cur["beta"][j],
                    cur["t0"], cur["fwhm"], irf_mode)
            else:
                Mb[:, j] = exp_irf_conv(t, cur["tau"][j], cur["t0"], cur["fwhm"])
        if has_inf:
            Mb[:, -1] = exp_irf_conv(t, np.inf, cur["t0"], cur["fwhm"])

        try:
            A = _lsqminnorm(Mb[mask, :], y[mask])
        except Exception:
            A = np.zeros(n_cols)
        if not np.all(np.isfinite(A)):
            A = np.zeros(n_cols)
        return A, Mb @ A

    def loss(x):
        _, fv = unpack(x)
        r = (y - fv)[mask]
        L = float(np.sum(r ** 2))
        return L if np.isfinite(L) else 1e30

    if x0.size:
        res = _minimize(loss, x0, method="Nelder-Mead",
                        options={"xatol": 1e-8, "fatol": _nm_fatol(y[mask]),
                                 "maxiter": 5000, "maxfev": 20000,
                                 "disp": False})
        A_final, fit_v = unpack(res.x)
        iters = int(res.nit)
        fval = float(res.fun)
    else:
        A_final, fit_v = unpack(np.array([]))
        iters = 0
        fval = float(np.sum(((y - fit_v)[mask]) ** 2))

    res_v = y - fit_v
    res_v[~mask] = np.nan
    rms = float(np.sqrt(np.nanmean(res_v[mask] ** 2))) if mask.any() else 0.0
    return {
        "tau": cur["tau"].copy(), "beta": cur["beta"].copy(),
        "t0": cur["t0"], "fwhm": cur["fwhm"], "A": A_final,
        "fit": fit_v, "residual": res_v,
        "info": {"iters": iters, "fval": fval, "rms": rms,
                 "mask": mask, "irf_mode": irf_mode},
    }


# ==========================================================================
# 3. Model - rebinning and slicing
# ==========================================================================
class TRESModel:
    """Holds the file and the rebinned display matrix used by every panel."""

    # Every setting __init__ creates, in one place: copy_settings_from() walks
    # this, so a preview model built from the live one cannot miss any.
    SETTINGS = ("rebin", "t_max_ps", "first_is_irf", "t0_align", "bg_sub",
                "bg_lo_ps", "bg_hi_ps", "wl_offset", "t_min_ps", "crop_wl",
                "masks", "solvent", "solvent_scale", "solvent_sub")

    def __init__(self, phu):
        self.phu = phu
        self.rebin = 4
        self.t_max_ps = self.t_data_ps   # as far as the counts go, until changed
        self.first_is_irf = True
        self.t0_align = False
        self.bg_sub = True
        self.bg_lo_ps = 0.0
        self.bg_hi_ps = 100.0
        self.wl_offset = 0.0     # nm added to every wavelength in the file
        # -- preprocessing (Crop dialog + Mask lambda dialog) ------------------
        # A crop keeps only a rectangular (wavelength, time) window; t_max_ps
        # above is its upper time edge, t_min_ps its lower one. crop_wl limits
        # the wavelength window (in offset-applied nm, i.e. what the user sees),
        # None meaning "full". masks is a list of (wl1, wl2) nm regions whose
        # rows are set to NaN so they drop out of the map, the spectra and the
        # fits. All operate on the pristine phu arrays, so any of them can be
        # widened or cleared again without reloading the file.
        self.t_min_ps = 0.0
        self.crop_wl = None
        self.masks = []
        # -- solvent subtraction (picked and scaled in the Crop dialog) --------
        # solvent is the phu dict of a pure-solvent record taken on the same
        # grid as the sample. While solvent_sub is on, solvent_scale times it
        # is subtracted bin for bin right after rebinning, and the negatives
        # left in the final E are clipped to 0.
        self.solvent = None
        self.solvent_scale = 1.0
        self.solvent_sub = False
        self.rebuild()

    @property
    def solvent_active(self):
        return self.solvent is not None and self.solvent_sub

    def copy_settings_from(self, other):
        """Take every setting of ``other`` (same file); rebuild() is the caller's."""
        for name in self.SETTINGS:
            setattr(self, name, getattr(other, name))
        self.masks = list(other.masks)

    # -- geometry ---------------------------------------------------------
    @property
    def t_full_ps(self):
        """Length of the whole measured record, in ps."""
        return self.phu["nbins"] * self.phu["res_ps"]

    @property
    def t_data_ps(self):
        """Length of the part of the record that holds counts, in ps.

        A histogram is only filled inside the sync period, so past the last
        photon every bin is an exact zero on every curve: no data was taken
        there, and showing it only squeezes the map. This is the default time
        span; the entry box still reaches t_full_ps if you want the tail.
        Falls back to the whole record when the file is empty everywhere.
        """
        hit = np.nonzero(self.phu["counts"].any(axis=0))[0]
        if not len(hit):
            return self.t_full_ps
        return min((int(hit[-1]) + 1) * self.phu["res_ps"], self.t_full_ps)

    @property
    def dt_ps(self):
        return self.rebin * self.phu["res_ps"]

    @property
    def t0(self):
        return self.irf_peak_ps if (self.t0_align and self.irf is not None) else 0.0

    @property
    def times(self):
        """Display-bin centres, in ps, already shifted by t0.

        t_off_ps is the real delay of the first displayed bin: 0 unless a crop
        dropped early bins, in which case the axis keeps the true delays.
        """
        return self.t_off_ps + (np.arange(self.n_t) + 0.5) * self.dt_ps - self.t0

    @property
    def t_lo(self):
        return self.t_off_ps - self.t0

    @property
    def t_hi(self):
        return self.t_off_ps + self.n_t * self.dt_ps - self.t0

    @property
    def wl_edges(self):
        dw = np.median(np.diff(self.wls)) if len(self.wls) > 1 else 5.0
        return self.wls[0] - dw / 2, self.wls[-1] + dw / 2

    # -- build ------------------------------------------------------------
    def rebuild(self):
        p = self.phu
        res = p["res_ps"]
        self.irf_idx = 0 if self.first_is_irf else None

        # -- wavelength window: drop the IRF curve, then any curve outside the
        #    crop range (compared in offset-applied nm, i.e. what the user
        #    picked). Fall back to the full sweep if the range keeps nothing.
        idx = [i for i in range(p["ncurves"]) if i != self.irf_idx]
        if self.crop_wl is not None:
            wl_lo, wl_hi = sorted(self.crop_wl)
            keep = [i for i in idx
                    if wl_lo - 1e-6 <= p["wls"][i] + self.wl_offset <= wl_hi + 1e-6]
            if keep:
                idx = keep

        # -- time window: bins for [t_min_ps, t_max_ps], rebinned by rb. The
        #    first kept bin's true delay is t_off_ps, so cropping early bins
        #    slides the axis origin instead of relabelling the delays.
        rb = max(1, int(self.rebin))
        b_lo = int(np.clip(round(self.t_min_ps / res), 0, p["nbins"] - 1))
        b_hi = int(np.clip(round(self.t_max_ps / res), b_lo + 1, p["nbins"]))
        n_t = max(1, (b_hi - b_lo) // rb)
        b_hi = b_lo + n_t * rb
        self.t_off_ps = b_lo * res

        block = p["counts"][idx, b_lo:b_hi].astype(np.float64)
        self.E_raw = block.reshape(len(idx), n_t, rb).sum(axis=2)  # (wavelength, time)
        self.wls = p["wls"][idx] + self.wl_offset
        self.n_w, self.n_t = self.E_raw.shape

        # -- solvent: the same curves, bins and rebinning as the sample block,
        #    so the two line up cell for cell (solvent_mismatch() made sure the
        #    grids agree). S_raw stays unscaled - the Crop preview draws it -
        #    and the subtraction itself only happens while it is switched on.
        if self.solvent is not None:
            sblock = self.solvent["counts"][idx, b_lo:b_hi].astype(np.float64)
            self.S_raw = sblock.reshape(len(idx), n_t, rb).sum(axis=2)
            if self.solvent_sub:
                self.E_raw = self.E_raw - self.solvent_scale * self.S_raw
        else:
            self.S_raw = None

        # -- wavelength masks: whole rows to NaN, so they drop out of the map,
        #    the summed spectra and the fits while staying in the axis as a gap.
        self.mask_rows = np.zeros(self.n_w, dtype=bool)
        for a, b in self.masks:
            self.mask_rows |= (self.wls >= min(a, b)) & (self.wls <= max(a, b))
        if self.mask_rows.any():
            self.E_raw[self.mask_rows, :] = np.nan
            if self.S_raw is not None:
                self.S_raw[self.mask_rows, :] = np.nan

        # IRF, kept at native resolution for the peak/FWHM numbers. The peak is
        # measured on the whole IRF curve so cropping the record does not move
        # it; only the drawn trace is sliced to the time window so it lines up
        # with the decay panel. Built before the background because t0 - and
        # with it the window - depends on it.
        if self.irf_idx is not None:
            full = p["counts"][self.irf_idx].astype(np.float64)
            self.irf = full[b_lo:b_hi].reshape(n_t, rb).sum(axis=1)
            self.irf_wl = p["wls"][self.irf_idx] + self.wl_offset
            self.irf_peak_ps, self.irf_fwhm_ps = fwhm_of(full, res)
        else:
            self.irf = None
            self.irf_wl = None
            self.irf_peak_ps = self.irf_fwhm_ps = 0.0

        self.subtract_background()

    def subtract_background(self):
        """Take the mean spectrum over the background window out of every bin."""
        if not self.bg_sub:
            self.bg_spec = None
            self.bg_window_ps = None
            self.E = self.E_raw
        else:
            i0, i1 = self.bg_slice()
            # nanmean: a masked (all-NaN) row averages to NaN and stays a gap.
            # The "Mean of empty slice" warning it raises for such rows is
            # expected, so silence it rather than spam the console.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                self.bg_spec = np.nanmean(self.E_raw[:, i0:i1], axis=1)
            self.bg_window_ps = (self.t_off_ps + i0 * self.dt_ps - self.t0,
                                 self.t_off_ps + i1 * self.dt_ps - self.t0)
            self.E = self.E_raw - self.bg_spec[:, None]

        # Solvent subtraction leaves noise scattered around zero. While it is
        # on, the negatives are clipped to 0 here - after the background, so
        # the final E has none - and clip_frac keeps the share of cells that
        # were cut, since clipping lifts every sum taken over them. A new
        # array rather than in place: with the background off, E is E_raw
        # itself. Masked (NaN) cells compare false and stay NaN.
        self.clip_frac = 0.0
        if self.solvent_active:
            negative = self.E < 0
            cells = int(np.isfinite(self.E).sum())
            self.clip_frac = float(negative.sum() / cells) if cells else 0.0
            self.E = np.where(negative, 0.0, self.E)

        # a window sitting on real signal drives almost everything negative,
        # which the map can only render as "below the colour scale". Masked
        # (NaN) cells are neither positive nor negative, so weigh only the rest.
        finite = int(np.isfinite(self.E).sum())
        self.neg_frac = float((self.E < 0).sum() / finite) if finite else 0.0
        self.vmax = max(float(np.nanmax(self.E)) if finite else 1.0, 1.0)

        # every delay summed: the steady-state spectrum, and its mirror image
        # over the wavelengths. nansum drops masked cells; a fully masked
        # wavelength stays NaN (a gap in the spectrum) instead of reading as 0.
        self.spec_total = np.nansum(self.E, axis=1)
        self.decay_total = np.nansum(self.E, axis=0)
        self.spec_total[np.isnan(self.E).all(axis=1)] = np.nan

    def bg_slice(self):
        """Background window as display-bin indices [i0, i1), always non-empty.

        The window is given in display-time coordinates, i.e. what the axes
        show, so it follows the "t0 at IRF peak" shift.
        """
        lo, hi = sorted((self.bg_lo_ps, self.bg_hi_ps))
        # invert times(): display t = t_off + (j + 0.5)*dt - t0  ->  j
        off = self.t0 - self.t_off_ps
        i0 = int(np.clip(np.floor((lo + off) / self.dt_ps), 0, self.n_t - 1))
        i1 = int(np.clip(np.ceil((hi + off) / self.dt_ps), i0 + 1, self.n_t))
        return i0, i1

    def solvent_spectrum(self):
        """Unscaled steady-state spectrum of the solvent, or None without one.

        Treated like the sample - same background window, same sum over time -
        so that (sample spectrum) - scale * (this) is the subtracted spectrum
        before clipping. Only the Crop preview draws it.
        """
        if self.S_raw is None:
            return None
        S = self.S_raw
        if self.bg_sub:
            i0, i1 = self.bg_slice()
            with warnings.catch_warnings():       # all-NaN (masked) rows
                warnings.simplefilter("ignore", RuntimeWarning)
                S = S - np.nanmean(S[:, i0:i1], axis=1)[:, None]
        spec = np.nansum(S, axis=1)
        spec[np.isnan(S).all(axis=1)] = np.nan
        return spec

    # -- slices -----------------------------------------------------------
    def decay_at(self, wi):
        return self.E[wi, :]

    def spectrum_at(self, ti):
        return self.E[:, ti]

    def locate(self, wl, t_ps):
        """Map data coordinates to (wavelength index, time index), or None."""
        lo, hi = self.wl_edges
        if not (lo <= wl <= hi) or not (self.t_lo <= t_ps <= self.t_hi):
            return None
        wi = int(np.clip(np.argmin(np.abs(self.wls - wl)), 0, self.n_w - 1))
        ti = int(np.clip((t_ps + self.t0 - self.t_off_ps) // self.dt_ps,
                         0, self.n_t - 1))
        return wi, ti


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

CMAPS = ["turbo", "viridis", "inferno", "magma", "plasma", "cividis", "gray"]
BIN_CHOICES = [("4 ps", 1), ("8 ps", 2), ("16 ps", 4), ("32 ps", 8),
               ("64 ps", 16), ("128 ps", 32), ("256 ps", 64)]


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

        ttk.Button(bar, text="Open file...", command=self.open_dialog).pack(side="left")
        ttk.Button(bar, text="Save map image...",
                   command=self.save_map_image).pack(side="left", padx=(6, 0))

        # -- combined data export: TRES map + steady state, always together --
        ttk.Button(bar, text="Export data...",
                   command=self.export_data).pack(side="left", padx=(12, 4))
        self.var_out_csv = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="CSV",
                        variable=self.var_out_csv).pack(side="left")
        self.var_out_opju = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text=".opju",
                        variable=self.var_out_opju).pack(side="left", padx=(4, 0))

        # -- preprocessing: crop + wavelength masks, each its own pop-up --
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=(12, 8))
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
            messagebox.showinfo("No data", "Load a .phu file first.")
            return
        if self._kinetics_win is not None and self._kinetics_win.alive:
            self._kinetics_win.lift_and_refresh()
            return
        self._kinetics_win = KineticsDialog(self)

    def open_global_analysis(self):
        """Open (or raise) the global-analysis window."""
        if not self.model:
            messagebox.showinfo("No data", "Load a .phu file first.")
            return
        if self._global_win is not None and self._global_win.alive:
            self._global_win.lift_and_refresh()
            return
        self._global_win = GlobalAnalysisDialog(self)

    def open_crop(self):
        """Open (or raise) the crop window (wavelength + time window)."""
        if not self.model:
            messagebox.showinfo("No data", "Load a .phu file first.")
            return
        if self._crop_win is not None and self._crop_win.alive:
            self._crop_win.lift_and_refresh()
            return
        self._crop_win = CropDialog(self)

    def open_mask(self):
        """Open (or raise) the wavelength-mask window."""
        if not self.model:
            messagebox.showinfo("No data", "Load a .phu file first.")
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
        cb2 = ttk.Combobox(row, textvariable=self.var_bin,
                           values=[b[0] for b in BIN_CHOICES], width=7, state="readonly")
        cb2.pack(side="left", padx=(0, 16))
        cb2.bind("<<ComboboxSelected>>", lambda e: self.apply_params())

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

        self.var_meta = tk.StringVar(value="")
        ttk.Label(row, textvariable=self.var_meta, style="Val.TLabel",
                  foreground=INK_FAINT).pack(side="right")

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

        self.var_bginfo = tk.StringVar(value="")
        ttk.Label(row2, textvariable=self.var_bginfo, style="Val.TLabel",
                  foreground=PIN).pack(side="left", padx=(0, 16))

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

        ttk.Label(row2, text="map: drag = zoom | click = pin | right-click = reset      "
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
            self.load(path)

    def load(self, path):
        try:
            phu = read_phu(path)
        except Exception as exc:
            messagebox.showerror("Could not read file", str(exc))
            return

        # the pop-up windows belong to the old file's data - drop them
        self._close_dialogs()
        self.model = TRESModel(phu)
        # A .phu header has no IRF flag, so whether curve 0 is an IRF-only
        # measurement is the user's call via the "First curve is IRF" checkbox.
        self.model.first_is_irf = self.var_irf.get()
        self.model.t0_align = self.var_t0.get()
        self.model.rebin = dict(BIN_CHOICES)[self.var_bin.get()]
        self.model.bg_sub = self.var_bgsub.get()
        # the offset calibrates the spectrograph, not the file, so it carries over
        self.model.wl_offset = self._float_var(self.var_offset, 0.0)
        # open on everything that was actually recorded, empty tail trimmed
        self.model.t_max_ps = self.model.t_data_ps
        self.var_tmax.set(f"{self.model.t_max_ps:.0f}")
        self.model.rebuild()
        self._set_bg_window(self.model.t_lo, self.model.t_lo + 100.0)
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
        """Read a Tk entry as a float, rewriting it when it does not parse."""
        try:
            return float(var.get())
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

    def apply_params(self):
        if not self.model:
            return
        m = self.model
        try:
            tmax = float(self.var_tmax.get())
            if tmax <= 0:
                raise ValueError
        except ValueError:
            tmax = m.t_data_ps          # unreadable entry falls back to the default
            self.var_tmax.set(f"{tmax:.0f}")

        t0_before = m.t0
        m.t_max_ps = min(tmax, m.t_full_ps)
        if tmax > m.t_max_ps:           # asked for more delay than was measured
            self.var_tmax.set(f"{m.t_max_ps:.0f}")
        m.rebin = dict(BIN_CHOICES)[self.var_bin.get()]
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

        # counts per bin change with the rebin factor and with the background,
        # so a contrast picked for the old scale is meaningless
        self.clim = None
        self._clamp_view()

        if self.cursor:
            wi, ti = self.cursor
            self.cursor = (min(wi, m.n_w - 1), min(ti, m.n_t - 1))
        self.redraw(full=True)

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
        m.wl_offset = new
        m.rebuild()          # the wavelengths come straight off the file each time

        # carry a zoom rectangle along, otherwise it would frame different lines
        if self.view:
            x0, x1, y0, y1 = self.view
            self.view = (x0 + delta, x1 + delta, y0, y1)
            self._clamp_view()
        self.redraw(full=True)

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
        self.ax_map.set_ylabel("Time (ps)", fontsize=9)
        self.ax_map.tick_params(labelbottom=False)
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
        self.ax_spec.fill_between(m.wls, np.maximum(m.spec_total, 0.7), 0.7,
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

        # ---- zoom: applied last, the shared axes follow ----
        x0, x1, y0, y1 = self.view if self.view else (w_lo, w_hi, m.t_lo, m.t_hi)
        self.ax_map.set_xlim(x0, x1)
        self.ax_map.set_ylim(y0, y1)

        self.canvas.draw()
        self.update_cursor()

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
            self.txt.set_color(PIN if self.pinned else INK)

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
        if not self.model:
            messagebox.showinfo("Nothing to save", "Load a .phu file first.")
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
            messagebox.showerror("Save failed", str(exc))
            return

        messagebox.showinfo(
            "Map image saved",
            f"{Z.shape[1]} wavelengths x {Z.shape[0]} time bins "
            f"({wls[0]:.0f}-{wls[-1]:.0f} nm, {times[0]:,.0f}-{times[-1]:,.0f} ps)"
            + ("  [current zoom]" if self.view else "") + "\n\n"
            f"image  {path}")

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
        """The project's Data\\ folder, the default home for exported data.

        In a frozen (PyInstaller) build __file__ sits in the unpack directory,
        which a one-file .exe deletes on exit - there Data\\ goes next to the
        .exe instead.
        """
        if getattr(sys, "frozen", False):
            return os.path.join(os.path.dirname(sys.executable), "Data")
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data")

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

    def export_data(self):
        """Export the TRES map and the steady-state spectrum, always together.

        The "CSV" and ".opju" tickboxes pick the output; at least one is
        required. Both datasets go out in full - the whole record, not the
        current zoom - so the archive does not depend on how the map is framed.
        """
        if not self.model:
            messagebox.showinfo("Nothing to export", "Load a .phu file first.")
            return
        want_csv = self.var_out_csv.get()
        want_opju = self.var_out_opju.get()
        if not (want_csv or want_opju):
            messagebox.showwarning(
                "No output selected",
                "Tick at least one of CSV / .opju before exporting.")
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
            )
            if not chosen:
                return
            stem = self._strip_export_suffix(
                os.path.splitext(os.path.basename(chosen))[0]) or phu_base
            folder = os.path.dirname(chosen) or data_dir or "."
            tres_csv = os.path.join(folder, f"{stem}_TRESmap.csv")
            steady_csv = os.path.join(folder, f"{stem}_steadystate.csv")

        # -- which opju to write into --
        opju_path = None
        if want_opju:
            opju_path = self._ask_opju_path(stem)
            if not opju_path:
                return

        # -- do the work --
        written = []
        try:
            if want_csv:
                wls, times, Z = self._map_arrays_full()
                self._write_map_csv(tres_csv, wls, times, Z, zoomed=False)
                self._write_steady_state_csv(steady_csv)
                written.append(f"CSV\n    {tres_csv}\n    {steady_csv}")
            if want_opju:
                self.win.config(cursor="watch")
                self.win.update()
                try:
                    tabs = self._write_opju(opju_path, stem)
                finally:
                    self.win.config(cursor="")
                written.append(f".opju  {opju_path}\n    tabs: "
                               + ", ".join(tabs))
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))
            return

        messagebox.showinfo("Export complete", "\n\n".join(written))

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
    def _require_pandas():
        """Lazy pandas import with a friendly install hint (opju needs it)."""
        try:
            import pandas as pd
            return pd
        except ImportError as exc:
            raise RuntimeError(
                "Writing .opju needs pandas.\n"
                f'Install it into {sys.executable}:\n'
                f'  "{sys.executable}" -m pip install pandas') from exc

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
                f'Install them into {sys.executable}:\n'
                f'  "{sys.executable}" -m pip install originpro pywin32') from exc

        folder = os.path.dirname(opju_path)
        exists = os.path.exists(opju_path)
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass
        written = []
        try:
            if exists:
                if not op.open(opju_path):
                    raise RuntimeError(f"Could not open the project: {opju_path}")
            else:
                if folder and not os.path.isdir(folder):
                    os.makedirs(folder, exist_ok=True)
                op.new()

            wb = _origin_book1(op)
            for tab_name, fill_fn in tabs:
                ws, _ = _origin_sheet(wb, tab_name)
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

    def export_analysis(self, default_base, parts):
        """CSV / .opju export for an analysis window, driven by the main tickboxes.

        Kinetics and Global-analysis results go out through exactly the same
        path as "Export data...": tick "CSV" on the main window to get CSV
        files, tick ".opju" to add worksheet tabs to Book1 of an Origin
        project (the one already holding the TRES map, if picked).

        `parts` is a list of dicts, one per table:
            {"suffix": str,          # names the file / tab: {stem}_{suffix}
             "csv":   fn(path),      # writes that CSV
             "fill":  fn(ws)}        # fills that opju worksheet
        """
        want_csv = self.var_out_csv.get()
        want_opju = self.var_out_opju.get()
        if not (want_csv or want_opju):
            messagebox.showwarning(
                "No output selected",
                "Tick CSV and/or .opju on the main window before exporting.")
            return

        data_dir = self._default_data_dir()
        stem = default_base
        written = []
        try:
            # -- CSV: one file per part, {stem}_{suffix}.csv --
            if want_csv:
                try:
                    os.makedirs(data_dir, exist_ok=True)
                except Exception:
                    data_dir = ""
                chosen = filedialog.asksaveasfilename(
                    title="Export results as CSV - choose a base name",
                    defaultextension=".csv", initialdir=data_dir or None,
                    initialfile=f"{default_base}.csv",
                    filetypes=[("CSV data", "*.csv"), ("All files", "*.*")])
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
                files = []
                for p in parts:
                    fp = os.path.join(folder, f"{stem}_{p['suffix']}.csv")
                    p["csv"](fp)
                    files.append(fp)
                written.append("CSV\n    " + "\n    ".join(files))

            # -- .opju: one worksheet tab per part, in Book1 --
            if want_opju:
                opju_path = self._ask_opju_path(stem)
                if not opju_path:
                    return
                self.win.config(cursor="watch")
                self.win.update()
                try:
                    tabs = self._opju_write_tabs(
                        opju_path,
                        [(f"{stem}_{p['suffix']}", p["fill"]) for p in parts])
                finally:
                    self.win.config(cursor="")
                written.append(f".opju  {opju_path}\n    tabs: " + ", ".join(tabs))
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))
            return

        messagebox.showinfo("Export complete", "\n\n".join(written))

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


# ==========================================================================
# 5. FLIM viewer - the PTU tab
# ==========================================================================
class FLIMViewer:
    """PTU (T3 TTTR) post-processing: intensity image, lifetime map, decay.

    Ported from FLIM_Post_Process/flim_viewer.py into a tab of this window.
    The heavy per-record loop runs on a worker thread and talks back through a
    queue, so every Tk / matplotlib touch stays on the main thread - which
    matters now that a second tab shares the same event loop.
    """

    def __init__(self, parent):
        self.parent = parent                  # the tab frame
        self.win = parent.winfo_toplevel()    # the window, for the cursor/after

        self.records = None
        self.hist = None
        self.intensity = None
        self.lifetime = None
        self.peak_bin = 0

        self.use_gpu = tk.BooleanVar(value=False)
        self.gpu_active = False

        self.nx_var = tk.IntVar(value=NX_DEFAULT)
        self.ny_var = tk.IntVar(value=NY_DEFAULT)
        self.nbins_var = tk.IntVar(value=NBINS_DEFAULT)
        self.cur_nx = NX_DEFAULT
        self.cur_ny = NY_DEFAULT
        self.cur_nbins = NBINS_DEFAULT

        self._q = queue.Queue()               # worker -> main-thread messages
        self._worker = None

        self._build_layout()

        start_gpu_detection()                 # background TensorFlow probe
        self._refresh_gpu_panel()
        self._poll_gpu()
        self.win.after(100, self._poll_queue)

    # -- layout -----------------------------------------------------------
    def _build_layout(self):
        top = ttk.Frame(self.parent, padding=8)
        top.pack(side="top", fill="x")

        ttk.Label(top, text="PTU FILE").pack(side="left", padx=(0, 6))
        self.path_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.path_var, font=("TkFixedFont", 9)
                  ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(top, text="Open file...", command=self.on_open_file).pack(side="left")
        self.process_btn = ttk.Button(top, text="Process", command=self.on_process)
        self.process_btn.pack(side="left", padx=(6, 8))
        self.progress = ttk.Progressbar(top, length=180, mode="determinate")
        self.progress.pack(side="left", padx=(0, 8))
        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(top, textvariable=self.status_var, style="Val.TLabel",
                  foreground=INK_DIM).pack(side="left")

        body = ttk.Frame(self.parent, padding=4)
        body.pack(side="top", fill="both", expand=True)

        # ---- left: compute device + image size ----
        left = ttk.LabelFrame(body, text="Compute device", padding=8)
        left.pack(side="left", fill="y", padx=4, pady=4)

        self.gpu_info = tk.StringVar(value="GPU: detecting...")
        self.gpu_info_lbl = ttk.Label(left, textvariable=self.gpu_info,
                                      foreground=INK_FAINT, justify="left")
        self.gpu_info_lbl.pack(anchor="w", pady=(0, 8))

        self.gpu_check = ttk.Checkbutton(left, text="Use GPU", variable=self.use_gpu,
                                         state="disabled")
        self.gpu_check.pack(anchor="w", pady=2)
        self.activate_btn = ttk.Button(left, text="Activate",
                                       command=self.on_activate_gpu, state="disabled")
        self.activate_btn.pack(anchor="w", pady=4)
        self.device_status = tk.StringVar(value="current: CPU")
        ttk.Label(left, textvariable=self.device_status,
                  foreground=ACCENT).pack(anchor="w", pady=(8, 0))

        ttk.Separator(left, orient="horizontal").pack(fill="x", pady=10)

        size_frame = ttk.LabelFrame(left, text="Image size", padding=6)
        size_frame.pack(anchor="w", fill="x", pady=(0, 4))

        def _size_row(label, var, hint):
            r = ttk.Frame(size_frame)
            r.pack(anchor="w", fill="x", pady=2)
            ttk.Label(r, text=label, width=7).pack(side="left")
            ttk.Entry(r, textvariable=var, width=8,
                      font=("TkFixedFont", 9)).pack(side="left")
            ttk.Label(r, text=hint, foreground=INK_FAINT).pack(side="left", padx=(4, 0))

        _size_row("Nx", self.nx_var, "(X px)")
        _size_row("Ny", self.ny_var, "(Y line)")
        _size_row("N_bins", self.nbins_var, "(dtime)")
        ttk.Button(size_frame, text="Apply size",
                   command=self.on_apply_size).pack(anchor="w", pady=(4, 0))
        self.size_status = tk.StringVar(
            value=f"current: {NX_DEFAULT} x {NY_DEFAULT} x {NBINS_DEFAULT}")
        ttk.Label(size_frame, textvariable=self.size_status,
                  foreground=ACCENT).pack(anchor="w", pady=(4, 0))

        self.info_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.info_var, justify="left",
                  foreground=PIN).pack(anchor="w", pady=(8, 0))

        # ---- right: images ----
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=4, pady=4)

        self.fig = Figure(figsize=(9, 7), dpi=100, facecolor=PANEL)
        self.ax_int = self.fig.add_subplot(2, 2, 1)
        self.ax_life = self.fig.add_subplot(2, 2, 2)
        self.ax_hist = self.fig.add_subplot(2, 1, 2)
        for ax in (self.ax_int, self.ax_life, self.ax_hist):
            self._style_ax(ax)
        self.ax_int.set_title("FLIM Intensity Image (0-2 count)")
        self.ax_life.set_title("FLIM Lifetime Map (relative to peak)")
        self.ax_hist.set_title("dtime Histogram (move the cursor over an image)")
        self.ax_hist.set_xlabel("dtime (bin)")
        self.ax_hist.set_ylabel("Photon count")
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("motion_notify_event", self.on_cursor_move)

    @staticmethod
    def _style_ax(ax):
        """Dark styling to match the rest of the window; reapply after clear()."""
        ax.set_facecolor(BG)
        for s in ax.spines.values():
            s.set_color(LINE)
        ax.tick_params(colors=INK_FAINT, labelsize=8, length=3)
        ax.xaxis.label.set_color(INK_FAINT)
        ax.yaxis.label.set_color(INK_FAINT)
        ax.title.set_color(INK_DIM)

    # -- GPU panel --------------------------------------------------------
    def _poll_gpu(self):
        """Re-check the background probe until it reports, then stop polling."""
        if _GPU_DONE.is_set():
            self._refresh_gpu_panel()
        else:
            self.win.after(200, self._poll_gpu)

    def _refresh_gpu_panel(self):
        if not _GPU_DONE.is_set():
            self.gpu_info.set("GPU: detecting... (loading TensorFlow)")
            self.gpu_info_lbl.configure(foreground=INK_FAINT)
            return
        if GPU_AVAILABLE:
            self.gpu_info.set(f"NVIDIA GPU detected:\n{GPU_NAME}\n"
                              f"TensorFlow {TF_VERSION}")
            self.gpu_info_lbl.configure(foreground=GOOD)
            self.gpu_check.configure(state="normal")
            self.activate_btn.configure(state="normal")
        else:
            self.gpu_info.set(f"No NVIDIA GPU - CPU only\nTensorFlow: {TF_VERSION}")
            self.gpu_info_lbl.configure(foreground=INK_FAINT)
            self.gpu_check.configure(state="disabled")
            self.activate_btn.configure(state="disabled")

    def on_activate_gpu(self):
        if not GPU_AVAILABLE:
            messagebox.showwarning("GPU", "No usable NVIDIA GPU.")
            return
        if self.use_gpu.get():
            self.gpu_active = True
            self.device_status.set(f"current: GPU\n{GPU_NAME}")
            messagebox.showinfo("GPU", f"GPU on (TensorFlow {TF_VERSION}):\n{GPU_NAME}")
        else:
            self.gpu_active = False
            self.device_status.set("current: CPU")
            messagebox.showinfo("GPU", "GPU off (CPU mode)")

    # -- image size -------------------------------------------------------
    def on_apply_size(self):
        try:
            nx = int(self.nx_var.get())
            ny = int(self.ny_var.get())
            nbins = int(self.nbins_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Image size", "Nx, Ny, N_bins must be integers.")
            return
        if nx <= 0 or ny <= 0 or nbins <= 0:
            messagebox.showerror("Image size", "All values must be positive integers.")
            return
        if nbins > 4096:
            messagebox.showwarning(
                "Image size",
                "N_bins cannot exceed the 12-bit dtime limit (4096); using 4096.")
            nbins = 4096
            self.nbins_var.set(4096)
        self.cur_nx, self.cur_ny, self.cur_nbins = nx, ny, nbins
        self.size_status.set(f"current: {nx} x {ny} x {nbins}")
        messagebox.showinfo("Image size",
                            f"Applied Nx={nx}, Ny={ny}, N_bins={nbins}\n"
                            "Takes effect on the next 'Process'.")

    # -- open / process ---------------------------------------------------
    def on_open_file(self):
        path = filedialog.askopenfilename(
            title="Open PTU file",
            filetypes=[("PTU files", "*.ptu"), ("All files", "*.*")])
        if path:
            self.path_var.set(path)
            self.status_var.set("file selected")

    def on_process(self):
        path = self.path_var.get().strip().strip('"')
        if not path or not os.path.exists(path):
            messagebox.showerror("Error", "Choose a valid PTU file first.")
            return
        if self._worker is not None and self._worker.is_alive():
            return
        self.process_btn.configure(state="disabled")
        self.progress["value"] = 0
        self._worker = threading.Thread(target=self._process_worker,
                                        args=(path,), daemon=True)
        self._worker.start()

    def _process_worker(self, path):
        """Runs off the main thread; all UI updates go through the queue."""
        try:
            self._q.put(("status", "loading file..."))
            records = load_ptu_records(path)
            nx, ny, nbins = self.cur_nx, self.cur_ny, self.cur_nbins
            self._q.put(("status",
                         f"processing... ({len(records):,} records, {nx}x{ny}x{nbins})"))

            def progress_cb(frac):
                self._q.put(("progress", frac))

            if self.gpu_active and GPU_AVAILABLE and tf is not None:
                hist = process_records_gpu(records, nx, ny, nbins, progress_cb)
                device = "GPU"
            else:
                hist = process_records_cpu(records, nx, ny, nbins, progress_cb)
                device = "CPU"

            intensity = compute_intensity(hist)
            lifetime, peak_bin = compute_lifetime_map(hist)
            self._q.put(("done", dict(
                records=records, hist=hist, intensity=intensity,
                lifetime=lifetime, peak_bin=peak_bin, device=device)))
        except Exception as exc:                       # reported on the main thread
            self._q.put(("error", str(exc)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "progress":
                    self.progress["value"] = payload * 100
                elif kind == "error":
                    self.status_var.set("error")
                    self.process_btn.configure(state="normal")
                    messagebox.showerror("Processing error", payload)
                elif kind == "done":
                    self._on_done(payload)
        except queue.Empty:
            pass
        self.win.after(100, self._poll_queue)

    def _on_done(self, payload):
        self.records = payload["records"]
        self.hist = payload["hist"]
        self.intensity = payload["intensity"]
        self.lifetime = payload["lifetime"]
        self.peak_bin = payload["peak_bin"]
        self.progress["value"] = 100
        self.process_btn.configure(state="normal")
        self.status_var.set(f"done ({payload['device']})")
        self.info_var.set(
            f"total photons: {int(self.intensity.sum()):,}\n"
            f"lit pixels:    {int(np.sum(self.intensity > 0)):,}\n"
            f"max intensity: {int(self.intensity.max())}\n"
            f"peak bin:      {self.peak_bin}")
        self._draw_images()

    # -- drawing ----------------------------------------------------------
    def _draw_images(self):
        self.ax_int.clear()
        self._style_ax(self.ax_int)
        self.ax_int.set_title("FLIM Intensity Image (0-2 count)")
        self.ax_int.imshow(self.intensity.T, cmap="hot", origin="lower",
                           aspect="auto", vmin=0, vmax=2)
        self.ax_int.set_xlabel("X pixel")
        self.ax_int.set_ylabel("Y line")

        self.ax_life.clear()
        self._style_ax(self.ax_life)
        self.ax_life.set_title("FLIM Lifetime Map (relative to peak)")
        masked = np.ma.masked_invalid(self.lifetime)
        self.ax_life.imshow(masked.T, cmap="jet", origin="lower", aspect="auto")
        self.ax_life.set_xlabel("X pixel")
        self.ax_life.set_ylabel("Y line")

        self.ax_hist.clear()
        self._style_ax(self.ax_hist)
        self.ax_hist.set_title("dtime Histogram (move the cursor over an image)")
        self.ax_hist.set_xlabel("dtime (bin)")
        self.ax_hist.set_ylabel("Photon count")

        self.fig.tight_layout()
        self.canvas.draw()

    def on_cursor_move(self, event):
        if self.hist is None or event.inaxes not in (self.ax_int, self.ax_life):
            return
        if event.xdata is None or event.ydata is None:
            return
        hnx, hny, hbins = self.hist.shape
        x = int(round(event.xdata))
        y = int(round(event.ydata))
        if not (0 <= x < hnx and 0 <= y < hny):
            return

        decay = self.hist[x, y, :]
        nz = np.where(decay > 0)[0]
        self.ax_hist.clear()
        self._style_ax(self.ax_hist)
        self.ax_hist.set_title(f"dtime Histogram  (x={x}, y={y}, "
                               f"{int(decay.sum()):,} photons)")
        self.ax_hist.set_xlabel("dtime (bin)")
        self.ax_hist.set_ylabel("Photon count")
        if len(nz) > 0:
            self.ax_hist.bar(nz, decay[nz], width=1.0, color=ACCENT)
            self.ax_hist.set_xlim(0, hbins)
        self.canvas.draw_idle()


# ==========================================================================
# 6. Analysis dialogs - Kinetics + Global analysis, each its own window
# ==========================================================================
def _style_analysis_ax(ax):
    """Paint a matplotlib axis in the shared dark palette (re-run after clear)."""
    ax.set_facecolor(BG)
    for s in ax.spines.values():
        s.set_color(LINE)
    ax.tick_params(colors=INK_FAINT, labelsize=8, length=3)
    ax.xaxis.label.set_color(INK_DIM)
    ax.yaxis.label.set_color(INK_DIM)
    ax.title.set_color(INK_DIM)


def _dark_toolbar(canvas, master):
    """A matplotlib navigation toolbar tinted to match the dark theme."""
    tb = NavigationToolbar2Tk(canvas, master, pack_toolbar=False)
    tb.configure(bg=PANEL)
    for child in tb.winfo_children():
        try:
            child.configure(bg=PANEL)
        except tk.TclError:
            pass
    tb.update()
    return tb


class ComponentTable(ttk.Frame):
    """Editable per-component grid: tau_init / fix / stretched / beta / beta-fix.

    set_n() rebuilds the rows for a new component count, preserving whatever the
    user already typed so changing the count is never destructive. read() hands
    back the five parallel numpy arrays the fit kernels expect.
    """

    HEADERS = ["#", "τ_init (ps)", "fix", "stretch", "β_init", "β fix"]
    _TAU_DEFAULTS = [100.0, 1000.0, 10000.0, 100000.0, 1_000_000.0]

    def __init__(self, master):
        super().__init__(master)
        for c, h in enumerate(self.HEADERS):
            ttk.Label(self, text=h).grid(row=0, column=c, padx=2, pady=(0, 3),
                                         sticky="w")
        self.rows = []

    def set_n(self, n):
        prev = self.read_raw()
        for r in self.rows:
            for w in r["widgets"]:
                w.destroy()
        self.rows = []
        for i in range(n):
            tau_v = tk.StringVar(
                value=prev[i]["tau"] if i < len(prev)
                else f"{self._TAU_DEFAULTS[i % 5]:g}")
            fix_v = tk.BooleanVar(
                value=prev[i]["tau_fixed"] if i < len(prev) else False)
            st_v = tk.BooleanVar(
                value=prev[i]["stretched"] if i < len(prev) else False)
            beta_v = tk.StringVar(value=prev[i]["beta"] if i < len(prev) else "1")
            bfix_v = tk.BooleanVar(
                value=prev[i]["beta_fixed"] if i < len(prev) else False)
            w0 = ttk.Label(self, text=str(i + 1))
            w1 = ttk.Entry(self, textvariable=tau_v, width=11,
                           font=("TkFixedFont", 9))
            w2 = ttk.Checkbutton(self, variable=fix_v)
            w3 = ttk.Checkbutton(self, variable=st_v)
            w4 = ttk.Entry(self, textvariable=beta_v, width=6,
                           font=("TkFixedFont", 9))
            w5 = ttk.Checkbutton(self, variable=bfix_v)
            rr = i + 1
            w0.grid(row=rr, column=0, padx=2, sticky="w")
            w1.grid(row=rr, column=1, padx=2, pady=1)
            w2.grid(row=rr, column=2)
            w3.grid(row=rr, column=3)
            w4.grid(row=rr, column=4, padx=2)
            w5.grid(row=rr, column=5)
            self.rows.append({"tau": tau_v, "fix": fix_v, "st": st_v,
                              "beta": beta_v, "bfix": bfix_v,
                              "widgets": [w0, w1, w2, w3, w4, w5]})

    def read_raw(self):
        return [{"tau": r["tau"].get(), "tau_fixed": r["fix"].get(),
                 "stretched": r["st"].get(), "beta": r["beta"].get(),
                 "beta_fixed": r["bfix"].get()} for r in self.rows]

    def read(self):
        tau, fix, st, beta, bfix = [], [], [], [], []
        for r in self.rows:
            try:
                tau.append(float(r["tau"].get()))
            except ValueError:
                tau.append(1.0)
            fix.append(bool(r["fix"].get()))
            st.append(bool(r["st"].get()))
            try:
                b = float(r["beta"].get())
            except ValueError:
                b = 1.0
            beta.append(min(max(b, 1e-3), 2.0))
            bfix.append(bool(r["bfix"].get()))
        return (np.asarray(tau, float), np.asarray(fix, bool),
                np.asarray(st, bool), np.asarray(beta, float),
                np.asarray(bfix, bool))


class _AnalysisDialog:
    """Common plumbing for the pop-up preprocessing and analysis windows.

    Wraps a dark Toplevel, tracks whether it is still open (so the launcher can
    raise an existing one instead of stacking duplicates), and exposes the live
    viewer/model so the window always works on the file currently loaded.
    """

    def __init__(self, app, title, geometry, minsize):
        self.app = app
        self.win = tk.Toplevel(app.win)
        self.win.title(title)
        self.win.geometry(geometry)
        self.win.minsize(*minsize)
        self.win.configure(bg=BG)
        self.alive = True
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)

    @property
    def model(self):
        return self.app.model

    def _on_close(self):
        self.alive = False
        self.win.destroy()

    def lift_and_refresh(self):
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()

    # -- defaults pulled from the current model --------------------------
    def _irf_defaults(self):
        """(t0, fwhm) guesses in display-time coordinates from the IRF curve."""
        m = self.model
        t0 = float(m.irf_peak_ps - m.t0) if m.irf is not None else 0.0
        fwhm = float(m.irf_fwhm_ps) if (m.irf is not None
                                        and m.irf_fwhm_ps > 0) else 0.0
        if fwhm <= 0:                       # no usable IRF - use a small guess
            span = float(m.times[-1] - m.times[0]) if m.n_t > 1 else 1.0
            fwhm = max(span / 200.0, m.dt_ps)
        return t0, fwhm

    def _cursor_wl(self):
        """The wavelength under the map cursor, or the middle of the axis."""
        m = self.model
        if self.app.cursor is not None:
            return float(m.wls[self.app.cursor[0]])
        return float(m.wls[m.n_w // 2])


class CropDialog(_AnalysisDialog):
    """Pick a rectangular (wavelength, time) window to keep.

    The whole-dataset heatmap is drawn once; editing the range only nudges the
    lightweight rectangle / dim overlays (debounced ~130 ms), the same
    cheap-overlay pattern the TA analyzer's crop window uses so the dialog stays
    responsive on a big map. Time is in ps from the record start (like the main
    TIME SPAN box), independent of any "t0 at IRF peak" display shift.

    The window also holds the solvent subtraction: load a pure-solvent .phu
    taken on the same grid, then move SCALE until its signal is gone. The
    heatmap shows the whole record minus scale x solvent, and the panel below
    it the steady-state spectrum before, the scaled solvent, and after - all
    a preview until Apply, which hands crop and solvent to the live model.

    Over those (faded) steady-state lines the same panel draws one time bin of
    the map in bold, on a right-hand scale of its own: the sample, the scaled
    solvent and their difference at the delay under the pointer. Double-click
    the map to pin that delay, double-click again to let it follow the mouse.

    The map can be looked at more closely without touching any of the above:
    the wheel zooms about the pointer (Ctrl: time only, Shift: wavelength
    only), a right-button drag moves the view, and the VIEW row switches the
    colour and the time axis between linear and log. All of it is forgotten
    when the window closes.
    """

    ZOOM_STEP = 1.25        # per wheel notch

    def __init__(self, app):
        super().__init__(app, "Crop data", "1000x920", (780, 680))
        m = self.model
        # An uncropped, unmasked copy for the preview so the user always sees
        # the full sweep they are selecting from, whatever crop is already live.
        self._full = TRESModel(m.phu)
        self._full.first_is_irf = m.first_is_irf
        self._full.rebin = m.rebin
        self._full.wl_offset = m.wl_offset
        self._full.bg_sub = False          # raw counts, not background-subtracted
        self._full.t0_align = False         # raw time axis, matches t_min/t_max
        self._full.rebuild()
        # The colour scale stays on the unsubtracted map, read here before any
        # solvent reaches _full: the solvent then visibly drops out of the
        # picture instead of the scale following it down.
        self._vmax0 = self._full.vmax
        self._full_key = None       # (solvent, scale) the heatmap is showing
        # ... and so does this: the sample's own raw counts on the heatmap's
        # grid, for the time-slice spectra. rebuild() makes a new E_raw each
        # time, so the array kept here is never the one a solvent is taken from.
        self._raw0 = self._full.E_raw
        self._slice_ti = None       # time bin whose spectrum is drawn, if any
        self._slice_pinned = False  # held by a double-click, else it follows the mouse
        self._pin_time = -np.inf    # when it was last toggled (triple-click guard)
        self._click_undo = None     # crop state before the latest single click

        # Steady-state preview: a second model, set up for every redraw exactly
        # as Apply would leave the live one, so its spectrum is the one the
        # main window shows afterwards.
        self._pv = TRESModel(m.phu)

        # the solvent picked in this window and its scale - a preview until Apply
        self._solvent = m.solvent
        self._scale = float(m.solvent_scale)
        self._busy = False          # guards the slider <-> entry round trip

        wls = self._full.wls
        self.wl_full = (float(wls.min()), float(wls.max()))
        self.t_full = (0.0, float(self._full.t_hi))

        cw = m.crop_wl if m.crop_wl is not None else self.wl_full
        wl0, wl1 = sorted(cw)
        t0 = max(m.t_min_ps, self.t_full[0])
        t1 = min(m.t_max_ps, self.t_full[1])
        self.var_wl_lo = tk.StringVar(value=f"{wl0:g}")
        self.var_wl_hi = tk.StringVar(value=f"{wl1:g}")
        self.var_t_lo = tk.StringVar(value=f"{t0:g}")
        self.var_t_hi = tk.StringVar(value=f"{t1:g}")
        self.var_info = tk.StringVar(value="")
        self.var_scale = tk.StringVar(value=f"{self._scale:g}")
        self.var_solv_name = tk.StringVar(value="")
        self._overlay = []      # transient rectangle / dim patches
        self._after = None      # debounce handle
        self._corner = None     # first click of a two-click rectangle pick

        # how the map is looked at - none of it reaches the crop or the model.
        # The colour scale starts as the main window has it and then goes its
        # own way.
        self.var_zlog = tk.BooleanVar(value=bool(app.var_log.get()))
        self.var_auto = tk.BooleanVar(value=False)   # colour range from the view
        self.var_tlog = tk.BooleanVar(value=False)   # log time axis
        self._pan = None        # right-button drag: (x, y in pixels, xlim, ylim) at its start

        self._build_ui()
        self._draw_base()
        self._update_overlay()

    # -- layout ----------------------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self.win, padding=(8, 8, 8, 4))
        top.pack(fill="x")

        def field(var):
            e = ttk.Entry(top, textvariable=var, width=8, font=("TkFixedFont", 9))
            e.pack(side="left", padx=2)
            e.bind("<KeyRelease>", lambda ev: self._schedule())
            e.bind("<Return>", lambda ev: self._update_overlay())
            return e

        ttk.Label(top, text="λ").pack(side="left")
        field(self.var_wl_lo)
        ttk.Label(top, text="to").pack(side="left", padx=2)
        field(self.var_wl_hi)
        ttk.Label(top, text="nm").pack(side="left", padx=(2, 4))
        ttk.Button(top, text="Full λ", width=6,
                   command=self._full_wl).pack(side="left", padx=(0, 16))

        ttk.Label(top, text="t").pack(side="left")
        field(self.var_t_lo)
        ttk.Label(top, text="to").pack(side="left", padx=2)
        field(self.var_t_hi)
        ttk.Label(top, text="ps").pack(side="left", padx=(2, 4))
        ttk.Button(top, text="Full t", width=6,
                   command=self._full_t).pack(side="left")

        # -- solvent: file + scale. The slider covers 0-2; the entry takes any
        #    value >= 0, so a larger factor can still be typed.
        srow = ttk.Frame(self.win, padding=(8, 0, 8, 4))
        srow.pack(fill="x")
        ttk.Label(srow, text="SOLVENT").pack(side="left", padx=(0, 6))
        ttk.Button(srow, text="Load solvent...",
                   command=self._load_solvent).pack(side="left")
        ttk.Button(srow, text="Clear", width=6,
                   command=self._clear_solvent).pack(side="left", padx=(6, 8))
        ttk.Label(srow, textvariable=self.var_solv_name, style="Val.TLabel",
                  foreground=PIN).pack(side="left", padx=(0, 12))
        ttk.Label(srow, text="SCALE").pack(side="left", padx=(0, 5))
        self.scale = ttk.Scale(srow, from_=0.0, to=2.0, length=150,
                               command=self._on_slider)
        self.scale.pack(side="left")
        self.ent_scale = ttk.Entry(srow, textvariable=self.var_scale, width=7,
                                   font=("TkFixedFont", 9))
        self.ent_scale.pack(side="left", padx=(6, 0))
        self.ent_scale.bind("<Return>", lambda ev: self._on_scale_entry())
        self.ent_scale.bind("<FocusOut>", lambda ev: self._on_scale_entry())
        self._set_scale(self._scale)
        self._sync_solvent_controls()

        # -- view: how the map is drawn, nothing more
        vrow = ttk.Frame(self.win, padding=(8, 0, 8, 4))
        vrow.pack(fill="x")
        ttk.Label(vrow, text="VIEW").pack(side="left", padx=(0, 6))
        ttk.Checkbutton(vrow, text="Log color", variable=self.var_zlog,
                        command=self._on_color).pack(side="left")
        ttk.Checkbutton(vrow, text="Auto color", variable=self.var_auto,
                        command=self._on_color).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(vrow, text="Log time", variable=self.var_tlog,
                        command=self._on_tscale).pack(side="left", padx=(8, 0))
        ttk.Button(vrow, text="Fit", width=6,
                   command=self._fit_view).pack(side="left", padx=(12, 0))
        ttk.Label(vrow, text="wheel zooms (Ctrl: time, Shift: λ)  |  right-drag moves",
                  foreground=INK_FAINT).pack(side="left", padx=(12, 0))

        self.fig = Figure(figsize=(8.8, 6.6), dpi=100, facecolor=PANEL)
        gs = GridSpec(2, 1, figure=self.fig, height_ratios=[3.0, 1.3],
                      left=0.09, right=0.915, top=0.975, bottom=0.085, hspace=0.07)
        self.ax = self.fig.add_subplot(gs[0])
        self.ax_ss = self.fig.add_subplot(gs[1], sharex=self.ax)
        style_plot_ax(self.ax)
        style_plot_ax(self.ax_ss)
        # right-hand scale of the lower panel, for the spectrum of one time bin:
        # a single bin holds hundreds of times fewer counts than the sum over all
        self.ax_t = self.ax_ss.twinx()
        for s in self.ax_t.spines.values():
            s.set_color(LINE)
        self.ax_t.tick_params(colors=INK_FAINT, labelsize=8, length=3)
        self.ax_t.yaxis.label.set_color(INK_FAINT)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.win)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=4)
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        # two ways off the map: onto another part of the figure (matplotlib
        # reports the axes left) or straight out of the canvas (it only
        # reports the figure left)
        self.canvas.mpl_connect("axes_leave_event", self._on_leave)
        self.canvas.mpl_connect("figure_leave_event", self._on_leave)
        self.canvas.mpl_connect("scroll_event", self._on_scroll)
        self.canvas.mpl_connect("button_release_event", self._on_release)

        bar = ttk.Frame(self.win, padding=(8, 4, 8, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="tip: click two opposite corners on the map to set the box"
                            "  |  double-click pins the spectrum at that time",
                  foreground=INK_FAINT).pack(side="left")
        ttk.Button(bar, text="Close", command=self._on_close).pack(side="right")
        ttk.Button(bar, text="Reset (full)",
                   command=self._reset).pack(side="right", padx=6)
        ttk.Button(bar, text="Apply", command=self._apply).pack(side="right")
        ttk.Label(bar, textvariable=self.var_info,
                  foreground=INK_DIM).pack(side="right", padx=12)

    # -- preview ---------------------------------------------------------
    def _draw_base(self):
        f = self._full
        self._transform, norm, cmap = preview_norm_cmap(
            self._vmax0, self.var_zlog.get(), self.app.var_cmap.get())
        w_lo, w_hi = f.wl_edges
        self._base_im = self.ax.imshow(
            self._transform(f.E.T), aspect="auto", origin="lower", cmap=cmap,
            norm=norm, extent=[w_lo, w_hi, f.t_lo, f.t_hi],
            interpolation="nearest")
        self.ax.set_xlim(w_lo, w_hi)
        self.ax.set_ylim(0.0, self.t_full[1])
        self.ax.set_ylabel("Time (ps from record start)", fontsize=9)
        self.ax.tick_params(labelbottom=False)

        # steady state of the kept box: the sample as it is, the scaled solvent,
        # and what is left - _update_preview() fills the three in
        #    Half transparent: they are the backdrop for the bold time slice.
        ax = self.ax_ss
        (self.ln_sample,) = ax.plot([], [], color=INK_DIM, lw=1.2, alpha=0.5,
                                    label="sample")
        (self.ln_solv,) = ax.plot([], [], color=PIN, lw=1.0, ls=":", alpha=0.5,
                                  label="s x solvent")
        (self.ln_sub,) = ax.plot([], [], color=ACCENT, lw=1.6, alpha=0.5,
                                 label="subtracted")
        ax.axhline(0.0, color=LINE, lw=0.6)
        ax.set_xlim(w_lo, w_hi)
        ax.set_xlabel("Wavelength (nm)", fontsize=9)
        ax.set_ylabel("Counts (all delays)", fontsize=9)
        ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_formatter(EngFormatter(places=0, sep=""))
        ax.grid(alpha=0.12, lw=0.5, color=INK_FAINT)

        # one time bin of the map above, in the colours of the steady-state
        # lines it sits on: raw counts like the heatmap, and the difference
        # left unclipped, so an over-subtraction dips below zero
        at = self.ax_t
        (self.ln_t_sample,) = at.plot([], [], color=INK_DIM, lw=2.2, label="sample")
        (self.ln_t_solv,) = at.plot([], [], color=PIN, lw=2.2, label="s x solvent")
        (self.ln_t_sub,) = at.plot([], [], color=ACCENT, lw=2.2, label="difference")
        at.set_ylabel("Counts (at t)", fontsize=9)
        at.yaxis.set_major_locator(MaxNLocator(4))
        at.yaxis.set_major_formatter(EngFormatter(places=0, sep=""))
        # the delay those come from, marked on the map
        self.hl_t = self.ax.axhline(np.nan, color="w", lw=0.9, ls="--", zorder=7)
        self._draw_slice()
        self.canvas.draw_idle()

    def _time_bin(self, t_ps):
        """Index of the heatmap's time bin that holds ``t_ps`` (from record start)."""
        return int(np.clip(t_ps // self._full.dt_ps, 0, self._full.n_t - 1))

    def _draw_slice(self):
        """Fill in the bold spectra of time bin _slice_ti, or hide them."""
        ti, has = self._slice_ti, self._solvent is not None
        lines = (self.ln_t_sample, self.ln_t_solv, self.ln_t_sub)
        shown = () if ti is None else lines if has else lines[:1]
        for ln in lines:
            ln.set_visible(ln in shown)
        self.hl_t.set_visible(ti is not None)
        if ti is None:
            leg = self.ax_t.get_legend()
            if leg is not None:
                leg.remove()
            return

        f = self._full
        sample = self._raw0[:, ti]
        self.ln_t_sample.set_data(f.wls, sample)
        if has:
            scaled = self._scale * f.S_raw[:, ti]
            self.ln_t_solv.set_data(f.wls, scaled)
            self.ln_t_sub.set_data(f.wls, sample - scaled)
        self._fit_y(self.ax_t, lines)

        t = (ti + 0.5) * f.dt_ps
        self.hl_t.set_ydata([t, t])
        self.hl_t.set_linestyle("-" if self._slice_pinned else "--")
        self.hl_t.set_color(PIN if self._slice_pinned else "w")
        leg = self.ax_t.legend(
            handles=list(shown), loc="upper left", fontsize=7.5, frameon=False, ncol=3,
            title=f"t = {t:,.0f} ps" + ("  (pinned)" if self._slice_pinned else ""),
            title_fontsize=8, alignment="left")
        for txt in (*leg.get_texts(), leg.get_title()):
            txt.set_color(INK)

    def _update_preview(self, box):
        """Redraw what the solvent subtraction would give, without applying it.

        The heatmap is the whole record minus scale x solvent in raw counts,
        like the map it replaces; it is only recomputed when the solvent or
        the scale changed. The spectra come from _pv, configured by the same
        _configure() Apply uses, so "subtracted" is the steady-state panel of
        the main window after Apply. Returns the share of bins clipped to 0.
        """
        sv = self._solvent
        key = (id(sv), self._scale) if sv is not None else None
        if key != self._full_key:
            f = self._full
            f.solvent, f.solvent_scale, f.solvent_sub = sv, self._scale, sv is not None
            f.rebuild()
            self._full_key = key
            self._recolor()

        pv = self._pv
        pv.copy_settings_from(self.model)
        self._configure(pv, box, sub=False)
        pv.rebuild()
        self.ln_sample.set_data(pv.wls, pv.spec_total)
        if sv is not None:
            pv.solvent_sub = True
            pv.rebuild()
            self.ln_solv.set_data(pv.wls, self._scale * pv.solvent_spectrum())
            self.ln_sub.set_data(pv.wls, pv.spec_total)
        shown = [self.ln_sample]
        for ln in (self.ln_solv, self.ln_sub):
            ln.set_visible(sv is not None)
            if sv is not None:
                shown.append(ln)
        self._fit_y(self.ax_ss, shown)
        leg = self.ax_ss.legend(handles=shown, loc="upper right", fontsize=7.5,
                                frameon=False, ncol=3, title="steady state",
                                title_fontsize=8, alignment="right")
        for txt in (*leg.get_texts(), leg.get_title()):
            txt.set_color(INK_DIM)
        self._draw_slice()          # a pinned slice follows the scale as well
        return pv.clip_frac if sv is not None else None

    def _schedule(self):
        if self._after is not None:
            self.win.after_cancel(self._after)
        self._after = self.win.after(130, self._update_overlay)

    def _update_overlay(self):
        self._after = None
        if not self.alive:          # a pending timer can outlive the window
            return
        for art in self._overlay:
            art.remove()
        self._overlay = []
        wl_lo, wl_hi, t_lo, t_hi = self._read()
        # on a log time axis the map starts above 0, and so does what is drawn
        # of a box that reaches down to 0
        (w_lo, w_hi), (y_lo, y_hi) = self._view_full()
        dim = dict(facecolor=BG, alpha=0.55, lw=0, zorder=3)
        if wl_lo > w_lo:
            self._overlay.append(self.ax.axvspan(w_lo, wl_lo, **dim))
        if wl_hi < w_hi:
            self._overlay.append(self.ax.axvspan(wl_hi, w_hi, **dim))
        if t_lo > y_lo:
            self._overlay.append(self.ax.axhspan(y_lo, t_lo, **dim))
        if t_hi < y_hi:
            self._overlay.append(self.ax.axhspan(t_hi, y_hi, **dim))
        r_lo = max(t_lo, y_lo)
        rect = Rectangle((wl_lo, r_lo), wl_hi - wl_lo, t_hi - r_lo, fill=False,
                         edgecolor=ACCENT, lw=1.6, zorder=6)
        self.ax.add_patch(rect)
        self._overlay.append(rect)
        clipped = self._update_preview((wl_lo, wl_hi, t_lo, t_hi))
        n = int(((self._full.wls >= wl_lo) & (self._full.wls <= wl_hi)).sum())
        self.var_info.set(f"keep {n} curves,  {wl_lo:g}-{wl_hi:g} nm,  "
                          f"{t_lo:g}-{t_hi:g} ps"
                          + ("" if clipped is None else f",  clipped {clipped:.0%}"))
        self.canvas.draw_idle()

    # -- view: zoom, colour and time scale ---------------------------------
    def _view_full(self):
        """((wl_lo, wl_hi), (t_lo, t_hi)) of the whole map.

        A log time axis has no 0: there the map starts in the middle of the
        first time bin.
        """
        t_lo = 0.5 * self._full.dt_ps if self.var_tlog.get() else 0.0
        return self._full.wl_edges, (t_lo, self.t_full[1])

    def _fit_y(self, ax, lines):
        """Scale ``ax`` to what the visible ``lines`` show in the wavelengths in view."""
        x0, x1 = self.ax.get_xlim()
        vals = [np.empty(0)]
        for ln in lines:
            if ln.get_visible():
                x, y = (np.asarray(a, float) for a in ln.get_data())
                vals.append(y[(x >= x0) & (x <= x1)])
        vals = np.concatenate(vals)
        vals = vals[np.isfinite(vals)]
        lo = min(float(vals.min()), 0.0) if vals.size else 0.0
        hi = max(float(vals.max()), 1.0) if vals.size else 1.0
        pad = 0.08 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)

    def _view_max(self):
        """Largest count among the map cells that are in view, 0 if there is none."""
        f = self._full
        (w_lo, w_hi), (x0, x1), (y0, y1) = f.wl_edges, self.ax.get_xlim(), self.ax.get_ylim()
        dw = (w_hi - w_lo) / f.n_w
        i0 = int(np.clip(np.floor((x0 - w_lo) / dw), 0, f.n_w - 1))
        i1 = int(np.clip(np.ceil((x1 - w_lo) / dw), i0 + 1, f.n_w))
        j0 = int(np.clip(np.floor(y0 / f.dt_ps), 0, f.n_t - 1))
        j1 = int(np.clip(np.ceil(y1 / f.dt_ps), j0 + 1, f.n_t))
        block = f.E[i0:i1, j0:j1]
        block = block[np.isfinite(block)]
        return float(block.max()) if block.size else 0.0

    def _recolor(self):
        """Give the map its colour scale: linear or log, up to the maximum of
        the whole unsubtracted map or, with Auto color, of the part in view."""
        vmax = self._view_max() if self.var_auto.get() else self._vmax0
        self._transform, norm, _ = preview_norm_cmap(
            vmax, self.var_zlog.get(), self.app.var_cmap.get())
        self._base_im.set_norm(norm)
        self._base_im.set_data(self._transform(self._full.E.T))

    def _set_view(self, xlim, ylim):
        """Show that part of the map; the panel below shares the wavelength range."""
        self.ax.set_xlim(*xlim)
        self.ax.set_ylim(*ylim)
        if self.var_auto.get():
            self._recolor()
        self._fit_y(self.ax_ss, (self.ln_sample, self.ln_solv, self.ln_sub))
        self._fit_y(self.ax_t, (self.ln_t_sample, self.ln_t_solv, self.ln_t_sub))
        self.canvas.draw_idle()

    def _fit_view(self):
        self._set_view(*self._view_full())

    def _on_color(self):
        self._recolor()
        self.canvas.draw_idle()

    def _on_tscale(self):
        """Switch the time axis between linear and log, keeping the range in view."""
        y0, y1 = self.ax.get_ylim()
        self.ax.set_yscale("log" if self.var_tlog.get() else "linear")
        if self.var_tlog.get():
            # zoomed in there may be no full decade in view: label 2, 5 ... too
            self.ax.yaxis.set_minor_formatter(LogFormatterSciNotation(
                labelOnlyBase=False, minor_thresholds=(2.5, 1.0)))
            self.ax.tick_params(axis="y", which="minor", colors=INK_FAINT, labelsize=7)
        f_lo, f_hi = self._view_full()[1]
        if y0 <= 0.5 * self._full.dt_ps:    # was at the bottom: stay there
            y0 = f_lo
        self.ax.set_ylim(y0, min(y1, f_hi))
        self._update_overlay()              # the box is drawn from the axis bottom

    def _moved(self, lim, full, log, k=1.0, at=None, shift=0.0):
        """``lim`` scaled by ``k`` about ``at`` and moved by ``shift`` of its
        width, kept inside ``full``. On a log axis all of that is done in decades,
        so the point under the pointer stays where it is."""
        to, back = (np.log10, lambda v: 10.0 ** v) if log else (float, float)
        lo, hi, f_lo, f_hi = to(lim[0]), to(lim[1]), to(full[0]), to(full[1])
        c = lo if at is None else to(at)
        lo, hi = c - (c - lo) * k, c + (hi - c) * k
        lo, hi = lo + shift * (hi - lo), hi + shift * (hi - lo)
        width = hi - lo
        if width >= f_hi - f_lo:
            return full
        if lo < f_lo:               # pushed back in, that end exactly on the edge
            return full[0], float(back(f_lo + width))
        if hi > f_hi:
            return float(back(f_hi - width)), full[1]
        return max(float(back(lo)), full[0]), min(float(back(hi)), full[1])

    def _zoomed(self, lim, full, log, step, at, least):
        """``lim`` after ``step`` wheel notches about ``at``. Zooming in stops
        at ``least``: a step that would go below it is cut back to the part
        that fits. Zooming out is never held back - a drag on the log axis can
        leave a view narrower than ``least``, and the wheel must get out of it."""
        def after(notches):
            return self._moved(lim, full, log, self.ZOOM_STEP ** -notches, at)

        new = after(step)
        if step <= 0 or new[1] - new[0] >= least:
            return new
        fits, over, best = 0.0, step, lim
        for _ in range(12):         # bisect between no step and the whole one
            part = 0.5 * (fits + over)
            new = after(part)
            if new[1] - new[0] >= least:
                fits, best = part, new
            else:
                over = part
        return best

    def _on_scroll(self, event):
        """Wheel over the map: zoom about the pointer. Ctrl zooms the time axis
        only, Shift the wavelength axis only."""
        if (event.inaxes is not self.ax or event.xdata is None
                or self._pan is not None):      # a drag owns the view until released
            return
        f = self._full
        step = float(np.clip(event.step, -20, 20))  # a free-spinning wheel sends many at once
        xlim, ylim = self.ax.get_xlim(), self.ax.get_ylim()
        full_x, full_y = self._view_full()
        if "ctrl" not in event.modifiers:           # never closer than two curves ...
            xlim = self._zoomed(xlim, full_x, False, step, event.xdata,
                                2 * (full_x[1] - full_x[0]) / f.n_w)
        if "shift" not in event.modifiers:          # ... or four time bins
            ylim = self._zoomed(ylim, full_y, self.var_tlog.get(), step, event.ydata,
                                4 * f.dt_ps)
        self._set_view(xlim, ylim)

    def _on_release(self, event):
        if event.button == 3:
            self._pan = None

    # -- helpers ---------------------------------------------------------
    def _read(self):
        def val(var, default):
            try:
                return float(var.get())
            except ValueError:
                return default
        wl_lo, wl_hi = sorted((val(self.var_wl_lo, self.wl_full[0]),
                               val(self.var_wl_hi, self.wl_full[1])))
        t_lo, t_hi = sorted((val(self.var_t_lo, self.t_full[0]),
                             val(self.var_t_hi, self.t_full[1])))
        wl_lo = max(wl_lo, self.wl_full[0])
        wl_hi = min(wl_hi, self.wl_full[1])
        t_lo = max(t_lo, self.t_full[0])
        t_hi = min(t_hi, self.t_full[1])
        if wl_hi <= wl_lo:
            wl_lo, wl_hi = self.wl_full
        if t_hi <= t_lo:
            t_lo, t_hi = self.t_full
        return wl_lo, wl_hi, t_lo, t_hi

    def _crop_state(self):
        return (self._corner, self.var_wl_lo.get(), self.var_wl_hi.get(),
                self.var_t_lo.get(), self.var_t_hi.get(), self.var_info.get())

    def _undo_click(self, before):
        """Take back what the single click just before did to the crop box.

        A double-click arrives as a single click followed by the double one,
        so by then its first half has already been read as a crop corner.
        ``before`` is the crop state that click found, or None if it missed
        the map.
        """
        if before is None:
            return
        box_changed = before[1:5] != self._crop_state()[1:5]
        self._corner = before[0]
        for var, value in zip((self.var_wl_lo, self.var_wl_hi,
                               self.var_t_lo, self.var_t_hi), before[1:5]):
            var.set(value)
        if box_changed:
            self._update_overlay()
        self.var_info.set(before[5])

    def _on_motion(self, event):
        """Unpinned, the time slice follows the pointer over the map.

        With the right button held the map follows it instead.
        """
        # a release that never arrived (the window lost the mouse meanwhile)
        # must not leave the map stuck to the pointer. matplotlib >= 3.10
        # reports the buttons held during a move; before that Tk's own event
        # says it (0x400: button 3 down)
        held = getattr(event, "buttons", None)
        if held is None:
            state = getattr(event.guiEvent, "state", None)
            if isinstance(state, int):
                held = (3,) if state & 0x400 else ()
        if held is not None and 3 not in held:
            self._pan = None
        if self._pan is not None:
            x, y, xlim, ylim = self._pan
            full_x, full_y = self._view_full()
            box = self.ax.bbox
            self._set_view(
                self._moved(xlim, full_x, False, shift=(x - event.x) / box.width),
                self._moved(ylim, full_y, self.var_tlog.get(),
                            shift=(y - event.y) / box.height))
            return
        if self._slice_pinned or event.inaxes is not self.ax or event.ydata is None:
            return
        ti = self._time_bin(event.ydata)
        if ti != self._slice_ti:
            self._slice_ti = ti
            self._draw_slice()
            self.canvas.draw_idle()

    def _on_leave(self, event):
        """The pointer left the map (or the whole figure): drop an unpinned slice."""
        if event.name == "axes_leave_event" and event.inaxes is not self.ax:
            return
        if not self._slice_pinned and self._slice_ti is not None:
            self._slice_ti = None
            self._draw_slice()
            self.canvas.draw_idle()

    def _on_click(self, event):
        if event.button != 1:       # the right button drags the view, no more
            if event.button == 3 and event.inaxes is self.ax:
                self._pan = (event.x, event.y, self.ax.get_xlim(), self.ax.get_ylim())
            return
        if self._pan is not None:   # a left click in the middle of a drag
            return
        # only the click directly before a double-click may be taken back
        undo, self._click_undo = self._click_undo, None
        if event.inaxes is not self.ax or event.xdata is None:
            return
        if event.dblclick:          # pin / release the time slice, crop untouched
            self._undo_click(undo)
            # Tk reports the third press of a triple click as a double one
            # again, which would undo the toggle the second press just made
            if time.monotonic() - self._pin_time < 0.5:
                return
            self._pin_time = time.monotonic()
            self._slice_pinned = not self._slice_pinned
            self._slice_ti = self._time_bin(event.ydata)
            self._draw_slice()
            self.canvas.draw_idle()
            return
        self._click_undo = self._crop_state()
        x = float(np.clip(event.xdata, *self.wl_full))
        y = float(np.clip(event.ydata, *self.t_full))
        if self._corner is None:
            self._corner = (x, y)
            self.var_info.set(f"corner at {x:.0f} nm, {y:.0f} ps - click the opposite one")
        else:
            x0, y0 = self._corner
            self._corner = None
            self.var_wl_lo.set(f"{min(x0, x):g}")
            self.var_wl_hi.set(f"{max(x0, x):g}")
            self.var_t_lo.set(f"{min(y0, y):g}")
            self.var_t_hi.set(f"{max(y0, y):g}")
            self._update_overlay()

    def _full_wl(self):
        self.var_wl_lo.set(f"{self.wl_full[0]:g}")
        self.var_wl_hi.set(f"{self.wl_full[1]:g}")
        self._update_overlay()

    def _full_t(self):
        self.var_t_lo.set(f"{self.t_full[0]:g}")
        self.var_t_hi.set(f"{self.t_full[1]:g}")
        self._update_overlay()

    # -- solvent ---------------------------------------------------------
    def _sync_solvent_controls(self):
        """File-name label and SCALE widgets follow whether a solvent is loaded."""
        loaded = self._solvent is not None
        self.var_solv_name.set(short_name(self._solvent["path"]) if loaded
                               else "none")
        self.scale.state(["!disabled"] if loaded else ["disabled"])
        self.ent_scale.configure(state="normal" if loaded else "disabled")

    def _set_scale(self, v, from_slider=False):
        """Take ``v`` as the scale and mirror it into the entry and the slider.

        Setting a ttk.Scale fires its command, so _busy keeps that from coming
        back in as a slider move; a value past the slider's range parks it at 2.
        """
        self._scale = v
        self.var_scale.set(f"{v:g}")
        if not from_slider:
            self._busy = True
            try:
                self.scale.set(min(v, 2.0))
            finally:
                self._busy = False

    def _on_slider(self, value):
        if self._busy:
            return
        v = round(float(value), 2)      # the widget reports 0.8532110091743119
        if v != self._scale:
            self._set_scale(v, from_slider=True)
            self._schedule()

    def _on_scale_entry(self):
        """Read the SCALE box; anything but a finite number >= 0 is put back."""
        if not self.alive:
            return
        try:
            v = float(self.var_scale.get())
        except ValueError:
            v = None
        if v is None or not np.isfinite(v) or v < 0:
            self.var_scale.set(f"{self._scale:g}")
            return
        if v != self._scale:
            self._set_scale(v)
            self._update_overlay()

    def _load_solvent(self):
        """Pick the solvent .phu; it is only taken if it sits on the sample's grid."""
        path = filedialog.askopenfilename(
            parent=self.win, title="Open the solvent measurement",
            filetypes=[("PicoQuant histogram", "*.phu"), ("All files", "*.*")])
        if not path:
            return
        try:
            solvent = read_phu(path)
        except Exception as exc:
            messagebox.showerror("Could not read file", str(exc), parent=self.win)
            return
        errors, notes = solvent_mismatch(self.model.phu, solvent)
        if errors:
            messagebox.showerror(
                "Solvent does not match the sample",
                "The solvent is subtracted bin for bin, so it has to be measured "
                "on the same grid as the sample.\n\n"
                + "\n".join(f"- {e}" for e in errors), parent=self.win)
            return
        if notes:
            messagebox.showwarning(
                "Solvent measured differently",
                "\n".join(f"- {n}" for n in notes)
                + "\n\nIt is loaded with the scale at 1 - adjust the scale to "
                  "make up for the difference.", parent=self.win)
        self._solvent = solvent
        self._sync_solvent_controls()   # enable the slider before moving it
        self._set_scale(1.0)
        self._update_overlay()

    def _clear_solvent(self):
        if self._solvent is None:
            return
        self._solvent = None
        self._set_scale(1.0)
        self._sync_solvent_controls()
        self._update_overlay()

    def _configure(self, model, box, with_solvent=True, sub=True):
        """Write this window's crop box - and solvent - into ``model``.

        The one place that maps the dialog onto a model, shared by the preview
        and by Apply so that the two cannot drift apart.
        """
        wl_lo, wl_hi, t_lo, t_hi = box
        full = (wl_lo <= self.wl_full[0] + 1e-6 and wl_hi >= self.wl_full[1] - 1e-6)
        model.crop_wl = None if full else (wl_lo, wl_hi)
        model.t_min_ps = t_lo
        model.t_max_ps = t_hi
        if with_solvent:
            model.solvent = self._solvent
            model.solvent_scale = self._scale
            model.solvent_sub = sub and self._solvent is not None

    def _reset(self):
        # the crop only: a solvent that was not applied yet stays a preview
        self._full_wl()
        self._full_t()
        self._apply(with_solvent=False)

    def _apply(self, with_solvent=True):
        self._on_scale_entry()      # a typed scale counts without Enter, too
        m = self.model
        self._configure(m, self._read(), with_solvent=with_solvent)
        m.rebuild()
        # keep the main viewer's TIME SPAN box and derived state consistent
        self.app.var_tmax.set(f"{m.t_max_ps:.0f}")
        self.app.clim = None
        self.app.view = None
        self.app.cursor = None
        self.app.pinned = False
        self.app.redraw(full=True)
        # a live mask window previews the (now re-cropped) map
        mw = self.app._mask_win
        if mw is not None and mw.alive:
            mw._draw()
            mw._refresh_list()
        self.var_info.set("applied")


class MaskDialog(_AnalysisDialog):
    """Add / remove wavelength bands that are set to NaN and so drop out of the
    map, the summed spectra and the fits (they stay in the axis as a gap)."""

    def __init__(self, app):
        super().__init__(app, "Mask wavelengths", "940x720", (760, 560))
        self.var_lo = tk.StringVar(value="")
        self.var_hi = tk.StringVar(value="")
        self.var_info = tk.StringVar(value="Click the map to pick From, then To.")
        self._pick_hi = False       # False -> next click sets From, True -> To
        self._build_ui()
        self._draw()
        self._refresh_list()

    def _build_ui(self):
        top = ttk.Frame(self.win, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="From").pack(side="left")
        ttk.Entry(top, textvariable=self.var_lo, width=8,
                  font=("TkFixedFont", 9)).pack(side="left", padx=2)
        ttk.Label(top, text="To").pack(side="left")
        ttk.Entry(top, textvariable=self.var_hi, width=8,
                  font=("TkFixedFont", 9)).pack(side="left", padx=2)
        ttk.Label(top, text="nm").pack(side="left", padx=(2, 8))
        ttk.Button(top, text="Add region", command=self._add).pack(side="left")
        ttk.Label(top, textvariable=self.var_info,
                  foreground=INK_FAINT).pack(side="left", padx=12)

        mid = ttk.Frame(self.win)
        mid.pack(fill="both", expand=True)
        self.fig = Figure(figsize=(7.6, 4.8), dpi=100, facecolor=PANEL)
        self.ax = self.fig.add_subplot(111)
        style_plot_ax(self.ax)
        self.canvas = FigureCanvasTkAgg(self.fig, master=mid)
        self.canvas.get_tk_widget().pack(side="left", fill="both", expand=True,
                                         padx=(8, 4), pady=4)
        self.canvas.mpl_connect("button_press_event", self._on_click)

        side = ttk.Frame(mid, padding=(4, 6))
        side.pack(side="left", fill="y")
        ttk.Label(side, text="Masked regions (NaN)").pack(anchor="w")
        self.listbox = tk.Listbox(side, width=20, height=14, bg=BG, fg=INK,
                                  selectbackground=ACCENT, selectforeground=BG,
                                  highlightthickness=1, highlightbackground=LINE,
                                  activestyle="none", font=("TkFixedFont", 9))
        self.listbox.pack(fill="y", expand=True, pady=3)
        ttk.Button(side, text="Remove selected",
                   command=self._remove).pack(fill="x", pady=1)
        ttk.Button(side, text="Clear all", command=self._clear).pack(fill="x", pady=1)
        ttk.Button(side, text="Close",
                   command=self._on_close).pack(fill="x", pady=(10, 1))

    def _draw(self):
        self.ax.clear()
        style_plot_ax(self.ax)
        m = self.model
        transform, norm, cmap = preview_norm_cmap(
            m.vmax, self.app.var_log.get(), self.app.var_cmap.get())
        w_lo, w_hi = m.wl_edges
        self.ax.imshow(transform(m.E.T), aspect="auto", origin="lower", cmap=cmap,
                       norm=norm, extent=[w_lo, w_hi, m.t_lo, m.t_hi],
                       interpolation="nearest")
        shade_wl_masks(self.ax, m.masks, w_lo, w_hi)
        self.ax.set_xlim(w_lo, w_hi)
        self.ax.set_ylim(m.t_lo, m.t_hi)
        self.ax.set_xlabel("Wavelength (nm)", fontsize=9)
        self.ax.set_ylabel("Time (ps)", fontsize=9)
        self.canvas.draw_idle()

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for lo, hi in self.model.masks:
            self.listbox.insert("end", f"{lo:.1f} - {hi:.1f} nm")

    def _on_click(self, event):
        if event.inaxes is not self.ax or event.xdata is None:
            return
        wl = float(event.xdata)
        if not self._pick_hi:
            self.var_lo.set(f"{wl:.1f}")
            self._pick_hi = True
            self.var_info.set("Now click the To (end) wavelength.")
        else:
            self.var_hi.set(f"{wl:.1f}")
            self._pick_hi = False
            self.var_info.set("Press Add region (or click to re-pick From).")

    def _add(self):
        try:
            lo = float(self.var_lo.get())
            hi = float(self.var_hi.get())
        except ValueError:
            messagebox.showwarning("Invalid range",
                                   "Enter numeric From / To wavelengths.",
                                   parent=self.win)
            return
        if hi < lo:
            lo, hi = hi, lo
        if hi <= lo:
            messagebox.showwarning("Invalid range",
                                   "From must differ from To.", parent=self.win)
            return
        self.model.masks.append((lo, hi))
        self._commit()
        self._pick_hi = False
        self.var_info.set(f"masked {lo:.1f}-{hi:.1f} nm - pick the next region")

    def _remove(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in sorted(sel, reverse=True):
            if 0 <= i < len(self.model.masks):
                self.model.masks.pop(i)
        self._commit()

    def _clear(self):
        if not self.model.masks:
            return
        self.model.masks = []
        self._commit()

    def _commit(self):
        self.model.rebuild()
        self.app.redraw(full=True)
        self._draw()
        self._refresh_list()


class KineticsDialog(_AnalysisDialog):
    """Fit the decay at one wavelength to a sum of IRF-convolved exponentials."""

    def __init__(self, app):
        super().__init__(app, "Kinetics fit - single wavelength",
                         "1180x760", (900, 560))
        self._last = None                   # last fit_single_trace result dict
        self._q = queue.Queue()             # worker -> main-thread messages
        self._running = False
        self._job = 0                       # bumped when a running fit goes stale
        self._build()
        self._refresh_plot(replot_data=True)
        self.win.after(100, self._poll_queue)

    # -- layout ----------------------------------------------------------
    def _build(self):
        m = self.model
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Labelframe(outer, text="Setup", padding=8)
        left.pack(side="left", fill="y")
        left.configure(width=430)
        left.pack_propagate(False)

        # wavelength + averaging window
        wl_row = ttk.Frame(left); wl_row.pack(fill="x")
        ttk.Label(wl_row, text="Centre λ (nm)").pack(side="left")
        self.var_wl = tk.StringVar(value=f"{self._cursor_wl():.2f}")
        e_wl = ttk.Entry(wl_row, textvariable=self.var_wl, width=9,
                         font=("TkFixedFont", 9))
        e_wl.pack(side="left", padx=(4, 8))
        ttk.Label(wl_row, text="± hw").pack(side="left")
        self.var_hw = tk.StringVar(value="0")
        e_hw = ttk.Entry(wl_row, textvariable=self.var_hw, width=6,
                         font=("TkFixedFont", 9))
        e_hw.pack(side="left", padx=(4, 8))
        # editing λ / half-width must redraw the trace (Enter or focus-out) -
        # without this the data points stay on the old wavelength
        for e in (e_wl, e_hw):
            e.bind("<Return>", self._on_wl_change)
            e.bind("<FocusOut>", self._on_wl_change)
        # remembers the last (λ, hw) actually drawn, so a focus-out that did
        # not change anything does not needlessly drop a good fit
        self._wl_key = (self.var_wl.get().strip(), self.var_hw.get().strip())
        ttk.Button(wl_row, text="Use cursor λ",
                   command=self._use_cursor).pack(side="left")

        # component count + inf offset
        n_row = ttk.Frame(left); n_row.pack(fill="x", pady=(8, 4))
        ttk.Label(n_row, text="Components").pack(side="left")
        self.var_n = tk.StringVar(value="2")
        cb = ttk.Combobox(n_row, textvariable=self.var_n, values=["1", "2", "3", "4"],
                          width=4, state="readonly")
        cb.pack(side="left", padx=(4, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self.table.set_n(int(self.var_n.get())))
        self.var_inf = tk.BooleanVar(value=False)
        ttk.Checkbutton(n_row, text="τ = ∞ offset",
                        variable=self.var_inf).pack(side="left")

        self.table = ComponentTable(left)
        self.table.pack(fill="x", pady=(2, 6))
        self.table.set_n(2)

        # IRF group
        t0d, fwd = self._irf_defaults()
        irf = ttk.Labelframe(left, text="IRF (Gaussian)", padding=6)
        irf.pack(fill="x", pady=(2, 6))
        self.var_t0 = tk.StringVar(value=f"{t0d:.4g}")
        self.var_t0_fix = tk.BooleanVar(value=True)
        self.var_fw = tk.StringVar(value=f"{fwd:.4g}")
        self.var_fw_fix = tk.BooleanVar(value=True)
        self._irf_row(irf, "t₀ (ps)", self.var_t0, self.var_t0_fix)
        self._irf_row(irf, "FWHM (ps)", self.var_fw, self.var_fw_fix)
        mode_row = ttk.Frame(irf); mode_row.pack(fill="x", pady=(2, 0))
        ttk.Label(mode_row, text="Stretched-IRF mode").pack(side="left")
        self.var_irf_mode = tk.StringVar(value="numerical")
        ttk.Combobox(mode_row, textvariable=self.var_irf_mode,
                     values=["numerical", "skip"], width=11,
                     state="readonly").pack(side="left", padx=(6, 0))

        # fit window
        win_row = ttk.Labelframe(left, text="Fit window (delay, ps)", padding=6)
        win_row.pack(fill="x", pady=(2, 6))
        self.var_tmin = tk.StringVar(value=f"{m.times[0]:.4g}")
        self.var_tmax = tk.StringVar(value=f"{m.times[-1]:.4g}")
        ttk.Label(win_row, text="From").pack(side="left")
        ttk.Entry(win_row, textvariable=self.var_tmin, width=9,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Label(win_row, text="To").pack(side="left")
        ttk.Entry(win_row, textvariable=self.var_tmax, width=9,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Button(win_row, text="Full", command=self._t_full).pack(side="left")

        # scale + run
        run_row = ttk.Frame(left); run_row.pack(fill="x", pady=(2, 6))
        ttk.Label(run_row, text="Time scale").pack(side="left")
        self.var_scale = tk.StringVar(value="Log")
        sc = ttk.Combobox(run_row, textvariable=self.var_scale,
                          values=["Log", "Linear"], width=8, state="readonly")
        sc.pack(side="left", padx=(4, 10))
        sc.bind("<<ComboboxSelected>>", lambda e: self._refresh_plot())
        self.btn_run = ttk.Button(run_row, text="Run Fit", command=self.run_fit)
        self.btn_run.pack(side="left")
        ttk.Button(run_row, text="Reset", command=self.reset).pack(side="left", padx=(6, 0))

        exp_row = ttk.Frame(left); exp_row.pack(fill="x")
        ttk.Label(exp_row, text="Export").pack(side="left")
        ttk.Button(exp_row, text="Export results",
                   command=self.export_results).pack(side="left", padx=(6, 0))
        ttk.Label(exp_row, text="(uses main CSV / .opju)",
                  style="Val.TLabel", foreground=INK_FAINT).pack(side="left", padx=(6, 0))

        self.var_status = tk.StringVar(value="Ready.")
        ttk.Label(left, textvariable=self.var_status, style="Val.TLabel",
                  foreground=ACCENT).pack(anchor="w", pady=(6, 2))
        self.txt = tk.Text(left, height=12, width=48, bg=BG, fg=INK,
                           insertbackground=INK, relief="flat",
                           font=("TkFixedFont", 9), wrap="none")
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", "Set up the fit on the left, then Run Fit.")

        # right: plots
        right = ttk.Labelframe(outer, text="Trace, fit, residual", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        self.fig = Figure(figsize=(7, 6), dpi=100, facecolor=PANEL)
        self.ax_main = self.fig.add_subplot(2, 1, 1)
        self.ax_res = self.fig.add_subplot(2, 1, 2, sharex=self.ax_main)
        self.fig.subplots_adjust(left=0.12, right=0.97, top=0.95, bottom=0.1,
                                 hspace=0.18)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        tb = _dark_toolbar(self.canvas, right)
        tb.pack(fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _irf_row(self, parent, label, var, fix_var):
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=10).pack(side="left")
        ttk.Entry(row, textvariable=var, width=10,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="fixed", variable=fix_var).pack(side="left")

    # -- helpers ---------------------------------------------------------
    def _on_wl_change(self, *_):
        """Redraw the trace when the centre λ / half-width is edited.

        Skips when nothing actually changed (a bare focus-out), so it will not
        throw away a fit for no reason. When λ does move, the previous fit
        belonged to the old wavelength, so it is dropped and only the new trace
        is shown until the user runs the fit again.
        """
        key = (self.var_wl.get().strip(), self.var_hw.get().strip())
        if key == self._wl_key:
            return
        self._wl_key = key
        self._job += 1                      # a fit still running is for the old λ
        if self._last is not None:
            self._last = None
            self.var_status.set("λ changed - run the fit again.")
        self._refresh_plot(replot_data=True)

    def _use_cursor(self):
        self.var_wl.set(f"{self._cursor_wl():.2f}")
        self._on_wl_change()

    def _t_full(self):
        m = self.model
        self.var_tmin.set(f"{m.times[0]:.4g}")
        self.var_tmax.set(f"{m.times[-1]:.4g}")

    def _get_trace(self):
        """(t, y, wl_actual, n_avg) - the decay to fit/plot at the chosen wl."""
        m = self.model
        try:
            wl = float(self.var_wl.get())
        except ValueError:
            wl = self._cursor_wl()
        try:
            hw = float(self.var_hw.get())
        except ValueError:
            hw = 0.0
        t = m.times.copy()
        if hw <= 0:
            wi = int(np.argmin(np.abs(m.wls - wl)))
            return t, m.E[wi, :].copy(), float(m.wls[wi]), 1
        sel = (m.wls >= wl - hw) & (m.wls <= wl + hw)
        if not sel.any():
            wi = int(np.argmin(np.abs(m.wls - wl)))
            return t, m.E[wi, :].copy(), float(m.wls[wi]), 1
        # nanmean: masked wavelengths inside the averaging window drop out
        # instead of turning the whole averaged decay into NaN.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            y = np.nanmean(m.E[sel, :], axis=0)
        return t, y, float(m.wls[sel].mean()), int(sel.sum())

    # -- run / reset -----------------------------------------------------
    def reset(self):
        self.var_n.set("2"); self.table.set_n(2)
        self.var_inf.set(False)
        t0d, fwd = self._irf_defaults()
        self.var_t0.set(f"{t0d:.4g}"); self.var_t0_fix.set(True)
        self.var_fw.set(f"{fwd:.4g}"); self.var_fw_fix.set(True)
        self.var_irf_mode.set("numerical")
        self._t_full()
        self._last = None
        self._job += 1
        self.var_status.set("Reset to defaults.")
        self.txt.delete("1.0", "end")
        self._refresh_plot(replot_data=True)

    # The fit runs on a worker thread, like the global one: a slow fit (a wide
    # window, a stretched component) must not leave the whole program "not
    # responding". The worker only computes; every widget is touched from
    # _poll_queue on the main thread.
    def run_fit(self):
        if self._running:
            return
        tau, fix, st, beta, bfix = self.table.read()
        if tau.size == 0:
            messagebox.showwarning("No components", "Add at least one component.")
            return
        if np.any(tau <= 0):
            messagebox.showwarning("Invalid input", "τ must be > 0.")
            return
        t_full, y_full, wl_actual, n_avg = self._get_trace()
        try:
            t_lo = float(self.var_tmin.get()); t_hi = float(self.var_tmax.get())
        except ValueError:
            t_lo, t_hi = float(t_full[0]), float(t_full[-1])
        if t_lo > t_hi:
            t_lo, t_hi = t_hi, t_lo
        sel = (t_full >= t_lo) & (t_full <= t_hi)
        n_in = int(sel.sum())
        n_min = int(tau.size) + (1 if self.var_inf.get() else 0) + 1
        if n_in < n_min:
            messagebox.showwarning(
                "Window too narrow", f"Need >= {n_min} delay points; got {n_in}.")
            return
        try:
            t0 = float(self.var_t0.get()); fw = float(self.var_fw.get())
        except ValueError:
            messagebox.showwarning("Invalid IRF", "t₀ and FWHM must be numbers.")
            return

        params = dict(
            tau_init=tau, tau_fixed=fix, beta_init=beta, beta_fixed=bfix,
            stretch_on=st, t0_init=t0, t0_fixed=self.var_t0_fix.get(),
            fwhm_init=fw, fwhm_fixed=self.var_fw_fix.get(),
            has_inf=self.var_inf.get(), irf_mode=self.var_irf_mode.get())
        # everything the result is shown with, as it is now: the boxes may be
        # edited while the fit runs
        extra = {"_t_fit": t_full[sel], "_y_fit": y_full[sel],
                 "_t_full": t_full, "_y_full": y_full,
                 "_wl": wl_actual, "_n_avg": n_avg,
                 "_stretch": st, "_has_inf": self.var_inf.get(),
                 "_t0_fixed": self.var_t0_fix.get(), "_fwhm_fixed": self.var_fw_fix.get()}
        report = (wl_actual, n_avg, t_lo, t_hi, n_in)
        # the fit runs on the boxes as they are now; remember them so a later
        # bare focus-out on the λ entry does not discard it
        self._wl_key = (self.var_wl.get().strip(), self.var_hw.get().strip())
        self._job += 1

        self._running = True
        self.btn_run.configure(state="disabled")
        self.win.configure(cursor="watch")
        self.var_status.set("Fitting...")
        threading.Thread(target=self._worker,
                         args=(t_full[sel], y_full[sel], params, extra, report, self._job),
                         daemon=True).start()

    def _worker(self, t, y, params, extra, report, job):
        try:
            res = fit_single_trace(t, y, **params)
            res.update(extra)
            self._q.put(("done", (res, report, job)))
        except Exception as exc:               # noqa: BLE001 - surfaced to UI
            self._q.put(("error", str(exc)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                self._running = False
                self.btn_run.configure(state="normal")
                self.win.configure(cursor="")
                if kind == "done":
                    self._on_done(*payload)
                else:
                    self.var_status.set("Fit failed.")
                    messagebox.showerror("Fit error", f"Fit failed:\n{payload}")
        except queue.Empty:
            pass
        finally:                # an error above must not end the polling
            if self.alive:
                self.win.after(100, self._poll_queue)

    def _on_done(self, res, report, job):
        if job != self._job:        # λ was changed or Reset pressed meanwhile
            self.var_status.set("Fit dropped - the setup changed while it ran.")
            return
        self._last = res
        self._report(res, *report)
        self.var_status.set(f"Fit done - RMS = {res['info']['rms']:.3g}")
        self._refresh_plot()

    def _report(self, res, wl, n_avg, t_lo, t_hi, n_in):
        L = [f"Fit converged ({res['info']['iters']} iters), "
             f"RMS = {res['info']['rms']:.4g}",
             f"λ centre = {wl:.2f} nm  (avg of {n_avg} px)",
             f"Window: [{t_lo:.4g}, {t_hi:.4g}] ps, n = {n_in}",
             f"IRF mode: {res['info']['irf_mode']}", "",
             "  i   τ (ps)        β       A          (type)"]
        st = res["_stretch"]
        for i in range(len(res["tau"])):
            tag = "stretched" if st[i] else "exp"
            L.append(f"  {i+1}   {res['tau'][i]:10.4g}  {res['beta'][i]:6.3g}  "
                     f"{res['A'][i]:10.4g}  ({tag})")
        if res["_has_inf"]:
            L.append(f"  ∞   {'':10}  {'':6}  {res['A'][-1]:10.4g}  (offset)")
        L += ["", f"t₀ = {res['t0']:.4g} ps"
              + ("  (fixed)" if res["_t0_fixed"] else ""),
              f"FWHM = {res['fwhm']:.4g} ps"
              + ("  (fixed)" if res["_fwhm_fixed"] else "")]
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", "\n".join(L))

    # -- plotting --------------------------------------------------------
    def _refresh_plot(self, replot_data=False):
        ax, axR = self.ax_main, self.ax_res
        # drop back to linear before clearing so clear() never autoscales a
        # log axis (which would warn about the non-positive default limits)
        ax.set_xscale("linear"); axR.set_xscale("linear")
        ax.clear(); axR.clear()
        _style_analysis_ax(ax); _style_analysis_ax(axR)

        if replot_data or self._last is None:
            t, y, wl, n_avg = self._get_trace()
        else:
            t = self._last["_t_full"]; y = self._last["_y_full"]
            wl = self._last["_wl"]; n_avg = self._last["_n_avg"]

        ax.plot(t, y, ".", color=INK_DIM, markersize=3, label="data")
        if self._last is not None:
            ax.plot(self._last["_t_fit"], self._last["fit"], "-",
                    color=ACCENT, linewidth=1.4, label="fit")
            axR.plot(self._last["_t_fit"], self._last["residual"], ".",
                     color=PIN, markersize=2)
        ax.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        axR.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        if self.var_scale.get() == "Log" and np.any(t > 0):
            pos = t[t > 0]
            ax.set_xscale("log"); axR.set_xscale("log")
            ax.set_xlim(pos.min(), t.max()); axR.set_xlim(pos.min(), t.max())
        else:
            ax.set_xscale("linear"); axR.set_xscale("linear")
            ax.set_xlim(t.min(), t.max()); axR.set_xlim(t.min(), t.max())
        ax.set_ylabel("intensity"); axR.set_ylabel("residual")
        axR.set_xlabel("delay (ps)")
        ax.set_title(f"λ = {wl:.2f} nm   (avg {n_avg} px)")
        leg = ax.legend(loc="best", fontsize=8, facecolor=PANEL, edgecolor=LINE)
        for txt in leg.get_texts():
            txt.set_color(INK)
        ax.grid(True, color=LINE, alpha=0.4); axR.grid(True, color=LINE, alpha=0.4)
        self.canvas.draw_idle()

    # -- export ----------------------------------------------------------
    def _param_summary(self, r):
        """Multi-line fit summary for the CSV preamble / opju column comment."""
        lines = [f"lambda = {r['_wl']:.2f} nm (avg {r['_n_avg']} px)",
                 f"RMS = {r['info']['rms']:.6g}, {r['info']['iters']} iters, "
                 f"IRF {r['info']['irf_mode']}",
                 f"t0 = {r['t0']:.6g} ps, FWHM = {r['fwhm']:.6g} ps"]
        st = r["_stretch"]
        for i in range(len(r["tau"])):
            tag = "stretched" if st[i] else "exp"
            lines.append(f"comp {i+1}: tau = {r['tau'][i]:.6g} ps, "
                         f"beta = {r['beta'][i]:.4g}, A = {r['A'][i]:.6g} ({tag})")
        if r["_has_inf"]:
            lines.append(f"offset: A_inf = {r['A'][-1]:.6g}")
        return lines

    def export_results(self):
        """Write the trace + fit + residual, honouring the main CSV/.opju ticks.

        One dataset ({stem}_kinetics): delay / data / fit / residual, with the
        fit parameters in the CSV preamble and the opju column comment.
        """
        if self._last is None:
            messagebox.showwarning("No fit", "Run the fit first.")
            return
        r = self._last
        phu_base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        default_base = phu_base            # suffix "kinetics" completes the name
        t = np.asarray(r["_t_fit"]); y = np.asarray(r["_y_fit"])
        fit = np.asarray(r["fit"]); resid = np.asarray(r["residual"])
        preamble = self._param_summary(r)
        taus = "; ".join(f"tau{i+1}={r['tau'][i]:.4g}ps" for i in range(len(r["tau"])))
        comment = f"{r['_wl']:.2f} nm; {taus}; RMS={r['info']['rms']:.4g}"

        def write_csv(path):
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write("# kinetics fit (single wavelength)\n")
                fh.write(f'# source: {self.model.phu["path"]}\n')
                for line in preamble:
                    fh.write(f"# {line}\n")
                if self.model.solvent_active:    # the trace was fitted after it
                    fh.write(f"# {self.app._export_note()}\n")
                fh.write("delay_ps,data,fit,residual\n")
                np.savetxt(fh, np.column_stack([t, y, fit, resid]),
                           delimiter=",", fmt="%.8g")

        def fill_ws(ws):
            pd = self.app._require_pandas()
            df = pd.DataFrame({"delay_ps": t, "data": y, "fit": fit, "residual": resid})
            _origin_fill_table(ws, df, [
                ("Delay", "ps", comment),
                ("Data", "a. u.", f"{r['_wl']:.2f} nm"),
                ("Fit", "a. u.", ""),
                ("Residual", "a. u.", "")])

        self.app.export_analysis(default_base, [
            {"suffix": "kinetics", "csv": write_csv, "fill": fill_ws}])


class GlobalAnalysisDialog(_AnalysisDialog):
    """VARPRO global fit of the whole map: fit maps, DADS, EADS, kinetics."""

    def __init__(self, app):
        super().__init__(app, "Global analysis - whole map",
                         "1500x960", (1100, 720))
        self._last = None                   # last fit_global_analysis result
        self._stop = threading.Event()
        self._q = queue.Queue()
        self._running = False
        self._kin_wl = self._cursor_wl()
        self._build()
        self.win.after(100, self._poll_queue)

    def _on_close(self):
        self._stop.set()
        super()._on_close()

    # -- layout ----------------------------------------------------------
    def _build(self):
        m = self.model
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)

        left = ttk.Labelframe(outer, text="Fit setup", padding=8)
        left.pack(side="left", fill="y")
        left.configure(width=380)
        left.pack_propagate(False)

        n_row = ttk.Frame(left); n_row.pack(fill="x")
        ttk.Label(n_row, text="Components").pack(side="left")
        self.var_n = tk.StringVar(value="3")
        cb = ttk.Combobox(n_row, textvariable=self.var_n,
                          values=["1", "2", "3", "4", "5"], width=4, state="readonly")
        cb.pack(side="left", padx=(4, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self.table.set_n(int(self.var_n.get())))
        self.var_inf = tk.BooleanVar(value=False)
        ttk.Checkbutton(n_row, text="Include τ = ∞",
                        variable=self.var_inf).pack(side="left")

        self.table = ComponentTable(left)
        self.table.pack(fill="x", pady=(4, 6))
        self.table.set_n(3)

        opt = ttk.Frame(left); opt.pack(fill="x", pady=(0, 4))
        ttk.Label(opt, text="Optimizer").pack(side="left")
        self.var_opt = tk.StringVar(value="TRF (fast)")
        ttk.Combobox(opt, textvariable=self.var_opt,
                     values=["TRF (fast)", "Nelder-Mead"], width=13,
                     state="readonly").pack(side="left", padx=(4, 10))
        ttk.Label(opt, text="Stretched-IRF").pack(side="left")
        self.var_irf_mode = tk.StringVar(value="numerical")
        ttk.Combobox(opt, textvariable=self.var_irf_mode,
                     values=["numerical", "skip"], width=10,
                     state="readonly").pack(side="left", padx=(4, 0))

        t0d, fwd = self._irf_defaults()
        irf = ttk.Labelframe(left, text="IRF (Gaussian)", padding=6)
        irf.pack(fill="x", pady=(2, 6))
        self.var_t0 = tk.StringVar(value=f"{t0d:.4g}")
        self.var_t0_fix = tk.BooleanVar(value=True)
        self.var_fw = tk.StringVar(value=f"{fwd:.4g}")
        self.var_fw_fix = tk.BooleanVar(value=True)
        self._irf_row(irf, "t₀ (ps)", self.var_t0, self.var_t0_fix)
        self._irf_row(irf, "FWHM (ps)", self.var_fw, self.var_fw_fix)

        tr = ttk.Labelframe(left, text="Fit t-range (ps)", padding=6)
        tr.pack(fill="x", pady=(2, 6))
        r1 = ttk.Frame(tr); r1.pack(fill="x")
        self.var_tmin = tk.StringVar(value=f"{m.times[0]:.4g}")
        self.var_tmax = tk.StringVar(value=f"{m.times[-1]:.4g}")
        ttk.Label(r1, text="From").pack(side="left")
        e0 = ttk.Entry(r1, textvariable=self.var_tmin, width=9, font=("TkFixedFont", 9))
        e0.pack(side="left", padx=(4, 8))
        ttk.Label(r1, text="To").pack(side="left")
        e1 = ttk.Entry(r1, textvariable=self.var_tmax, width=9, font=("TkFixedFont", 9))
        e1.pack(side="left", padx=(4, 8))
        ttk.Button(r1, text="Full", command=self._t_full).pack(side="left")
        self.var_tcount = tk.StringVar(value="")
        ttk.Label(tr, textvariable=self.var_tcount, style="Val.TLabel",
                  foreground=INK_FAINT).pack(anchor="w", pady=(3, 0))
        for e in (e0, e1):
            e.bind("<KeyRelease>", lambda ev: self._update_tcount())
        self._update_tcount()

        btns = ttk.Frame(left); btns.pack(fill="x", pady=(2, 6))
        self.btn_run = ttk.Button(btns, text="Run Fit", command=self.run_fit)
        self.btn_run.pack(side="left")
        self.btn_stop = ttk.Button(btns, text="Stop", command=self.stop_fit,
                                   state="disabled")
        self.btn_stop.pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Reset", command=self.reset).pack(side="left", padx=(6, 0))

        exp = ttk.Frame(left); exp.pack(fill="x")
        ttk.Label(exp, text="Export").pack(side="left")
        ttk.Button(exp, text="Export results",
                   command=self.export_results).pack(side="left", padx=(6, 0))
        ttk.Label(exp, text="(DADS + EADS; uses main CSV / .opju)",
                  style="Val.TLabel", foreground=INK_FAINT).pack(side="left", padx=(6, 0))

        self.var_status = tk.StringVar(value="Ready.")
        ttk.Label(left, textvariable=self.var_status, style="Val.TLabel",
                  foreground=ACCENT).pack(anchor="w", pady=(6, 2))
        self.txt = tk.Text(left, height=14, width=42, bg=BG, fg=INK,
                           insertbackground=INK, relief="flat",
                           font=("TkFixedFont", 9), wrap="none")
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", "Results will appear here after fitting.")

        # right: kinetics controls + figure
        right = ttk.Labelframe(outer, text="Results", padding=6)
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))

        kin = ttk.Frame(right); kin.pack(fill="x")
        ttk.Label(kin, text="Kinetics λ (nm)").pack(side="left")
        self.var_kin_wl = tk.StringVar(value=f"{self._kin_wl:.2f}")
        ek = ttk.Entry(kin, textvariable=self.var_kin_wl, width=9, font=("TkFixedFont", 9))
        ek.pack(side="left", padx=(4, 8))
        ek.bind("<Return>", lambda ev: self._set_kin_wl())
        ttk.Button(kin, text="Use cursor λ",
                   command=self._use_cursor_kin).pack(side="left")
        ttk.Label(kin, text="Scale").pack(side="left", padx=(10, 4))
        self.var_kin_scale = tk.StringVar(value="Log")
        sc = ttk.Combobox(kin, textvariable=self.var_kin_scale,
                          values=["Log", "Linear"], width=8, state="readonly")
        sc.pack(side="left")
        sc.bind("<<ComboboxSelected>>", lambda e: self._plot_kinetics())
        ttk.Label(kin, text="  (click a map to pick λ)",
                  style="Val.TLabel", foreground=INK_FAINT).pack(side="left", padx=(8, 0))

        self.fig = Figure(figsize=(11, 8), dpi=100, facecolor=PANEL)
        gs = GridSpec(4, 3, figure=self.fig, height_ratios=[1.4, 1.0, 1.0, 1.1],
                      left=0.07, right=0.97, top=0.95, bottom=0.06,
                      hspace=0.5, wspace=0.28)
        self.ax_data = self.fig.add_subplot(gs[0, 0])
        self.ax_fit = self.fig.add_subplot(gs[0, 1])
        self.ax_resid = self.fig.add_subplot(gs[0, 2])
        self.ax_dads = self.fig.add_subplot(gs[1, 0:2])
        self.ax_dads_n = self.fig.add_subplot(gs[1, 2])
        self.ax_eads = self.fig.add_subplot(gs[2, 0:2])
        self.ax_eads_n = self.fig.add_subplot(gs[2, 2])
        self.ax_kin = self.fig.add_subplot(gs[3, :])
        self._all_axes = [self.ax_data, self.ax_fit, self.ax_resid,
                          self.ax_dads, self.ax_dads_n, self.ax_eads,
                          self.ax_eads_n, self.ax_kin]
        for ax in self._all_axes:
            _style_analysis_ax(ax)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        tb = _dark_toolbar(self.canvas, right)
        tb.pack(fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("button_press_event", self._on_map_click)
        self.canvas.draw_idle()

    def _irf_row(self, parent, label, var, fix_var):
        row = ttk.Frame(parent); row.pack(fill="x", pady=1)
        ttk.Label(row, text=label, width=10).pack(side="left")
        ttk.Entry(row, textvariable=var, width=10,
                  font=("TkFixedFont", 9)).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(row, text="fixed", variable=fix_var).pack(side="left")

    # -- small helpers ---------------------------------------------------
    def _t_full(self):
        m = self.model
        self.var_tmin.set(f"{m.times[0]:.4g}")
        self.var_tmax.set(f"{m.times[-1]:.4g}")
        self._update_tcount()

    def _update_tcount(self):
        m = self.model
        try:
            lo = float(self.var_tmin.get()); hi = float(self.var_tmax.get())
        except ValueError:
            self.var_tcount.set(""); return
        if lo > hi:
            lo, hi = hi, lo
        n_in = int(((m.times >= lo) & (m.times <= hi)).sum())
        self.var_tcount.set(f"  -> fit will use {n_in} of {m.n_t} delay points")

    def _use_cursor_kin(self):
        self._kin_wl = self._cursor_wl()
        self.var_kin_wl.set(f"{self._kin_wl:.2f}")
        self._plot_kinetics()

    def _set_kin_wl(self):
        try:
            self._kin_wl = float(self.var_kin_wl.get())
        except ValueError:
            return
        self._plot_kinetics()

    def _on_map_click(self, event):
        if event.inaxes in (self.ax_data, self.ax_fit, self.ax_resid) \
                and event.xdata is not None:
            self._kin_wl = float(event.xdata)
            self.var_kin_wl.set(f"{self._kin_wl:.2f}")
            self._plot_kinetics()

    def reset(self):
        self.var_n.set("3"); self.table.set_n(3)
        self.var_inf.set(False)
        self.var_opt.set("TRF (fast)"); self.var_irf_mode.set("numerical")
        t0d, fwd = self._irf_defaults()
        self.var_t0.set(f"{t0d:.4g}"); self.var_t0_fix.set(True)
        self.var_fw.set(f"{fwd:.4g}"); self.var_fw_fix.set(True)
        self._t_full()
        self._last = None
        self.var_status.set("Reset to defaults.")
        self.txt.delete("1.0", "end")

    # -- run (threaded) --------------------------------------------------
    def run_fit(self):
        if self._running:
            return
        m = self.model
        tau, fix, st, beta, bfix = self.table.read()
        if tau.size == 0 or np.any(tau <= 0):
            messagebox.showwarning("Invalid input", "τ must be > 0.")
            return
        try:
            t0 = float(self.var_t0.get()); fw = float(self.var_fw.get())
            lo = float(self.var_tmin.get()); hi = float(self.var_tmax.get())
        except ValueError:
            messagebox.showwarning("Invalid input", "Check the IRF / t-range boxes.")
            return
        if lo > hi:
            lo, hi = hi, lo
        tsel = (m.times >= lo) & (m.times <= hi)
        if int(tsel.sum()) < tau.size + 2:
            messagebox.showwarning("Window too narrow",
                                   "Widen the fit t-range.")
            return
        # snapshot the data so the worker never touches the live model
        D = m.E[:, tsel].copy()
        t = m.times[tsel].copy()
        # masked wavelengths are all-NaN rows; drop them so the fit only sees
        # real spectra (they simply never appear in the global-analysis result).
        wls_fit = m.wls.copy()
        keep = ~np.isnan(D).any(axis=1)
        if not keep.all():
            D = D[keep]
            wls_fit = wls_fit[keep]
        if D.shape[0] < 2:
            messagebox.showwarning(
                "Nothing to fit",
                "Every wavelength in range is masked out. Clear some masks "
                "or widen the crop.")
            return
        method = "trf" if self.var_opt.get().startswith("TRF") else "nm"
        params = dict(
            tau_init=tau, tau_fixed=fix, t0_init=t0, fwhm_init=fw,
            t0_fixed=self.var_t0_fix.get(), fwhm_fixed=self.var_fw_fix.get(),
            has_inf=self.var_inf.get(), beta_init=beta, beta_fixed=bfix,
            stretch_on=st, irf_mode=self.var_irf_mode.get(), method=method)

        # snapshot exactly what the fit sees, so redraws never depend on the
        # entry boxes the user may edit while / after the fit runs
        self._fit_D = D
        self._fit_t = t
        self._fit_wls = wls_fit
        self._stop.clear()
        self._running = True
        self.btn_run.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.var_status.set("Fitting...")
        threading.Thread(target=self._worker, args=(D, t, params),
                         daemon=True).start()

    def _worker(self, D, t, params):
        try:
            res = fit_global_analysis(
                D, t, stop_check=self._stop.is_set, **params)
            self._q.put(("done", res))
        except GlobalAnalysisStopped:
            self._q.put(("stopped", None))
        except Exception as exc:               # noqa: BLE001 - surfaced to UI
            self._q.put(("error", str(exc)))

    def stop_fit(self):
        if self._running:
            self._stop.set()
            self.btn_stop.configure(state="disabled")
            self.var_status.set("Stopping...")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                if kind == "done":
                    self._on_done(payload)
                elif kind == "stopped":
                    self._finish_run("Stopped by user.")
                elif kind == "error":
                    self._finish_run("Fit failed.")
                    messagebox.showerror("Fit error", str(payload))
        except queue.Empty:
            pass
        finally:                # an error above must not end the polling
            if self.alive:
                self.win.after(150, self._poll_queue)

    def _finish_run(self, status):
        self._running = False
        self.btn_run.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.var_status.set(status)

    def _on_done(self, res):
        self._last = res
        # DADS = the amplitude spectra A (M x k); EADS from the sequential model
        A = res["A"]
        tau = res["tau"]
        has_inf = self.var_inf.get()
        try:
            eads, tau_sorted, _ = compute_eads_from_dads(A, tau, has_inf)
        except Exception:
            eads, tau_sorted = A.copy(), np.sort(tau)
        res["_eads"] = eads
        res["_tau_sorted"] = tau_sorted
        self._report_global(res)
        self._finish_run(f"Fit done - RMS = {res['info']['rms']:.4g} "
                         f"({res['info']['iters']} evals)")
        self._draw_all()

    def _report_global(self, res):
        has_inf = self.var_inf.get()
        L = [f"Global fit: RMS = {res['info']['rms']:.4g}  "
             f"(initial {res['info']['initialRMS']:.4g})",
             f"method = {res['info']['method']}, "
             f"{res['info']['iters']} objective evals",
             f"IRF: t₀ = {res['t0']:.4g} ps, FWHM = {res['fwhm']:.4g} ps",
             f"IRF mode: {res['info']['irf_mode']}", "",
             "  i   τ (ps)         β      (type)"]
        st = res["stretch_on"]
        for i in range(len(res["tau"])):
            tag = "stretched" if st[i] else "exp"
            L.append(f"  {i+1}   {res['tau'][i]:11.5g}  {res['beta'][i]:6.3g}  ({tag})")
        if has_inf:
            L.append("  ∞   (constant offset)")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", "\n".join(L))

    # -- drawing ---------------------------------------------------------
    def _draw_all(self):
        self._plot_maps()
        self._plot_spectra()
        self._plot_kinetics()
        self.canvas.draw_idle()

    def _plot_maps(self):
        res = self._last
        wl = self._fit_wls
        t = self._fit_t
        D = self._fit_D
        fit = res["fit"]
        resid = D - fit
        ext = [wl[0], wl[-1], t[-1], t[0]]
        cmap = self.app.var_cmap.get()
        vmax = float(np.nanmax(np.abs(D))) or 1.0
        rmax = float(np.nanmax(np.abs(resid))) or 1.0
        for ax, Z, title in ((self.ax_data, D, "data"),
                             (self.ax_fit, fit, "global fit"),
                             (self.ax_resid, resid, "residual")):
            ax.clear(); _style_analysis_ax(ax)
            if title == "residual":
                ax.imshow(Z.T, aspect="auto", extent=ext, cmap="RdBu_r",
                          vmin=-rmax, vmax=rmax, origin="upper",
                          interpolation="nearest")
            else:
                ax.imshow(Z.T, aspect="auto", extent=ext, cmap=cmap,
                          vmin=0, vmax=vmax, origin="upper",
                          interpolation="nearest")
            ax.set_title(title)
            ax.set_xlabel("wavelength (nm)")
        self.ax_data.set_ylabel("delay (ps)")

    def _plot_spectra(self):
        res = self._last
        wl = self._fit_wls
        has_inf = self.var_inf.get()
        A = res["A"]; eads = res["_eads"]
        tau = res["tau"]
        labels = [f"{tau[i]:.3g} ps" for i in range(len(tau))]
        if has_inf:
            labels.append("∞")
        elabels = [f"{res['_tau_sorted'][i]:.3g} ps"
                   for i in range(len(res["_tau_sorted"]))]
        if has_inf:
            elabels.append("∞")
        self._plot_spectrum_pair(self.ax_dads, self.ax_dads_n, wl, A, labels, "DADS")
        self._plot_spectrum_pair(self.ax_eads, self.ax_eads_n, wl, eads, elabels, "EADS")

    def _plot_spectrum_pair(self, ax, axn, wl, S, labels, kind):
        ax.clear(); axn.clear()
        _style_analysis_ax(ax); _style_analysis_ax(axn)
        k = S.shape[1]
        colors = matplotlib.colormaps["turbo"](np.linspace(0.1, 0.9, max(k, 2)))
        for j in range(k):
            ax.plot(wl, S[:, j], color=colors[j], linewidth=1.2,
                    label=labels[j] if j < len(labels) else str(j))
            peak = np.nanmax(np.abs(S[:, j])) or 1.0
            axn.plot(wl, S[:, j] / peak, color=colors[j], linewidth=1.2)
        ax.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        axn.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        ax.set_title(kind); axn.set_title(kind + " (norm.)")
        ax.set_ylabel("amplitude"); ax.set_xlabel("wavelength (nm)")
        axn.set_xlabel("wavelength (nm)")
        leg = ax.legend(loc="best", fontsize=7, facecolor=PANEL, edgecolor=LINE,
                        ncol=2)
        if leg:
            for txt in leg.get_texts():
                txt.set_color(INK)

    def _plot_kinetics(self):
        if self._last is None:
            return
        ax = self.ax_kin
        ax.set_xscale("linear")             # avoid clear() warning on log axis
        ax.clear(); _style_analysis_ax(ax)
        wl = self._fit_wls
        wi = int(np.argmin(np.abs(wl - self._kin_wl)))
        t = self._fit_t
        D = self._fit_D
        ax.plot(t, D[wi, :], ".", color=INK_DIM, markersize=3, label="data")
        ax.plot(t, self._last["fit"][wi, :], "-", color=ACCENT, linewidth=1.4,
                label="fit")
        ax.axhline(0, color=LINE, linestyle=":", linewidth=0.6)
        if self.var_kin_scale.get() == "Log" and np.any(t > 0):
            ax.set_xscale("log"); ax.set_xlim(t[t > 0].min(), t.max())
        else:
            ax.set_xscale("linear"); ax.set_xlim(t.min(), t.max())
        ax.set_title(f"kinetics @ {wl[wi]:.2f} nm")
        ax.set_xlabel("delay (ps)"); ax.set_ylabel("intensity")
        leg = ax.legend(loc="best", fontsize=8, facecolor=PANEL, edgecolor=LINE)
        for txt in leg.get_texts():
            txt.set_color(INK)
        ax.grid(True, color=LINE, alpha=0.4)
        self.canvas.draw_idle()

    # -- export ----------------------------------------------------------
    def _param_summary(self, res):
        """Multi-line GA summary for the CSV preamble / opju column comment."""
        lines = [f"RMS = {res['info']['rms']:.6g} "
                 f"(initial {res['info']['initialRMS']:.6g})",
                 f"method = {res['info']['method']}, {res['info']['iters']} evals, "
                 f"IRF {res['info']['irf_mode']}",
                 f"t0 = {res['t0']:.6g} ps, FWHM = {res['fwhm']:.6g} ps"]
        st = res["stretch_on"]
        for i in range(len(res["tau"])):
            tag = "stretched" if st[i] else "exp"
            lines.append(f"comp {i+1}: tau = {res['tau'][i]:.6g} ps, "
                         f"beta = {res['beta'][i]:.4g} ({tag})")
        if self.var_inf.get():
            lines.append("offset: tau = inf")
        return lines

    def export_results(self):
        """Write DADS + EADS, honouring the main window's CSV / .opju ticks.

        Two datasets ({stem}_DADS, {stem}_EADS): wavelength + one amplitude
        column per lifetime component, with the fit parameters in the CSV
        preamble and the opju column comments. Same path as "Export data..."
        so the tabs land in Book1 alongside the TRES map.
        """
        if self._last is None:
            messagebox.showwarning("No fit", "Run the fit first.")
            return
        res = self._last
        phu_base = os.path.splitext(os.path.basename(self.model.phu["path"]))[0]
        default_base = phu_base            # suffixes "DADS"/"EADS" complete the names
        wl = np.asarray(self._fit_wls)
        A = np.asarray(res["A"]); eads = np.asarray(res["_eads"])
        tau = res["tau"]; tsort = res["_tau_sorted"]
        inf = ["inf"] if self.var_inf.get() else []
        dads_labels = [f"{tau[i]:.4g}ps" for i in range(len(tau))] + inf
        eads_labels = [f"{tsort[i]:.4g}ps" for i in range(len(tsort))] + inf
        preamble = self._param_summary(res)

        def make_csv(S, labels, kind):
            def _w(path):
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.write(f"# global analysis - {kind}\n")
                    fh.write(f'# source: {self.model.phu["path"]}\n')
                    for line in preamble:
                        fh.write(f"# {line}\n")
                    if self.model.solvent_active:    # the map was fitted after it
                        fh.write(f"# {self.app._export_note()}\n")
                    fh.write("wavelength_nm,"
                             + ",".join(f"{kind}_{lb}" for lb in labels) + "\n")
                    np.savetxt(fh, np.column_stack([wl, S]),
                               delimiter=",", fmt="%.8g")
            return _w

        def make_fill(S, labels, kind):
            def _f(ws):
                pd = self.app._require_pandas()
                cols = {"Wavelength": wl}
                for j, lb in enumerate(labels):
                    cols[f"{kind}_{lb}"] = S[:, j]
                df = pd.DataFrame(cols)
                specs = [("Wavelength", "nm", "")]
                specs += [(kind, "a. u.", f"tau={lb}") for lb in labels]
                _origin_fill_table(ws, df, specs)
            return _f

        self.app.export_analysis(default_base, [
            {"suffix": "DADS", "csv": make_csv(A, dads_labels, "DADS"),
             "fill": make_fill(A, dads_labels, "DADS")},
            {"suffix": "EADS", "csv": make_csv(eads, eads_labels, "EADS"),
             "fill": make_fill(eads, eads_labels, "EADS")}])


# ==========================================================================
# 7. Application - the two tabs in one window
# ==========================================================================
APP_VERSION = "1.4.2"


class FreezeLog:
    """Write down where the program is when its window stops answering.

    A windowed .exe shows nothing when it hangs or when a callback fails, so
    the cause can only be guessed afterwards. This keeps a small log next to
    the program (TCSPC_analysis_freeze.log) with what is needed to find it:

    - the main loop marks the time every half second; a watcher thread
      notices when that stops for LIMIT_S and writes the call stack of every
      thread - the main thread's is where the program is stuck;
    - an exception in a Tk callback, with its traceback (it still goes to the
      console as well, when there is one);
    - Python's own dump if the main loop stays silent for HARD_S (written by
      faulthandler, which needs no Python thread and so also works when the
      watcher cannot run).

    File dialogs and message boxes keep the main loop running and are not
    reported. With no callback running the program itself is not stuck - Tk
    is waiting inside its own loop - so that only counts after IDLE_S.
    Slow but healthy work on the main thread (starting Origin for an .opju
    export) is reported like any other stall; the stack says what it was.
    No measured data is written, only the name of the open file, and the
    user's home folder is cut out of every path the program writes itself
    (faulthandler's dump shows source paths as Python has them).
    """

    NAME = "TCSPC_analysis_freeze.log"
    BEAT_MS = 500
    LIMIT_S = 5.0       # a callback that keeps the window from answering this long
    IDLE_S = 30.0       # the same, with no callback running
    HARD_S = 60         # faulthandler's own dump
    MAX_BYTES = 512 * 1024

    def __init__(self, root, describe=lambda: ""):
        self.root = root
        self.describe = describe    # one line on what is loaded; main thread only
        self.path, self._fh = self._open()
        home = [re.escape(p) for p in re.split(r"[\\/]+", os.path.expanduser("~")) if p]
        # the home folder however it is spelt: either slash, doubled in a repr, any case
        self._home = re.compile(r"[\\/]+".join(home), re.IGNORECASE)
        self._lock = threading.Lock()
        self._note = ""
        self._seen = time.monotonic()
        self._told = None           # when the stall being reported began
        self._closed = threading.Event()
        if self._fh is None:        # nowhere to write: run without the log
            return
        self.write(f"started, version {APP_VERSION}, "
                   f"{'exe' if getattr(sys, 'frozen', False) else 'source'}, "
                   f"Python {sys.version.split()[0]}")
        root.report_callback_exception = self._callback_error
        self._beat()
        threading.Thread(target=self._watch, daemon=True).start()

    @classmethod
    def _open(cls):
        """(path, file) of the log: beside the program, else in LOCALAPPDATA."""
        here = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                               else os.path.abspath(__file__))
        local = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                             "TCSPC_analysis")
        for folder in (here, local):
            path = os.path.join(folder, cls.NAME)
            try:
                os.makedirs(folder, exist_ok=True)
                big = os.path.exists(path) and os.path.getsize(path) > cls.MAX_BYTES
                return path, open(path, "w" if big else "a", encoding="utf-8",
                                  errors="replace", buffering=1)
            except OSError:
                continue
        return None, None

    def write(self, text):
        """Append a time-stamped entry; the user's home folder is left out of it."""
        if self._fh is None:
            return
        text = self._home.sub("~", text)
        with self._lock:
            try:
                self._fh.write(f"==== {time.strftime('%Y-%m-%d %H:%M:%S')}  {text}\n")
            except (OSError, ValueError):       # disk full, or closed on exit
                pass

    def _beat(self):
        """Main thread: the loop is alive."""
        if self._closed.is_set():
            return
        now = time.monotonic()
        if self._told is not None:
            self.write(f"answering again after {now - self._told:.1f} s")
            self._told = None
        self._seen = now
        try:
            self._note = self.describe()
        except Exception:                       # noqa: BLE001 - never break the loop
            self._note = ""
        faulthandler.dump_traceback_later(self.HARD_S, file=self._fh)
        self.root.after(self.BEAT_MS, self._beat)

    def _watch(self):
        """Watcher thread: report a main loop that has gone silent, once."""
        main = threading.main_thread().ident
        while not self._closed.wait(1.0):
            seen = self._seen
            quiet = time.monotonic() - seen
            if quiet < self.LIMIT_S or self._told is not None:
                continue
            frames = sys._current_frames()
            at = frames.get(main)
            if at is None:
                continue
            code = at.f_code                    # waiting in Tk's own loop?
            idle = (code.co_name == "mainloop"
                    and os.path.basename(os.path.dirname(code.co_filename)) == "tkinter")
            if idle and quiet < self.IDLE_S:
                continue
            names = {t.ident: t.name for t in threading.enumerate()}
            lines = [f"window not answering for {quiet:.0f} s"
                     + (" (no callback running: Tk itself is busy, or the window is"
                        " being moved)" if idle else ""),
                     f"open: {self._note or '-'}"]
            for ident, frame in frames.items():
                lines.append(f"-- thread {names.get(ident, ident)}"
                             + ("  <-- the window's thread" if ident == main else ""))
                lines += [ln.rstrip() for ln in traceback.format_stack(frame)]
            self._told = seen
            self.write("\n".join(lines))

    def _callback_error(self, exc, val, tb):
        self.write("error in a callback\n"
                   + "".join(traceback.format_exception(exc, val, tb)).rstrip())
        if sys.stderr is not None:              # as Tk does without the log
            print("Exception in Tkinter callback", file=sys.stderr)
            traceback.print_exception(exc, val, tb)

    def close(self):
        self._closed.set()
        if self._fh is not None:
            faulthandler.cancel_dump_traceback_later()
            with self._lock:
                self._fh.close()


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


if __name__ == "__main__":
    main()
