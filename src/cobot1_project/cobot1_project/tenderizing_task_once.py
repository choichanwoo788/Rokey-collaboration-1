#!/usr/bin/env python3
"""
1. amove_periodic으로 비동기
    .1 좌표 틀어짐 수정
2. stemp 모드 추가
"""


import signal
import sys
import time
import traceback

import rclpy
import DR_init


# ==========================================================
# 로봇 설정 상수
# ==========================================================

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA_v1"

VELOCITY = 50
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
    print(f"[TENDERIZING_ONCE] Signal received: {signum}", flush=True)
    stop_requested = True


def check_stop():
    if stop_requested:
        print("[TENDERIZING_ONCE] STOP detected", flush=True)
        raise StopRequestedException("STOPPED_BY_USER")


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
    print("[TENDERIZING_ONCE] Initializing robot", flush=True)
    print(f"ROBOT_ID: {ROBOT_ID}", flush=True)
    print(f"ROBOT_MODEL: {ROBOT_MODEL}", flush=True)
    print(f"ROBOT_TCP: {ROBOT_TCP}", flush=True)
    print(f"ROBOT_TOOL: {ROBOT_TOOL}", flush=True)
    print(f"VELOCITY: {VELOCITY}", flush=True)
    print(f"ACC: {ACC}", flush=True)
    print("#" * 50, flush=True)

    set_robot_mode(ROBOT_MODE_MANUAL)
    time.sleep(0.5)

    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)

    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    time.sleep(2.0)

    print("#" * 50, flush=True)
    print("[TENDERIZING_ONCE] Robot initialized", flush=True)
    print(f"ROBOT_TCP: {get_tcp()}", flush=True)
    print(f"ROBOT_TOOL: {get_tool()}", flush=True)
    print(f"ROBOT_MODE: {get_robot_mode()}", flush=True)
    print("#" * 50, flush=True)


# ==========================================================
# 힘 제어 안전 해제
# ==========================================================

def safe_release_force_control():
    try:
        from DSR_ROBOT2 import (
            release_force,
            release_compliance_ctrl,
            set_ref_coord,
            DR_BASE
        )

        print("[TENDERIZING_ONCE] Releasing force/compliance control...", flush=True)

        release_force()
        release_compliance_ctrl()
        set_ref_coord(DR_BASE)

    except Exception as e:
        print(f"[TENDERIZING_ONCE] force release skipped or failed: {e}", flush=True)


# ==========================================================
# 실제 연육 작업
# ==========================================================

