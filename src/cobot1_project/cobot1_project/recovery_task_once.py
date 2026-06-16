#!/usr/bin/env python3

import signal
import sys
import time
import traceback

import rclpy
import DR_init


# ============================================================
"""
 recovery_task_once.py
 - 실제 복구 동작 1회 수행
 - all_task_service_server가 subprocess로 실행
 - 서비스 서버 기능 없음
 .1 리커버리를 gripper 상태를 확인해서 조건 수정 
 - gripper ON : 버리기
 - gripper OFF : HOME으로
 .2 리커버리 상태에서 x 700~900 좌표 회피동작 추가 
 - 리커버리 동작 시에 작업 도구 대가 문제가 생기면 z축으로 200 올려서 회피
"""
# ============================================================

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA_v1"

# 속도 / 가속도
VELOCITY = 80
ACC = 40

# 디지털 출력 상태
ON, OFF = 1, 0

# DR_init 기본 설정
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# STOP 요청 플래그
stop_requested = False


# ============================================================
# STOP 처리
# ============================================================

class StopRequestedException(Exception):
    pass


def signal_handler(signum, frame):
    global stop_requested

    print(f"[RECOVERY_ONCE] Signal received: {signum}", flush=True)
    stop_requested = True


def check_stop():
    if stop_requested:
        print("[RECOVERY_ONCE] STOP detected", flush=True)
        raise StopRequestedException("STOPPED_BY_USER")


def safe_wait(wait_func, seconds, step=0.2):
    """
    긴 wait 중에도 STOP 신호를 빠르게 반영하기 위한 분할 wait.
    """
    elapsed = 0.0

    while elapsed < seconds:
        check_stop()

        remain = seconds - elapsed
        dt = step if remain > step else remain

        wait_func(dt)
        elapsed += dt

    check_stop()


# ============================================================
# 로봇 초기화
# ============================================================

def initialize_robot():
    """로봇 Tool/TCP 설정 및 자동 모드 전환"""

    from DSR_ROBOT2 import (
        set_tool,
        set_tcp,
        get_tool,
        get_tcp,
        ROBOT_MODE_MANUAL,
        ROBOT_MODE_AUTONOMOUS,
        get_robot_mode,
        set_robot_mode,
    )

    print("#" * 50, flush=True)
    print("[RECOVERY_ONCE] Robot initialization start", flush=True)
    print(f"ROBOT_ID: {ROBOT_ID}", flush=True)
    print(f"ROBOT_MODEL: {ROBOT_MODEL}", flush=True)
    print(f"ROBOT_TOOL: {ROBOT_TOOL}", flush=True)
    print(f"ROBOT_TCP: {ROBOT_TCP}", flush=True)
    print("#" * 50, flush=True)

    # 수동 모드에서 Tool/TCP 설정
    set_robot_mode(ROBOT_MODE_MANUAL)
    time.sleep(0.5)

    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)

    # 자동 모드 전환
    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    time.sleep(2.0)

    print("#" * 50, flush=True)
    print("[RECOVERY_ONCE] Robot initialized with the following settings:", flush=True)
    print(f"ROBOT_ID: {ROBOT_ID}", flush=True)
    print(f"ROBOT_MODEL: {ROBOT_MODEL}", flush=True)
    print(f"ROBOT_TCP: {get_tcp()}", flush=True)
    print(f"ROBOT_TOOL: {get_tool()}", flush=True)
    print(f"ROBOT_MODE (0:수동, 1:자동): {get_robot_mode()}", flush=True)
    print(f"VELOCITY: {VELOCITY}", flush=True)
    print(f"ACC: {ACC}", flush=True)
    print("#" * 50, flush=True)


# ============================================================
# 안전 출력 해제
# ============================================================

def safe_release_outputs():
    """
    복구 종료/중단/오류 시 그리퍼 출력이 애매하게 남지 않도록 release 상태로 정리.
    """
    try:
        from DSR_ROBOT2 import set_digital_output

        print("[RECOVERY_ONCE] safe_release_outputs()", flush=True)

        set_digital_output(2, ON)
        set_digital_output(1, OFF)
        set_digital_output(3, OFF)

    except Exception as e:
        print(f"[RECOVERY_ONCE] safe_release_outputs failed: {e}", flush=True)


# ============================================================
# 실제 복구 작업
# ============================================================

