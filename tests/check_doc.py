"""ARCHITECTURE.md vs the tcspc_analysis package: the document must describe the code that is there."""
import ast
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "tcspc_analysis")
doc = io.open(ROOT + r"\ARCHITECTURE.md", encoding="utf-8").read().replace("\r\n", "\n")
files = sorted(os.path.relpath(os.path.join(d, f), PKG).replace("\\", "/")
               for d, _, fs in os.walk(PKG) for f in fs if f.endswith(".py"))
text = {f: io.open(os.path.join(PKG, f), encoding="utf-8").read() for f in files}
src = "\n".join(text.values())
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def n_lines(s):
    lines = s.split("\n")
    return len(lines) - 1 if lines[-1] == "" else len(lines)


# 1) every backticked identifier exists in the code
toks = set(re.findall(r"`([^`\n]+)`", doc))
missing = []
for t in sorted(toks):
    if any(x in t for x in (".py", ".phu", ".ptu", ".opju", ".csv", ".bat", "python ", "{", "/")):
        continue
    for p in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", t):
        if not re.search(r"\b" + re.escape(p) + r"\b", src):
            missing.append((t, p))
check(f"all {len(toks)} backticked identifiers exist in the code", not missing, str(missing))

# 2) mermaid blocks: closed, typed, identifiers in labels exist, node ids defined
blocks = re.findall(r"```mermaid\n(.*?)```", doc, re.S)
bad = []
for b in blocks:
    for lab in re.findall(r'\["([^"]+)"\]', b):
        for p in re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", lab):
            if not re.search(r"\b" + re.escape(p) + r"\b", src):
                bad.append(p)
    if b.startswith("flowchart"):
        defined = set(re.findall(r'\b([A-Za-z0-9_]+)\["', b)) | set(
            re.findall(r"subgraph ([A-Za-z0-9_]+)", b))
        for ln in b.split("\n"):
            mm = re.match(r'\s*([A-Za-z0-9_]+)(?:\["[^"]*"\])?\s*-->\s*([A-Za-z0-9_]+)', ln)
            if mm:
                bad += [x for x in mm.groups() if x not in defined]
kinds = [b.split("\n")[0].strip().split()[0] for b in blocks]
check(f"{len(blocks)} mermaid blocks closed, typed, known identifiers and node ids",
      doc.count("```") == 2 * len(blocks) and not bad
      and all(k in ("flowchart", "classDiagram", "sequenceDiagram") for k in kinds),
      f"{kinds} {bad}")

# 3) the module table: every file of the package, with its line count and names that live in it
rows = re.findall(r"^\| `([\w/]+\.py)` \| (\d+) \| [^|]*\| ([^|]*) \|$", doc, re.M)
listed = [r[0] for r in rows]
check("the module table lists every file of the package, once",
      sorted(listed) == files, str(sorted(set(listed) ^ set(files))))
wrong = [(f, int(n), n_lines(text[f])) for f, n, _ in rows if f in text and int(n) != n_lines(text[f])]
check("module line counts match the files", not wrong, str(wrong))
total = sum(n_lines(s) for s in text.values())
check("file and line totals in the doc match the package",
      f"파일 {len(files)}개, {total:,}줄" in doc, f"{len(files)} files, {total} lines")


def top_names(s):
    out = set()
    for node in ast.parse(s).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            out |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return out


astray = [(f, n) for f, _, names in rows if f in text
          for n in re.findall(r"`(\w+)`", names) if n not in top_names(text[f])]
check("the names in the module table are defined in that module", not astray, str(astray))


# 4) the dependency table against the imports in the code
def module_of(f, level, name):
    base = f.split("/")[:-1]
    base = base[:len(base) - (level - 1)] if level > 1 else base
    return "/".join(base + name.split(".")) + ".py"


real = {}
for f, s in text.items():
    uses = set()
    for node in ast.walk(ast.parse(s)):
        if isinstance(node, ast.ImportFrom) and node.level:
            uses.add(module_of(f, node.level, node.module))
    real[f] = uses
a = doc.index("| 모듈 | 가져다 쓰는 모듈 |")
dep_rows = re.findall(r"^\| ([^|]+) \| ([^|]+) \|$", doc[a:doc.index("\n\n", a)], re.M)[1:]
told = {}
for left, right in dep_rows:
    for f in re.findall(r"`([\w/]+\.py)`", left):
        told[f] = set(re.findall(r"`([\w/]+\.py)`", right))
entry = {"__init__.py", "__main__.py", "dialogs/__init__.py"}        # not in the table: no code of their own
diff = [(f, sorted(real[f]), sorted(told.get(f, {"(missing)"}))) for f in files
        if f not in entry and real[f] != told.get(f)]
check("the dependency table is exactly the package's internal imports", not diff and not set(told) - set(files),
      str(diff))
check("the entry modules import nothing but app.main",
      real["__init__.py"] == set() and real["dialogs/__init__.py"] == set() and real["__main__.py"] == {"app.py"})

# 5) names the document must keep explaining
need = ["solvent", "solvent_scale", "solvent_sub", "solvent_mismatch",
        "copy_settings_from", "solvent_spectrum", "neg_frac", "program_dir"]
check("key names are documented", all(f"`{n}`" in doc for n in need),
      str([n for n in need if f"`{n}`" not in doc]))

# 6) tables keep their column count
tbl_bad, rows_, i = [], doc.split("\n"), 0
while i < len(rows_):
    if rows_[i].startswith("|") and i + 1 < len(rows_) and rows_[i + 1].startswith("|---"):
        n = re.sub(r"`[^`]*`", "", rows_[i]).count("|")
        j = i
        while j < len(rows_) and rows_[j].startswith("|"):
            if re.sub(r"`[^`]*`", "", rows_[j]).count("|") != n:
                tbl_bad.append(j + 1)
            j += 1
        i = j
    else:
        i += 1
check("tables have consistent column counts", not tbl_bad, str(tbl_bad))

# 7) the package docstring describes the features and how to start the program
head = ast.get_docstring(ast.parse(text["__init__.py"]), clean=False)
check("package docstring mentions the solvent subtraction",
      "Load solvent..." in head and "sample - scale x solvent" in head)
check("package docstring gives the way to start the package", "python -m tcspc_analysis [file.phu]" in head)
check("no caveat / improvement sections crept into the doc",
      not [w for w in ["주의점", "한계", "개선", "리팩터", "문제점", "권장"] if w in doc])
stale = [w for w in ("단일 파일", "섹션 2", "TCSPC_analysis_1.4ver.py [file.phu]") if w in doc]
check("nothing still describes the program as one file", not stale, str(stale))

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILED: {fails}")
sys.exit(1 if fails else 0)
