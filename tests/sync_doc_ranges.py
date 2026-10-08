"""Bring the per-module line counts and the totals in ARCHITECTURE.md in step with the package.

Run after any edit that changes the length of a module; check_doc.py verifies the result.
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "tcspc_analysis")
DOC = ROOT + r"\ARCHITECTURE.md"


def n_lines(path):
    lines = io.open(path, encoding="utf-8").read().split("\n")
    return len(lines) - 1 if lines[-1] == "" else len(lines)


counts = {os.path.relpath(os.path.join(d, f), PKG).replace("\\", "/"): n_lines(os.path.join(d, f))
          for d, _, fs in os.walk(PKG) for f in fs if f.endswith(".py")}
s = io.open(DOC, encoding="utf-8", newline="").read()
for mod, n in counts.items():
    s, hits = re.subn(r"(^\| `" + re.escape(mod) + r"` \| )\d+( \|)",
                      lambda mm: f"{mm.group(1)}{n}{mm.group(2)}", s, flags=re.M)
    assert hits == 1, mod
s, hits = re.subn(r"\(파일 \d+개, [\d,]+줄\)", f"(파일 {len(counts)}개, {sum(counts.values()):,}줄)", s)
assert hits == 1
io.open(DOC, "w", encoding="utf-8", newline="").write(s)
print("line counts synced;", len(counts), "files,", sum(counts.values()), "lines")
