# Rokey Collaboration 1

AutoKatz는 Doosan M0609 협동로봇을 활용해 반복적인 조리 공정을 자동화하는 ROS2 기반 스마트 조리 시스템입니다. React 대시보드에서 조리 공정을 선택하면 Flask API가 ROS2 중앙 컨트롤러에 명령을 전달하고, 중앙 컨트롤러는 각 조리 작업 노드를 실행합니다.

## 프로젝트 목표

- 반복 조리 공정의 작업 피로와 인력 의존도를 줄입니다.
- 밑간, 연육, 튀김, 소스 작업을 로봇 작업 단위로 분리해 자동화합니다.
- GUI 기반으로 작업 시작, 정지, 복구, 상태 확인, 이력 조회를 제공합니다.
- 긴급 정지와 복구 흐름을 포함해 실제 작업 중단 상황에 대응합니다.

## 주요 기능

- React / Vite 기반 조리 공정 대시보드
- Flask + SQLAlchemy 기반 로그인, 세션, 작업 이력 API
- ROS2 Bridge를 통한 웹 API와 로봇 제어 노드 연결
- 중앙 컨트롤러 기반 상태 관리
- `SEASONING`, `TENDERIZING`, `FRYING`, `SAUCING` 작업 실행
- `/dsr01/motion/move_stop` 기반 즉시 정지
- Recovery 작업 실행 후 재시도 가능 상태 전환
- SQLite 기반 작업 세션, 액션, 로그 저장

## 기술 스택

- ROS2 Humble
- Python 3.10
- Flask
- Flask-CORS
- Flask-SQLAlchemy
- React 18
- Vite
- SQLite
- OpenCV
- NumPy
- Doosan Robotics ROS2 패키지
- `dsr_msgs2`
- Doosan M0609

## 폴더 구조

```text
frontend/
  src/App.jsx
  src/pages/Login.jsx
  src/pages/Dashboard.jsx
  src/components/LogHistory.jsx

src/cobot1_project/
  setup.py
  package.xml
  sauce_robot_points2.csv
  cobot1_project/
    app2_1_ch.py
    central_controller1_1_ch.py
    all_task_service_server.py
    seasoning_task_once.py
    tenderizing_task_once.py
    frying_task_once.py
    saucing_task_once.py
    recovery_task_once.py
    preprocessing_img.py
```

## 시스템 구조

```text
React Dashboard
  -> Flask API / SQLite
  -> RobotBridgeNode
  -> CentralControllerNode
  -> all_task_service_server
  -> task_once subprocess
  -> Doosan M0609 motion
```

주요 ROS2 서비스 흐름은 다음과 같습니다.

```text
Frontend action
  -> /api/action/start
  -> /cobot/controller/{task}/start
  -> /dsr01/{task}/start
  -> ros2 run cobot1_project {task}_task_once
```

정지와 복구 흐름은 다음 서비스를 사용합니다.

```text
/cobot/controller/stop
  -> /dsr01/{running_task}/stop
  -> /dsr01/motion/move_stop

/cobot/controller/recovery/start
  -> /dsr01/recovery/start
  -> recovery_task_once
```

## 시스템 실행 방법

### 1. ROS2 작업공간 준비

`cobot1_project`를 ROS2 workspace의 `src` 아래에 둔 뒤 빌드합니다.

```bash
source /opt/ros/humble/setup.bash
cd ~/ros2_ws
colcon build --packages-select cobot1_project
source install/setup.bash
```

Doosan 로봇 패키지와 메시지 패키지가 먼저 준비되어 있어야 합니다.

```text
dsr_msgs2
dsr_control2
DSR_ROBOT2
Doosan Robotics ROS2 driver
```

### 2. Python / Flask 의존성 설치

```bash
pip install -r requirements.txt
```

`requirements.txt`에는 Flask API와 OpenCV 기반 이미지 처리에 필요한 기본 패키지가 포함되어 있습니다.

### 3. SQLite DB 경로 확인

`app2_1_ch.py`는 기본 DB 경로를 절대 경로로 가지고 있습니다.

```text
/home/eycho/g2_2_ws/src/cobot1_project/cobot1_project/instance/robot_proc.db
```

다른 PC에서 실행할 경우 `SQLALCHEMY_DATABASE_URI`를 현재 workspace 경로에 맞게 수정해야 합니다. Flask 서버가 처음 실행될 때 기본 사용자도 생성됩니다.

```text
username: admin
password: 1234
```

### 4. 작업 서비스 서버 실행

작업 서비스 서버는 각 조리 task를 subprocess로 실행합니다.

```bash
ros2 run cobot1_project all_task_service_server
```

이 서버가 제공하는 작업은 다음과 같습니다.

```text
/dsr01/seasoning/start
/dsr01/tenderizing/start
/dsr01/frying/start
/dsr01/saucing/start
/dsr01/recovery/start
```

각 작업은 내부적으로 다음 실행 파일을 호출합니다.

```text
seasoning_task_once
tenderizing_task_once
frying_task_once
saucing_task_once
recovery_task_once
```

### 5. 중앙 컨트롤러 실행

중앙 컨트롤러는 웹 API가 호출하는 상위 제어 서비스를 제공합니다.

```bash
ros2 run cobot1_project central_controller1_1_ch
```

중앙 컨트롤러의 주요 상태는 다음과 같습니다.

```text
IDLE
TASK_RUNNING
STOP_REQUESTED
STOPPED
RECOVERY_RUNNING
READY_TO_RETRY
ERROR
```

### 6. Flask API / ROS Bridge 실행

Flask API는 기본 포트 `5000`에서 실행됩니다.

```bash
ros2 run cobot1_project app2_1_ch
```

직접 Python으로 실행할 수도 있습니다.

```bash
cd src/cobot1_project
python3 -m cobot1_project.app2_1_ch
```

주요 API는 다음과 같습니다.

```text
POST /api/login
POST /api/session/start
POST /api/action/start
POST /api/action/stop
POST /api/recovery/start
GET  /api/system/state
GET  /api/history
```

### 7. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 Vite 개발 서버로 접속합니다.

```text
http://localhost:5173
```

프론트엔드는 기본적으로 아래 API 서버를 호출합니다.

```text
http://localhost:5000/api
```

다른 주소를 사용할 경우 `VITE_API_URL` 환경변수로 지정합니다.

```bash
VITE_API_URL=http://<server-ip>:5000/api npm run dev
```

## 실행 순서 요약

터미널을 나누어 아래 순서로 실행합니다.

```bash
# 1. 작업 서비스 서버
ros2 run cobot1_project all_task_service_server

# 2. 중앙 컨트롤러
ros2 run cobot1_project central_controller1_1_ch

# 3. Flask API / ROS Bridge
ros2 run cobot1_project app2_1_ch

# 4. React dashboard
cd frontend
npm run dev
```

## 실행 전 확인 사항

- 실제 로봇 연결, Doosan ROS2 driver, `dsr_msgs2` 서비스가 정상 동작해야 합니다.
- `all_task_service_server.py`는 `/dsr01/motion/move_stop` 서비스를 사용하므로 로봇 컨트롤러 쪽 서비스 준비가 필요합니다.
- `setup.py`에는 과거 개발 중 사용한 엔트리포인트가 일부 남아 있습니다. 현재 정리된 저장소에서는 README에 적힌 실행 파일 기준으로 사용하세요.
- `sauce_robot_points2.csv`와 로봇 TCP/툴 설정은 현장 환경에 맞게 확인해야 합니다.
- 로봇 동작 테스트는 안전 영역, 비상정지, 그리퍼 상태를 확인한 뒤 수행해야 합니다.