def perform_recovery_task():
    """
    비상 위치 이동 후 원점 복귀 작업 1회 수행.
    현재 좌표를 확인하여 장애물 구역(X:700~800)일 경우 수직 탈출 기동을 먼저 수행함.
    """

    from DSR_ROBOT2 import (
        posx,
        movej,
        movel,              # ★ 직선 이동(수직 상승)을 위해 추가
        get_current_posx,   # ★ 현재 좌표 확인을 위해 추가
        set_digital_output,
        get_digital_input,
        wait,
    )

    # ========================================================
    # 좌표 정의 (기존과 동일)
    # ========================================================
    p_origin_j = [0, 0, 90, 0, 90, 0]

    emergency_up_j = [47.493, 31.560, 51.198, -5.173, 92.396, 0.468]
    emergency_down_j = [49.912, 49.198, 55.294, -4.052, 74.659, 50.994]

    # ========================================================
    # 그리퍼 함수 (기존과 동일)
    # ========================================================
    def release():
        print("[RECOVERY_ONCE][GRIPPER] Release", flush=True)
        set_digital_output(2, ON)
        set_digital_output(1, OFF)
        set_digital_output(3, OFF)
        safe_wait(wait, 1.0)
        check_stop()

    def grip_pepper():
        print("[RECOVERY_ONCE][GRIPPER] Grip", flush=True)
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        safe_wait(wait, 1.0)
        check_stop()

    # ========================================================
    # 작업 시작
    # ========================================================
    
    TOOL_SENSOR_PIN = 1                 
    
    print("[RECOVERY_ONCE] Waiting for IO state to stabilize...", flush=True)
    safe_wait(wait, 0.5)
    check_stop()
    
    is_holding_tool = (get_digital_input(TOOL_SENSOR_PIN) == ON)

    # 🌟 현재 로봇의 TCP 좌표 확인
    current_pos = get_current_posx()[0]  # [x, y, z, rx, ry, rz] 리스트 반환
    current_x = current_pos[0]
    current_z = current_pos[2]
    
    
    print(f"[RECOVERY_ONCE] Current X position: {current_x:.1f}", flush=True)

    # ========================================================
    # 🌟 공통 회피 기동 (장애물 구역에 있다면 무조건 수직 상승)
    # ========================================================
    if 700 <= current_x <= 900 and current_z >100:  # 여유 공간을 위해 850까지 잡음
        print(">>> 🚨 Obstacle zone detected! Executing vertical escape.", flush=True)
        escape_pos = current_pos.copy()
        escape_pos[2] += 200  # 현재 높이에서 200mm 수직 상승 (장치물 높이에 맞춰 숫자 조절하세요)
        
        # 만약 절대 안전 높이(예: Z=500)로 가고 싶다면 아래 코드를 사용하세요.
        # escape_pos[2] = 500 
        
        # 주변을 치지 않도록 수직(직선)으로만 띄웁니다.
        movel(escape_pos, vel=VELOCITY, acc=ACC)
        check_stop()
    else:
        print("1. movej → origin", flush=True)
        movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
        check_stop()



    # ========================================================
    # 상태에 따른 목적지 이동
    # ========================================================
    if is_holding_tool:
        print("=== Holding Tool: Moving to Emergency Tray ===", flush=True)
        print("0. movej → origin", flush=True)
        movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
        check_stop()

        # 1. 비상 트레이 up point 이동
        print("1. movej → emergency_up", flush=True)
        movej(emergency_up_j, vel=VELOCITY, acc=ACC, r=20)
        check_stop()

        # 2. 비상 트레이 down point 이동
        print("2. movej → emergency_down", flush=True)
        movej(emergency_down_j, vel=VELOCITY, acc=ACC, r=0)
        check_stop()

        # 3. 그리퍼 열기
        print("3. gripper open", flush=True)
        release()
        check_stop()

        # 4. 비상 트레이 up point 복귀
        print("4. movej → emergency_up", flush=True)
        movej(emergency_up_j, vel=VELOCITY, acc=ACC, r=20)
        check_stop()

        # 5. 원점 복귀
        print("5. movej → origin", flush=True)
        movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
        check_stop()

    else:
        print("=== Empty Gripper: Moving to Origin ===", flush=True)
        
        # 원점 복귀 (이미 위에서 장애물 회피를 했으므로 안전하게 이동 가능)
        print("1. movej → origin", flush=True)
        movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
        check_stop()

    print("=== Emergency Recovery Process Finished ===", flush=True)

# ============================================================
# shutdown
# ============================================================

def shutdown_node(node):
    try:
        safe_release_outputs()
    except Exception:
        pass


    try:
        if node is not None:
            node.destroy_node()
    except Exception as e:
        print(f"[RECOVERY_ONCE] destroy_node failed: {e}", flush=True)

    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception as e:
        print(f"[RECOVERY_ONCE] rclpy.shutdown failed: {e}", flush=True)


# ============================================================
# main
# ============================================================

def main(args=None):
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    node = None

    try:
        print("[RECOVERY_ONCE] rclpy.init()", flush=True)
        rclpy.init(args=args)

        print("[RECOVERY_ONCE] create_node()", flush=True)
        node = rclpy.create_node(
            "recovery_task_once",
            namespace=ROBOT_ID
        )

        # 중요:
        # DSR_ROBOT2가 사용할 ROS2 node를 DR_init에 연결
        DR_init.__dsr__node = node

        initialize_robot()
        check_stop()

        perform_recovery_task()

        print("[RECOVERY_ONCE] Recovery task completed successfully", flush=True)

        shutdown_node(node)
        sys.exit(0)

    except StopRequestedException:
        print("[RECOVERY_ONCE] Recovery task stopped by user", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except KeyboardInterrupt:
        print("[RECOVERY_ONCE] KeyboardInterrupt received", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except Exception as e:
        print(f"[RECOVERY_ONCE] Recovery task failed: {e}", flush=True)
        traceback.print_exc()
        shutdown_node(node)
        sys.exit(1)


if __name__ == "__main__":
    main()