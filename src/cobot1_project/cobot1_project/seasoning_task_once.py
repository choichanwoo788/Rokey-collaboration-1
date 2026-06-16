#!/usr/bin/env python3

"""
1. 예외처리용 amove사용 + 모션 계선
"""

import signal
import sys
import time

import rclpy
import DR_init


# ==========================================================
# 로봇 설정 상수
# ==========================================================

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA_v1"

VELOCITY = 80
ACC = 40

ON, OFF = 1, 0

DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

stop_requested = False


# ==========================================================
# STOP 처리
# ==========================================================

class StopRequestedException(Exception):
    pass


def signal_handler(signum, frame):
    global stop_requested

    print(f"[TASK_ONCE] Signal received: {signum}", flush=True)
    stop_requested = True


def check_stop():
    if stop_requested:
        print("[TASK_ONCE] STOP detected. Abort seasoning task.", flush=True)
        raise StopRequestedException("STOPPED_BY_USER")


# ==========================================================
# 로봇 초기화
# ==========================================================

def initialize_robot():
    from DSR_ROBOT2 import (
        set_tool,
        set_tcp,
        get_tool,
        get_tcp,
        ROBOT_MODE_MANUAL,
        ROBOT_MODE_AUTONOMOUS,
        get_robot_mode,
        set_robot_mode
    )

    print("#" * 50, flush=True)
    print("[TASK_ONCE] Initializing robot", flush=True)
    print(f"ROBOT_ID: {ROBOT_ID}", flush=True)
    print(f"ROBOT_MODEL: {ROBOT_MODEL}", flush=True)
    print(f"ROBOT_TOOL: {ROBOT_TOOL}", flush=True)
    print(f"ROBOT_TCP: {ROBOT_TCP}", flush=True)
    print("#" * 50, flush=True)

    set_robot_mode(ROBOT_MODE_MANUAL)
    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)

    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    time.sleep(2)

    print("#" * 50, flush=True)
    print("[TASK_ONCE] Robot initialized", flush=True)
    print(f"ROBOT_TCP: {get_tcp()}", flush=True)
    print(f"ROBOT_TOOL: {get_tool()}", flush=True)
    print(f"ROBOT_MODE (0:수동, 1:자동): {get_robot_mode()}", flush=True)
    print("#" * 50, flush=True)


# ==========================================================
# 실제 시즈닝 작업
# ==========================================================

def safe_wait(wait_func, seconds, step=0.2):
    """
    긴 wait 중에도 STOP 신호를 조금 더 빨리 반영하기 위한 분할 wait.
    DSR wait()는 초 단위 실수 사용 가능하다고 가정.
    """
    elapsed = 0.0

    while elapsed < seconds:
        check_stop()
        remain = seconds - elapsed
        dt = step if remain > step else remain
        wait_func(dt)
        elapsed += dt

    check_stop()


