"""The PTU / FLIM tab: T3 record processing and its viewer."""
import os
import queue
import threading

import numpy as np

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .theme import ACCENT, BG, GOOD, INK_DIM, INK_FAINT, LINE, PANEL, PIN


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
