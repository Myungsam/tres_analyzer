# tres_analyzer

**한국어** | [English](README.en.md)

PicoQuant PicoHarp 300 TCSPC 측정 파일을 후처리하는 Windows용 GUI 프로그램입니다. `.phu`(TRES: 파장별 시간 분해 형광)와 `.ptu`(FLIM)를 한 창의 두 탭에서 다룹니다.

- TRES 지도(파장 × 시간)와 steady-state 스펙트럼 보기, 배경 빼기, 파장 보정
- 파장·시간 범위 자르기(Crop), solvent 측정 차감, 파장 대역 가리기(Mask)
- 한 파장의 감쇠 피팅(Kinetics), 지도 전체의 global analysis(DADS·EADS)
- CSV와 Origin `.opju`로 내보내기

![본 화면](docs/images/00_overview.png)

최신 버전은 **1.6**입니다. 버전마다 달라진 것은 [아래의 버전 표](#버전)와 [CHANGELOG.md](CHANGELOG.md)에 있습니다.

## 목차

- [설치](#설치)
- [사용법: 시료와 solvent 측정으로 따라 하기](#사용법-시료와-solvent-측정으로-따라-하기)
- [마우스·키 조작](#마우스키-조작)
- [자주 묻는 질문](#자주-묻는-질문)
- [용어](#용어)
- [프로그램이 멈췄을 때](#프로그램이-멈췄을-때)
- [PTU · FLIM 탭](#ptu--flim-탭)
- [버전](#버전)

## 설치

두 가지 방법이 있습니다. Python을 모르면 **실행 파일**을 쓰세요.

### 방법 1. 실행 파일 (Python 필요 없음)

1. [Releases](https://github.com/Myungsam/tres_analyzer/releases) 페이지에서 최신 버전의 `TCSPC_analysis_1.6.zip`을 받습니다.
2. 풀기 전에 zip 파일을 오른쪽 클릭 → **속성** → 아래쪽의 **차단 해제**를 체크하고 확인을 누릅니다. 이렇게 하지 않으면 Windows가 풀린 파일마다 "인터넷에서 받은 파일" 표시를 붙여 첫 실행 때 하나하나 검사합니다.
3. zip 파일을 오른쪽 클릭해 **모두 압축 풀기**로 풉니다. 풀 곳은 **OneDrive 등으로 동기화되지 않는 로컬 폴더**로 하세요(예: `C:\Programs`). zip 안에 `TCSPC_analysis` 폴더가 들어 있어, 이 예라면 `C:\Programs\TCSPC_analysis\TCSPC_analysis.exe`가 생깁니다. 동기화되는 폴더에 두면 파일이 많아 동기화가 느려지고, 실행할 때 파일을 내려받느라 시작이 늦어질 수 있습니다.
4. 그 폴더 안의 `TCSPC_analysis.exe`를 실행합니다. 폴더 안의 다른 파일(`_internal` 폴더 등)은 exe가 쓰므로 옮기거나 지우지 마세요. 바탕 화면에 아이콘을 두려면 exe를 오른쪽 클릭 → **보내기** → **바탕 화면에 바로 가기 만들기**.
5. 처음 실행할 때 "Windows의 PC 보호" 창이 뜨면 **추가 정보**를 누른 뒤 **실행**을 누릅니다(서명하지 않은 프로그램이라 뜨는 경고입니다).
6. 실행 파일은 내보낸 파일의 기본 폴더(`Data`)와 멈춤 기록을 `문서\TCSPC_analysis` 아래에 만듭니다.

새 버전으로 바꿀 때는 이전 폴더를 지우고 새 zip을 같은 방법으로 풀면 됩니다. `문서\TCSPC_analysis`의 파일은 그대로 남습니다.

### 방법 2. 소스에서 실행 (Python 3.9 이상)

1. [python.org](https://www.python.org/downloads/)에서 Python 3.9 이상을 설치합니다. 설치 첫 화면에서 **Add python.exe to PATH**를 체크하세요.
2. 이 저장소를 받습니다. 저장소 첫 화면의 **Code** → **Download ZIP**으로 받아 풀거나, `git clone https://github.com/Myungsam/tres_analyzer`로 받습니다.
3. 받은 폴더의 `TCSPC_analysis.bat`을 더블 클릭합니다. 첫 실행 때는 인터넷이 연결되어 있어야 하며, 다음을 자동으로 합니다(몇 분 걸립니다).
   - 설치된 Python을 찾음
   - `%LOCALAPPDATA%\TCSPC_analysis\venv`에 이 프로그램 전용 가상 환경을 만듦
   - 시험에 쓴 버전의 패키지(`requirements-lock.txt`: numpy, scipy, matplotlib)와 `.opju` 내보내기용 패키지를 설치
   - 프로그램을 띄움
4. 두 번째부터는 바로 시작합니다. 바탕 화면 아이콘이 필요하면 `TCSPC_analysis.bat`을 오른쪽 클릭 → **보내기** → **바탕 화면에 바로 가기 만들기**로 만드세요(다른 PC에서 복사한 바로 가기는 그 PC의 폴더를 가리킵니다).

명령 줄에서는 이 폴더에서 `python -B run_tcspc_analysis.py [파일.phu]`로 실행합니다. `-B`는 이 폴더에 `__pycache__`가 생기지 않게 합니다. 가상 환경 문제, 패키지 목록, 실행 파일 빌드 방법은 [SETUP.md](SETUP.md)에 있습니다.

## 사용법: 시료와 solvent 측정으로 따라 하기

아래 그림은 405 nm로 여기한 시료 용액의 측정(`sample_ex405nm.phu`)과 같은 조건으로 잰 용매만의 측정(`solvent_ex405nm.phu`)으로 만들었습니다. 시료 측정에는 시료의 형광과 함께 용매의 레이저 산란광(400 nm 부근)과 라만 신호(455 nm 부근)가 들어 있고, solvent 측정으로 이것을 빼는 것이 이 예의 중심입니다.

> 그림에 나오는 값(BIN 32 ps, crop 범위, solvent 배율 0.2, mask 392–410 nm, 성분 수)은 **사용법을 보이기 위한 예시**입니다. 알맞은 값은 측정마다 다르니 자신의 데이터를 보고 정하세요.

순서는 다음과 같습니다.

1. [파일 열기와 본 화면 설정](#1-파일-열기와-본-화면-설정)
2. [Crop: 범위 자르기](#2-crop-범위-자르기)
3. [Crop: solvent 빼기](#3-crop-solvent-빼기)
4. [Mask: 남은 산란광 가리기](#4-mask-남은-산란광-가리기)
5. [Kinetics: 한 파장의 감쇠 피팅](#5-kinetics-한-파장의-감쇠-피팅)
6. [Global analysis: 지도 전체 피팅](#6-global-analysis-지도-전체-피팅)
7. [내보내기](#7-내보내기)

### 1. 파일 열기와 본 화면 설정

![본 화면](docs/images/01_main.png)

1. **Open file...**을 눌러 시료의 `.phu`를 엽니다. FILE 칸에 경로가, Subtract solvent 줄의 오른쪽 끝에 측정 정보(장비, 곡선 수, 파일에 적힌 그대로의 파장 범위, bin 수와 폭, 곡선당 측정 시간)가 나옵니다. 이 파장은 OFFSET을 적용하기 전의 값이라 지도의 파장축과 다를 수 있습니다.
2. **BIN**: 시간 bin 몇 개를 하나로 합칠지 고릅니다. 목록의 값은 합친 뒤의 bin 폭입니다(4 ps 해상도 파일이면 4, 8, 16 ps …). 예에서는 잡음을 줄이려고 32 ps로 했습니다. **TIME END**는 지도에 보일 마지막 시각(ps)입니다.
3. **First curve is IRF**: 파일의 첫 곡선이 IRF(장비 응답) 측정이면 켭니다(기본값). 켜면 그 곡선은 지도에서 빠지고, IRF의 봉우리 위치와 폭(FWHM)을 재는 데만 쓰입니다. **t0 at IRF peak**를 켜면 시간축의 0이 IRF 봉우리로 옮겨 갑니다. 예에서는 켰습니다.
4. **Subtract background**: 곡선마다 **BG WINDOW**(ps) 구간의 평균을 배경으로 보고 뺍니다. 기본 구간은 기록의 처음 100 ps이고, 같은 줄 오른쪽의 주황색 글자에 실제로 쓰인 구간과 평균값이 나옵니다. 레이저 펄스가 오기 전, 신호가 없는 구간을 고르세요.
5. **OFFSET**: 파일에 적힌 파장을 몇 nm 옮길지(분광기 보정) 정하고 **Apply offset**을 누릅니다. 기본값은 −50 nm이며, 값은 항상 파일의 파장에서부터 셉니다(두 번 눌러도 두 번 옮겨지지 않음).
6. 가운데가 **TRES 지도**(가로 파장, 세로 시간, 색 = 카운트)입니다. 마우스를 올리면 그 자리의 감쇠(왼쪽 Decay)와 스펙트럼(아래 Spectrum)이 나오고, 클릭하면 그 자리에 고정됩니다(다시 클릭하면 풀림). 왼쪽 아래는 모든 시각을 더한 steady-state 스펙트럼입니다. 지도에서 드래그하면 확대, 오른쪽 클릭하면 원래대로 돌아갑니다.

COLORMAP과 **Log color**는 색만 바꿉니다. 오른쪽 색 막대를 위아래로 드래그하면 대비가 바뀌고, **Auto contrast**나 색 막대 오른쪽 클릭으로 되돌립니다.

### 2. Crop: 범위 자르기

PREP의 **Crop...**을 누르면 Crop 창이 열립니다. 이 창은 기록 전체를 보여 주고, 남길 범위는 파란 상자로 표시합니다. 바깥은 어둡게 보입니다.

![Crop 창: 범위](docs/images/02_crop_box.png)

1. **λ … to … nm**와 **t … to … ps**에 남길 범위를 적습니다. 시간은 **기록 시작부터의 ps**입니다(t0 at IRF peak와 상관없음). 지도에서 두 모서리를 차례로 클릭해도 상자가 정해지고, 첫 클릭 뒤 Esc를 누르면 취소됩니다. **Full λ**, **Full t**는 전체 범위로 되돌립니다.
2. 지도는 휠로 확대(Ctrl: 시간만, Shift: 파장만), 오른쪽 드래그로 이동합니다. VIEW 줄의 **Log color**, **Auto color**, **Log time**, **Fit view**는 보는 방식만 바꾸며 결과에는 영향이 없습니다.

예에서는 형광이 없는 300–380 nm와 신호가 끝난 50 ns 뒤를 빼고 380–700 nm, 0–50,000 ps를 남겼습니다.

> **시간 범위의 시작을 자를 때 주의**: 배경 구간(BG WINDOW)은 남긴 범위 안에 있어야 합니다. 범위 밖이면 프로그램은 남긴 범위의 가장자리 bin(구간이 범위 앞에 있으면 첫 bin)을 배경으로 씁니다. 그 자리에 신호(앞 펄스의 꼬리 등)가 있으면 배경을 너무 많이 빼게 됩니다. 이 예에서는 펄스 전 약 12 ns를 남겨 기본 배경 구간(기록의 처음 100 ps)이 그대로 쓰이게 했습니다. Apply 뒤에는 본 화면의 주황색 글자로 실제 배경 구간을 확인하세요.

이 그림의 아래 칸에는 아직 시료(sample)의 steady-state만 있고, 400 nm의 큰 봉우리가 레이저 산란광입니다.

### 3. Crop: solvent 빼기

같은 Crop 창에서 용매만 잰 측정을 불러와 뺍니다.

![Crop 창: solvent 빼기](docs/images/03_crop_solvent.png)

1. **Load solvent...**로 solvent의 `.phu`를 엽니다. 시료와 같은 파장·시간 격자로 잰 파일이어야 합니다. bin 단위로 빼기 때문에 격자(곡선 수, 파장, 시간 해상도, bin 수)가 다르면 이유를 적은 오류가 나고, 측정 시간만 다르면 경고가 뜹니다. 불러온 solvent의 배율은 항상 1에서 시작합니다. 파일 이름 왼쪽의 **Clear**는 불러온 solvent를 버립니다.
2. **SOLVENT SCALE**: solvent에 곱할 배율입니다. 막대는 0–2이고, 칸에는 그보다 큰 값도 적을 수 있습니다. 산란광과 라만 봉우리가 사라질 때까지 조절합니다. 예에서는 0.2입니다.
3. 아래 칸에서 결과를 미리 봅니다. 흐린 선은 steady-state(모든 시각의 합)의 **sample**, **s x solvent**(배율을 곱한 solvent), **subtracted**(뺀 결과)이고, 굵은 선은 한 시각의 같은 세 가지입니다. 지도 위에서 마우스를 움직이면 굵은 선의 시각이 따라오고, 더블 클릭하면 그 시각에 고정됩니다(그림은 산란광이 가장 센 시각에 고정한 것). 창 아래에는 0보다 작아진 bin의 비율이 나옵니다. 뺀 결과의 음수는 자르지 않고 그대로 둡니다.
4. **Apply**를 누르면 범위와 solvent 빼기가 본 화면에 적용됩니다. **Reset (full)**은 범위를 전체로 되돌려 곧바로 본 화면에 적용합니다. solvent는 건드리지 않습니다. **Close**로 창을 닫습니다.

Apply 뒤의 본 화면입니다.

![solvent를 뺀 본 화면](docs/images/04_main_solvent.png)

1. **Subtract solvent**가 켜지고, 옆에 배율과 solvent 파일 이름, 0보다 작은 bin의 비율이 나옵니다. 이 체크를 끄면 빼기 전의 데이터로 돌아가 비교할 수 있습니다(solvent는 기억함). 비율이 30 %로 큰 것은 신호가 없는 펄스 전 구간의 잡음이 0 주위에 흩어져 있기 때문입니다.
2. 배경 구간이 남긴 범위 안에 있는지 확인합니다. 주황색 글자의 구간이 BG WINDOW에 적은 구간과 같으면 됩니다.
3. 지도와 steady-state 스펙트럼에서 455 nm 부근의 라만 봉우리가 거의 사라졌습니다. 400 nm 부근에는 산란광이 다 빠지지 않은 자국(steady-state의 위아래로 튀는 부분)이 남아, 다음 단계에서 가립니다.

### 4. Mask: 남은 산란광 가리기

PREP의 **Mask λ...**를 누르면 Mask 창이 열립니다. 가린 파장은 지도, 합한 스펙트럼, 피팅에서 빠지고(값이 비게 됨) 축에는 빈 띠로 남습니다.

![Mask 창](docs/images/05_mask.png)

1. **From**, **To**에 가릴 파장(nm)을 적고 **Add region**을 누릅니다. 지도에서 시작 파장과 끝 파장을 차례로 클릭해도 칸이 채워집니다.
2. **Masked regions** 목록에 가린 대역이 쌓입니다. 고른 대역은 **Remove selected**, 전부는 **Clear all**로 지웁니다.
3. 가린 대역은 지도에 빗금으로 보입니다.

예에서는 392–410 nm를 가렸습니다.

### 5. Kinetics: 한 파장의 감쇠 피팅

ANALYSIS의 **Kinetics...**를 누르면 한 파장의 감쇠를 IRF와 합성곱한 지수 함수의 합으로 피팅하는 창이 열립니다.

![Kinetics 창](docs/images/06_kinetics.png)

1. **λ (nm)**: 피팅할 파장입니다. **± half-width (nm)**를 0보다 크게 하면 그 범위의 곡선을 평균합니다. **Use cursor λ**는 본 화면 지도에 고정한 커서의 파장을 가져옵니다.
2. **Components**: 성분 수(1–4)입니다. 표에서 성분마다 τ 시작값(τ_init), 고정(fix), stretched 지수 사용(stretch)과 그 β를 정합니다. **Include τ = ∞ offset**은 상수 성분을 더합니다.
3. **IRF (Gaussian)**: IRF를 가우시안으로 보고 쓰는 t₀와 FWHM입니다. 기본값은 IRF 곡선에서 잰 값이고 "fixed"가 켜져 있습니다. 끄면 함께 피팅합니다. **Stretched-IRF mode**는 stretch를 켠 성분에만 쓰입니다. numerical은 IRF와 수치로 합성곱하고, skip은 합성곱하지 않는 대신 IRF 아래의 지연을 피팅에서 뺍니다.
4. **Fit range (ps)**: 피팅에 쓸 시간 구간입니다. **Full**은 전체 구간입니다.
5. **Run fit**으로 피팅을 시작합니다. 피팅은 따로 돌기 때문에 그동안 창을 써도 되고, **Stop**으로 멈출 수 있습니다. **Reset**은 설정을 기본값으로 되돌립니다. **Time scale**은 그래프의 시간축(Log/Linear)입니다.
6. **Export results**: 데이터, 피팅, 잔차를 내보냅니다. 형식(CSV/.opju)은 본 화면의 체크로 정합니다([7. 내보내기](#7-내보내기)).
7. 결과 보고서: 수렴 여부, RMS, 성분별 τ와 진폭(A)이 나옵니다. τ가 허용 범위의 끝에 걸렸거나 진폭끼리 상쇄하는 등 주의할 점이 있으면 여기와 상태 줄에 적힙니다.

예에서는 520 nm를 성분 3개로 피팅했습니다.

### 6. Global analysis: 지도 전체 피팅

ANALYSIS의 **Global analysis...**를 누르면 모든 파장을 공통의 τ로 한꺼번에 피팅하는 창이 열립니다.

![Global analysis 창](docs/images/07_global.png)

1. **Components**: 성분 수(1–5, 기본 3)와 성분별 τ 시작값입니다. 표는 Kinetics 창과 같습니다. 그 아래의 **Optimizer**는 TRF (fast)와 Nelder-Mead 중에서 고르며, IRF와 Fit range는 Kinetics 창과 같습니다. Fit range 아래에는 피팅에 쓰일 시간 점의 수가 나옵니다.
2. **Run fit** / **Stop** / **Reset**: Kinetics 창과 같습니다.
3. 결과 보고서: RMS, 반복 수, 성분별 τ.
4. **data**, **global fit**, **residual** 지도: 데이터, 피팅으로 다시 만든 지도, 그 차이입니다. 가린 대역은 빈 띠로 남습니다.
5. **DADS**(성분별 진폭 스펙트럼)와 **EADS**(순차 모델의 성분 스펙트럼), 오른쪽은 각각을 정규화한 그림(norm.)입니다.
6. **λ (nm)**와 **Use cursor λ**: 아래 감쇠 그림의 파장을 고릅니다. 위의 세 지도 가운데 하나를 클릭해도 그 파장으로 바뀝니다. 옆의 Time scale은 그 그림의 시간축(Log/Linear)입니다.
7. 고른 파장의 데이터와 피팅 곡선입니다.

**Export results**는 DADS와 EADS를 내보냅니다.

### 7. 내보내기

![내보내기 버튼](docs/images/08_export.png)

1. **Export data...**는 TRES 지도와 steady-state 스펙트럼을 함께 내보냅니다. 옆의 **CSV**, **.opju** 체크로 형식을 고르며, 이 체크는 Kinetics와 Global analysis 창의 Export results에도 그대로 쓰입니다. 지도는 화면의 확대와 상관없이 처리한 전체 범위가 나갑니다.
2. **Save map image...**는 지금 화면에 보이는(확대한 상태 그대로의) 지도를 PNG, PDF 또는 SVG로 저장합니다.

CSV를 고르면 이름을 정하는 창이 뜹니다. 여기에 적은 이름(예: `sample_ex405nm`)에 뒤붙이를 붙여 다음 파일이 만들어집니다. 기본 폴더는 소스에서 실행하면 프로그램 폴더의 `Data`, 실행 파일이면 `문서\TCSPC_analysis\Data`입니다.

| 파일 | 어디서 | 내용 |
|---|---|---|
| `이름_TRESmap.csv` | 본 화면 Export data... | 첫 열이 시간(ps), 첫 줄이 파장(nm)인 지도. 값은 bin당 카운트(Subtract background와 Subtract solvent가 켜져 있으면 뺀 값) |
| `이름_steadystate.csv` | 본 화면 Export data... | `wavelength_nm, counts_sum, counts_norm`: 모든 시각의 합과 그 최댓값으로 나눈 값 |
| `이름_kinetics.csv` | Kinetics의 Export results | `delay_ps, data, fit, residual` |
| `이름_DADS.csv`, `이름_EADS.csv` | Global analysis의 Export results | 첫 열이 파장, 그다음 열이 성분별 스펙트럼(열 이름에 τ) |

모든 CSV는 `#`으로 시작하는 머리말 줄에 원본 파일의 전체 경로와 설정(BIN, 배경 구간, OFFSET, crop, mask, solvent와 배율)을 적습니다. 지도와 steady-state 파일에는 장비와 일련번호도, 피팅 결과 파일에는 피팅 결과와 피팅 구간, 고정한 파라미터도 적힙니다. 머리말을 건너뛰고 읽으려면 예를 들어 `pandas.read_csv(경로, comment="#")`를 쓰세요.

**.opju**를 고르면 Origin 프로젝트를 고르는 창이 뜹니다. 있는 `.opju`를 고르면 거기에 더하고, 새 이름을 적으면 새로 만듭니다. 데이터는 프로젝트의 `Book1`에 `이름_TRESmap`, `이름_steadystate`(피팅 결과는 `이름_kinetics`, `이름_DADS`, `이름_EADS`) 시트로 들어갑니다. 이 기능은 **OriginLab Origin이 설치된 PC**에서만 동작합니다. Origin이 없으면 CSV로 내보내세요.

## 마우스·키 조작

| 창 | 조작 | 동작 |
|---|---|---|
| 본 화면 지도 | 마우스 올리기 | 그 자리의 감쇠와 스펙트럼 표시 |
| | 클릭 | 커서 고정 / 풀기 |
| | 드래그 | 그 범위로 확대 |
| | 오른쪽 클릭 | 확대 해제 (Reset zoom과 같음) |
| 본 화면 색 막대 | 위아래 드래그 | 그 범위로 대비 조절 |
| | 오른쪽 클릭 | 자동 대비 (Auto contrast와 같음) |
| 본 화면 입력 칸 | Enter | TIME END, BG WINDOW, OFFSET 값 적용 (TIME END와 BG WINDOW는 다른 곳을 클릭해도 적용) |
| Crop 지도 | 클릭 두 번 | 남길 상자의 두 모서리 |
| | Esc | 첫 모서리 취소 |
| | 더블 클릭 | 아래 칸의 한 시각 스펙트럼을 고정 / 풀기 |
| | 휠 | 마우스 위치를 중심으로 확대·축소 (Ctrl: 시간만, Shift: 파장만) |
| | 오른쪽 드래그 | 보는 범위 이동 |
| Mask 지도 | 클릭 | 처음엔 From, 다음엔 To 파장 |
| Global analysis 지도 | 클릭 | 아래 감쇠 그림의 파장 선택 |
| Kinetics, Global analysis 그림 | 위쪽 도구 막대 | 확대, 이동, 처음 보기로, 그림 저장 (matplotlib 도구) |

## 자주 묻는 질문

**피팅 보고서에 τ가 하한에 걸렸다는 경고가 나옵니다.**
1.6의 두 피팅은 τ를 시간 bin의 1/10부터 피팅 구간의 100배까지만 허용합니다. 하한에 걸린 성분은 IRF보다 훨씬 빠른, IRF 모양의 성분(산란광 등)이라는 뜻이고, 그 성분은 진폭 × τ만 의미가 있습니다. 산란광이 원인이면 solvent를 빼거나 그 파장을 Mask로 가리고 다시 피팅하세요.

**solvent 배율은 어떻게 정하나요?**
Crop 창 아래 칸에서 산란광(여기 파장 부근)과 라만 봉우리가 subtracted 선에서 평평해질 때까지 SOLVENT SCALE을 조절합니다. 값은 1과 크게 다를 수 있습니다(이 예에서는 0.2). 측정 시간이나 레이저 세기가 다르면 그 비율만큼 달라지고, 시료 용액이 빛을 흡수하면 용매의 산란광과 라만 신호도 약해지기 때문입니다. 너무 크게 빼면 그 파장이 0 아래로 내려가고, 창 아래의 "bins below 0" 비율이 커집니다. 다만 그 비율에는 신호가 없는 곳의 잡음도 들어가므로 0이 될 필요는 없습니다.

**solvent 파일을 불러오면 "Solvent does not match the sample" 오류가 납니다.**
solvent는 bin 단위로 빼기 때문에 곡선 수, 파장, 시간 해상도, bin 수가 시료와 같아야 합니다. 같은 설정으로 다시 측정한 파일을 쓰세요.

**파일이 열리지 않거나 오래 걸립니다.**
손상된 `.phu`나 곡선마다 시간 해상도·bin 수가 다른 `.phu`는 이유를 적은 오류로 알리고 열지 않습니다. OneDrive에서 "온라인 전용"인 파일은 Windows가 먼저 내려받아야 해서, 그동안 "Reading …"이 표시됩니다.

**새 파일을 열었더니 Crop, Mask, Kinetics, Global analysis 창이 닫혔습니다.**
이 창들은 연 파일의 데이터에 묶여 있어 새 파일을 열면 닫힙니다. 남겨야 할 피팅 결과는 새 파일을 열기 전에 내보내세요. solvent도 새 파일에서는 다시 불러와야 합니다.

**글자가 흐리거나 창이 이상한 크기로 보입니다.**
1.6은 Windows 화면 배율(125 %, 150 %)을 직접 처리합니다. 문제가 있으면 환경 변수 `TCSPC_DPI_AWARE=0`을 설정하고 실행하세요. 설정 방법은 [SETUP.md](SETUP.md)의 Troubleshooting에 있습니다.

**`.opju` 내보내기가 실패합니다.**
Origin이 설치되어 있어야 합니다. Origin이 시작되는 데 시간이 걸리는 동안 창이 잠시 응답하지 않을 수 있습니다. Origin이 없는 PC에서는 CSV로 내보내세요.

## 용어

| 용어 | 뜻 |
|---|---|
| TCSPC | 시간 상관 단일 광자 계수(time-correlated single photon counting). 광자가 레이저 펄스 뒤 언제 왔는지를 세어 감쇠 곡선을 만드는 측정법 |
| TRES | 시간 분해 방출 스펙트럼(time-resolved emission spectra). 파장마다 잰 감쇠 곡선을 모은 파장 × 시간 지도 |
| bin | 시간축의 한 칸. PicoHarp 300의 기본 해상도는 4 ps이고, BIN으로 여러 칸을 합칠 수 있음 |
| IRF | 장비 응답 함수(instrument response function). 무한히 짧은 빛에 장비가 내는 신호의 모양 |
| FWHM | 반치폭(full width at half maximum). 여기서는 IRF의 폭 |
| t₀ | 시간의 기준점. t0 at IRF peak를 켜면 IRF 봉우리가 0 |
| steady-state 스펙트럼 | 모든 시각의 카운트를 파장마다 더한 스펙트럼 |
| 배경(background) | 레이저 펄스와 상관없이 들어오는 카운트. BG WINDOW 구간의 평균으로 잼 |
| OFFSET | 분광기 파장 보정. 파일의 파장에 더하는 nm |
| solvent 빼기 | 용매만 잰 측정에 배율을 곱해 시료 측정에서 빼는 것. 산란광과 라만 신호를 없앰 |
| Crop / Mask | 남길 파장·시간 범위 / 분석에서 뺄 파장 대역 |
| DADS | decay-associated (difference) spectra. 성분마다 그 진폭을 파장에 대해 그린 스펙트럼 |
| EADS | evolution-associated (difference) spectra. 같은 결과를 순차 모델(1 → 2 → 3 …)의 성분 스펙트럼으로 바꾼 것 |
| RMS | 피팅의 잔차 제곱 평균의 제곱근. 작을수록 피팅이 데이터에 가까움 |

## 프로그램이 멈췄을 때

1.4부터는 창이 5초 이상 응답하지 않거나 내부 오류가 나면, 그때 실행 중이던 코드 위치를 `TCSPC_analysis_freeze.log`에 남깁니다. 이 파일은 실행 파일(1.6부터)로 쓰면 `문서\TCSPC_analysis\`에, 소스에서 실행하면 `run_tcspc_analysis.py` 옆에 있습니다(1.4.2까지의 실행 파일은 exe 옆). 측정 값은 기록하지 않고 열려 있던 파일의 이름만 적습니다. 문제를 알릴 때 이 파일을 함께 보내 주세요. 오래 걸리지만 정상인 작업(`.opju` 내보내기에서 Origin이 시작될 때 등)도 같은 방식으로 기록되며, 이런 기록은 오류가 아닙니다.

## PTU · FLIM 탭

`.ptu`(PicoHarp 300 T3 기록)에서 강도 이미지, 수명 맵, 픽셀별 감쇠 히스토그램을 만듭니다. 이 탭은 1.0에서 옮겨 온 그대로이며 다음을 전제로 합니다.

- 기록 안의 마커 1을 픽셀 클럭, 마커 2를 라인 끝으로 읽습니다. 스캐너가 다른 마커를 내면 이미지가 맞지 않습니다.
- 이미지 크기의 기본값은 X 99, Y 100, 시간 bin 4,096개입니다. 값을 고친 뒤에는 **Apply size**를 눌러야 다음 Process에 반영됩니다.
- 첫 프레임(처음 Y줄)만 사용합니다.
- 강도 이미지는 0–2 카운트 범위로 표시되고, 수명 맵의 값은 bin 단위입니다.
- 이미지 위로 마우스를 옮기면 그 픽셀의 감쇠 히스토그램이 보입니다.
- GPU 사용은 선택이며 없어도 CPU로 동작합니다(`SETUP.md`).

FLIM 탭의 정비는 별도 계획으로 남아 있습니다.

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
| 1.6 | `tcspc_analysis/` (태그 `v1.6`) | 코드 리뷰에서 나온 결함 수정과 화면 정리. 일부 피팅·내보내기 결과가 1.5와 달라짐([CHANGELOG.md](CHANGELOG.md)) |

`TCSPC_analysis.bat`과 문서(`SETUP.md`, `ARCHITECTURE.md`)는 패키지를 기준으로 합니다. 1.5에는 실행 파일을 따로 올리지 않았습니다(계산 결과는 1.4.2와 같습니다). 1.4까지의 버전을 직접 실행하려면 `python TCSPC_analysis_1.2ver.py [file.phu]`처럼 파일을 지정합니다.

프로그램 구조는 [ARCHITECTURE.md](ARCHITECTURE.md), 회귀 시험과 돌리는 방법은 [tests/README.md](tests/README.md)에 있습니다(측정 파일 두 개가 따로 필요합니다).
