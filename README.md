# tres_analyzer

PicoQuant PicoHarp 300 TCSPC 측정 파일을 후처리하는 데스크톱 GUI 프로그램입니다.
`.phu`(TRES)와 `.ptu`(FLIM)를 한 창의 두 탭에서 다룹니다.

## 버전

1.4까지는 버전마다 소스 파일 하나입니다. 1.5부터는 `tcspc_analysis/` 패키지 하나를 고쳐 나가고, 버전은 git 태그(`v1.5`, …)로 구분합니다. 이전 버전의 파일은 그대로 남겨 둡니다.

| 버전 | 파일 | 추가된 것 |
|---|---|---|
| 1.0 | `TCSPC_analysis_1.0ver.py` | 기본 프로그램: TRES 맵, Crop, Mask, Kinetics, Global analysis, FLIM, CSV/.opju 내보내기 |
| 1.1 | `TCSPC_analysis_1.1ver.py` | Crop 창의 solvent 차감 (solvent `.phu` 불러오기, 비율 조절, 실시간 미리보기) |
| 1.2 | `TCSPC_analysis_1.2ver.py` | Crop 창의 시각별 스펙트럼 (마우스 위치의 시간 bin, 더블 클릭으로 고정) |
| 1.3 | `TCSPC_analysis_1.3ver.py` | Crop 창의 확대/이동 (휠, 오른쪽 드래그), 색·시간축 linear/log 전환, Auto color |
| 1.4 | `TCSPC_analysis_1.4ver.py` | 멈춤 기록(`TCSPC_analysis_freeze.log`), Kinetics 피팅을 별도 스레드로, 새 파일을 열면 분석 창 자동 닫기 |
| 1.4.2 | `TCSPC_analysis_1.4ver.py` (같은 파일) | Kinetics 피팅과 Global analysis(Nelder-Mead)의 종료 기준을 데이터 크기에 맞춤. 피팅이 반복 한도까지 돌며 수 초씩 걸리던 문제 해결 |
| 1.5 | `tcspc_analysis/` (패키지), `run_tcspc_analysis.py` | 기능 변화 없음. 1.4.2의 코드를 내용 그대로 여러 모듈로 나눔 |
| 1.6 | `tcspc_analysis/` (태그 `v1.6`) | 코드 리뷰에서 나온 결함 수정과 화면 정리. 일부 피팅·내보내기 결과가 1.5와 달라짐(아래 "1.6에서 달라진 것") |

최신 버전은 1.6이며, `TCSPC_analysis.bat`과 문서(`SETUP.md`, `ARCHITECTURE.md`)는 패키지를 기준으로 합니다. 1.5에는 실행 파일을 따로 올리지 않았습니다(계산 결과는 1.4.2와 같습니다).

## 1.6에서 달라진 것

결과가 1.5와 같은 변경:

- 피팅: Kinetics 창에 Stop 버튼. 한계에 걸린 τ, bin보다 짧은 τ, 서로 상쇄하는 진폭, 수렴하지 못한 피팅을 보고서와 상태 줄에 표시. 계산할 수 없는 입력은 0으로 채운 결과 대신 이유를 적은 오류로 알림.
- 파일: 손상된 `.phu`를 열 때 멈추지 않고 오류로 알림. 파일 읽기와 `.opju` 내보내기 동안 진행 표시. 한글로 적은 파일 주석을 읽음.
- 내보내기: 덮어쓰기 확인을 실제로 쓰이는 파일 이름으로 물음. 일부만 쓰인 경우 무엇이 쓰였는지 알림.
- 화면: 좁은 창에서 잘리던 버튼과 설정 줄 정리, 문구 통일, 창 제목에 버전 표시, 색·대비·확대를 바꿀 때의 다시 그리기 시간 약 40 % 단축. Crop 창에서 마우스를 움직일 때 그림 전체를 다시 그리지 않음(약 80 ms → 14 ms).
- 화면 배율: Windows의 배율(125 %, 150 %)을 프로그램이 직접 처리해 글자가 흐릿하지 않고, 창 크기가 배율을 따름. 문제가 있으면 환경 변수 `TCSPC_DPI_AWARE=0`으로 끌 수 있음(`SETUP.md`).
- 지도: 파장 간격이 고르지 않은 파일(첫 곡선을 IRF로 빼지 않은 경우 등)에서도 각 곡선이 제 파장 자리에 그려짐. Global 창의 세 지도는 mask한 대역을 빈 띠로 남기고 제 파장에 그림.
- `.opju` 내보내기에 pandas가 필요 없어짐(Origin에 넘기는 값은 같음).
- 실행 파일: 폴더 형태(zip)로 바뀌어 시작이 6.2초에서 1.7초로 줄었고, 기본 `Data` 폴더와 멈춤 기록은 `문서\TCSPC_analysis`에 둠.