def perform_task():
    print("[TASK_ONCE] Performing seasoning task...", flush=True)

    from DSR_ROBOT2 import (
        posx,
        movej,
        movel,
        set_digital_output,
        wait,
        move_periodic,
        amove_periodic
    )

    # ========================
    # 트레이 좌표
    # ========================
    p_t_origin = [0, 5, 85, 0, 90, 0]
    p_p_origin = [0, -10, 100, 0, 90, 0]

    p_tray_ready = posx([649.532, -5.771, 77.583, 19.484, 177.756, 21.65])
    p_tray_pick = posx([652.783, -8.346, 33.137, 20.774, 177.922, 23.197])

    p_tray_lift = posx([652.783, -8.346, 60, 20.774, 177.922, 23.197])
    p_tray_pull = posx([600, -8.346, 60, 20.774, 177.922, 23.197])
    p_tray_up = posx([600, -8.346, 70, 20.774, 177.922, 23.197])

    p_place_down = posx([193.317, 23.735, 34.454, 47.065, 176.508, 47.77])

    p_origin = [0, 0, 90, 0, 90, 0]
    p_shaking_ready_j = [43.741, 17.664, 96.683, -58.8, 121.922, 37.679]

    # ==============================
    # Pepper Pick 위치
    # ==============================
    p_pp_pick = posx([837.817, -123.486, 216.725, 177.235, -92.275, -89.767])
    p_pp_pick_up = [-10.999, 24.029, 85.166, -18.255, -18.536, 106.086]
    p_pp_pick_ready = [-10.234, -3.806, 106.115, -10.945, 16.545, 99.224]

    # ==============================
    # Salt Pick 위치
    # ==============================
    p_st_pick = posx([844.009, -33.077, 217.12, 177.487, -94.323, -88.444])
    p_st_pick_ready = [-2.515, 0.72, 97.951, -5.952, 31.145, 95.362]
    p_st_pick_up = [-3.283, 23.903, 89.001, -5.951, -19.695, 95.364]

    snap_amp = [0, 0, 20, 5, 0, 0]

    def release():
        print("Releasing...", flush=True)
        set_digital_output(2, ON)
        set_digital_output(1, OFF)
        set_digital_output(3, OFF)
        wait(1.5)
        check_stop()

    def grip_pepper():
        print("Gripping pepper/salt...", flush=True)
        set_digital_output(3, ON)
        set_digital_output(2, ON)
        set_digital_output(1, OFF)
        wait(1.5)
        check_stop()

    def grip_tray():
        print("Gripper Close Tray", flush=True)
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        set_digital_output(3, ON)
        wait(1.5)
        check_stop()

    # ========================
    # 트레이 시작
    # ========================
    print("=== Tray Task Start ===", flush=True)

    check_stop()
    movej(p_t_origin, vel=VELOCITY, acc=ACC)
    check_stop()

    release()
    check_stop()

    movel(p_tray_ready, vel=VELOCITY, acc=ACC)
    check_stop()

    movel(p_tray_pick, vel=70, acc=30)
    check_stop()

    grip_tray()
    check_stop()

    movel(p_tray_lift, vel=70, acc=30)
    check_stop()

    movel(p_tray_pull, vel=70, acc=40)
    check_stop()

    movel(p_tray_up, vel=VELOCITY, acc=ACC)
    check_stop()

    movej(p_t_origin, vel=50, acc=25)
    check_stop()

    movel(p_place_down, vel=30, acc=30)
    check_stop()

    release()
    check_stop()

    movej(p_t_origin, vel=VELOCITY, acc=ACC)
    check_stop()

    # ==========================================================
    # Pepper Process
    # ==========================================================
    print("=== Pepper Start Process ===", flush=True)

    print("movej → origin", flush=True)
    movej(p_origin, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    release()
    check_stop()

    print("movej → pepper pick_ready", flush=True)
    movej(p_pp_pick_ready, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → pepper pick_up", flush=True)
    movej(p_pp_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movel → pepper pick", flush=True)
    movel(p_pp_pick, vel=VELOCITY, acc=ACC)
    check_stop()

    grip_pepper()
    check_stop()

    print("movej → pepper pick_up", flush=True)
    movej(p_pp_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → pepper pick_ready", flush=True)
    movej(p_pp_pick_ready, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → origin", flush=True)
    movej(p_origin, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → shaking_ready", flush=True)
    movej(p_shaking_ready_j, vel=VELOCITY, acc=ACC)
    check_stop()

    print("move_periodic → pepper shaking", flush=True)

    # for i in range(3):
    check_stop()
    for i in range(3):
        print(f"pepper shake {i+1}", flush=True)
        amove_periodic(
            amp=snap_amp,
            period=0.5,
            atime=0.2,
            repeat=1,
            ref=0
        )
        safe_wait(wait, 1) # 이 안에서 지속적으로 check_stop()이 돌아감
        check_stop()

    wait(1)
    check_stop()

    print("movej → origin", flush=True)
    movej(p_p_origin, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → pepper pick_up", flush=True)
    movej(p_pp_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movel → pepper pick", flush=True)
    movel(p_pp_pick, vel=VELOCITY, acc=ACC)
    check_stop()

    release()
    check_stop()

    print("movej → pepper pick_up", flush=True)
    movej(p_pp_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → pepper pick_ready", flush=True)
    movej(p_pp_pick_ready, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("=== Pepper Process Finished ===", flush=True)

    # ==========================================================
    # Salt Process
    # ==========================================================
    print("=== Salt Start Process ===", flush=True)

    release()
    check_stop()

    print("movej → salt pick_ready", flush=True)
    movej(p_st_pick_ready, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → salt pick_up", flush=True)
    movej(p_st_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movel → salt pick", flush=True)
    movel(p_st_pick, vel=VELOCITY, acc=ACC)
    check_stop()

    grip_pepper()
    check_stop()

    wait(0.5)
    check_stop()

    print("movej → salt pick_up", flush=True)
    movej(p_st_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → salt pick_ready", flush=True)
    movej(p_st_pick_ready, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → origin", flush=True)
    movej(p_origin, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → shaking_ready", flush=True)
    movej(p_shaking_ready_j, vel=VELOCITY, acc=ACC)
    check_stop()

    print("move_periodic → salt shaking", flush=True)

    check_stop()
    for i in range(3):
        print(f"pepper shake {i+1}", flush=True)
        amove_periodic(
            amp=snap_amp,
            period=0.5,
            atime=0.2,
            repeat=1,
            ref=0
        )
        safe_wait(wait, 1) # 이 안에서 지속적으로 check_stop()이 돌아감
        check_stop()

    wait(1)
    check_stop()

    print("movej → origin", flush=True)
    movej(p_p_origin, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → salt pick_ready", flush=True)
    movej(p_st_pick_ready, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → salt pick_up", flush=True)
    movej(p_st_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movel → salt pick", flush=True)
    movel(p_st_pick, vel=VELOCITY, acc=ACC)
    check_stop()

    release()
    check_stop()

    wait(0.5)
    check_stop()

    print("movej → salt pick_up", flush=True)
    movej(p_st_pick_up, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → salt pick_ready", flush=True)
    movej(p_st_pick_ready, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("movej → origin", flush=True)
    movej(p_origin, vel=VELOCITY, acc=ACC)
    check_stop()

    wait(1)
    check_stop()

    print("=== Salt Process Finished ===", flush=True)
    print("=== Seasoning Task Finished ===", flush=True)


# ==========================================================
# main
# ==========================================================

def main(args=None):
    global stop_requested

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    rclpy.init(args=args)

    node = rclpy.create_node("seasoning_task_once", namespace=ROBOT_ID)

    DR_init.__dsr__node = node

    try:
        initialize_robot()
        check_stop()

        perform_task()

        print("[TASK_ONCE] Seasoning task completed successfully", flush=True)
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(0)

    except StopRequestedException:
        print("[TASK_ONCE] Seasoning task stopped by user", flush=True)
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(130)

    except KeyboardInterrupt:
        print("[TASK_ONCE] KeyboardInterrupt received", flush=True)
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(130)

    except Exception as e:
        print(f"[TASK_ONCE] Seasoning task failed: {e}", flush=True)
        node.destroy_node()
        rclpy.shutdown()
        sys.exit(1)


if __name__ == "__main__":
    main()