"""Split TCSPC_analysis_1.4ver.py into the package tcspc_analysis/ - mechanically.

    python tools/split_1_4.py TCSPC_analysis_1.4ver.py . --version 1.5 --manifest tools/split_manifest.json

Every top-level statement keeps its source lines byte for byte (with the comments, banners and
blank lines in front of it); only the import block of each module is generated, from the names
the module really uses (symtable, so a local that shadows a module name is not mistaken for it).
The few places that cannot be a plain copy are listed in WHITELIST below.
Writes <output>/tcspc_analysis/..., <output>/run_tcspc_analysis.py and the manifest (module -> the
source line ranges it was built from; default <output>/split_manifest.json).

This is the tool that made version 1.5 out of 1.4.2; it is kept for that one release so the split
can be checked and repeated, and goes away afterwards.
"""
import ast
import builtins
import io
import json
import os
import re
import symtable
import sys

PKG = "tcspc_analysis"

# top-level name -> module, for the names that do not follow their section's default
BY_NAME = {
    "CMAPS": "viewer", "BIN_CHOICES": "viewer", "TRESViewer": "viewer",
    "_style_analysis_ax": "dialogs/common", "_dark_toolbar": "dialogs/common",
    "ComponentTable": "dialogs/common", "_AnalysisDialog": "dialogs/common",
    "CropDialog": "dialogs/crop", "MaskDialog": "dialogs/mask",
    "KineticsDialog": "dialogs/kinetics", "GlobalAnalysisDialog": "dialogs/global_analysis",
    "APP_VERSION": "version", "FreezeLog": "freezelog", "main": "app",
}
BY_SECTION = {"1": "phu", "2": "util", "2b": "origin", "2c": "flim", "2d": "fitting",
              "3": "model", "4": "theme", "5": "flim"}
ORDER = ["version", "paths", "phu", "util", "origin", "fitting", "model", "theme", "flim",
         "dialogs/common", "dialogs/crop", "dialogs/mask", "dialogs/kinetics",
         "dialogs/global_analysis", "viewer", "freezelog", "app"]
# module -> the package modules it may import from (anything else is an error)
ALLOWED = {
    "version": [], "paths": [], "phu": [], "util": [], "origin": [], "fitting": [], "theme": [],
    "model": ["util"], "flim": ["theme"],
    "dialogs/common": ["theme"],
    "dialogs/crop": ["dialogs/common", "theme", "model", "phu", "util"],
    "dialogs/mask": ["dialogs/common", "theme"],
    "dialogs/kinetics": ["dialogs/common", "theme", "fitting", "origin"],
    "dialogs/global_analysis": ["dialogs/common", "theme", "fitting", "origin"],
    "viewer": ["dialogs/crop", "dialogs/mask", "dialogs/kinetics", "dialogs/global_analysis",
               "theme", "model", "phu", "util", "origin", "paths"],
    "freezelog": ["paths", "version"],
    "app": ["viewer", "flim", "theme", "freezelog"],
}
DOC = {
    "version": "The version of the program.",
    "paths": "Where the program lives on disk.",
    "phu": "PicoQuant .phu (PQHISTO) reader.",
    "util": "Small helpers shared by the model and the windows.",
    "origin": "Writing OriginLab .opju worksheets.",
    "fitting": "Kinetics and global-analysis fit kernels.",
    "model": "TRESModel: rebinning, slicing and the preprocessing of one .phu file.",
    "theme": "Colours, the ttk theme and the plot helpers every window shares.",
    "flim": "The PTU / FLIM tab: T3 record processing and its viewer.",
    "dialogs/common": "What the pop-up windows share.",
    "dialogs/crop": "The Crop window (crop box, solvent subtraction, time slices, zoom).",
    "dialogs/mask": "The Mask window.",
    "dialogs/kinetics": "The Kinetics window (single-wavelength fit).",
    "dialogs/global_analysis": "The Global-analysis window.",
    "viewer": "The PHU / TRES tab.",
    "freezelog": "FreezeLog: notes where the program is when its window stops answering.",
    "app": "The application window with its two tabs.",
}
PATHS_PY = '''"""Where the program lives on disk."""
import os
import sys


def program_dir():
    """The folder the program is started from: the one holding the .exe in a
    frozen build, otherwise the one holding the package (where the launcher
    and Data\\\\ are)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
'''
# (name, old text, new text): the only edits made to copied lines
WHITELIST = [
    ("W1", '        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Data")\n',
     '        return os.path.join(program_dir(), "Data")\n'),
    ("W2", '        here = os.path.dirname(sys.executable if getattr(sys, "frozen", False)\n'
           '                               else os.path.abspath(__file__))\n',
     '        here = program_dir()\n'),
]