결과가 1.5와 달라지는 변경(같은 파일을 1.5와 1.6으로 처리하면 값이 다를 수 있습니다):

| 무엇 | 1.5 | 1.6 |
|---|---|---|
| IRF 폭(FWHM) | 반높이 아래로 내려간 bin까지 세어 넓게 읽음(예: 308 ps) | 기준선(봉우리에서 떨어진 bin들의 중앙값)을 빼고 반높이 지점을 보간(같은 곡선이 301.7 ps). 지도 제목, 내보내기 머리말, 두 피팅 창의 기본 FWHM이 이 값을 씀 |
| 피팅의 τ 범위 | Global은 FWHM/9.42보다 짧은 τ를 허용하지 않음. Kinetics는 제한 없음(τ가 1e-10 ps까지 갈 수 있었음) | 두 피팅 모두 시간 bin의 1/10 – 피팅 구간의 100배. 하한에 걸린 τ는 IRF 모양의 성분(산란광 등)으로, 진폭 × τ만 의미가 있다는 경고가 붙음 |
| Global 피팅(TRF) | τ가 한계에 닿으면 최소점이 아닌 곳에서 멈출 수 있었음 | 한계를 최적화기에 경계로 알려 줘 Nelder-Mead와 같은 답으로 수렴 |
| Global의 진폭 한계 | 1e10 카운트 고정 | 데이터 최댓값의 100만 배 |
| Global, stretched + IRF 모드 skip + t₀/FWHM 자유 | 피팅이 데이터를 가려 손실을 줄일 수 있었음 | 손실에 넣는 지연 구간을 시작값으로 고정 |
| 기본·Full 피팅 구간 | 끝의 1–2점이 빠질 수 있었음 | 첫 지연과 마지막 지연까지 포함 |
| solvent 차감 뒤의 음수 | 0으로 자름(합과 피팅 입력이 올라감) | 자르지 않음. 지도의 색은 0 미만을 0으로 표시 |
| 본 화면에서 solvent 차감을 끈 뒤 Crop의 Apply | 차감이 다시 켜짐 | 꺼진 채 유지 |
| OFFSET을 바꿀 때의 crop 범위와 mask | nm 숫자가 그대로라 다른 곡선을 가리킴 | 함께 옮겨 같은 곡선을 유지 |
| 지도·steady-state CSV의 숫자 | 6자리 | 8자리 |
| Kinetics·DADS·EADS CSV의 머리말 | 설정 줄이 solvent 사용 시에만, 내보내는 순간의 값으로 적힘 | 피팅을 시작할 때의 설정 줄, 피팅 구간, 고정한 파라미터를 항상 적음(줄 2개 추가) |
| `_TRES`, `_steady`로 끝나는 `.phu`의 내보내기 이름 | 그 부분이 잘림(`sample_TRES.phu` → `sample_TRESmap.csv`) | 유지(`sample_TRES_TRESmap.csv`) |
| Origin steady-state 시트의 Counts 열 단위 | nm | counts |
| Global, stretched + IRF 모드 skip의 RMS(화면, DADS·EADS CSV 머리말) | 손실에 넣지 않은 지연까지 센 개수로 나눔(예: 14.42) | 손실에 넣은 지연만으로 나눔(같은 τ와 스펙트럼에 대해 15.58) |
| Global, stretched 성분 + skip 모드에서 IRF 뒤에 남는 지연이 성분 수 이하일 때 | 말없이 전체 구간으로 피팅 | 피팅하지 않고 이유를 알림 |
| 파장을 내림차순으로 측정한 파일 | 측정한 순서대로 | 파장 오름차순으로 보관: 지도·steady-state CSV와 Origin의 열·행 순서가 바뀜 |
| 곡선마다 시간 해상도나 bin 수가 다른 `.phu` | 첫 곡선의 시간축으로 열림 | 열지 않고 이유를 알림 |
| Crop의 Apply 뒤 시간 bin 수 | 본 화면 입력 칸에서 포커스가 나갈 때 한 줄 줄어들 수 있었음(320 → 319) | 그대로 |

