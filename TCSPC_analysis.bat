@echo off
setlocal EnableExtensions
REM ================================================================
REM  TCSPC analysis launcher  (PHU/TRES + PTU/FLIM)
REM
REM  Portable across computers.  On the first run it locates Python,
REM  builds an isolated virtual environment under
REM      %LOCALAPPDATA%\TCSPC_analysis\venv
REM  and installs the packages from requirements.txt into it.  Every
REM  later run detects that environment and just launches the app.
REM
REM  On a NEW computer you only need:
REM    * Python 3.9+  (https://www.python.org/downloads/, tick
REM      "Add python.exe to PATH")
REM    * an internet connection on the first run, for pip
REM
REM  The environment lives in LOCALAPPDATA - deliberately NOT in this
REM  (possibly OneDrive-synced) folder - so it is per-machine and can
REM  never be synced to, or broken on, another computer.
REM ================================================================
cd /d "%~dp0"

REM Bump REQ_VERSION whenever requirements.txt changes to force a reinstall.
REM v2: added the .opju export libraries (pandas, pywin32, originpro) so a
REM     distributed copy can write .opju on a fresh machine out of the box.
REM v3: the .opju libraries are installed in a step of their own, so a PC on
REM     which one of them cannot be installed still gets the program.
REM v4: the tested versions (requirements-lock.txt) are installed first.
REM v5: pandas is no longer needed (the .opju export writes its columns itself).
REM v6: the tested .opju versions are a file of their own, so a missing one
REM     does not make the core packages fall back to the newest versions.
set "REQ_VERSION=6"
set "VENVDIR=%LOCALAPPDATA%\TCSPC_analysis"
set "VENV=%VENVDIR%\venv"
set "VPY=%VENV%\Scripts\python.exe"
set "STAMP=%VENV%\deps_ok.txt"
set "REQ=%~dp0requirements.txt"
set "REQ_OPJU=%~dp0requirements-opju.txt"
set "REQ_LOCK=%~dp0requirements-lock.txt"
set "REQ_OPJU_LOCK=%~dp0requirements-opju-lock.txt"

REM ---- 1) find a base Python to build the environment -----------
REM Validate each candidate by actually running it (skips the Windows
REM Store "python" stub, which exits non-zero).  "python" is tried first
REM so a standard CPython is preferred over a free-threaded "py -3" build,
REM which lacks prebuilt wheels for the scientific stack.
set "BASEPY="
REM It must be 3.9 or newer and come with tkinter (the python.org installer does).
set "PYOK=import sys,tkinter;sys.exit(0 if sys.version_info[:2]>=(3,9) else 1)"
python -c "%PYOK%" >nul 2>nul && set "BASEPY=python"
if defined BASEPY goto have_base
py -3 -c "%PYOK%" >nul 2>nul && set "BASEPY=py -3"
if defined BASEPY goto have_base
echo.
echo   No usable Python was found on this computer ^(3.9 or newer, with tkinter^).
echo   Install Python 3 from  https://www.python.org/downloads/
echo   and tick "Add python.exe to PATH", then run this file again.
echo.
pause
exit /b 1
:have_base

REM ---- 2) build the isolated environment on the first run ------
if exist "%VPY%" goto have_venv
echo   Creating a local Python environment ^(first run only^) ...
if not exist "%VENVDIR%" mkdir "%VENVDIR%"
REM Clean, isolated venv - dependencies are installed as prebuilt wheels
REM (see requirements.txt --only-binary), so no compiler is ever needed.
%BASEPY% -m venv "%VENV%"
if errorlevel 1 goto venv_fail
:have_venv

REM ---- 3) install / update dependencies when needed ------------
set "NEED=1"
if exist "%STAMP%" set /p HAVE=<"%STAMP%"
if defined HAVE if "%HAVE%"=="%REQ_VERSION%" set "NEED=0"
if "%NEED%"=="0" goto launch_prep
echo   Checking / installing required packages ...
"%VPY%" -m pip install --upgrade pip
REM First the exact versions the program was tested with. They exist as wheels
REM for the Python they were tested on; another Python may lack one, and then
REM the newest versions that requirements.txt allows are taken instead.
"%VPY%" -m pip install -r "%REQ_LOCK%"
if not errorlevel 1 goto core_done
echo.
echo   The tested package versions are not all available for this Python -
echo   installing the newest ones instead.
echo.
"%VPY%" -m pip install -r "%REQ%"
if errorlevel 1 goto pip_fail
:core_done
REM The .opju export only: the program must start without these. The tested
REM versions first, then whatever this Python has wheels for.
"%VPY%" -m pip install -r "%REQ_OPJU_LOCK%"
if not errorlevel 1 goto deps_done
"%VPY%" -m pip install -r "%REQ_OPJU%"
if errorlevel 1 (
    echo.
    echo   Note: the packages for the .opju ^(Origin^) export could not be installed.
    echo   Everything else works and CSV export is unaffected.
    echo.
)
:deps_done
> "%STAMP%" echo %REQ_VERSION%

REM ---- 4) point the venv's tkinter at the base Python's Tcl/Tk --
REM A Windows venv does not carry its own Tcl/Tk, so tkinter cannot find
REM init.tcl and tk.tcl unless TCL_LIBRARY / TK_LIBRARY are set to the
REM base install's copies.  Resolve them from the venv's base_prefix.
REM (runs on every launch - env vars do not persist between runs.)
:launch_prep
REM (Asked straight from Python: going through a file in %%TEMP%% put that
REM  path inside a Python string, which an apostrophe in the user name broke.)
set "BP="
for /f "delims=" %%P in ('call "%VPY%" -c "import sys;print(sys.base_prefix)"') do set "BP=%%P"
if not defined BP goto run
set "TCL_LIBRARY="
set "TK_LIBRARY="
if exist "%BP%\tcl\tcl8.6\init.tcl" set "TCL_LIBRARY=%BP%\tcl\tcl8.6"
if not defined TCL_LIBRARY for /d %%D in ("%BP%\tcl\tcl8*" "%BP%\tcl\tcl9*") do if exist "%%D\init.tcl" set "TCL_LIBRARY=%%D"
if exist "%BP%\tcl\tk8.6\tk.tcl" set "TK_LIBRARY=%BP%\tcl\tk8.6"
if not defined TK_LIBRARY for /d %%D in ("%BP%\tcl\tk8*" "%BP%\tcl\tk9*") do if exist "%%D\tk.tcl" set "TK_LIBRARY=%%D"

REM ---- 5) launch the app --------------------------------------
:run
REM The package is compiled on first import; keep those files out of this
REM (possibly OneDrive-synced) folder.
set "PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\TCSPC_analysis\pycache"
"%VPY%" "%~dp0run_tcspc_analysis.py" %*
set "rc=%errorlevel%"
if not "%rc%"=="0" (
    echo.
    echo   TCSPC_analysis exited with error code %rc%.
    pause
)
endlocal
exit /b 0

:venv_fail
echo.
echo   Failed to create the environment with:  %BASEPY%
echo   Make sure the Python install includes the "venv" module.
echo.
pause
exit /b 1

:pip_fail
echo.
echo   Package installation failed.  Check the internet connection
echo   and run this file again.  To install by hand:
echo       "%VPY%" -m pip install -r "%REQ%"
echo.
pause
exit /b 1
