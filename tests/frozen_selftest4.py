"""Frozen (windowed) self test of the package: build with PyInstaller, run with a .phu path, read
frozen_selftest4_result.txt beside the .exe.

Checks what only a frozen build can show: the freeze log and the default Data folder are in
Documents\\TCSPC_analysis and nothing is written beside the .exe but the result file (a stuck callback
and a failing callback are both noted in the log), a Kinetics fit finishes, and the modules the
program imports late (scipy.optimize, scipy.special, pythoncom, originpro) were packed - and pandas, which
the program no longer uses, was not.
The log this run writes is removed again when the test wrote all of it.
"""
import os
import sys
import time
import traceback

import tkinter as tk
from tkinter import ttk

from tcspc_analysis.freezelog import FreezeLog
from tcspc_analysis.paths import program_dir, user_dir
from tcspc_analysis.theme import apply_theme
from tcspc_analysis.version import APP_VERSION
from tcspc_analysis.viewer import TRESViewer

HERE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
out = []
try:
    root = tk.Tk()
    root.geometry("1200x800+0+0")
    apply_theme(root)
    tab = ttk.Frame(root)
    tab.pack(fill="both", expand=True)
    tres = None
    log = FreezeLog(root, lambda: os.path.basename(tres.var_path.get()) if tres else "")
    tres = TRESViewer(tab, sys.argv[1])

    def stuck_in_frozen_build():
        time.sleep(7.0)

    def kinetics():
        tres.open_kinetics()
        tres._kinetics_win.run_fit()

    def finish(tries=120):
        k = tres._kinetics_win
        # the first fit also loads scipy, which takes a while from a one-file exe
        if k._running and tries:
            root.after(500, lambda: finish(tries - 1))
            return
        out.append(f"version={APP_VERSION} frozen={getattr(sys, 'frozen', False)} stderr={sys.stderr!r}")
        out.append(f"log={os.path.basename(log.path)} in_user_dir="
                   f"{os.path.normcase(os.path.dirname(log.path)) == os.path.normcase(user_dir())}"
                   f" program_dir_is_exe_dir={os.path.normcase(program_dir()) == os.path.normcase(HERE)}"
                   f" user_dir={user_dir()!r}")
        late = []
        for name in ("scipy.optimize", "scipy.special"):
            try:
                __import__(name)
                late.append(name + "=ok")
            except Exception as exc:                    # noqa: BLE001 - report whatever went wrong
                late.append(f"{name}=MISSING({type(exc).__name__})")
        import importlib.util as _u                    # pandas is left out of the build since 1.6 (D-27)
        late.append("pandas=" + ("PACKED(should not be)" if _u.find_spec("pandas") else "absent(as intended)"))
        try:
            import pythoncom                            # noqa: F401 - pywin32, used by the .opju export
            late.append("pythoncom=ok")
        except Exception as exc:                        # noqa: BLE001
            late.append(f"pythoncom=MISSING({type(exc).__name__})")
        import importlib.util
        for name in ("originpro", "OriginExt"):         # importing them needs Origin itself: only look
            late.append(f"{name}={'ok' if importlib.util.find_spec(name) else 'MISSING(not packed)'}")
        out.append("late imports: " + " ".join(late))
        global tres_data
        tres_data = tres._default_data_dir()
        out.append(f"default data dir={tres_data!r}")
        out.append(f"kinetics={k.var_status.get()!r} running={k._running}")
        root.destroy()

    root.after(800, stuck_in_frozen_build)
    root.after(9000, lambda: 1 / 0)
    root.after(9500, kinetics)
    root.after(14000, finish)
    root.mainloop()
    log.close()
    body = open(log.path, encoding="utf-8").read()
    ok = ("window not answering" in body and "stuck_in_frozen_build" in body
          and "answering again after" in body and "error in a callback" in body
          and "ZeroDivisionError" in body and "open: " + os.path.basename(sys.argv[1]) in body
          and os.path.expanduser("~") not in body and "Fit done" in out[-1]
          and "in_user_dir=True program_dir_is_exe_dir=True" in out[1]
          and os.path.basename(user_dir()) == "TCSPC_analysis"
          and os.path.normcase(os.path.dirname(user_dir())) != os.path.normcase(os.path.dirname(HERE))
          and not os.path.exists(os.path.join(HERE, "Data"))
          and not os.path.exists(os.path.join(HERE, FreezeLog.NAME))
          and "MISSING" not in out[2] and out[2].count("=ok") == 6
          and os.path.normcase(tres_data) == os.path.normcase(os.path.join(user_dir(), "Data"))
          and "version=1.6 " in out[0] and "started, version " + APP_VERSION + "," in body)
    out.append(body[-1800:])
    if body.count("started, version") == 1:        # the log holds only this run: leave nothing behind
        os.remove(log.path)
        if not os.listdir(user_dir()):
            os.rmdir(user_dir())
except Exception:
    out.append(traceback.format_exc())
    ok = False
out.append("SELFTEST " + ("PASS" if ok else "FAIL"))
open(os.path.join(HERE, "frozen_selftest4_result.txt"), "w", encoding="utf-8").write("\n".join(out))
sys.exit(0 if ok else 1)
