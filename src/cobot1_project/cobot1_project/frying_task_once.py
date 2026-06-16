#!/usr/bin/env python3

import signal
import sys
import time
import traceback

import rclpy
import DR_init

# flip, 내려가는 코드 , 기름망 좌표다시
# ============================================================
# frying_task_once.py
# - 서비스 서버 없음
# - all_task_service_server가 subprocess로 1회 실행
# - 실행 후 정상 종료 / STOP / ERROR 코드 반환
# ============================================================

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"
ROBOT_TOOL = "Tool Weight"
ROBOT_TCP = "GripperDA_v1"

# 속도 / 가속도
VELOCITY = 90
ACC = 30
V_F = 110
FLIP = 80

SLOW_VELOCITY = 50
SLOW_ACC = 20

FRYER_VELOCITY = 50
FRYER_ACC = 20
LIFT_VELOCITY = 70
LIFT_ACC = 20

# 디지털 출력
ON, OFF = 1, 0

# 작업 파라미터
COOKING_TIME = 3
GRIP_WAIT = 1.5
RELEASE_WAIT = 1.5
SHAKE_REPEAT = 4

# DR_init 설정
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

    print(f"[FRYING_ONCE] Signal received: {signum}", flush=True)
    stop_requested = True


def check_stop():
    if stop_requested:
        print("[FRYING_ONCE] STOP detected", flush=True)
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
    print("[FRYING_ONCE] Initializing robot", flush=True)
    print(f"ROBOT_ID: {ROBOT_ID}", flush=True)
    print(f"ROBOT_MODEL: {ROBOT_MODEL}", flush=True)
    print(f"ROBOT_TCP: {ROBOT_TCP}", flush=True)
    print(f"ROBOT_TOOL: {ROBOT_TOOL}", flush=True)
    print("#" * 50, flush=True)

    set_robot_mode(ROBOT_MODE_MANUAL)
    time.sleep(0.5)

    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)

    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    time.sleep(2.0)

    print("#" * 50, flush=True)
    print("[FRYING_ONCE] Robot initialized", flush=True)
    print(f"ROBOT_TCP: {get_tcp()}", flush=True)
    print(f"ROBOT_TOOL: {get_tool()}", flush=True)
    print(f"ROBOT_MODE: {get_robot_mode()}", flush=True)
    print(f"VELOCITY: {VELOCITY}", flush=True)
    print(f"ACC: {ACC}", flush=True)
    print("#" * 50, flush=True)


# ============================================================
# 실제 튀김 작업
# ============================================================

