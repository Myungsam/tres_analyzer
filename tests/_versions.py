"""Load a version of the program for the tests.

Up to 1.4 a version is one source file, TCSPC_analysis_<X.Y>ver.py (a plain `import` cannot take the
dot in the name). From 1.5 on the program is the package tcspc_analysis/ and is loaded as a facade
object that behaves like the single module did: reading a name finds it in the package, and assigning
a name replaces it in every module of the package that holds it - which is what replacing a global of
the single file used to do (the package's modules import each other's names with plain, unaliased
`from .x import name`, so the same name is the same thing everywhere).

    NEW = _versions.load()                    # newest: the package (or TCSPC_VERSION=1.4 -> the file)
    OLD = _versions.load("1.4")               # a single-file version
    X = _versions.load(path=r"...\\copy.py")   # some other single file
    Y = _versions.load_package(root=r"...")   # a (mutated) copy of the package in another folder
"""
import importlib
import json
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = "tcspc_analysis"
NEWEST = os.environ.get("TCSPC_VERSION", "1.5")
MODULES = ["version", "paths", "phu", "util", "origin", "fitting", "model", "theme", "flim",
           "dialogs.common", "dialogs.crop_view", "dialogs.crop_slice", "dialogs.crop_solvent",
           "dialogs.crop", "dialogs.mask", "dialogs.kinetics",
           "dialogs.global_analysis", "viewer_figure", "viewer_export", "viewer", "freezelog", "app"]
_packages = {}


def samples():
    """Paths of the two sample records the tests were written for: (A, B).

    They are measurements and not part of the repository. tests/samples.json names them -
    {"A": "Data/....phu", "B": "Data/....phu"}, a relative path counts from the project folder - or, without
    that file, the environment variables TCSPC_SAMPLE_A and TCSPC_SAMPLE_B. tests/README.md says what the two
    records have to be like.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    named = {}
    try:
        with open(os.path.join(here, "samples.json"), encoding="utf-8") as fh:
            named = json.load(fh)
    except OSError:
        pass
    out = []
    for key in ("A", "B"):
        path = named.get(key) or os.environ.get("TCSPC_SAMPLE_" + key, "")
        if path and not os.path.isabs(path):
            path = os.path.join(ROOT, path)
        if not path or not os.path.exists(path):
            raise SystemExit(f"The tests need the sample record {key} ({path or 'not named'}): "
                             "see tests/README.md.")
        out.append(os.path.normpath(path))
    return tuple(out)


class Facade:
    """The package seen as one namespace (see the module docstring)."""

    def __init__(self, name, root, modules):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_root", root)
        object.__setattr__(self, "_modules", modules)

    def __getattr__(self, name):
        if name == "__file__":          # where the package's code is
            return os.path.join(self._root, PACKAGE, "__init__.py")
        for mod in self._modules.values():
            if name in vars(mod):
                return vars(mod)[name]
        raise AttributeError(f"{self._name} has no {name!r}")

    def __setattr__(self, name, value):
        hit = [mod for mod in self._modules.values() if name in vars(mod)]
        if not hit:
            raise AttributeError(f"{self._name} has no {name!r} to replace")
        for mod in hit:
            setattr(mod, name, value)

    def holders(self, name):
        """The package modules that hold ``name`` (what an assignment reaches)."""
        return [key for key, mod in self._modules.items() if name in vars(mod)]

    def sources(self):
        """Paths of the package's source files, in module order."""
        return [mod.__file__ for mod in self._modules.values()]


def load_package(root=None, name=None):
    """The package under ``root`` (default: the project) as a Facade, loaded once per root."""
    root = os.path.abspath(root or ROOT)
    if root in _packages:
        return _packages[root]
    if os.path.normcase(root) == os.path.normcase(os.path.abspath(ROOT)):
        name = PACKAGE
        if root not in sys.path:
            sys.path.insert(0, root)
        importlib.import_module(name)
    else:                               # a copy: its own name, so both can be loaded side by side
        name = name or f"{PACKAGE}_{len(_packages)}"
        init = os.path.join(root, PACKAGE, "__init__.py")
        spec = importlib.util.spec_from_file_location(
            name, init, submodule_search_locations=[os.path.dirname(init)])
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[name] = pkg
        spec.loader.exec_module(pkg)
    modules = {m: importlib.import_module(f"{name}.{m}") for m in MODULES}
    _packages[root] = Facade(name, root, modules)
    return _packages[root]


def load(version=None, path=None):
    """The module of a single-file version (or of the file at ``path``), or the package facade."""
    if path is not None:
        if os.path.isdir(path):
            return load_package(path)
        name = os.path.splitext(os.path.basename(path))[0].replace(".", "_")
    else:
        version = version or NEWEST
        path = os.path.join(ROOT, f"TCSPC_analysis_{version}ver.py")
        if not os.path.exists(path):
            return load_package()
        name = "TCSPC_analysis_v" + version.replace(".", "_")
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def rules_of_1_5(new=None):
    """Put back, in ``new`` (default: the package), the rules that 1.6 changed on purpose and that change
    results: the fits' limits and how they are held (A-1), the amplitude limit (A-10), how the IRF width is
    measured (A-13), the first / last point of a default fit range (C-8), the digits of the map CSV (B-20).
    With them back, a comparison against 1.4 checks that nothing ELSE changed. Returns a function that
    restores the 1.6 rules. Not switchable (they are not one name): the fixed skip mask (A-2, only with a
    free t0 / FWHM), the two extra preamble lines of a fit export (C-9), the unit of the Origin Counts column
    (Q-2), the export stem (B-19), crop and masks following OFFSET (C-14), no cut to 0 after the solvent (A-9),
    Crop Apply leaving the solvent off (C-5). Two changes of 1.6 that were classed as "results unchanged"
    also stay: the RMS of a global fit in "skip" mode counts only the delays that were fitted (A-15; tau,
    amplitudes and fit are the same), and input 1.4 answered with an all-zero fit is an error (A-3).

    The tests of the changes themselves are test_g7.py / test_g8.py; this is for the tests that were written
    as "identical to 1.4". Names a state of the code does not have yet are skipped.
    """
    import numpy as np
    new = new or load()
    s2 = 2.0 * np.sqrt(2.0 * np.log(2.0))
    old = load("1.4")
    swaps = {"_limits": lambda *a, **k: None,
             "_shortest_tau": lambda fwhm, dt: fwhm / s2 / 4.0,
             "_amp_limit": lambda D, masked: 1e8 if masked else 1e10,
             "fwhm_of": old.fwhm_of,
             "fmt_ps": lambda value: f"{value:.4g}",
             "in_range": lambda t, lo, hi: (np.asarray(t, float) >= lo) & (np.asarray(t, float) <= hi),
             "CSV_NUMBER": "%.6g"}
    saved = {}
    for name, repl in swaps.items():
        try:
            saved[name] = getattr(new, name)
        except AttributeError:
            continue
        setattr(new, name, repl)

    def restore():
        for name, value in saved.items():
            setattr(new, name, value)
    return restore
