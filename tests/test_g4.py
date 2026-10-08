"""Stage 3, group G4: exports that go wrong (review items B-8/C-10, B-11, A-12, B-23, S-2). See _harness.py."""
import os
import sys
import types

from _harness import *                        # noqa: F401,F403
from _harness import NEW, SAMPLE_A, TMP, boxes, check, finish, make_app, np, pump, section, wait


class Sheet:
    def __init__(self, name):
        self.name, self.cleared, self.filled = name, 0, 0

    def clear(self):
        self.cleared += 1

    def from_list(self, j, data, *a, **k):      # how the program fills a sheet since 1.6 (D-27)
        self.filled += 1

    def set_label(self, *a):
        pass


class Book:
    def __init__(self, names=("Sheet1",)):
        self.name, self.sheets = "Book1", [Sheet(n) for n in names]

    def __iter__(self):
        return iter(self.sheets)

    def add_sheet(self, name):
        self.sheets.append(Sheet(name))
        return self.sheets[-1]


def fake_origin(book=None, start_error=None, new_error=None):
    """Put stand-ins for originpro and pythoncom in sys.modules. Returns (state, restore)."""
    st = {"book": book, "calls": [], "co": 0}
    op = types.ModuleType("originpro")
    com = types.ModuleType("pythoncom")

    def new():
        st["calls"].append("new")
        if new_error:
            raise new_error
        st["book"] = None

    def op_open(path):
        st["calls"].append("open")
        return True
    op.new, op.open = new, op_open
    op.find_book = lambda kind, name: st["book"]
    op.new_book = lambda kind: st.__setitem__("book", Book()) or st["book"]
    op.save = lambda path: (st["calls"].append("save"), open(path, "wb").close(), True)[2]
    op.exit = lambda: st["calls"].append("exit")
    com.CoInitialize = lambda: st.__setitem__("co", st["co"] + 1)
    com.CoUninitialize = lambda: st.__setitem__("co", st["co"] - 1)
    saved = {k: sys.modules.get(k) for k in ("originpro", "pythoncom")}
    sys.modules["originpro"], sys.modules["pythoncom"] = op, com
    if start_error:
        class Boom(types.ModuleType):
            def __getattr__(self, name):
                raise start_error
        sys.modules["originpro"] = Boom("originpro")

    def restore():
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return st, restore


def asks(kind):
    return [b for b in boxes if b[0] == kind]


top, app = make_app(SAMPLE_A)
real_save = NEW.filedialog.asksaveasfilename
save_calls = []


def choose(path):
    def fake(**kw):
        save_calls.append(kw)
        return path
    NEW.filedialog.asksaveasfilename = fake


# ---------------------------------------------------------------------------------------------
if section("B-8"):
    # the overwrite question is about the files that are really written
    folder = os.path.join(TMP, "b8"); os.makedirs(folder, exist_ok=True)
    real = [os.path.join(folder, "run1_TRESmap.csv"), os.path.join(folder, "run1_steadystate.csv")]
    for p in real:
        open(p, "w").write("EARLIER EXPORT")
    app.var_out_csv.set(True); app.var_out_opju.set(False)
    choose(os.path.join(folder, "run1.csv"))
    # 1) the user says no
    NEW.messagebox.askyesno = lambda title="", msg="", **kw: (boxes.append(("askyesno", title, str(msg))), False)[1]
    boxes.clear(); save_calls.clear()
    app.export_data(); pump(0.1)
    q = asks("askyesno")
    check("exporting over an earlier export asks once, naming both real files",
          len(q) == 1 and all(os.path.basename(p) in q[0][2] for p in real), str(q))
    check("the file dialog itself no longer asks about <name>.csv (which is never written)",
          save_calls and save_calls[0].get("confirmoverwrite") is False, str(save_calls[:1]))
    check("answering No leaves the earlier files untouched and reports nothing as exported",
          all(open(p).read() == "EARLIER EXPORT" for p in real) and not asks("showinfo"), str(boxes))
    # 2) the user says yes
    NEW.messagebox.askyesno = lambda title="", msg="", **kw: (boxes.append(("askyesno", title, str(msg))), True)[1]
    boxes.clear()
    app.export_data(); pump(0.1)
    check("answering Yes replaces them", all(open(p).read() != "EARLIER EXPORT" for p in real) and len(asks("showinfo")) == 1)
    # 3) new names: no question
    choose(os.path.join(folder, "run2.csv"))
    boxes.clear()
    app.export_data(); pump(0.1)
    check("a new name is written without any question", not asks("askyesno") and len(asks("showinfo")) == 1, str(boxes))
    # 4) the same for a fit export (C-10)
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.2)
    kin = os.path.join(folder, "fitA_kinetics.csv")
    open(kin, "w").write("EARLIER FIT")
    choose(os.path.join(folder, "fitA.csv"))
    NEW.messagebox.askyesno = lambda title="", msg="", **kw: (boxes.append(("askyesno", title, str(msg))), False)[1]
    boxes.clear()
    k.export_results(); pump(0.1)
    q = asks("askyesno")
    check("C-10: a fit export asks about <name>_kinetics.csv and No keeps the earlier file",
          len(q) == 1 and "fitA_kinetics.csv" in q[0][2] and open(kin).read() == "EARLIER FIT", str(boxes))
    k._on_close(); pump(0.2)

