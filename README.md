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

최신 버전은 1.5이며, `TCSPC_analysis.bat`과 문서(`SETUP.md`, `ARCHITECTURE.md`)는 패키지를 기준으로 합니다. 1.5에는 실행 파일을 따로 올리지 않았고, Releases의 최신 실행 파일은 1.4.2입니다(계산 결과는 1.5와 같습니다).

## 실행

- **실행 파일**: [Releases](https://github.com/Myungsam/tres_analyzer/releases)에서 받습니다. Python 설치가 필요 없습니다. 1.6부터는 zip 파일이며, 동기화되지 않는 로컬 폴더에 풀어 그 안의 `TCSPC_analysis.exe`를 실행합니다(푸는 방법은 `SETUP.md`). 1.4.2까지는 `TCSPC_analysis.exe` 파일 하나입니다.
- **소스에서**: `TCSPC_analysis.bat`을 실행합니다. 첫 실행 때 가상 환경을 만들고 `requirements.txt`의 패키지를 설치합니다. Python 3.9 이상이 필요합니다.
- 1.4까지의 버전을 직접 실행하려면 `python TCSPC_analysis_1.2ver.py [file.phu]`처럼 파일을 지정합니다. 패키지는 이 폴더에서 `python -B run_tcspc_analysis.py [file.phu]` 또는 `python -B -m tcspc_analysis [file.phu]`로 실행합니다. `-B`는 이 폴더(OneDrive로 동기화될 수 있음)에 `__pycache__`가 생기지 않게 합니다. 런처가 만든 가상 환경의 Python으로 직접 실행할 때 필요한 설정은 `SETUP.md`의 Troubleshooting에 있습니다.

설치와 빌드 방법은 `SETUP.md`, 프로그램 구조는 `ARCHITECTURE.md`에 있습니다.

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
