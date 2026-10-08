#!/bin/bash
# Everything that must hold after a change, in the program's own Python environment.
#   bash tests/run_all.sh [label]     outputs go to tests/out/suite_<label>/ and tests/out/<label>/
# Needs the two sample records (tests/README.md). The reference outputs of 1.4.2 are made once, from
# TCSPC_analysis_1.4ver.py, into tests/out/ref_1.4.2/.
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE" || exit 1
LABEL="${1:-run}"
BASE=$(python -c "import sys;print(sys.base_prefix.replace(chr(92),'/'))")
export TCL_LIBRARY="$BASE/tcl/tcl8.6" TK_LIBRARY="$BASE/tcl/tk8.6" PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8
VPY="$LOCALAPPDATA/TCSPC_analysis/venv/Scripts/python.exe"
OUT="out/suite_$LABEL"
mkdir -p "$OUT"
python -B sync_doc_ranges.py > "$OUT/doc_sync.out" 2>&1
BAD=0
for t in test_numeric test_gui test_slice test_zoom test_v14 test_v14_native test_fatol test_facade test_paths test_dpi \
         $(ls test_g*.py 2>/dev/null | grep -v test_gui | sed 's/\.py$//') check_doc; do
    "$VPY" -B $t.py > "$OUT/$t.out" 2>&1
    RC=$?
    [ $RC -ne 0 ] && BAD=1
    echo "$t exit=$RC pass=$(grep -ac '^PASS' "$OUT/$t.out") fail=$(grep -ac '^FAIL' "$OUT/$t.out")"
    grep -a '^FAIL' "$OUT/$t.out" | cut -c1-220 | head -5
done
# pyflakes, when this environment (or the folder LINT names) has it
if PYTHONPATH="${LINT:-}" "$VPY" -B -c "import pyflakes" 2>/dev/null; then
    PYTHONPATH="${LINT:-}" "$VPY" -B -m pyflakes ../tcspc_analysis ../run_tcspc_analysis.py > "$OUT/pyflakes.out" 2>&1
    echo "pyflakes: $(wc -l < "$OUT/pyflakes.out") messages"; cut -c1-160 "$OUT/pyflakes.out"
else
    echo "pyflakes: not installed (pip install pyflakes, or LINT=<folder that holds it>)"
fi
if [ ! -d out/ref_1.4.2 ]; then
    "$VPY" -B artefacts.py --target 1.4 --out out/ref_1.4.2 > "$OUT/artefacts_ref.out" 2>&1
    echo "reference outputs of 1.4.2 made: exit=$?"
fi
rm -rf "out/$LABEL" "out/${LABEL}_rules15"
"$VPY" -B artefacts.py --target package --out "out/$LABEL" > "$OUT/artefacts_produce.out" 2>&1
echo "artefacts produce exit=$?"
# With the rules 1.6 changed on purpose put back (_versions.rules_of_1_5), what still differs from 1.4.2
# is listed in that function: the fit exports' two extra preamble lines, one Origin unit, the solvent cases.
"$VPY" -B artefacts.py --target package --rules 1.5 --out "out/${LABEL}_rules15" > "$OUT/artefacts_produce_rules15.out" 2>&1
echo "artefacts (1.5 rules) produce exit=$?"
"$VPY" -B artefacts.py --compare out/ref_1.4.2 "out/${LABEL}_rules15" > "$OUT/artefacts_compare_rules15.out" 2>&1
grep -v "^PNG" "$OUT/artefacts_compare_rules15.out" | tail -30 | cut -c1-200
ls ../*.log 2>/dev/null; find ../tcspc_analysis -name __pycache__
exit $BAD