## 실행

- **실행 파일**: [Releases](https://github.com/Myungsam/tres_analyzer/releases)에서 받습니다. Python 설치가 필요 없습니다. 1.6부터는 zip 파일이며, 동기화되지 않는 로컬 폴더에 풀어 그 안의 `TCSPC_analysis.exe`를 실행합니다(푸는 방법은 `SETUP.md`). 1.4.2까지는 `TCSPC_analysis.exe` 파일 하나입니다.
- **소스에서**: `TCSPC_analysis.bat`을 실행합니다. 첫 실행 때 가상 환경을 만들고 시험에 쓴 버전의 패키지(`requirements-lock.txt`)를 설치합니다. Python 3.9 이상이 필요합니다.
- 1.4까지의 버전을 직접 실행하려면 `python TCSPC_analysis_1.2ver.py [file.phu]`처럼 파일을 지정합니다. 패키지는 이 폴더에서 `python -B run_tcspc_analysis.py [file.phu]` 또는 `python -B -m tcspc_analysis [file.phu]`로 실행합니다. `-B`는 이 폴더(OneDrive로 동기화될 수 있음)에 `__pycache__`가 생기지 않게 합니다. 런처가 만든 가상 환경의 Python으로 직접 실행할 때 필요한 설정은 `SETUP.md`의 Troubleshooting에 있습니다.

설치와 빌드 방법은 `SETUP.md`, 프로그램 구조는 `ARCHITECTURE.md`에 있습니다. 회귀 시험과 돌리는 방법은 `tests/README.md`에 있습니다(측정 파일 두 개가 따로 필요합니다).

## PTU · FLIM 탭

`.ptu`(PicoHarp 300 T3 기록)에서 강도 이미지, 수명 맵, 픽셀별 감쇠 히스토그램을 만듭니다. 이 탭은 1.0에서 옮겨 온 그대로이며 다음을 전제로 합니다.

- 기록 안의 마커 1을 픽셀 클럭, 마커 2를 라인 끝으로 읽습니다. 스캐너가 다른 마커를 내면 이미지가 맞지 않습니다.
- 이미지 크기의 기본값은 X 99, Y 100, 시간 bin 4,096개입니다. 값을 고친 뒤에는 **Apply size**를 눌러야 다음 Process에 반영됩니다.
- 첫 프레임(처음 Y줄)만 사용합니다.
- 강도 이미지는 0–2 카운트 범위로 표시되고, 수명 맵의 값은 bin 단위입니다.
- 이미지 위로 마우스를 옮기면 그 픽셀의 감쇠 히스토그램이 보입니다.
- GPU 사용은 선택이며 없어도 CPU로 동작합니다(`SETUP.md`).

FLIM 탭의 정비는 별도 계획으로 남아 있습니다.

## 프로그램이 멈췄을 때

1.4부터는 창이 5초 이상 응답하지 않거나 내부 오류가 나면, 그때 실행 중이던 코드 위치를 `TCSPC_analysis_freeze.log`에 남깁니다. 이 파일은 실행 파일(1.6부터)로 쓰면 `문서\TCSPC_analysis\`에, 소스에서 실행하면 `run_tcspc_analysis.py` 옆에 있습니다(1.4.2까지의 실행 파일은 exe 옆). 측정 값은 기록하지 않고 열려 있던 파일의 이름만 적습니다. 문제를 알릴 때 이 파일을 함께 보내 주세요. 오래 걸리지만 정상인 작업(`.opju` 내보내기에서 Origin이 시작될 때 등)도 같은 방식으로 기록되며, 이런 기록은 오류가 아닙니다.

새 파일을 열면 Crop, Mask, Kinetics, Global analysis 창이 모두 닫힙니다. 남겨야 할 피팅 결과는 새 파일을 열기 전에 내보내세요.
