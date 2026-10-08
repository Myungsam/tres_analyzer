# One launcher run in a brand-new environment with an apostrophe in TEMP (used for the intermediate
# commits of G10; the full set of environments is launcher_check.ps1). Exit code = the smoke run's.
param([string]$label = "launcher-step")
$env:PYTHONIOENCODING = "utf-8"
$env:SMOKE_WAIT = "600"
$env:SMOKE_OUTPUT = "20000"
$root = Split-Path $PSScriptRoot -Parent
$work = Join-Path $env:TEMP "tcspc_launcher_step"
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
$odd = Join-Path $work "O'Brien tmp"
New-Item -ItemType Directory -Force $odd | Out-Null
$realLocal = $env:LOCALAPPDATA; $realTemp = $env:TEMP
$env:LOCALAPPDATA = Join-Path $work "fresh"
New-Item -ItemType Directory -Force $env:LOCALAPPDATA | Out-Null
$env:TEMP = $odd; $env:TMP = $odd
$phu = (python -B -c "import sys; sys.path.insert(0, sys.argv[1]); import _versions; print(_versions.samples()[0])" $PSScriptRoot)
$out = python -B "$PSScriptRoot\smoke_entry.py" $label cmd.exe /c "$root\TCSPC_analysis.bat" $phu
$rc = $LASTEXITCODE
$out | Select-Object -First 1
$vpy = Join-Path $env:LOCALAPPDATA "TCSPC_analysis\venv\Scripts\python.exe"
if (Test-Path $vpy) {
    & $vpy -c "import importlib.util as u; print('packages:', {m: bool(u.find_spec(m)) for m in ('numpy','scipy','matplotlib','pandas','originpro','win32com')})"
    "stamp: " + (Get-Content (Join-Path $env:LOCALAPPDATA "TCSPC_analysis\venv\deps_ok.txt"))
}
$env:LOCALAPPDATA = $realLocal; $env:TEMP = $realTemp; $env:TMP = $realTemp
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $root -Filter *.log | ForEach-Object { "LOG LEFT: $($_.Name)" }
exit $rc
