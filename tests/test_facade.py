"""The package facade must behave like the single module did when a test replaces one of its names."""
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


P = _versions.load_package()
mods = P._modules
check("load() gives the package facade for the newest version, once",
      _versions.load() is P and _versions.load_package() is P and isinstance(P, _versions.Facade))
check("a name defined in the package reads as the defining module's object",
      P.TRESModel is mods["model"].TRESModel and P.read_phu is mods["phu"].read_phu
      and P.APP_VERSION == mods["version"].APP_VERSION and P.CropDialog is mods["dialogs.crop"].CropDialog)
import tkinter.messagebox                     # noqa: E402
import os as real_os                          # noqa: E402
check("a name the package only imports is found too (shared library modules)",
      P.messagebox is tkinter.messagebox and P.os is real_os and P.np.__name__ == "numpy")
check("holders() lists where a name lives",
      P.holders("read_phu") == ["phu", "dialogs.crop_solvent", "viewer"]
      and P.holders("fit_single_trace") == ["fitting", "dialogs.kinetics"]
      and P.holders("TRESViewer") == ["viewer", "app"]
      and P.holders("program_dir") == ["paths", "app"]       # D-28 (1.6): the window icon is found there
      and P.holders("user_dir") == ["paths", "viewer_export", "freezelog"], str(P.holders("user_dir")))

real = P.read_phu
marker = object()
P.read_phu = marker
check("assigning a name replaces it in every module that holds it",
      all(vars(mods[m])["read_phu"] is marker for m in ("phu", "dialogs.crop_solvent", "viewer")))
check("... and reads back as the replacement", P.read_phu is marker)
P.read_phu = real
check("... and can be put back", all(vars(mods[m])["read_phu"] is real for m in ("phu", "dialogs.crop_solvent", "viewer")))

called = []
real_fit = P.fit_single_trace
P.fit_single_trace = lambda *a, **k: called.append(1) or real_fit(*a, **k)
import numpy as np                            # noqa: E402
check("the function a dialog would call is the replacement",
      mods["dialogs.kinetics"].fit_single_trace is P.fit_single_trace is not real_fit)
P.fit_single_trace = real_fit

for bad in ("no_such_name_anywhere",):
    try:
        getattr(P, bad)
        ok_get = False
    except AttributeError:
        ok_get = True
    try:
        setattr(P, bad, 1)
        ok_set = False
    except AttributeError:
        ok_set = True
    check("an unknown name raises on read and on assignment (no silent new attribute)", ok_get and ok_set)

check("__file__ points into the package, sources() lists its 22 module files",
      P.__file__.endswith(os.path.join("tcspc_analysis", "__init__.py")) and len(P.sources()) == 22
      and all(os.path.exists(s) for s in P.sources()))

# a copy in another folder loads beside the original, as its own set of modules
tmp = tempfile.mkdtemp(prefix="facade_copy_")
try:
    shutil.copytree(os.path.join(_versions.ROOT, "tcspc_analysis"), os.path.join(tmp, "tcspc_analysis"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    C = _versions.load(path=tmp)
    check("a copied package loads as a separate facade with its own classes",
          C is not P and C.TRESModel is not P.TRESModel and C.TRESModel.__module__ != P.TRESModel.__module__
          and C.holders("read_phu") == P.holders("read_phu"))
    C.read_phu = marker
    check("replacing a name in the copy leaves the original alone", P.read_phu is real and C.read_phu is marker)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

one = _versions.load("1.4")
check("a single-file version still loads as a plain module",
      not isinstance(one, _versions.Facade) and one.APP_VERSION == "1.4.2"
      and one.__file__.endswith("TCSPC_analysis_1.4ver.py"))
print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
