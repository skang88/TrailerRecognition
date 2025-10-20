# Trailer Recognition & Gate Control System

## 1. 프로젝트 개요

RTSP 카메라 스트림을 통해 차량을 실시간으로 탐지하고 추적하는 시스템입니다. 특정 구역(게이트) 내에서 차량이 설정된 시간 이상 정차하면, 웹훅(Webhook)을 호출하여 차단기 등 외부 장치를 제어합니다.

본 시스템은 `YOLOv8` 모델을 사용하여 차량을 탐지하며, `PySimpleGUI`를 통해 주요 설정값을 실시간으로 변경할 수 있는 제어 패널을 제공합니다.

## 2. 주요 기능

- **실시간 차량 탐지 및 추적**: RTSP 스트림에서 자동차, 트럭, 버스 등 지정된 차량 객체를 탐지하고 개별 ID로 추적합니다.
- **정차 감지**: 특정 구역(게이트) 내에서 차량의 움직임을 감지하여, 설정된 시간 이상 멈추면 '정차'로 판단합니다.
- **자동 게이트 제어**: 차량 정차가 감지되면 지정된 API (Shelly 웹훅)를 호출하여 외부 장치를 제어합니다.
- **운영 시간 설정**: 특정 시간대(예: 새벽 3시 ~ 저녁 7시)에만 게이트 제어 기능이 활성화되도록 설정할 수 있습니다.
- **실시간 제어 패널**: GUI를 통해 다음 설정값을 프로그램을 중단하지 않고 실시간으로 변경할 수 있습니다.
  - 정차 판단 시간
  - 움직임 허용 오차 (픽셀)
  - 프레임 처리 간격
  - 게이트 재작동 방지 시간
- **좌표 확인 유틸리티**: `get_coordinates.py`를 통해 영상에서 게이트 영역을 설정할 좌표를 쉽게 확인할 수 있습니다.

## 3. 설치 방법

1.  **Git Repository 복제:**
    ```bash
    git clone https://github.com/skang88/TrailerRecognition.git
    cd TrailerRecognition/TrailerRecognition
    ```

2.  **가상 환경 생성 및 활성화:**
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS / Linux
    source .venv/bin/activate
    ```

3.  **필요 라이브러리 설치:**
    `requirements.txt` 파일에 일부 라이브러리가 누락되어 있습니다. 다음 명령어로 모든 라이브러리를 설치하세요.
    ```bash
    pip install ultralytics numpy opencv-python requests pysimplegui lap
    ```

4.  **YOLOv8 모델 다운로드:**
    프로그램이 처음 실행될 때 `yolov8n.pt` 모델을 자동으로 다운로드하지만, 미리 다운로드해 두는 것을 권장합니다.

## 4. 설정

메인 스크립트(`TrailerRecognition.py`) 상단의 설정값을 환경에 맞게 수정해야 합니다.

- `RTSP_URL`: 연결할 카메라의 RTSP 주소를 입력합니다.
- `API_BASE_URL`: Shelly 웹훅을 제어하기 위한 기본 API 주소입니다.
- `GATES`: 영상 내에서 감지할 게이트의 좌표 `[x1, y1, x2, y2]`를 설정합니다. `get_coordinates.py`를 사용하여 좌표를 얻을 수 있습니다.
- `GATES_CONFIG`: 각 게이트의 이름과 제어할 Shelly 장치의 ID를 매핑합니다.

## 5. 사용 방법

### 5.1. 메인 시스템 실행

터미널에서 다음 명령어를 입력하여 차량 탐지 및 제어 시스템을 시작합니다.

```bash
python TrailerRecognition.py
```

실행 시, "Vehicle Detection System"이라는 영상 창과 "제어 패널" GUI 창이 나타납니다.

### 5.2. 게이트 좌표 확인

게이트 영역으로 사용할 좌표를 얻으려면 다음 스크립트를 실행합니다.

```bash
python get_coordinates.py
```

나타나는 영상 창에서 원하는 지점을 클릭하면 터미널에 해당 위치의 `(x, y)` 좌표가 출력됩니다. 이 좌표를 `TrailerRecognition.py`의 `GATES` 설정에 사용하세요.

## 6. 주요 의존성

- `ultralytics`: YOLOv8 모델 실행
- `OpenCV`: 비디오 처리 및 시각화
- `Requests`: 웹훅 API 호출
- `PySimpleGUI`: 실시간 제어 패널 GUI
- `NumPy`: 좌표 및 데이터 계산