def perform_strainer_task():
    from DSR_ROBOT2 import (
        posx,
        movej,
        movel,
        set_digital_output,
        wait,
        move_periodic,
        amove_periodic,
        mwait,
        check_motion,
        amovej
    )
    from dsr_msgs2.srv import MovePause, MoveResume

    # ------------------------------------------------------------
    # move_pause / move_resume service helper
    # - DSR_ROBOT2.py in this environment does not export motion_pause().
    # - MovePause / MoveResume are ROS2 service types, so they must be
    #   called through a service client with MovePause.Request(), not MovePause().
    # ------------------------------------------------------------
    motion_node = DR_init.__dsr__node
    if motion_node is None:
        raise RuntimeError("DR_init.__dsr__node is None")

    pause_client = motion_node.create_client(
        MovePause,
        f"/{ROBOT_ID}/motion/move_pause"
    )
    resume_client = motion_node.create_client(
        MoveResume,
        f"/{ROBOT_ID}/motion/move_resume"
    )

    def call_motion_service(client, request, service_name, timeout_sec=2.0):
        if not client.wait_for_service(timeout_sec=timeout_sec):
            raise RuntimeError(
                f"/{ROBOT_ID}/motion/{service_name} service is not available"
            )

        future = client.call_async(request)
        rclpy.spin_until_future_complete(
            motion_node,
            future,
            timeout_sec=timeout_sec
        )

        if not future.done():
            raise RuntimeError(f"{service_name} service call timeout")

        result = future.result()
        if result is None:
            raise RuntimeError(f"{service_name} service returned None")

        if hasattr(result, "success") and not result.success:
            raise RuntimeError(f"{service_name} service failed: {result}")

        return result

    def motion_pause_service():
        return call_motion_service(
            pause_client,
            MovePause.Request(),
            "move_pause"
        )

    def motion_resume_service():
        return call_motion_service(
            resume_client,
            MoveResume.Request(),
            "move_resume"
        )

    print("=== Strainer Task Start ===", flush=True)

    p_place_down = posx([193.317, 23.735, 34.454, 47.065, 176.508, 47.77])

    dish_waypoint_1_l = posx([
        653.895, -9.928, 32.000,
        58.673, -178.530, 60.363
    ])

    dish_waypoint_1_up_l = posx([
        653.895, -9.928, 100.000,
        58.673, -178.530, 60.363
    ])

    dish_waypoint_2_up_l = posx([
        424.022, 13.806, 100.000,
        52.135, -178.383, 53.607
    ])

    dish_waypoint_3_l = posx([
        416.194, -131.309, 100.00,
        88.846, -174.714, 90.252
    ])

    dish_waypoint_3_j = [
        -14.518, 13.578, 101.484,
        -5.831, 63.863, -10.232
    ]

    dish_waypoint_3_down_l = posx([
        416.194, -131.309, 31.099,
        88.846, -174.714, 90.252
    ])

    dish_transform_0_j = [
        -43.456, 26.727, 94.757,
        66.389, 122.759, -37.768
    ]

    dish_transform_2_j = [
        -49.839, 64.488, 72.255,
        50.029, 120.368, -57.936
    ]

    dish_transform_3_j = [
        -21.519, 34.655, 79.158,
        65.811, 124.187, -35.117
    ]

    flip_waypoint1_j = [
        132.34, 23.932, 133.036,
        97.799, 82.948, -82.875
    ]

    flip_waypoint2_j = [
        132.337, 22.172, 132.647,
        98.186, 82.018, -186.105
    ]

    flip_waypoint3_j = [
        132.337, 21.443, 132.652,
        98.187, 82.01, -235.088
    ]

    flip_bwaypoint5_j = [
        90.863, 24.032, 108.272,
        67.344, 108.939, -52.572
    ]

    p_origin_j = [0, 0, 90, 0, 90, 0]

    p_1_waypoint_j = [
        100.258, 2.233, 87.887,
        0.029, 89.844, 99.966
    ]

    p_2_grip_tcp = posx([
        -443.197, 94.264, 85.817,
        134.029, -177.864, 44.456
    ])

    p_2_grip_transform_tcp = posx([
        -451.11, 80.424, 111.076,
        90.876, -167.131, 0.757
    ])

    p_2_grip_transform_j = [
        159.636, 16.953, 84.686,
        11.99, 83.166, 67.942
    ]

    p_2_grip_z_j = [
        148.486, 15.717, 67.617,
        23.901, 103.393, 66.167
    ]

    p_2_grip_lift_tcp = posx([
        -444.656, 93.849, 225.297,
        121.764, 178.043, 32.295
    ])

    p_3_after_grip_j = [
        104.877, 32.231, 55.425,
        0.691, 91.999, 18.986
    ]

    p_4_fryer_approach_j = [
        65.991, -2.709, 119.494,
        1.267, 46.923, -203.516
    ]

    p_5_fryer_down_tcp = posx([
        163.689, 421.866, -155.425,
        69.264, 163.989, 160.091
    ])

    p_5_fryer_down_tcp_after = posx([
        163.689, 430.866, -145.425,
        69.264, 163.989, 160.091
    ])

    p_6_after_place_tcp = posx([
        161.100, 462.868, 150.170,
        71.320, 164.196, 161.661
    ])

    a_oil_shake = [0, 0, 20, 0, 0, 0]

    def grip_tray():
        print("Gripper Close", flush=True)
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        set_digital_output(3, ON)
        safe_wait(wait, 1.5)
        check_stop()

    def grip_mesh():
        print("Gripper Close / Grip", flush=True)
        set_digital_output(1, ON)
        set_digital_output(2, OFF)
        set_digital_output(3, ON)
        safe_wait(wait, GRIP_WAIT)
        check_stop()

    def release():
        print("Gripper Open / Release", flush=True)
        set_digital_output(2, ON)
        set_digital_output(1, OFF)
        set_digital_output(3, OFF)
        safe_wait(wait, RELEASE_WAIT)
        check_stop()

    check_stop()

    print("0. movej → origin", flush=True)
    movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Dish 1. movel → dish_waypoint_1", flush=True)
    movel(dish_waypoint_1_l, vel=VELOCITY, acc=ACC)
    check_stop()

    print("Dish 2. grip at dish_waypoint_1", flush=True)
    grip_tray()
    check_stop()

    print("Dish 3. movel → dish_waypoint_1_y_up", flush=True)
    movel(dish_waypoint_1_up_l, vel=LIFT_VELOCITY, acc=LIFT_ACC)
    check_stop()

    print("Dish 4. movel → dish_waypoint_2_same_z", flush=True)
    movel(dish_waypoint_2_up_l, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Dish 5. movej → dish_waypoint_3_same_z", flush=True)
    movej(dish_waypoint_3_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Dish 6. movel → dish_waypoint_3_down", flush=True)
    movel(dish_waypoint_3_down_l, vel=VELOCITY, acc=ACC, r=0)
    check_stop()

    print("Dish 7. release at dish_waypoint_3", flush=True)
    release()
    check_stop()

    print("0. movej → origin", flush=True)
    movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("after origin gripper transform", flush=True)
    movej(dish_transform_0_j, vel=VELOCITY, acc=ACC, r=0)
    check_stop()

    print("setting new gripper shape", flush=True)
    movej(dish_transform_2_j, vel=VELOCITY, acc=ACC, r=0)
    check_stop()

    print("Dish 9. grip at dish_transform_1", flush=True)
    grip_tray()
    check_stop()

    print("Dish 10. movej → dish_transform_3", flush=True)
    movej(dish_transform_3_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Flip 전 경유 위치 5 이동", flush=True)
    movej(flip_bwaypoint5_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Flip waypoint 1 이동", flush=True)
    movej(flip_waypoint1_j, vel=SLOW_VELOCITY, acc=FLIP, r=20)
    check_stop()

    # flip waypoint 2까지 가는 시간이 약 1.8초라고 했으므로 time 기반으로 맞춤
    FLIP_WP2_TIME = 1.8

    # 1.8초 중간 부근에서 정지
    # 너무 늦게 멈추면 이미 물건이 튕길 수 있으니 0.75~0.95 사이에서 튜닝 추천
    FLIP_PAUSE_AT = 0.4 #0.4

    # 정지 유지 시간
    # 처음에는 0.18초 정도로 시작하고, 물건이 여전히 튀면 0.25~0.35로 증가
    FLIP_DWELL = 0.8   # 0.18

    flip_paused = False

    try:
        # 비동기 MoveJ 시작
        # amovej에는 r 파라미터를 넣지 않음
        amovej(
            flip_waypoint2_j,
            vel=SLOW_VELOCITY,
            acc=SLOW_ACC,
            t=FLIP_WP2_TIME
        )

        # flip 진행 중 중간 지점까지 기다림
        safe_wait(wait, FLIP_PAUSE_AT, step=0.02)
        check_stop()

        # check_motion:
        # 0 = 수행 중인 모션 없음
        # 1 = 모션 연산 중
        # 2 = 모션 수행 중
        motion_state = check_motion()

        if motion_state in (1, 2):
            print("Flip 중간 pause", flush=True)

            motion_pause_service()
            flip_paused = True

            try:
                safe_wait(wait, FLIP_DWELL, step=0.01)
                check_stop()
            finally:
                if flip_paused:
                    motion_resume_service()
                    flip_paused = False

        # 다음 movej를 보내기 전에 비동기 모션 종료 대기
        mwait(0)
        check_stop()

    except StopRequestedException:
        # STOP이 pause 중에 들어오면 pause 상태만 풀고 상위 STOP 처리로 넘김
        if flip_paused:
            try:
                motion_resume_service()
            except Exception as e:
                print(f"[FRYING_ONCE] move_resume during STOP failed: {e}", flush=True)
        raise

    print("Flip waypoint 3 이동", flush=True)
    movej(flip_waypoint3_j, vel=V_F, acc=FLIP, r=10)
    check_stop()

    print("Flip 복귀 waypoint 3 이동", flush=True)
    movej(flip_waypoint3_j, vel=VELOCITY, acc=ACC, r=10)
    check_stop()

    print("Flip 복귀 waypoint 2 이동", flush=True)
    movej(flip_waypoint2_j, vel=VELOCITY, acc=ACC, r=10)
    check_stop()

    print("Flip 복귀 waypoint 1 이동", flush=True)
    movej(flip_waypoint1_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Flip 후 경유 위치 5 복귀", flush=True)
    movej(flip_bwaypoint5_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Dish 10. movej → dish_transform_3", flush=True)
    movej(dish_transform_3_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("setting new gripper shape", flush=True)
    movej(dish_transform_2_j, vel=VELOCITY, acc=ACC, r=0)
    check_stop()

    print("Dish 7. release at dish_waypoint_3", flush=True)
    release()
    check_stop()

    print("after origin gripper transform", flush=True)
    movej(dish_transform_0_j, vel=VELOCITY, acc=ACC, r=0)
    check_stop()

    print("0. movej → origin", flush=True)
    movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("Dish 5. movel → dish_waypoint_3_same_z", flush=True)
    movel(dish_waypoint_3_l, vel=VELOCITY, acc=ACC, r=10)
    check_stop()

    print("Dish 6. movel → dish_waypoint_3_down", flush=True)
    movel(dish_waypoint_3_down_l, vel=VELOCITY, acc=ACC, r=0)
    check_stop()

    print("Dish 9. grip at dish_transform_1", flush=True)
    grip_tray()
    check_stop()

    print("0. movej → origin", flush=True)
    movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("내려가라", flush=True)
    movel(p_place_down, vel=VELOCITY, acc=ACC)
    check_stop()

    print("1. release gripper", flush=True)
    release()
    check_stop()

    print("0. movej → origin", flush=True)
    movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()
 # =====================여기까지가 플립==========

    print("2. movej → waypoint 1", flush=True)
    movej(p_1_waypoint_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("2-1. movel → grip safe down", flush=True)                # 바꾸기
    movel(p_2_grip_lift_tcp, vel=LIFT_VELOCITY, acc=LIFT_ACC, r=0)
    check_stop()

    print("3. movel → grip strainer position", flush=True)          # 바꾸기 
    movel(p_2_grip_tcp, vel=SLOW_VELOCITY, acc=SLOW_ACC)
    check_stop()

    print("4. grip strainer", flush=True)
    grip_mesh()
    check_stop()

    print("4-1. movel → grip transform", flush=True)   #자세조정 
    movej(p_2_grip_transform_j, vel=LIFT_VELOCITY, acc=LIFT_ACC, r=0)
    check_stop()


    # print("4-1. movel → grip safe lift", flush=True)
    # movel(p_2_grip_lift_tcp, vel=LIFT_VELOCITY, acc=LIFT_ACC, r=0)
    # check_stop()

    print("5. movej → after grip waypoint", flush=True)
    movej(p_3_after_grip_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("6. movej → fryer approach waypoint", flush=True)
    movej(p_4_fryer_approach_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("7. movel → fryer down / place strainer", flush=True)
    movel(p_5_fryer_down_tcp, vel=FRYER_VELOCITY, acc=FRYER_ACC, r=0)
    check_stop()

    print("8. release strainer in fryer", flush=True)
    release()
    check_stop()

    print("9. movel → after place waypoint", flush=True)
    movel(p_6_after_place_tcp, vel=FRYER_VELOCITY, acc=FRYER_ACC, r=0)
    check_stop()

    print(f"10. cooking wait: {COOKING_TIME} sec", flush=True)
    for _ in range(COOKING_TIME):
        safe_wait(wait, 1.0)
        check_stop()

    print("11. movel → fryer down for re-grip", flush=True)
    movel(p_5_fryer_down_tcp_after, vel=FRYER_VELOCITY, acc=FRYER_ACC)
    check_stop()

    print("12. grip strainer again", flush=True)
    grip_mesh()
    check_stop()

    print("12-1. movel → lift strainer from fryer", flush=True)
    movel(p_6_after_place_tcp, vel=FRYER_VELOCITY, acc=FRYER_ACC, r=0)
    check_stop()

    safe_wait(wait, 0.3)
    check_stop()

    print("13. move_periodic → oil shaking at lifted position", flush=True)

    # 기존 move_periodic 틀 유지: period / atime / repeat 값은 그대로 사용
    # 중간에 pause를 넣기 위해 같은 모션의 비동기 버전만 사용
    PERIOD = 0.4
    ATIME = 0.2

    # 안전한 '탁!' 느낌용 파라미터
    # 한 주기마다 1번만 짧게 멈춤
    TAP_DWELL = 0.04
    FIRST_TAP_DELAY = 0.30
    TAP_INTERVAL = PERIOD
    TAP_COUNT = SHAKE_REPEAT

    tap_paused = False

    try:
        amove_periodic(
            amp=a_oil_shake,
            period=PERIOD,
            atime=ATIME,
            repeat=SHAKE_REPEAT
        )

        safe_wait(wait, FIRST_TAP_DELAY, step=0.02)
        check_stop()

        for i in range(TAP_COUNT):
            check_stop()

            motion_state = check_motion()

            # 0: 수행 중인 모션 없음
            if motion_state == 0:
                break

            # 2: 모션 수행 중일 때만 pause/resume
            if motion_state == 2:
                motion_pause_service()
                tap_paused = True

                try:
                    safe_wait(wait, TAP_DWELL, step=0.01)
                    check_stop()
                finally:
                    if tap_paused:
                        motion_resume_service()
                        tap_paused = False

            if i < TAP_COUNT - 1:
                safe_wait(wait, TAP_INTERVAL, step=0.02)
                check_stop()

        # 다음 movej/movel 전에 비동기 periodic 종료 대기
        # 중요: mwait(0)은 for문 안이 아니라 for문 밖에 있어야 함
        mwait(0)
        check_stop()

    except StopRequestedException:
        # pause 상태에서 STOP이 들어온 경우, service class를 직접 호출하지 말고
        # resume service로 pause 상태만 풀어준 뒤 상위 STOP 처리로 넘긴다.
        if tap_paused:
            try:
                motion_resume_service()
            except Exception as e:
                print(f"[FRYING_ONCE] move_resume during STOP failed: {e}", flush=True)
        raise

    safe_wait(wait, 0.5)
    check_stop()

    print("15. movej → after grip waypoint", flush=True)
    movej(p_3_after_grip_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("16. movej → original place position_z", flush=True)
    movej(p_2_grip_z_j, vel=VELOCITY, acc=ACC)
    check_stop()

    print("16. movel → original place position", flush=True)
    movel(p_2_grip_tcp, vel=VELOCITY, acc=ACC)
    check_stop()

    print("17. release strainer at original position", flush=True)
    release()
    check_stop()

    print("18. movel → place safe lift", flush=True)
    movel(p_2_grip_lift_tcp, vel=LIFT_VELOCITY, acc=LIFT_ACC, r=0)
    check_stop()

    print("20. movej → origin", flush=True)
    movej(p_origin_j, vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("=== Strainer Task Finished ===", flush=True)


# ============================================================
# 안전 종료
# ============================================================

def safe_release_outputs():
    try:
        from DSR_ROBOT2 import set_digital_output

        print("[FRYING_ONCE] safe_release_outputs()", flush=True)

        set_digital_output(2, ON)
        set_digital_output(1, OFF)
        set_digital_output(3, OFF)

    except Exception as e:
        print(f"[FRYING_ONCE] safe_release_outputs failed: {e}", flush=True)


def shutdown_node(node):
    try:
        safe_release_outputs()
    except Exception:
        pass

    try:
        if node is not None:
            node.destroy_node()
    except Exception as e:
        print(f"[FRYING_ONCE] destroy_node failed: {e}", flush=True)

    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception as e:
        print(f"[FRYING_ONCE] rclpy.shutdown failed: {e}", flush=True)


# ============================================================
# main
# ============================================================

def main(args=None):
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    node = None

    try:
        print("[FRYING_ONCE] rclpy.init()", flush=True)
        rclpy.init(args=args)

        print("[FRYING_ONCE] create_node()", flush=True)
        node = rclpy.create_node("frying_task_once", namespace=ROBOT_ID)

        DR_init.__dsr__node = node

        initialize_robot()
        check_stop()

        perform_strainer_task()

        print("[FRYING_ONCE] Frying task completed successfully", flush=True)

        shutdown_node(node)
        sys.exit(0)

    except StopRequestedException:
        print("[FRYING_ONCE] Frying task stopped by user", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except KeyboardInterrupt:
        print("[FRYING_ONCE] KeyboardInterrupt received", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except Exception as e:
        print(f"[FRYING_ONCE] Frying task failed: {e}", flush=True)
        traceback.print_exc()
        shutdown_node(node)
        sys.exit(1)


if __name__ == "__main__":
    main()