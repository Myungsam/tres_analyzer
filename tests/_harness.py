"""Shared scaffolding for the stage-3 item tests (test_g*.py).

    from _harness import *        # NEW, OLD, ROOT, SAMPLE_A, SAMPLE_B, check, section, pump, wait, make_app, finish ...

Each test file is a sequence of sections, one per review item:

    if section("C-1"):
        ...checks...

`python test_g1.py C-1 A-3` runs only those sections (to record that an item's checks fail before
its fix); with no argument every section runs. Message boxes are recorded in `boxes`, Tk callback
errors in `cb_errors`; `finish()` adds the two closing checks and exits.
"""
import os
import struct
import sys
import tempfile
import time
import traceback

import numpy as np                            # noqa: F401 - re-exported

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _versions                              # noqa: E402
import tkinter as tk                          # noqa: E402
from tkinter import ttk                       # noqa: E402

NEW = _versions.load()
OLD = _versions.load("1.4")
ROOT = _versions.ROOT
SAMPLE_A = _versions.samples()[0]
SAMPLE_B = _versions.samples()[1]
TMP = tempfile.mkdtemp(prefix="tcspc_s3_")
ONLY = [a for a in sys.argv[1:] if not a.startswith("-")]
fails, cb_errors, boxes, ran = [], [], [], []
_current = [""]


def check(name, ok, detail=""):
    name = f"{_current[0]}: {name}" if _current[0] else name
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def section(item):
    """True when the checks of review item ``item`` are to run."""
    go = not ONLY or item in ONLY
    _current[0] = item if go else ""
    if go:
        ran.append(item)
        boxes.clear()
    return go


for kind in ("showerror", "showwarning", "showinfo"):
    setattr(NEW.messagebox, kind,
            lambda title="", msg="", _k=kind, **kw: boxes.append((_k, title, str(msg))))
for kind in ("askyesno", "askokcancel"):
    setattr(NEW.messagebox, kind,
            lambda title="", msg="", _k=kind, **kw: (boxes.append((_k, title, str(msg))), True)[1])

root = tk.Tk()
root.geometry("300x80+0+0")
NEW.apply_theme(root)
root.report_callback_exception = lambda *a: cb_errors.append("".join(traceback.format_exception(*a)))


def pump(seconds=0.0):
    end = time.time() + seconds
    root.update()
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def wait(cond, limit=60.0):
    end = time.time() + limit
    while not cond() and time.time() < end:
        pump(0.05)
    return cond()


def make_app(path=SAMPLE_A, size="1440x920+0+0"):
    """A TRES viewer in its own top-level window, loaded with ``path``."""
    top = tk.Toplevel(root)
    top.geometry(size)
    tab = ttk.Frame(top)
    tab.pack(fill="both", expand=True)
    app = NEW.TRESViewer(tab, path)
    pump(0.3)
    return top, app


def make_phu(path, ncurves=3, nbins=64, res=4e-12, patch=None, cut=None, n_descr=None, header_end=True):
    """Write a small .phu. ``patch`` maps (tag name, index) -> (type, value bytes or number) overrides;
    ``cut`` truncates the file; ``n_descr`` writes fewer per-curve descriptors than curves."""
    patch = patch or {}
    n_descr = ncurves if n_descr is None else n_descr
    tags = [("HistoResult_NumberOfCurves", -1, NEW.TY_INT8, ncurves)]
    for i in range(n_descr):
        tags += [("HistResDscr_HistogramBins", i, NEW.TY_INT8, nbins),
                 ("HistResDscr_DataOffset", i, NEW.TY_INT8, None),
                 ("HistResDscr_MDescResolution", i, NEW.TY_FLOAT8, res),
                 ("ParValue0", i, NEW.TY_FLOAT8, 500.0 + 5.0 * i)]
    tags.append(("File_Comment", -1, NEW.TY_ANSISTRING, b"made by test_g2\x00\x00"))
    if header_end:
        tags.append(("Header_End", -1, NEW.TY_EMPTY8, 0))
    # where the counts start: after the header as it is really written (a patched string may be longer)
    written = [patch.get((n, i), (t, v))[1] for n, i, t, v in tags]
    size = 16 + sum(48 + (len(v) if isinstance(v, bytes) else 0) for v in written)
    out = bytearray(b"PQHISTO\x00" + b"1.0\x00\x00\x00\x00\x00")
    for name, idx, typ, val in tags:
        if name == "HistResDscr_DataOffset":
            val = size + 4 * nbins * idx
        if (name, idx) in patch:
            typ, val = patch[(name, idx)]
        out += name.encode("ascii").ljust(32, b"\x00") + struct.pack("<i", idx) + struct.pack("<I", typ)
        if isinstance(val, bytes):
            n = patch.get((name, "length"), len(val))
            out += struct.pack("<q", n) + val
        elif isinstance(val, float):
            out += struct.pack("<d", val)
        else:
            out += struct.pack("<q", int(val))
    rng = np.random.default_rng(0)
    out += rng.integers(0, 50, size=(ncurves, max(nbins, 0)), dtype=np.uint32).astype("<u4").tobytes()
    data = bytes(out[:cut] if cut else out)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def finish():
    _current[0] = ""
    check("no Tk callback exception", not cb_errors, cb_errors[0][-900:] if cb_errors else "")
    if ONLY and sorted(set(ONLY)) != sorted(set(ran)):
        check("every requested section exists", False, str(sorted(set(ONLY) - set(ran))))
    try:
        root.destroy()
    except tk.TclError:
        pass
    log = os.path.join(ROOT, "TCSPC_analysis_freeze.log")
    check("no freeze log left in the project folder", not os.path.exists(log))
    print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
    sys.exit(1 if fails else 0)