def perform_task():
    """연육 작업 1회 수행"""

    print("[TENDERIZING_ONCE] Performing tenderizing task...", flush=True)

    from DSR_ROBOT2 import (
            posx, movej, movel, amove_periodic, move_periodic,
            set_digital_output, wait, get_current_posx,
            check_force_condition, DR_AXIS_Z # ★ 추가됨
        )

    from DSR_ROBOT2 import (
        release_compliance_ctrl,
        release_force,
        task_compliance_ctrl,
        set_desired_force,
        set_ref_coord,
        DR_FC_MOD_REL,
        DR_BASE,
        get_current_posx
    )

    def release():
        print("Releasing...", flush=True)
        set_digital_output(2, ON)
        set_digital_output(1, OFF)
        set_digital_output(3, OFF)
        wait(2)
        check_stop()

    def grip():
        print("Gripping...", flush=True)
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        set_digital_output(3, OFF)
        wait(2)
        check_stop()

    def grip2():
        print("Gripper Close", flush=True)
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        set_digital_output(3, ON)
        safe_wait(wait, 1.5)
        check_stop()

    # ======================================================
    # 좌표 설정
    # ======================================================

    pos3 = posx([328.119, 12.487, 250.5, 150, 179, 150])
    pos3_j =[    1.582,
    -5.615,
    76.645,
    1.203,
    108.199,
    1.528]
    pos4 = posx([328.119, 20.487, 165.5, 150, 179, 150])
    pos4_1 = posx([328.119, 20.487, 165.5, 41.12, 179, -46.552])

    pos_t = posx([726.751, 79.904, 287.273, 177.569, -93.134, 90.085])

    JReady = [0, 0, 90, 0, 90, 0]
    JReady2 = [0, -5, 95, 0, 90, 90]

    Jgrip1 = [13.925, 25.333, 129.06, 17.172, -65.657, -98.87]
    Jgrip2 = [ 10.437, 31.46,115.376, 14.81,-56.765, -97.49]
    Jgrip3 = [12.723, 14.14, 113.659, 26.022, -37.488, -106.49]
    Jgrip4 = [9.8460, -17.412, 128.317, 2.8836, -4.2408, -90.2022]

    a0 = [10, 50, 0, 0, 0, 0]
    a1 = [10, 50, 0, 0, 0, 0]

    p0 = [3, 6, 0, 0, 0, 0]
    p1 = [3, 6, 0, 0, 0, 0]

    # ========================
    # 트레이 복원 좌표
    # ========================

    p_origin = [0, 5, 85, 0, 90, 0]

    p_tray_ready = posx([649.532, -5.771, 77.583, 19.484, 177.756, 21.65])
    p_tray_pick = posx([652.783, -8.346, 33.137, 20.774, 177.922, 23.197])
    p_place_down = posx([193.317, 23.735, 34.454, 47.065, 176.508, 47.77])

    # ======================================================
    # 연육 도구 집기
    # ======================================================

    print("=== Tenderizing Tool Pick Start ===", flush=True)

    check_stop()
    movej(JReady, vel=VELOCITY, acc=ACC)
    check_stop()

    release()
    safe_wait(wait, 1.0)

    movej(Jgrip4, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    movej(Jgrip1, vel=VELOCITY, acc=ACC)
    check_stop()

    movej(Jgrip2, vel=VELOCITY, acc=ACC)
    check_stop()

    grip()
    safe_wait(wait, 1.0)

    movel(pos_t, vel=VELOCITY, acc=ACC)
    check_stop()

    movej(Jgrip4, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    # ======================================================
    #  스템프
    # ======================================================
    movej(pos3_j, vel=VELOCITY, acc=ACC, r=70)
    check_stop()

    movel(pos4, vel=VELOCITY, acc=ACC)
    check_stop()

    print("=== Surface Detection by Force Control ===", flush=True)
    
    # 1. 고기 위쪽 안전 높이(pos3)로 이동
    movel(pos4, vel=VELOCITY, acc=ACC)
    check_stop()

    print("힘 제어 기반 하강 시작 (스스로 고기를 찾습니다)...", flush=True)
    
    # 2. 컴플라이언스 켜기
    set_ref_coord(1) # Tool 기준
    task_compliance_ctrl(stx=[2500, 2500, 500, 200, 200, 200])
    safe_wait(wait, 0.5)



    # 4. 표면 감지 루프 (check_force_condition 활용)
    print("고기 표면 안착 대기 중...", flush=True)
    
    while True:
        check_stop()
        
        # ★ 핵심: Z축 힘이 -8N ~ 8N 범위를 벗어나는지 확인
        # (목표 힘이 10N이므로, 고기에 닿아 저항력(8N 이상)이 발생하면 루프 탈출)
        # 방향에 따라 양수/음수가 나올 수 있으므로 min, max를 대칭으로 여유있게 잡아줍니다.
        ret = check_force_condition(DR_AXIS_Z, min=-8.0, max=8.0)
        
        # ret가 0이 아니면(범위 이탈, 즉 힘이 8N 이상 걸림) 고기에 닿은 것!
        if ret != 0:
            print(f"고기 표면 감지 완료! (조건 반환값: {ret})", flush=True)
            break
            
        # 안전장치: 고기가 없어서 바닥까지 뚫고 내려가는 것 방지
        current_pos = get_current_posx(DR_BASE)
        if current_pos[0][2] <= 110.0:
            print("고기 미감지: 하강 한계점 도달", flush=True)
            break
            
        wait(0.1)

    check_stop()
    
    current_pos = get_current_posx(DR_BASE)
    print(f"감지된 최종 Z축 높이: {current_pos[0][2]:.2f}", flush=True)

    # ------------------------------------------------------
    # 5. 사전 누르기 (Pre-stamping) 동작
    # ------------------------------------------------------
    print("사전 누르기(스탬핑) 동작 3회 실시...", flush=True)
    stamp_amp = [0, 30, 10, 0, 0, 0]
    stamp_period = [0, 5, 1, 0, 0, 0]
    amove_periodic(amp=stamp_amp, period=stamp_period, atime=0.5, repeat=3)
    safe_wait(wait, 16) # ★ 정확한 대기 시간
    check_stop()
    # ======================================================
    # 연육 작업 1
    # ======================================================

    print("=== Tenderizing Rolling 1 Start ===", flush=True)

    movej(JReady, vel=VELOCITY, acc=ACC, r=70)
    check_stop()

    # movel(pos3, vel=VELOCITY, acc=ACC)
    # check_stop()

    # movel(pos4, vel=VELOCITY, acc=ACC)
    # check_stop()

    print("힘 제어 시작...", flush=True)

    current_pos = get_current_posx(DR_BASE)
    current_z = current_pos[0][2]

    print(f"현재 높이: {current_z:.2f}", flush=True)

    set_ref_coord(1)
    task_compliance_ctrl(stx=[500, 500, 1000, 200, 200, 200])
    safe_wait(wait, 0.5)

    set_desired_force(
        fd=[0, 0, 10, 0, 0, 0],
        dir=[0, 0, 1, 0, 0, 0],
        mod=DR_FC_MOD_REL
    )

    try:
        a_p = 50
        while current_z > 160:
            check_stop()

            a0 = [10, a_p, 0, 0, 0, 0]
            amove_periodic(
                amp=a0,
                period=p0,
                atime=2,
                repeat=2
            )
            expected_time = 15.0 
            safe_wait(wait, expected_time) # 이 안에서 지속적으로 check_stop()이 돌아감

            check_stop()

            current_pos = get_current_posx(DR_BASE)
            current_z = current_pos[0][2]

            print(f"현재 높이: {current_z:.2f} 밀대 너비 {a_p}", flush=True)
            a_p += 1

    finally:
        print("힘 제어 해제...", flush=True)
        release_force()
        release_compliance_ctrl()
        set_ref_coord(DR_BASE)
        safe_wait(wait, 0.5)

    check_stop()

    # ======================================================
    # 연육 작업 2
    # ======================================================

    print("=== Tenderizing Rolling 2 Start ===", flush=True)


    movel(pos3, vel=VELOCITY, acc=ACC)
    check_stop()

    safe_wait(wait, 1.0)

    movel(pos4_1, vel=VELOCITY, acc=ACC)
    check_stop()

    print("힘 제어 시작...", flush=True)

    current_pos = get_current_posx(DR_BASE)
    current_z = current_pos[0][2]

    print(f"현재 높이: {current_z:.2f}", flush=True)

    set_ref_coord(1)
    task_compliance_ctrl(stx=[500, 500, 1000, 200, 200, 200])
    safe_wait(wait, 0.5)

    set_desired_force(
        fd=[0, 0, 10, 0, 0, 0],
        dir=[0, 0, 1, 0, 0, 0],
        mod=DR_FC_MOD_REL
    )

    try:
        a_p = 30
        while current_z > 160:
            check_stop()

            a1 = [10, a_p, 0, 0, 0, 0]
            amove_periodic(
                amp=a1,
                period=p1,
                atime=2,
                repeat=2
            )
            expected_time = 15.0 
            safe_wait(wait, expected_time) # 이 안에서 지속적으로 check_stop()이 돌아감

            check_stop()

            current_pos = get_current_posx(DR_BASE)
            current_z = current_pos[0][2]
            print(f"현재 높이: {current_z:.2f} 밀대 너비 {a_p}", flush=True)
            a_p += 1

    finally:
        print("힘 제어 해제...", flush=True)
        release_force()
        release_compliance_ctrl()
        set_ref_coord(DR_BASE)
        safe_wait(wait, 0.5)

    check_stop()

    # ======================================================
    # 연육 도구 내려놓기
    # ======================================================

    print("=== Tenderizing Tool Place Start ===", flush=True)

    movej(JReady, vel=VELOCITY, acc=ACC, r=30)
    check_stop()

    movej(Jgrip4, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    movej(Jgrip3, vel=40, acc=20)
    check_stop()

    movej(Jgrip2, vel=40, acc=20)
    check_stop()

    safe_wait(wait, 2.0)

    release()
    safe_wait(wait, 1.0)

    movej(Jgrip1, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    movej(Jgrip4, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    movej(JReady, vel=VELOCITY, acc=ACC)
    check_stop()

    # ======================================================
    # 트레이 복원
    # ======================================================

    print("=== Tray Back Task Start ===", flush=True)

    safe_wait(wait, 1.0)

    set_ref_coord(DR_BASE)

    movej(JReady, vel=VELOCITY, acc=ACC)
    check_stop()

    safe_wait(wait, 1.0)

    movel(p_place_down, vel=60, acc=40)
    check_stop()

    grip2()
    check_stop()

    movej(p_origin, vel=50, acc=40)
    check_stop()

    movel(p_tray_pick, vel=60, acc=40)
    check_stop()

    release()
    check_stop()

    movel(p_tray_ready, vel=VELOCITY, acc=ACC)
    check_stop()

    movej(p_origin, vel=50, acc=40)
    check_stop()

    print("=== Tray Task Finished ===", flush=True)
    print("=== Tenderizing Task Finished ===", flush=True)


# ==========================================================
# shutdown
# ==========================================================

def shutdown_node(node):
    try:
        safe_release_force_control()
    except Exception:
        pass

    try:
        if node is not None:
            node.destroy_node()
    except Exception as e:
        print(f"[TENDERIZING_ONCE] destroy_node failed: {e}", flush=True)

    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception as e:
        print(f"[TENDERIZING_ONCE] rclpy.shutdown failed: {e}", flush=True)


# ==========================================================
# main
# ==========================================================

def main(args=None):
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    node = None

    try:
        print("[TENDERIZING_ONCE] rclpy.init()", flush=True)
        rclpy.init(args=args)

        print("[TENDERIZING_ONCE] create_node()", flush=True)
        node = rclpy.create_node("tenderizing_task_once", namespace=ROBOT_ID)

        DR_init.__dsr__node = node

        initialize_robot()
        check_stop()

        perform_task()

        print("[TENDERIZING_ONCE] Tenderizing task completed successfully", flush=True)

        shutdown_node(node)
        sys.exit(0)

    except StopRequestedException:
        print("[TENDERIZING_ONCE] Tenderizing task stopped by user", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except KeyboardInterrupt:
        print("[TENDERIZING_ONCE] KeyboardInterrupt received", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except Exception as e:
        print(f"[TENDERIZING_ONCE] Tenderizing task failed: {e}", flush=True)
        traceback.print_exc()
        shutdown_node(node)
        sys.exit(1)


if __name__ == "__main__":
    main()