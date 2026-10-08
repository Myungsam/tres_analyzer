"""D5: where the program writes on its own - the default Data folder and the freeze log.

Run from source: the program folder, as before. Frozen: Documents\\TCSPC_analysis, because the folder
of a folder-type build is replaced as a whole by the next version.
"""
import os
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _versions                              # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def same(a, b):
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


NEW = _versions.load()
OLD = _versions.load("1.4")
ROOT = _versions.ROOT
paths = NEW._modules["paths"]
viewer = NEW.TRESViewer.__new__(NEW.TRESViewer)          # _default_data_dir uses no instance state
old_viewer = OLD.TRESViewer.__new__(OLD.TRESViewer)

# ---- run from source: nothing moved ---------------------------------------------------------
check("source: program_dir() and user_dir() are the project folder",
      same(NEW.program_dir(), ROOT) and same(NEW.user_dir(), ROOT), f"{NEW.program_dir()} {NEW.user_dir()}")
check("source: the default Data folder is the one 1.4 used",
      same(viewer._default_data_dir(), old_viewer._default_data_dir())
      and same(viewer._default_data_dir(), os.path.join(ROOT, "Data")), viewer._default_data_dir())

# ---- the Documents folder ------------------------------------------------------------------------
docs = paths._documents_dir()
check("the Documents folder exists and is asked from Windows",
      os.path.isdir(docs) and os.path.isabs(docs), docs)
import ctypes                                 # noqa: E402
real_shell = ctypes.windll.shell32.SHGetFolderPathW
try:
    class _Broken:
        def __getattr__(self, name):
            raise OSError("no shell")
    real_windll = ctypes.windll
    ctypes.windll = _Broken()
    fallback = paths._documents_dir()
finally:
    ctypes.windll = real_windll
check("... and falls back to ~\\Documents when Windows cannot be asked",
      same(fallback, os.path.join(os.path.expanduser("~"), "Documents")), fallback)

# ---- frozen: Documents\TCSPC_analysis -----------------------------------------------------------
TMP = tempfile.mkdtemp(prefix="paths_test_")
exe_dir = os.path.join(TMP, "unzipped", "TCSPC_analysis")
os.makedirs(exe_dir)
fake_docs = os.path.join(TMP, "Documents")
os.makedirs(fake_docs)
real_docs, real_exe = paths._documents_dir, sys.executable
real_local = os.environ.get("LOCALAPPDATA")
sys.frozen = True
sys.executable = os.path.join(exe_dir, "TCSPC_analysis.exe")
NEW._documents_dir = lambda: fake_docs
try:
    home = os.path.join(fake_docs, "TCSPC_analysis")
    check("frozen: program_dir() is still the .exe's folder", same(NEW.program_dir(), exe_dir), NEW.program_dir())
    check("frozen: user_dir() is Documents\\TCSPC_analysis", same(NEW.user_dir(), home), NEW.user_dir())
    check("frozen: the default Data folder is Documents\\TCSPC_analysis\\Data",
          same(viewer._default_data_dir(), os.path.join(home, "Data")), viewer._default_data_dir())
    check("frozen: asking for the folders creates nothing", not os.path.exists(home))
    p, f = NEW.FreezeLog._open()
    f.write("x\n")
    f.close()
    check("frozen: the freeze log is opened in Documents\\TCSPC_analysis (folder made on demand)",
          same(p, os.path.join(home, NEW.FreezeLog.NAME)) and os.path.getsize(p) > 0, str(p))
    check("frozen: nothing is written into the program folder", os.listdir(exe_dir) == [], str(os.listdir(exe_dir)))
    # Documents cannot be written: the log goes to LOCALAPPDATA as before
    blocked = os.path.join(TMP, "blocked")
    open(blocked, "w").close()                               # a file where a folder is needed
    NEW._documents_dir = lambda: blocked
    os.environ["LOCALAPPDATA"] = os.path.join(TMP, "Local")
    p2, f2 = NEW.FreezeLog._open()
    f2.close()
    check("frozen: if Documents cannot be used the log goes to LOCALAPPDATA\\TCSPC_analysis",
          same(p2, os.path.join(TMP, "Local", "TCSPC_analysis", NEW.FreezeLog.NAME)), str(p2))
finally:
    del sys.frozen
    sys.executable = real_exe
    NEW._documents_dir = real_docs
    if real_local is None:
        os.environ.pop("LOCALAPPDATA", None)
    else:
        os.environ["LOCALAPPDATA"] = real_local
    shutil.rmtree(TMP, ignore_errors=True)
check("after the test the program is back to its source folders",
      same(NEW.user_dir(), ROOT) and not getattr(sys, "frozen", False))
check("no freeze log was left in the project folder",
      not os.path.exists(os.path.join(ROOT, NEW.FreezeLog.NAME)))
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