# ---------------------------------------------------------------------------------------------
if section("B-11"):
    # an export that fails half way says what is already on disk; names are asked before anything is written
    folder = os.path.join(TMP, "b11"); os.makedirs(folder, exist_ok=True)
    NEW.messagebox.askyesno = lambda title="", msg="", **kw: True
    app.var_out_csv.set(True); app.var_out_opju.set(False)
    choose(os.path.join(folder, "half.csv"))
    real_ss = app._write_steady_state_csv

    def no_space(path):
        raise OSError("disk full")
    app._write_steady_state_csv = no_space
    boxes.clear()
    app.export_data(); pump(0.1)
    app._write_steady_state_csv = real_ss
    err = asks("showerror")
    check("the second CSV fails: the error box says so and names the first file, which is on disk",
          len(err) == 1 and "disk full" in err[0][2] and "half_TRESmap.csv" in err[0][2]
          and os.path.exists(os.path.join(folder, "half_TRESmap.csv")), str(err))
    # CSV fine, .opju fails
    app.var_out_opju.set(True)
    app._ask_opju_path = lambda stem: os.path.join(folder, "p.opju")
    real_opju = app._write_opju

    def origin_down(path, stem):
        raise RuntimeError("Origin did not answer")
    app._write_opju = origin_down
    choose(os.path.join(folder, "both.csv"))
    boxes.clear()
    app.export_data(); pump(0.1)
    app._write_opju = real_opju
    err = asks("showerror")
    check("CSV written, .opju fails: the error box lists the two CSV files as written",
          len(err) == 1 and "Origin did not answer" in err[0][2] and "both_TRESmap.csv" in err[0][2]
          and "both_steadystate.csv" in err[0][2], str(err))
    # a fit export: the .opju name is asked before the CSV is written
    app.open_kinetics(); pump(0.3)
    k = app._kinetics_win
    k.run_fit(); wait(lambda: not k._running, 60); pump(0.2)
    choose(os.path.join(folder, "fitB.csv"))
    app._ask_opju_path = lambda stem: None        # the user cancels the second dialog
    boxes.clear()
    k.export_results(); pump(0.1)
    check("fit export, the .opju dialog cancelled: nothing was written before the question",
          not os.path.exists(os.path.join(folder, "fitB_kinetics.csv")) and not boxes, f"{os.listdir(folder)} {boxes}")
    k._on_close(); pump(0.2)
    app.var_out_opju.set(False)

