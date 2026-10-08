# 회귀 시험

프로그램을 고친 뒤 "전과 같아야 하는 것이 같은지, 고친 것이 고쳐졌는지"를 확인하는 스크립트들입니다. 시험 프레임워크 없이 각 파일이 스스로 `PASS` / `FAIL` 줄을 출력하고, 실패가 있으면 종료 코드 1로 끝납니다.

## 준비

1. **실행 환경.** 프로그램과 같은 가상 환경을 씁니다(`TCSPC_analysis.bat`을 한 번 실행하면 `%LOCALAPPDATA%\TCSPC_analysis\venv`에 만들어집니다).
2. **시료 측정 파일 두 개.** 측정 데이터는 저장소에 없습니다. `samples.example.json`을 `samples.json`으로 복사하고 두 `.phu` 파일의 경로를 적습니다(상대 경로는 프로젝트 폴더 기준). `samples.json`은 git에 올라가지 않습니다. 시험의 기대값은 다음과 같은 두 파일에 맞춰져 있습니다.

   | | 곡선 | 파장 | 시간 bin |
   |---|---|---|---|
   | A | 64개(첫 곡선이 IRF) | 435–750 nm, 5 nm 간격 | 4 ps |
   | B | 42개(첫 곡선이 IRF) | 첫 곡선 535 nm, 나머지 550–750 nm, 5 nm 간격 | 4 ps |

   다른 파일로 돌리면 곡선 수나 수치를 직접 적은 검사는 실패합니다.

## 실행

Git Bash에서:

```bash
bash tests/run_all.sh mylabel
```

모든 시험 파일을 차례로 돌리고 묶음별 통과·실패 수를 출력합니다. 출력 파일은 `tests/out/suite_mylabel/`에 남습니다(`tests/out/`은 git에 올라가지 않습니다). 화면에 창이 여러 번 뜨고 닫히며 10–20분 걸립니다. 도는 동안 마우스와 키보드로 그 창들을 건드리지 않습니다.

시험 하나만 돌릴 때는 Tcl/Tk 위치를 알려 줘야 합니다(런처가 하는 일과 같습니다).

```bash
BASE=$(python -c "import sys;print(sys.base_prefix.replace(chr(92),'/'))")
export TCL_LIBRARY="$BASE/tcl/tcl8.6" TK_LIBRARY="$BASE/tcl/tk8.6" PYTHONIOENCODING=utf-8
"$LOCALAPPDATA/TCSPC_analysis/venv/Scripts/python.exe" -B tests/test_g7.py          # 파일 전체
"$LOCALAPPDATA/TCSPC_analysis/venv/Scripts/python.exe" -B tests/test_g7.py A-13     # 한 항목만
```

## 무엇이 들어 있나

| 파일 | 확인하는 것 |
|---|---|
| `test_numeric.py`, `test_gui.py`, `test_slice.py`, `test_zoom.py` | 1.1–1.3에서 넣은 기능(solvent 차감, 시각별 스펙트럼, Crop 창의 확대)이 그대로인지 |
| `test_v14.py`, `test_v14_native.py`, `test_fatol.py` | 1.4의 멈춤 기록·스레드 피팅, 1.4.2의 종료 기준 |
| `test_facade.py`, `test_paths.py` | 패키지 구조, 프로그램이 쓰는 폴더 |
| `test_g1.py` – `test_g12.py`, `test_dpi.py` | 1.6에서 고친 리뷰 항목마다 한 구역(`section("A-13")`처럼 항목 ID로 고름). `test_g12.py`는 최종 리뷰의 지적 |
| `check_doc.py`, `sync_doc_ranges.py` | `ARCHITECTURE.md`가 코드와 맞는지 / 모듈을 고친 뒤 문서의 줄 수를 맞추는 도구(직접 실행. `run_all.sh`는 돌리지 않음) |
| `artefacts.py` | 여러 설정에서의 계산 배열, 내보낸 CSV, Origin에 넘기는 값, 창의 위젯과 그림을 한 폴더에 모으고 두 폴더를 비교 |
| `launcher_check.ps1`, `launcher_step.ps1`, `smoke_entry.py` | `TCSPC_analysis.bat`을 새 환경을 포함한 네 가지 환경에서 실제로 실행(PowerShell에서 실행) |
| `frozen_selftest4.py`, `start_time.py` | 빌드한 exe의 자가 점검, 시작 시간 |
| `results_probe.py`, `results_probe_a1.py` | 1.6에서 결과가 달라진 항목의 전후 수치 |
| `_harness.py`, `_versions.py` | 공통 도구: 창 만들기, 메시지 상자 기록, 버전 불러오기 |
| `baselines/TCSPC_analysis_1_4_1.py` | 1.4.2의 수정 전 소스(종료 기준 비교용) |

## 이전 버전과 비교하는 방법

`_versions.py`가 버전을 불러옵니다. 1.4까지는 `TCSPC_analysis_<버전>ver.py` 파일을, 그 뒤는 `tcspc_analysis/` 패키지를 한 이름공간처럼 다룹니다.

1.6은 일부 결과를 일부러 바꿨습니다(피팅 한계, IRF 폭 재는 법 등, `README.md`의 "1.6에서 달라진 것"). 이전 버전과 값을 비교하는 시험은 `_versions.rules_of_1_5(NEW)`로 그 규칙들을 1.5의 것으로 되돌린 뒤 비교합니다. 그렇게 해서 "일부러 바꾼 것 말고는 달라지지 않았다"를 확인합니다. `run_all.sh`의 마지막 단계도 같은 방식으로 1.4.2의 산출물(`tests/out/ref_1.4.2/`, 처음 실행 때 `TCSPC_analysis_1.4ver.py`에서 만듦)과 비교하며, 남는 차이는 `rules_of_1_5`의 설명에 적힌 것(피팅 CSV 머리말의 두 줄, Origin의 단위 한 곳, solvent를 쓰는 경우)뿐이어야 합니다.

## 이 PC에서 확인할 수 없는 것

- 실제 Origin에서의 `.opju` 쓰기: 기록만 하는 대역 모듈로 호출과 넘기는 값을 확인합니다.
- 실제 `.ptu`(FLIM): 합성 레코드로만 확인합니다.
- 실제 125 % / 150 % 화면: `test_dpi.py`가 Tk에 그 해상도를 알려 주는 방식으로 흉내 냅니다.