def split(source_path, out_dir, version=None, manifest_path=None):
    text = io.open(source_path, encoding="utf-8", newline="").read()
    assert "\r" not in text
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    tree = ast.parse(text)

    banners = {}
    for i, ln in enumerate(lines, 1):
        m = re.match(r"# (\d[a-d]?)\. ", ln)
        if m and lines[i - 2].startswith("# ===="):
            banners[i] = m.group(1)

    def section_at(lineno):
        cur = "0"
        for start in sorted(banners):
            if lineno >= start:
                cur = banners[start]
        return cur

    def names_of(node):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            return [node.name]
        if isinstance(node, ast.Assign):
            return [n.id for t in node.targets for n in ast.walk(t) if isinstance(n, ast.Name)]
        return []

    # ---- header: docstring, imports, matplotlib.use -------------------------------------
    doc_node = tree.body[0]
    assert isinstance(doc_node, ast.Expr) and doc_node.lineno == 3
    imports = {}            # bound name -> (order, statement text or (module, name))
    header_end = doc_node.end_lineno
    use_line = None
    body_nodes = []
    for node in tree.body[1:]:
        if isinstance(node, ast.Import):
            for a in node.names:
                bound = a.asname or a.name.split(".")[0]
                stmt = f"import {a.name}" + (f" as {a.asname}" if a.asname else "")
                imports[bound] = (node.lineno, stmt, None)
            header_end = node.end_lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                assert a.asname is None and node.level == 0
                imports[a.name] = (node.lineno, None, node.module)
            header_end = node.end_lineno
        elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
              and ast.unparse(node.value.func) == "matplotlib.use"):
            use_line = node.lineno
            header_end = node.end_lineno
        else:
            body_nodes.append(node)
    assert use_line is not None

    # ---- assign every remaining top-level node to a module, with the lines in front of it
    owner = {}              # top-level name -> module
    chunks = {m: [] for m in ORDER}         # module -> [(first line, last line)]
    prev_end = header_end
    dropped = []
    for node in body_nodes:
        first, last = prev_end + 1, node.end_lineno
        prev_end = node.end_lineno
        if isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'":
            dropped.append(("W6", first, last))
            continue
        nm = names_of(node)
        assert nm, (node.lineno, type(node).__name__)
        mod = BY_NAME.get(nm[0]) or BY_SECTION[section_at(node.lineno)]
        assert all((BY_NAME.get(n) or BY_SECTION[section_at(node.lineno)]) == mod for n in nm)
        for n in nm:
            assert n not in owner, n
            owner[n] = mod
        if nm[0] == "APP_VERSION":          # W4: the section banner in front of it goes with FreezeLog
            chunks["freezelog"].append((first, node.lineno - 1))
            chunks[mod].append((node.lineno, last))
        else:
            chunks[mod].append((first, last))
    assert prev_end == len(lines), (prev_end, len(lines))
    owner["program_dir"] = "paths"

    def body_text(mod):
        return "".join("\n".join(lines[a - 1:b]) + "\n" for a, b in chunks[mod])

    builtin_names = set(dir(builtins))

    def free_names(src):
        top = symtable.symtable(src, "<module>", "exec")
        defined, need = set(), set()
        for s in top.get_symbols():
            if s.is_assigned() or s.is_namespace() or s.is_imported():
                defined.add(s.get_name())
            elif s.is_referenced():
                need.add(s.get_name())

        def walk(tab):
            for child in tab.get_children():
                for s in child.get_symbols():
                    if s.is_global():
                        need.add(s.get_name())
                walk(child)
        walk(top)
        return need - defined - builtin_names - {"__file__", "__name__"}

    def rel(frm, to):
        if "/" in frm:                       # inside dialogs/
            return "." + to.split("/")[1] if to.startswith("dialogs/") else ".." + to
        return "." + to.replace("/", ".")

    pkg_dir = os.path.join(out_dir, PKG)
    os.makedirs(os.path.join(pkg_dir, "dialogs"), exist_ok=True)
    manifest = {"source": os.path.basename(source_path), "source_lines": len(lines),
                "header": [1, header_end], "dropped": dropped, "modules": {}, "whitelist": []}
    used_whitelist = set()
    for mod in ORDER:
        if mod == "paths":
            content = PATHS_PY
        else:
            body = body_text(mod)
            for tag, old, new in WHITELIST:
                if old in body:
                    assert body.count(old) == 1, tag
                    body = body.replace(old, new)
                    used_whitelist.add(tag)
                    manifest["whitelist"].append([tag, mod])
            if mod == "version" and version:
                body, n = re.subn(r'APP_VERSION = "[^"]*"', f'APP_VERSION = "{version}"', body)
                assert n == 1
                manifest["whitelist"].append(["W4", mod])
            need = sorted(free_names(body))
            ext, own = {}, {}
            for name in need:
                if name in owner:
                    assert owner[name] != mod, (mod, name)
                    assert owner[name] in ALLOWED[mod], f"{mod} may not import {name} from {owner[name]}"
                    own.setdefault(owner[name], []).append(name)
                elif name in imports:
                    ext[name] = imports[name]
                else:
                    raise SystemExit(f"{mod}: unresolved name {name!r}")
            out, last_group = [], None
            froms = {}
            for name, (ln, stmt, module) in sorted(ext.items(), key=lambda kv: kv[1][0]):
                if stmt is None:
                    froms.setdefault((ln, module), []).append(name)
            emitted = set()
            for name, (ln, stmt, module) in sorted(ext.items(), key=lambda kv: (kv[1][0], kv[0])):
                group = lines[ln - 2] == "" and ln or last_group
                if stmt is not None:
                    out.append((ln, stmt))
                elif (ln, module) not in emitted:
                    emitted.add((ln, module))
                    # the names in the order the original statement lists them
                    orig = [a.name for n in tree.body if isinstance(n, ast.ImportFrom) and n.lineno == ln
                            for a in n.names]
                    keep = [a for a in orig if a in froms[(ln, module)]]
                    out.append((ln, f"from {module} import {', '.join(keep)}"))
                last_group = group
            block, prev_ln = [], None
            for ln, stmt in out:
                # keep the blank lines that separated the import groups in the original
                if prev_ln is not None and any(lines[k - 1] == "" for k in range(prev_ln, ln)):
                    block.append("")
                block.append(stmt)
                prev_ln = ln
            if own:
                if block:
                    block.append("")
                for target in ORDER:
                    if target in own:
                        block.append(f"from {rel(mod, target)} import {', '.join(sorted(own[target]))}")
            head = f'"""{DOC[mod]}"""\n' + ("\n".join(block) + "\n" if block else "")
            content = head + body
            manifest["modules"][mod] = {"ranges": chunks[mod], "import_lines": head.count("\n")}
        path = os.path.join(pkg_dir, *mod.split("/")) + ".py"
        io.open(path, "w", encoding="utf-8", newline="").write(content)
    assert used_whitelist == {"W1", "W2"}, used_whitelist

    # ---- __init__ (W5, W3, W7), __main__, the run script (W6) ------------------------------
    doc = "\n".join(lines[:doc_node.end_lineno]) + "\n"
    usage = [ln for ln in doc.split("\n") if re.match(r"\s+python TCSPC_analysis_\S+ \[file\.phu\]$", ln)]
    assert len(usage) == 1, usage
    doc = doc.replace(usage[0], re.match(r"\s+", usage[0]).group(0) + f"python -m {PKG} [file.phu]")
    mpl = "\n".join(lines[use_line - 2:use_line + 1]) + "\n"    # import matplotlib / use / pyplot
    assert mpl.startswith("import matplotlib\nmatplotlib.use(") and "pyplot" in mpl, mpl
    io.open(os.path.join(pkg_dir, "__init__.py"), "w", encoding="utf-8", newline="").write(
        doc + "\n" + mpl)
    io.open(os.path.join(pkg_dir, "dialogs", "__init__.py"), "w", encoding="utf-8", newline="").write("")
    io.open(os.path.join(pkg_dir, "__main__.py"), "w", encoding="utf-8", newline="").write(
        f'"""python -m {PKG} [file.phu]"""\nfrom .app import main\n\n'
        'if __name__ == "__main__":\n    main()\n')
    io.open(os.path.join(out_dir, "run_tcspc_analysis.py"), "w", encoding="utf-8", newline="").write(
        '"""Start TCSPC_analysis (what the launcher and the .exe build run)."""\n'
        f"from {PKG}.app import main\n\n"
        'if __name__ == "__main__":\n    main()\n')
    manifest["whitelist"] += [["W3", "__init__"], ["W5", "__init__"], ["W7", "__init__"], ["W6", "__main__"]]
    json.dump(manifest, io.open(manifest_path or os.path.join(out_dir, "split_manifest.json"), "w",
                                encoding="utf-8", newline="\n"), indent=1)
    return manifest


if __name__ == "__main__":
    ver = sys.argv[sys.argv.index("--version") + 1] if "--version" in sys.argv else None
    man = sys.argv[sys.argv.index("--manifest") + 1] if "--manifest" in sys.argv else None
    mf = split(sys.argv[1], sys.argv[2], ver, man)
    for mod, info in mf["modules"].items():
        n = sum(b - a + 1 for a, b in info["ranges"])
        print(f"{mod:26s} {n:5d} lines from {len(info['ranges'])} ranges, {info['import_lines']} head lines")
