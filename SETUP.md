# TCSPC_analysis — running it on another computer

`TCSPC_analysis` is a Python GUI (PicoHarp 300 post-processing: **PHU/TRES** +
**PTU/FLIM**). It is launched by **`TCSPC_analysis.bat`** (or the
**`TCSPC_analysis.lnk`** shortcut, which shows the app icon).

## First run on a new computer

1. Install **Python 3.9 or newer** from <https://www.python.org/downloads/>.
   In the installer tick **“Add python.exe to PATH.”**
2. Copy the whole `TCSPC_plot` folder to the new computer
   (the `tcspc_analysis\` folder, `run_tcspc_analysis.py`, `.bat`, `requirements*.txt`,
   `.ico`, `Data\`, …).
3. Double-click **`TCSPC_analysis.bat`** (or the shortcut).
   The first launch, with an internet connection, will automatically:
   - find Python,
   - build an isolated environment at
     `%LOCALAPPDATA%\TCSPC_analysis\venv`,
   - install the packages in `requirements.txt` into it,
   - then open the app.
4. Every later run detects that environment and starts immediately.

That is all the “package management” the user has to do — the launcher
handles the rest.

### Why the environment is in `%LOCALAPPDATA%`

This project folder may be **OneDrive-synced**. A virtual environment is
machine-specific (absolute paths, compiled binaries) and must never be
synced, so the launcher keeps it in `%LOCALAPPDATA%\TCSPC_analysis\`, which
is local to each computer. The synced folder only ever holds the source and
the small text/asset files. For the same reason the launcher sets
`PYTHONPYCACHEPREFIX` to `%LOCALAPPDATA%\TCSPC_analysis\pycache`, so Python's
compiled copies of the `tcspc_analysis` modules are written there and no
`__pycache__` folder appears next to the source.

## Dependencies

| File | Contents | Installed |
|------|----------|-----------|
| `requirements.txt` | numpy, scipy, matplotlib, pandas, pywin32, originpro | automatically, on first run |
| `requirements-optional.txt` | tensorflow (FLIM GPU only) | manually, only if you want GPU |

`tkinter` ships with the standard python.org installer, so it is not listed.

Everything the app normally does — viewing PHU/TRES and PTU/FLIM, Kinetics and
Global-analysis fits, and both **CSV** and **`.opju`** export — is covered by
`requirements.txt`, so it all works on a fresh machine with no manual step.

> **`.opju` (Origin) export** also needs **OriginLab Origin** itself installed
> on the PC: `pandas`, `pywin32` and `originpro` only drive Origin over COM.
> Without Origin the app still runs and CSV export is unaffected.

### Enabling the optional GPU feature

Install the extra into the **same** environment the launcher built, only if you
want GPU-accelerated FLIM:

```bat
"%LOCALAPPDATA%\TCSPC_analysis\venv\Scripts\python" -m pip install -r requirements-optional.txt
```

- **FLIM GPU** needs `tensorflow==2.10.1` plus CUDA 11.2 / cuDNN 8.1. Without
  it the FLIM tab still runs on the CPU.

## Resetting / updating

- To rebuild the environment from scratch, delete
  `%LOCALAPPDATA%\TCSPC_analysis\` and run the `.bat` again.
- If `requirements.txt` changes, bump `REQ_VERSION` near the top of
  `TCSPC_analysis.bat` (e.g. `1` → `2`); the next launch reinstalls.

## Troubleshooting

- **“Python was not found.”** Install Python 3 and tick *Add to PATH*, or open
  a terminal and confirm `python --version` works.
- **Install failed.** Re-run the `.bat` with an internet connection, or run the
  manual `pip install -r requirements.txt` line it prints.
- **The console window stays open** behind the app. That is normal — it shows
  any error messages. Close it after quitting the app. To launch with no
  console, run `...\venv\Scripts\pythonw.exe -B run_tcspc_analysis.py` from this
  folder instead (`-B` keeps `__pycache__` out of it; see the last point below
  for the two Tcl/Tk variables this needs).

The launcher already handles the two things that usually break a portable
Python GUI, so you should not have to:

- **No C/Fortran compiler is needed.** `requirements.txt` installs prebuilt
  wheels only (`--only-binary`), so pip never tries to compile numpy/scipy.
- **Free-threaded Python is skipped.** If both the standard and the
  free-threaded (`3.13t`) Python are installed, the launcher picks the
  standard one — the free-threaded build has almost no scientific wheels yet.
- **tkinter/Tcl is wired up automatically.** A Windows venv does not carry its
  own Tcl/Tk; the launcher sets `TCL_LIBRARY`/`TK_LIBRARY` to the base Python’s
  copies so the GUI opens. (If you launch the venv’s `python` yourself and see
  a “Can’t find init.tcl” error, set those two variables the same way.)

## Zero-Python machines (optional, standalone .exe)

If a target computer cannot have Python installed at all, use the frozen build:
**`TCSPC_analysis_<version>.zip`** from the GitHub Releases page. It holds one
folder, `TCSPC_analysis\`, with `TCSPC_analysis.exe` and an `_internal\`
folder beside it (about 80 MB zipped, 180 MB unpacked, no console window).

1. Before unpacking, right-click the downloaded zip → **Properties** → tick
   **Unblock** → OK. (Otherwise Windows marks every unpacked file as
   downloaded and checks each one on the first start.)
2. Unpack it to a **local** folder that is not synced (not OneDrive) - for
   example `C:\Users\<you>\TCSPC_analysis\`. The folder holds about 2,000
   small files.
3. Start `TCSPC_analysis\TCSPC_analysis.exe`; a `.phu` path can be passed as an
   argument. Make a shortcut to the .exe if you want one on the desktop - do
   **not** move the .exe out of its folder, it needs `_internal\` next to it.
4. If Windows SmartScreen shows “Windows protected your PC” on the first start
   (the program is not signed), choose **More info → Run anyway**.

To upgrade, delete the old `TCSPC_analysis\` folder and unpack the new zip.
Nothing of yours is inside it:

- Exported data defaults to **`Documents\TCSPC_analysis\Data\`** (the save
  dialogs open there; any other folder can be chosen).
- If the window ever stops answering for more than 5 seconds, or a step fails
  silently, the program notes where it was in
  **`Documents\TCSPC_analysis\TCSPC_analysis_freeze.log`** (next to
  `run_tcspc_analysis.py` when run from source; in
  `%LOCALAPPDATA%\TCSPC_analysis\` if that folder cannot be written). The log
  holds code locations and the name of the open file, no measured data - it is
  the file to send along with a bug report. A slow but healthy step is noted
  the same way (starting Origin for an `.opju` export easily takes longer
  than 5 seconds); such an entry names the export and is not a fault.
- `.opju` export still needs OriginLab Origin installed on that PC; the
  `originpro` / `pywin32` drivers are inside the build.
- FLIM GPU (TensorFlow) is not part of the frozen build; the FLIM tab runs on
  the CPU.

The build is a folder rather than a single .exe because a single-file .exe
unpacks itself on every start: measured on the development PC, the window is
up after about 1.7 s from the folder against about 6.2 s for the 1.4.2
single-file .exe.

To rebuild it after changing the code in `tcspc_analysis\`, from this folder (the
`set` lines let PyInstaller find the venv's Tcl/Tk; build files and the
unpacked folder go to `%LOCALAPPDATA%`, so only the finished zip lands in a
synced folder):

```bat
set "VENV=%LOCALAPPDATA%\TCSPC_analysis\venv"
set "BUILD=%LOCALAPPDATA%\TCSPC_analysis\build"
for /f "delims=" %%P in ('"%VENV%\Scripts\python" -c "import sys;print(sys.base_prefix)"') do set "BP=%%P"
set "TCL_LIBRARY=%BP%\tcl\tcl8.6"
set "TK_LIBRARY=%BP%\tcl\tk8.6"
"%VENV%\Scripts\python" -m pip install --only-binary=:all: pyinstaller
"%VENV%\Scripts\python" -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --icon "%CD%\TCSPC_analysis.ico" --name TCSPC_analysis ^
    --workpath "%BUILD%\work" --specpath "%BUILD%" --distpath "%BUILD%\dist" ^
    --exclude-module tensorflow ^
    --collect-submodules originpro --collect-all OriginExt run_tcspc_analysis.py
if not exist release mkdir release
"%VENV%\Scripts\python" -c "import shutil;shutil.make_archive(r'release\TCSPC_analysis_1.6','zip',r'%BUILD%\dist','TCSPC_analysis')"
```

(Typed at a prompt rather than saved in a `.bat`, write `%P` instead of `%%P`.)

Only `tensorflow` is excluded (the GPU path is optional and would add several
hundred MB). Nothing else is left out on purpose: scipy, pandas, numpy,
pywin32 and originpro are all imported late, inside functions, and a module
missing from the build would only show as a failure when that feature is
first used.