# ---------------------------------------------------------------------------------------------
if section("A-12"):
    # a lone "Sheet..." of an EXISTING project is not renamed and overwritten
    b = Book(("Sheet1",))
    ws, created = NEW._origin_sheet(b, "sample_TRESmap")
    check("existing project with a single Sheet1: a new tab is added, Sheet1 keeps its name",
          [s.name for s in b.sheets] == ["Sheet1", "sample_TRESmap"] and ws is b.sheets[1] and created,
          str([s.name for s in b.sheets]))
    b2 = Book(("Sheet1",))
    ws2, created2 = NEW._origin_sheet(b2, "sample_TRESmap", fresh=True)
    check("a project created just now: its empty Sheet1 is still renamed (one tab, as before)",
          [s.name for s in b2.sheets] == ["sample_TRESmap"] and created2)
    b3 = Book(("Sheet1", "sample_TRESmap"))
    ws3, created3 = NEW._origin_sheet(b3, "sample_TRESmap")
    check("a tab of that name is found and reused", ws3 is b3.sheets[1] and not created3)
    # through the writer: an existing .opju
    existing = Book(("Sheet1",))
    st, restore = fake_origin(book=existing)
    try:
        path = os.path.join(TMP, "have.opju"); open(path, "wb").close()
        tabs = app._opju_write_tabs(path, [("t1", lambda ws: ws.from_list(0, []))])
        check("writing into an existing project leaves its Sheet1 alone",
              [s.name for s in existing.sheets] == ["Sheet1", "t1"] and existing.sheets[0].filled == 0 and "open" in st["calls"],
              str([s.name for s in existing.sheets]))
        st2, restore2 = fake_origin()
        new_path = os.path.join(TMP, "new.opju")
        app._opju_write_tabs(new_path, [("t1", lambda ws: ws.from_list(0, []))])
        check("writing a new project gives one tab named after the data",
              [s.name for s in st2["book"].sheets] == ["t1"] and "new" in st2["calls"], str(st2["calls"]))
        restore2()
    finally:
        restore()

# ---------------------------------------------------------------------------------------------
if section("B-23"):
    # Origin missing or not answering: a sentence, and COM is left as it was found
    class ComError(Exception):
        pass
    st, restore = fake_origin(new_error=ComError("(-2147221005, 'Invalid class string', None, None)"))
    try:
        try:
            app._opju_write_tabs(os.path.join(TMP, "x.opju"), [("t", lambda ws: None)])
            msg = ""
        except Exception as exc:                # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
        check("Origin cannot be started: a RuntimeError that says Origin is needed, with the raw error as detail",
              msg.startswith("RuntimeError") and "Origin" in msg and "installed" in msg and "Invalid class string" in msg,
              msg[:200])
        check("COM is uninitialised exactly as often as it was initialised", st["co"] == 0, str(st["co"]))
    finally:
        restore()
    st, restore = fake_origin()
    try:
        com = sys.modules["pythoncom"]

        def no_init():
            raise ComError("already initialised in another mode")
        com.CoInitialize = no_init
        app._opju_write_tabs(os.path.join(TMP, "y.opju"), [("t", lambda ws: None)])
        check("when CoInitialize fails, CoUninitialize is not called for it", st["co"] == 0, str(st["co"]))
    finally:
        restore()

# ---------------------------------------------------------------------------------------------
if section("S-2"):
    # the install hint must not tell the user of the .exe to pip-install into the .exe
    import builtins
    real_import = builtins.__import__

    def no_pandas(name, *a, **k):
        if name in ("pandas", "originpro", "pythoncom"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *a, **k)
    exe = sys.executable
    for frozen in (True, False):
        if frozen:
            sys.frozen = True
            sys.executable = r"C:\Tools\TCSPC_analysis\TCSPC_analysis.exe"
        builtins.__import__ = no_pandas
        try:
            msgs = []
            # (up to 1.5 pandas was asked for in the same way; the program no longer uses it - D-27)
            for fn in (lambda: app._opju_write_tabs(os.path.join(TMP, "z.opju"), []),):
                try:
                    fn()
                    msgs.append("")
                except Exception as exc:            # noqa: BLE001
                    msgs.append(str(exc))
        finally:
            builtins.__import__ = real_import
            if frozen:
                del sys.frozen
                sys.executable = exe
        if frozen:
            check("in the .exe: no 'pip install' into the .exe is suggested; the hint says what to do instead",
                  all(m and "pip install" not in m and "TCSPC_analysis.exe" not in m and "CSV" in m for m in msgs),
                  str(msgs))
        else:
            check("from source: the pip command for this Python is still given",
                  all(m and "pip install" in m and exe in m for m in msgs), str(msgs))

NEW.filedialog.asksaveasfilename = real_save
top.destroy()
finish()
