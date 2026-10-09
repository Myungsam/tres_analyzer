# Runs TCSPC_analysis.bat the way a user's PC would meet it (G10: D-18, D-19, D-20).
#   1. this PC's environment as it is                      -> window comes up
#   2. a TEMP folder with an apostrophe in its name (D-18)  -> window comes up (Tcl/Tk found)
#   3. a brand-new environment (LOCALAPPDATA redirected)    -> venv built, tested versions installed, window comes up
#   4. the same with one .opju package made uninstallable (D-19) -> a note, and the window still comes up
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$env:SMOKE_WAIT = "900"      # a first run builds an environment and installs packages
$env:SMOKE_OUTPUT = "20000"
$root = Split-Path $PSScriptRoot -Parent
$smoke = "$PSScriptRoot\smoke_entry.py"
$phu = (python -B -c "import sys; sys.path.insert(0, sys.argv[1]); import _versions; print(_versions.samples()[0])" $PSScriptRoot)
$work = Join-Path $env:TEMP "tcspc_launcher_check"
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $work | Out-Null
$realLocal = $env:LOCALAPPDATA
$realTemp = $env:TEMP

Write-Output "== 1. as it is"
python -B $smoke "launcher" cmd.exe /c "$root\TCSPC_analysis.bat" $phu

Write-Output "== 2. TEMP with an apostrophe"
$odd = Join-Path $work "O'Brien tmp"
New-Item -ItemType Directory -Force $odd | Out-Null
$env:TEMP = $odd; $env:TMP = $odd
python -B $smoke "launcher-apostrophe" cmd.exe /c "$root\TCSPC_analysis.bat" $phu
$env:TEMP = $realTemp; $env:TMP = $realTemp

Write-Output "== 3. a new environment"
$env:LOCALAPPDATA = Join-Path $work "fresh"
New-Item -ItemType Directory -Force $env:LOCALAPPDATA | Out-Null
python -B $smoke "launcher-fresh" cmd.exe /c "$root\TCSPC_analysis.bat" $phu
$vpy = Join-Path $env:LOCALAPPDATA "TCSPC_analysis\venv\Scripts\python.exe"
if (Test-Path $vpy) {
    & $vpy -c "import numpy, scipy, matplotlib, originpro, win32com, importlib.util as u; print('installed:', numpy.__version__, scipy.__version__, matplotlib.__version__, 'pandas present (not expected since 1.6)' if u.find_spec('pandas') else 'no pandas (as intended)')"
    Get-Content (Join-Path $env:LOCALAPPDATA "TCSPC_analysis\venv\deps_ok.txt")
}

Write-Output "== 4. a new environment in which an .opju package cannot be installed"
$env:LOCALAPPDATA = Join-Path $work "noopju"
New-Item -ItemType Directory -Force $env:LOCALAPPDATA | Out-Null
$copy = Join-Path $work "copy"
New-Item -ItemType Directory -Force $copy | Out-Null
Copy-Item "$root\TCSPC_analysis.bat", "$root\requirements.txt", "$root\run_tcspc_analysis.py", "$root\TCSPC_analysis.ico" $copy
Copy-Item "$root\tcspc_analysis" $copy -Recurse
# no lock file that installs, and .opju lists that cannot be installed
Set-Content (Join-Path $copy "requirements-lock.txt") "--only-binary=:all:`r`nnumpy==0.0.1"
# (versions that do not exist of packages that do: a made-up package NAME could be registered by anyone)
Set-Content (Join-Path $copy "requirements-opju-lock.txt") "--only-binary=:all:`r`npywin32==0.0.1"
Set-Content (Join-Path $copy "requirements-opju.txt") "--only-binary=:all:`r`npywin32==0.0.1"
$out = python -B $smoke "launcher-no-opju" cmd.exe /c "$copy\TCSPC_analysis.bat" $phu
$out | Select-Object -First 1
($out -join "`n") -match "tested package versions are not all available" | ForEach-Object { "said that the tested versions were not available: $_" }
($out -join "`n") -match "could not be installed" | ForEach-Object { "said that the .opju packages could not be installed: $_" }
$env:LOCALAPPDATA = $realLocal
Get-ChildItem $copy -Filter *.log | ForEach-Object { "log left in the copy: $($_.Name)" }
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $root -Filter *.log | Select-Object -ExpandProperty Name
