# Rokey Collaboration 1

AutoKatz는 Doosan M0609 협동로봇을 활용해 반복적인 조리 공정을 자동화하는 ROS2 기반 스마트 조리 시스템입니다. 발표자료 기준으로, 재료 이송부터 밑간, 연육, 튀김, 소스 작업까지 이어지는 조리 흐름을 로봇 작업 단위로 나누고, React GUI와 Flask/ROS2 Bridge를 통해 작업 상태를 모니터링하도록 구성했습니다.

## 프로젝트 목표

- 반복 조리 공정의 작업 피로와 인력 의존도를 줄입니다.
- 조리 품질 편차를 줄이고 일정한 조리 결과를 목표로 합니다.
- 고온 튀김 공정 등 위험 작업을 자동화해 작업 안전성을 높입니다.
- GUI 기반으로 작업 시작, 종료, 상태 확인, 이력 조회를 수행합니다.

## 주요 기능

- Pick & Place 기반 재료 이송
- Shaking 기반 시즈닝 작업
- Rolling 및 로봇 모션 기반 연육 작업
- 튀김 공정 제어
- 소스 도포 경로 처리
- 긴급 정지 및 복구 작업 흐름
- React 기반 작업 대시보드
- SQLite 기반 작업, 태스크, 로봇 로그 기록

## 기술 스택

- ROS2 Humble
- Python 3.10
- Flask
- React / Vite
- SQLite
- OpenCV
- NumPy
- Doosan M0609

## 폴더 구조

```text
frontend/
  src/pages/Dashboard.jsx
  src/pages/Login.jsx
  src/components/LogHistory.jsx

src/cobot1_project/
  cobot1_project/
    central_controller1_1_ch.py
    all_task_service_server.py
    app2_1_ch.py
    frying_task_once.py
    tenderizing_task_once.py
    seasoning_task_once.py
    saucing_task_once.py
    recovery_task_once.py
    preprocessing_img.py
```

## 실행 예시

Python 의존성:

```bash
pip install -r requirements.txt
```

프론트엔드:

```bash
cd frontend
npm install
npm run dev
```

ROS2 패키지 빌드 후 실행:

```bash
colcon build --packages-select cobot1_project
source install/setup.bash
ros2 run cobot1_project central_controller1_1_ch
ros2 run cobot1_project all_task_service_server
```

## 시스템 흐름

```text
React GUI
  -> Flask / ROS2 Bridge
  -> Central Controller
  -> Task Service Server
  -> Doosan M0609 Motion Tasks
  -> SQLite Log / History
```

## 참고

실제 로봇 실행 전에는 Doosan ROS2 패키지, 로봇 IP/컨트롤러 설정, 안전 영역, 툴 무게, 그리퍼 상태를 현장 환경에 맞게 다시 확인해야 합니다.
