"""The controls of every window and what they are bound to, to compare two versions (test_v17.py UI-8).

    install()                         # once, before any window is built: records the Tcl name of every callback
    inv = inventory(owner, window)    # the controls of ``window``, whose variables are attributes of ``owner``
    lost = compare(old_inv, new_inv)  # what ``old_inv`` has and ``new_inv`` has not

A control is a widget a user works or reads: a button, tick box, entry (number boxes included), combobox,
scale, list, text box, or a label that shows a variable. For each the record holds its family, its text in
a normal form (lower case, without a closing colon, spaces collapsed, then RELABEL), the owner attribute of
its Tk variable, the names its command calls and, for every event binding, the names the handler calls.
Matplotlib's toolbar is left out (it is new in the main window and in four of the five others).
"""
import functools
import re
import tkinter as tk

from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk

# texts that were renamed on purpose (normal form -> normal form). The 1.7 labels are the 1.6 captions in
# normal case with a colon, which the normal form already makes equal; what is left are real renames.
RELABEL = {}
# ui.spin binds these on every number box; they are additions, not changes
SPIN_SEQUENCES = {"<<Increment>>", "<<Decrement>>", "<MouseWheel>", "<Destroy>"}
FAMILIES = {"TButton": "button", "Button": "button", "TCheckbutton": "check", "Checkbutton": "check",
            "TEntry": "entry", "Entry": "entry", "TSpinbox": "entry", "Spinbox": "entry",
            "TCombobox": "combobox", "TScale": "scale", "Scale": "scale", "Listbox": "list", "Text": "text",
            "TLabel": "label", "Label": "label"}
_names = {}                 # Tcl command name -> the Python callable behind it


def install():
    """Record, from now on, which Python callable each Tcl command name stands for."""
    if getattr(tk.Misc._register, "_inventory", False):
        return
    real = tk.Misc._register

    def register(self, func, subst=None, needcleanup=1):
        name = real(self, func, subst, needcleanup)
        _names[name] = func
        return name
    register._inventory = True
    tk.Misc._register = register


def calls(func, seen=None):
    """The names a callback calls: a method's own name; for a lambda, partial or closure, the names in its
    code and, through its closure cells, in the callables it holds (ui.spin's _step -> on_change)."""
    seen = set() if seen is None else seen
    if id(func) in seen:
        return set()
    seen.add(id(func))
    if isinstance(func, functools.partial):
        return calls(func.func, seen)
    if hasattr(func, "__func__"):                       # a bound method
        return {func.__func__.__name__}
    code = getattr(func, "__code__", None)
    if code is None:
        return {getattr(func, "__name__", type(func).__name__)}
    out = set(code.co_names)
    if func.__name__ not in ("<lambda>",):
        out.add(func.__name__)
    for cell in func.__closure__ or ():
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if callable(value) and not isinstance(value, (type, tk.Misc, tk.Variable)):
            out |= calls(value, seen)
    return out


def _script_calls(script):
    """The names behind the Tcl command(s) a binding script or a -command calls."""
    out = set()
    for word in re.findall(r"[0-9]+[A-Za-z_<>][\w<>]*", str(script)):
        if word in _names:
            out |= calls(_names[word])
    return out


def normal(text):
    t = re.sub(r"\s+", " ", str(text)).strip().lower()
    t = t[:-1].rstrip() if t.endswith(":") else t
    return RELABEL.get(t, t)


def _walk(widget):
    for child in widget.winfo_children():
        if isinstance(child, (NavigationToolbar2Tk, tk.Toplevel)):
            continue
        yield child
        yield from _walk(child)


def inventory(owner, window):
    """The controls of ``window`` (see the module docstring), as a list of dicts."""
    variables = {}
    for obj in (owner, getattr(owner, "app", None)):
        for name, value in (vars(obj) if obj is not None else {}).items():
            if isinstance(value, tk.Variable):
                variables.setdefault(str(value), name)
    out = []
    for w in _walk(window):
        family = FAMILIES.get(w.winfo_class())
        if family is None:
            continue
        rec = {"family": family, "text": "", "var": None, "command": set(), "bind": {}, "widget": w}
        for option in ("textvariable", "variable"):
            try:
                value = str(w.cget(option))
            except tk.TclError:
                continue
            if value:
                rec["var"] = variables.get(value, "?")
        if family == "label" and rec["var"] is None:
            continue                                    # a caption: its words are the glossary test's
        try:
            # (a label's text is its variable's value: the variable is what is compared)
            if family not in ("entry", "combobox", "list", "text", "label"):
                rec["text"] = normal(w.cget("text"))
        except tk.TclError:
            pass
        try:
            rec["command"] = _script_calls(w.cget("command"))
        except tk.TclError:
            pass
        for seq in w.bind():
            rec["bind"][seq] = _script_calls(w.bind(seq))
        out.append(rec)
    return out


def describe(rec):
    return (f"{rec['family']} text={rec['text']!r} var={rec['var']} command={sorted(rec['command'])} "
            f"bind={ {k: sorted(v) for k, v in rec['bind'].items()} }")


def _same_control(old, new):
    if old["family"] != new["family"]:
        return False
    if old["var"] not in (None, "?"):
        return new["var"] == old["var"]
    if old["command"]:
        return old["command"] <= new["command"] and old["text"] == new["text"]
    if old["text"]:
        return old["text"] == new["text"]
    return False


def compare(old_inv, new_inv):
    """What of ``old_inv`` is missing in ``new_inv``: (lost controls, lost bindings, unmatched count note).

    Every control of the old version must have a control of the same family in the new one with the same
    variable (or, without one, the same command and text); its text (normal form), command names and every
    binding sequence with the names it calls must be there as well (the new one may call more). Controls
    with neither a named variable nor a command nor a text (the rows of a ComponentTable) are compared by
    their number per family."""
    lost, lost_bind = [], []
    free = []
    anonymous_old, anonymous_new = {}, {}
    for rec in new_inv:
        if rec["var"] in (None, "?") and not rec["command"] and not rec["text"]:
            anonymous_new[rec["family"]] = anonymous_new.get(rec["family"], 0) + 1
        else:
            free.append(rec)
    for old in old_inv:
        if old["var"] in (None, "?") and not old["command"] and not old["text"]:
            anonymous_old[old["family"]] = anonymous_old.get(old["family"], 0) + 1
            continue
        match = next((n for n in free if _same_control(old, n)), None)
        if match is None:
            lost.append(describe(old))
            continue
        free.remove(match)
        problems = []
        if old["text"] != match["text"]:
            problems.append(f"text {old['text']!r} -> {match['text']!r}")
        if not old["command"] <= match["command"]:
            problems.append(f"command {sorted(old['command'])} -> {sorted(match['command'])}")
        for seq, names in old["bind"].items():
            if seq not in match["bind"] or not names <= match["bind"][seq]:
                problems.append(f"binding {seq} {sorted(names)} -> {sorted(match['bind'].get(seq, ()))}")
        if problems:
            lost_bind.append(describe(old) + " :: " + "; ".join(problems))
    for family, n in anonymous_old.items():
        if anonymous_new.get(family, 0) < n:
            lost.append(f"{n} unnamed {family} controls, {anonymous_new.get(family, 0)} now")
    return lost, lost_bind, free            # free: the new version's named controls 1.6 did not have
