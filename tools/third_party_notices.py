r"""Put the license texts of everything bundled into a frozen build next to it.

    python tools/third_party_notices.py <build folder>

<build folder> is the PyInstaller output (the folder holding TCSPC_analysis.exe and _internal\).
Run it with the Python of the environment the build was made from (the launcher's venv, with
PyInstaller installed): the license files are read from the packages installed there. Writes
into <build folder>:

    LICENSE                    this program's license (MIT), copied from the repository
    THIRD-PARTY-NOTICES.txt    Python (with the libraries its license page covers: OpenSSL, expat,
                               libffi, zlib, libmpdec ...), bzip2, Tcl/Tk, a note on the PyInstaller
                               bootloader, and each installed package that is in the build, with
                               its license file(s)

A package counts as bundled when one of its top-level import names is in the build: a folder,
module or extension in _internal\, or a module in the PYZ archive inside the .exe (where the
pure-Python packages are). Exits with 1, naming them, when a bundled package has no license file.
"""
import glob
import os
import shutil
import sys
from html.parser import HTMLParser
from importlib import metadata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LICENSE_NAMES = ("license", "licence", "copying", "notice")


def read(path):
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


class _MainText(HTMLParser):
    """The text of a Sphinx page's main block (<div class="body">), one line per block."""
    BLOCKS = {"p", "div", "pre", "li", "h1", "h2", "h3", "h4", "tr", "br", "section"}

    def __init__(self):
        super().__init__()
        self.depth = 0          # div nesting inside the main block; 0 = outside
        self.out = []

    def handle_starttag(self, tag, attrs):
        if self.depth:
            if tag == "div":
                self.depth += 1
            if tag in self.BLOCKS:
                self.out.append("\n")
        elif tag == "div" and "body" in (dict(attrs).get("class") or "").split():
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth:
            if tag in self.BLOCKS:
                self.out.append("\n")
            if tag == "div":
                self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.out.append(data)


def html_text(page):
    p = _MainText()
    p.feed(page)
    lines = [ln.rstrip() for ln in "".join(p.out).replace("\xb6", "").splitlines()]
    text = "\n".join(lines)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def build_names(build):
    """Every top-level name in the build: the _internal entries and the PYZ's modules."""
    internal = os.path.join(build, "_internal")
    names = set()
    for entry in os.listdir(internal):
        names.add(entry.split(".")[0])
    from PyInstaller.archive.readers import CArchiveReader
    for exe in glob.glob(os.path.join(build, "*.exe")):
        arch = CArchiveReader(exe)
        for key, entry in arch.toc.items():
            if entry[-1] == "z":
                names.update(n.split(".")[0] for n in arch.open_embedded_archive(key).toc)
    return names


def top_level_names(dist):
    """The import names a distribution installs: top_level.txt, else its files."""
    text = dist.read_text("top_level.txt")
    if text:
        raw = text.split()
    else:
        raw = [str(f) for f in dist.files or ()]
    names = set()
    for n in raw:
        first = n.replace("\\", "/").split("/")[0]
        if first.endswith((".dist-info", ".data")) or first in ("..", ""):
            continue
        names.add(first.split(".")[0])
    return names


def license_files(dist):
    """(name, text) of the license files shipped in a distribution's metadata."""
    out = []
    for f in dist.files or ():
        if f.parts[0].endswith(".dist-info") and \
                os.path.basename(str(f)).lower().startswith(LICENSE_NAMES):
            try:
                out.append((str(f), read(dist.locate_file(f))))
            except OSError:
                pass
    return out


def license_label(dist):
    """A short license name for the section title, or ''."""
    meta = dist.metadata
    expr = meta.get("License-Expression")
    if expr:
        return expr
    lic = (meta.get("License") or "").strip()
    if lic and "\n" not in lic and len(lic) <= 60:
        return lic
    for c in meta.get_all("Classifier") or ():
        if c.startswith("License ::"):
            return c.split("::")[-1].strip()
    return ""


def section(title, texts):
    bar = "=" * 78
    body = "\n\n".join(f"--- {name} ---\n\n{text.strip()}" for name, text in texts)
    return f"{bar}\n{title}\n{bar}\n\n{body}\n\n"


def main(build):
    internal = os.path.join(build, "_internal")
    if not os.path.isdir(internal):
        sys.exit(f"no _internal folder in {build}")
    names = build_names(build)
    parts, missing = [], []

    # Python, and the libraries its Windows build brings along (OpenSSL, expat, libffi, zlib,
    # libmpdec ...): the license page of its documentation. Not LICENSE.txt in the Python
    # folder - originpro / OriginExt install their own LICENSE.txt over it.
    page = os.path.join(sys.base_prefix, "Doc", "html", "license.html")
    if not os.path.exists(page):
        sys.exit(f"Python's license page is missing: {page}")
    parts.append(section(f"Python {sys.version.split()[0]} and the software it incorporates",
                         [("Doc/html/license.html", html_text(read(page)))]))
    if glob.glob(os.path.join(internal, "_bz2*.pyd")):
        parts.append(section("bzip2 (in _bz2.pyd)",
                             [("bzip2 LICENSE", read(os.path.join(ROOT, "tools", "notices", "bzip2-LICENSE.txt")))]))
    if glob.glob(os.path.join(internal, "_lzma*.pyd")):
        parts.append(section("xz / liblzma (in _lzma.pyd)",
                             [("note", "liblzma is in the public domain (0BSD in newer releases); "
                                       "no notice is required.")]))
    parts.append(section("PyInstaller bootloader (the start-up code of TCSPC_analysis.exe)",
                         [("note", "PyInstaller is distributed under the GPL 2.0 with an exception "
                                   "that allows programs built with it to be distributed under any "
                                   "license. See https://pyinstaller.org/en/stable/license.html")]))
    # Tcl and Tk: from the build itself, else from the Python they came with
    tcltk = {}
    for path in (glob.glob(os.path.join(internal, "_t*_data", "license.terms"))
                 + glob.glob(os.path.join(sys.base_prefix, "tcl", "*", "license.terms"))):
        part = os.path.basename(os.path.dirname(path))
        key = "Tk" if "tk" in part.lower() else "Tcl"
        tcltk.setdefault(key, (f"{part}/license.terms", read(path)))
    if tcltk:
        # python.org's Windows build ships Tk's license.terms only; Tcl's terms are the same text
        title = "Tcl/Tk" if len(tcltk) == 2 else "Tcl/Tk (Tcl and Tk are distributed under the same terms)"
        parts.append(section(title, [tcltk[k] for k in sorted(tcltk)]))

    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        if not names & top_level_names(dist):
            continue
        texts = license_files(dist)
        label = license_label(dist)
        title = f"{dist.metadata['Name']} {dist.version}" + (f"  ({label})" if label else "")
        if texts:
            parts.append(section(title, texts))
        else:
            missing.append(dist.metadata["Name"])

    head = ("TCSPC_analysis bundles the third-party software below. Each part is "
            "distributed under its own license, reproduced here.\n"
            "TCSPC_analysis itself is under the MIT License (see LICENSE).\n\n")
    with open(os.path.join(build, "THIRD-PARTY-NOTICES.txt"), "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(head + "".join(parts))
    shutil.copyfile(os.path.join(ROOT, "LICENSE"), os.path.join(build, "LICENSE"))
    print(f"wrote LICENSE and THIRD-PARTY-NOTICES.txt ({len(parts)} parts) to {build}")
    if missing:
        print("no license file found for: " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
