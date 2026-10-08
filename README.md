# tres_analyzer

PicoQuant PicoHarp 300 TCSPC 측정 파일을 후처리하는 데스크톱 GUI 프로그램입니다.
`.phu`(TRES)와 `.ptu`(FLIM)를 한 창의 두 탭에서 다룹니다.

## 버전

버전마다 소스 파일 하나입니다. 번호가 올라갈수록 기능이 추가됩니다.

| 버전 | 파일 | 추가된 것 |
|---|---|---|
| 1.0 | `TCSPC_analysis_1.0ver.py` | 기본 프로그램: TRES 맵, Crop, Mask, Kinetics, Global analysis, FLIM, CSV/.opju 내보내기 |
| 1.1 | `TCSPC_analysis_1.1ver.py` | Crop 창의 solvent 차감 (solvent `.phu` 불러오기, 비율 조절, 실시간 미리보기) |
| 1.2 | `TCSPC_analysis_1.2ver.py` | Crop 창의 시각별 스펙트럼 (마우스 위치의 시간 bin, 더블 클릭으로 고정) |
| 1.3 | `TCSPC_analysis_1.3ver.py` | Crop 창의 확대/이동 (휠, 오른쪽 드래그), 색·시간축 linear/log 전환, Auto color |
| 1.4 | `TCSPC_analysis_1.4ver.py` | 멈춤 기록(`TCSPC_analysis_freeze.log`), Kinetics 피팅을 별도 스레드로, 새 파일을 열면 분석 창 자동 닫기 |
| 1.4.2 | `TCSPC_analysis_1.4ver.py` (같은 파일) | Kinetics 피팅과 Global analysis(Nelder-Mead)의 종료 기준을 데이터 크기에 맞춤. 피팅이 반복 한도까지 돌며 수 초씩 걸리던 문제 해결 |

최신 버전은 1.4.2(파일은 `TCSPC_analysis_1.4ver.py`)이며, `TCSPC_analysis.bat`과 문서(`SETUP.md`, `ARCHITECTURE.md`)는 이 파일을 기준으로 합니다.

## 실행

- **실행 파일**: [Releases](https://github.com/Myungsam/tres_analyzer/releases)에서 `TCSPC_analysis.exe`를 받아 실행합니다. Python 설치가 필요 없습니다.
- **소스에서**: `TCSPC_analysis.bat`을 실행합니다. 첫 실행 때 가상 환경을 만들고 `requirements.txt`의 패키지를 설치합니다. Python 3.9 이상이 필요합니다.
- 다른 버전을 직접 실행하려면 `python TCSPC_analysis_1.2ver.py [file.phu]`처럼 파일을 지정합니다.

설치와 빌드 방법은 `SETUP.md`, 프로그램 구조는 `ARCHITECTURE.md`에 있습니다.

## 프로그램이 멈췄을 때

1.4부터는 창이 5초 이상 응답하지 않거나 내부 오류가 나면, 그때 실행 중이던 코드 위치를 실행 파일(또는 소스 파일) 옆의 `TCSPC_analysis_freeze.log`에 남깁니다. 측정 값은 기록하지 않고 열려 있던 파일의 이름만 적습니다. 문제를 알릴 때 이 파일을 함께 보내 주세요. 오래 걸리지만 정상인 작업(`.opju` 내보내기에서 Origin이 시작될 때 등)도 같은 방식으로 기록되며, 이런 기록은 오류가 아닙니다.

새 파일을 열면 Crop, Mask, Kinetics, Global analysis 창이 모두 닫힙니다. 남겨야 할 피팅 결과는 새 파일을 열기 전에 내보내세요.
