#!/usr/bin/env python3

import signal
import sys
import time
import csv
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

# 일반 이동 속도 / 가속도
VELOCITY = 80
ACC = 40

# 입/눈 그리기용 속도 / 가속도
DRAW_VEL = 25
DRAW_ACC = 50

# 안전 상승 높이
SAFE_Z_OFFSET = 0.0

# 입 경로 point 줄이기
MOUTH_SKIP = 2

# 입 경로 movel 블렌딩 반경
MOUTH_BLEND_R = 1

# 디지털 출력 상태
ON, OFF = 1, 0

# CSV 경로
# 기존 코드가 /home/ccw/cobot_ws/src/cobot1/... 를 사용하고 있었음.
# 현재 패키지가 cobot1_project라면 아래 경로가 맞는지 확인 필요.
# CSV_PATH = "/home/ccw/cobot_ws/src/cobot1_project/sauce_robot_points2.csv"
CSV_PATH ="/home/eycho/g2_2_ws/src/cobot1_project/sauce_robot_points2.csv"

# False: 소스 안 짜고 경로만 확인
# True : 실제 소스 사출
ENABLE_KETCHUP = True

# 소스 사출 튜닝값
EYE_SQUEEZE_TIME = 0.50
LINE_PRIME_TIME = 0.08

# DR_init 설정
DR_init.__dsr__id = ROBOT_ID
DR_init.__dsr__model = ROBOT_MODEL

# STOP 요청 플래그
stop_requested = False


# ==========================================================
# STOP 처리
# ==========================================================

class StopRequestedException(Exception):
    pass


def signal_handler(signum, frame):
    global stop_requested

    print(f"[SAUCING_ONCE] Signal received: {signum}", flush=True)
    stop_requested = True


def check_stop():
    if stop_requested:
        print("[SAUCING_ONCE] STOP detected. Abort saucing task.", flush=True)
        raise StopRequestedException("STOPPED_BY_USER")


def safe_wait(wait_func, seconds, step=0.2):
    """
    긴 wait 중에도 STOP 신호를 조금 더 빨리 반영하기 위한 분할 wait.
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
# 로봇 초기 설정
# ==========================================================

def initialize_robot():
    """로봇 초기 설정"""
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
    print("[SAUCING_ONCE] Initializing robot", flush=True)
    print(f"ROBOT_ID: {ROBOT_ID}", flush=True)
    print(f"ROBOT_MODEL: {ROBOT_MODEL}", flush=True)
    print(f"ROBOT_TOOL: {ROBOT_TOOL}", flush=True)
    print(f"ROBOT_TCP: {ROBOT_TCP}", flush=True)
    print("#" * 50, flush=True)

    set_robot_mode(ROBOT_MODE_MANUAL)
    time.sleep(0.5)

    set_tool(ROBOT_TOOL)
    set_tcp(ROBOT_TCP)

    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    time.sleep(2.0)

    print("#" * 50, flush=True)
    print("[SAUCING_ONCE] Robot initialized", flush=True)
    print(f"ROBOT_ID: {ROBOT_ID}", flush=True)
    print(f"ROBOT_MODEL: {ROBOT_MODEL}", flush=True)
    print(f"ROBOT_TCP: {get_tcp()}", flush=True)
    print(f"ROBOT_TOOL: {get_tool()}", flush=True)
    print(f"ROBOT_MODE (0:수동, 1:자동): {get_robot_mode()}", flush=True)
    print(f"VELOCITY: {VELOCITY}", flush=True)
    print(f"ACC: {ACC}", flush=True)
    print(f"DRAW_VEL: {DRAW_VEL}", flush=True)
    print(f"DRAW_ACC: {DRAW_ACC}", flush=True)
    print(f"MOUTH_SKIP: {MOUTH_SKIP}", flush=True)
    print(f"MOUTH_BLEND_R: {MOUTH_BLEND_R}", flush=True)
    print(f"ENABLE_KETCHUP: {ENABLE_KETCHUP}", flush=True)
    print("#" * 50, flush=True)


# ==========================================================
# CSV 로드
# ==========================================================

def load_draw_commands(csv_path):
    dots = []
    mouth_points = []

    print(f"[SAUCING_ONCE] Loading CSV: {csv_path}", flush=True)

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            check_stop()

            cmd_type = row["type"]
            name = row["name"]

            point = {
                "type": cmd_type,
                "name": name,
                "point_id": int(row["point_id"]),
                "x": float(row["robot_x"]),
                "y": float(row["robot_y"]),
                "z": float(row["robot_z"]),
                "rx": float(row["rx"]),
                "ry": float(row["ry"]),
                "rz": float(row["rz"]),
            }

            if cmd_type == "dot":
                dots.append(point)

            elif cmd_type == "path" and name == "mouth":
                mouth_points.append(point)

    # 눈은 left → right 순서
    dots = sorted(dots, key=lambda p: p["name"])

    # 입은 point_id 순서대로 이동
    mouth_points = sorted(mouth_points, key=lambda p: p["point_id"])

    # 입 경로 waypoint 줄이기
    if MOUTH_SKIP > 1 and len(mouth_points) > 2:
        original_count = len(mouth_points)

        reduced = mouth_points[::MOUTH_SKIP]

        # 마지막 점은 반드시 포함
        if reduced[-1]["point_id"] != mouth_points[-1]["point_id"]:
            reduced.append(mouth_points[-1])

        mouth_points = reduced

        print(
            f"[SAUCING_ONCE][MOUTH REDUCE] {original_count} -> {len(mouth_points)} points",
            flush=True
        )

    print(
        f"[SAUCING_ONCE] CSV loaded: dots={len(dots)}, mouth_points={len(mouth_points)}",
        flush=True
    )

    return dots, mouth_points


# ==========================================================
# posx 변환
# ==========================================================

def make_pos(point, z_offset=0.0):
    from DSR_ROBOT2 import posx

    return posx([
        point["x"],
        point["y"],
        point["z"] + z_offset,
        point["rx"],
        point["ry"],
        point["rz"]
    ])


# ==========================================================
# 그리퍼 / 소스통 상태 제어
# ==========================================================

def release():
    from DSR_ROBOT2 import set_digital_output

    print("[SAUCING_ONCE] release", flush=True)

    set_digital_output(3, OFF)
    set_digital_output(2, ON)
    set_digital_output(1, OFF)

    check_stop()


def grip_source():
    from DSR_ROBOT2 import set_digital_output

    print("[SAUCING_ONCE] grip_source", flush=True)

    if ENABLE_KETCHUP:
        set_digital_output(2, OFF)
        set_digital_output(3, ON) 
        set_digital_output(1, OFF)

    check_stop()


def grip_squeeze_weak():
    from DSR_ROBOT2 import set_digital_output

    print("[SAUCING_ONCE] grip_squeeze_weak", flush=True)

    if ENABLE_KETCHUP:
        set_digital_output(3, ON)
        set_digital_output(2, ON)
        set_digital_output(1, OFF)

    check_stop()


# ==========================================================
# 이동 / 그리기 함수
# ==========================================================

def move_to_point(point, z_offset=0.0, vel=VELOCITY, acc=ACC, r=0):
    from DSR_ROBOT2 import movel

    check_stop()

    movel(
        make_pos(point, z_offset=z_offset),
        vel=vel,
        acc=acc,
        r=r
    )

    check_stop()


def draw_dot(point):
    from DSR_ROBOT2 import wait

    print(f"[SAUCING_ONCE] Drawing dot: {point['name']}", flush=True)

    check_stop()

    move_to_point(
        point,
        z_offset=SAFE_Z_OFFSET,
        vel=VELOCITY,
        acc=ACC,
        r=0
    )

    move_to_point(
        point,
        z_offset=-70.0,
        vel=DRAW_VEL,
        acc=DRAW_ACC,
        r=0
    )

    # 기존 코드 wait(3)은 너무 길어 STOP 반응이 느릴 수 있어 safe_wait로 분할
    safe_wait(wait, EYE_SQUEEZE_TIME)

    grip_squeeze_weak()

    safe_wait(wait, 0.3)

    grip_source()

    safe_wait(wait, 0.5)

    move_to_point(
        point,
        z_offset=SAFE_Z_OFFSET,
        vel=VELOCITY,
        acc=ACC,
        r=0
    )

    check_stop()


def draw_mouth_path(mouth_points):
    from DSR_ROBOT2 import movel, wait

    if not mouth_points:
        raise RuntimeError("mouth_points가 비어 있음")

    start = mouth_points[0]
    end = mouth_points[-1]

    print("[SAUCING_ONCE] Drawing mouth path...", flush=True)
    print(f"[SAUCING_ONCE] mouth point count: {len(mouth_points)}", flush=True)
    print(
        f"[SAUCING_ONCE] mouth start: {start['x']:.3f}, {start['y']:.3f}, {start['z']:.3f}",
        flush=True
    )
    print(
        f"[SAUCING_ONCE] mouth end  : {end['x']:.3f}, {end['y']:.3f}, {end['z']:.3f}",
        flush=True
    )

    check_stop()

    # 시작점 상공 이동
    move_to_point(
        start,
        z_offset=SAFE_Z_OFFSET,
        vel=VELOCITY,
        acc=ACC,
        r=0
    )

    # 시작점으로 하강
    move_to_point(
        start,
        z_offset=-70.0,
        vel=DRAW_VEL,
        acc=DRAW_ACC,
        r=0
    )

    # 소스 사출 시작
    safe_wait(wait, LINE_PRIME_TIME)

    grip_squeeze_weak()

    # 이미 start 지점에 있으므로 mouth_points[1:]부터 이동
    for idx, point in enumerate(mouth_points[1:], start=1):
        check_stop()

        print(
            f"[SAUCING_ONCE] mouth point {idx}/{len(mouth_points) - 1}",
            flush=True
        )

        movel(
            make_pos(point, z_offset=-70.0),
            vel=DRAW_VEL,
            acc=DRAW_ACC,
            r=MOUTH_BLEND_R
        )

        check_stop()

    # 소스 사출 정지
    grip_source()

    # 끝점 상공으로 상승
    move_to_point(
        end,
        z_offset=SAFE_Z_OFFSET,
        vel=VELOCITY,
        acc=ACC,
        r=0
    )

    check_stop()


def draw_smile_from_csv(csv_path):
    """
    CSV를 읽어서 웃는 얼굴을 그린다.
    """
    print("[SAUCING_ONCE] draw_smile_from_csv start", flush=True)

    dots, mouth_points = load_draw_commands(csv_path)

    print("#" * 50, flush=True)
    print("[SAUCING_ONCE] Loaded drawing commands", flush=True)
    print(f"dot count: {len(dots)}", flush=True)
    print(f"mouth point count after reduce: {len(mouth_points)}", flush=True)
    print(f"ENABLE_KETCHUP: {ENABLE_KETCHUP}", flush=True)
    print("#" * 50, flush=True)

    if len(dots) != 2:
        print("[SAUCING_ONCE][WARNING] dot 개수가 2개가 아님. CSV 확인 필요.", flush=True)

    if len(mouth_points) < 2:
        raise RuntimeError("입 경로 point가 부족함.")

    for dot in dots:
        check_stop()
        draw_dot(dot)

    check_stop()

    draw_mouth_path(mouth_points)

    print("[SAUCING_ONCE] draw_smile_from_csv finished", flush=True)


# ==========================================================
# Waypoint 정리
# ==========================================================

P = {
    "origin_j": [
        0, 0, 90, 0, 90, 0
    ],

    "source_pick_ready_j": [
        -29.822, 28.039, 106.876,
        -37.449, -48.947, 116.555
    ],

    "source_pick": [
        823.214, -233.323, 220.976,
        179.674, -88.173, -89.296
    ],

    "source_pick_up": [
        823.214, -233.323, 300.976,
        179.674, -88.173, -89.296
    ],

    "source_pick_ready_up": [
        693.153, -223.323, 300.976,
        179.674, -88.173, -89.296
    ],

    "source_pick_ready_up_j": [
        -31.347, 14.092, 111.199,
        -43.935, -41.312, 125.357
    ],

    "source_squeeze_ready_up2_j": [
        -42.584, 30.075, 107.975,
        50.335, 116.74, -77.294
    ],

    "source_squeeze_ready_down2_j": [
        -42.768, 30.369, 108.246,
        50.339, 116.378, -236.985
    ],
}


# ==========================================================
# Pick / Move / Place 함수화
# ==========================================================

def pick_source():
    from DSR_ROBOT2 import movej, movel, wait

    print("[SAUCING_ONCE] pick_source start", flush=True)

    check_stop()

    print("[SAUCING_ONCE] movej → origin", flush=True)
    movej(P["origin_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    release()

    safe_wait(wait, 0.5)

    print("[SAUCING_ONCE] movej → source_pick_ready", flush=True)
    movej(P["source_pick_ready_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movel → source_pick", flush=True)
    movel(P["source_pick"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    safe_wait(wait, 1.0)

    grip_source()

    safe_wait(wait, 0.5)

    print("[SAUCING_ONCE] movel → source_pick_up", flush=True)
    movel(P["source_pick_up"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    # 기존 코드는 source_pick_ready_up을 movel로 이동했음.
    # 다만 place_source에서는 source_pick_ready_up_j를 movej로 사용하므로,
    # 충돌 가능성이 있다면 아래 movel 대신 movej(P["source_pick_ready_up_j"])를 사용할 수 있음.
    print("[SAUCING_ONCE] movel → source_pick_ready_up", flush=True)
    movel(P["source_pick_ready_up"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] pick_source finished", flush=True)


def move_to_donkatsu_center():
    """
    소스통을 들고 돈까스 중심 그리기 시작 pose 근처로 이동.
    """
    from DSR_ROBOT2 import movej

    print("[SAUCING_ONCE] move_to_donkatsu_center start", flush=True)

    check_stop()

    print("[SAUCING_ONCE] movej → origin", flush=True)
    movej(P["origin_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movej → source_squeeze_ready_up", flush=True)
    movej(P["source_squeeze_ready_up2_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movej → source_squeeze_ready_down", flush=True)
    movej(P["source_squeeze_ready_down2_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] move_to_donkatsu_center finished", flush=True)


def place_source():
    """
    소스통 반납 시퀀스.
    release 후에는 먼저 직선 상승한 뒤 movej 수행.
    """
    from DSR_ROBOT2 import movej, movel, wait

    print("[SAUCING_ONCE] place_source start", flush=True)

    check_stop()

    print("[SAUCING_ONCE] movej → origin", flush=True)
    movej(P["origin_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movej → source_pick_ready_up", flush=True)
    movej(P["source_pick_ready_up_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movel → source_pick_up", flush=True)
    movel(P["source_pick_up"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movel → source_pick", flush=True)
    movel(P["source_pick"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    safe_wait(wait, 0.5)

    release()

    safe_wait(wait, 0.5)

    print("[SAUCING_ONCE] movel → source_pick_up", flush=True)
    movel(P["source_pick_up"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movej → source_pick_ready_up", flush=True)
    movej(P["source_pick_ready_up_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] movej → origin", flush=True)
    movej(P["origin_j"], vel=VELOCITY, acc=ACC, r=20)
    check_stop()

    print("[SAUCING_ONCE] place_source finished", flush=True)


# ==========================================================
# 안전 출력 해제
# ==========================================================

def safe_release_outputs():
    """
    종료/중단/오류 시 그리퍼 출력이 애매하게 남지 않도록 release 상태로 정리.
    """
    try:
        from DSR_ROBOT2 import set_digital_output

        print("[SAUCING_ONCE] safe_release_outputs()", flush=True)

        set_digital_output(1, OFF)
        set_digital_output(2, ON)
        set_digital_output(3, OFF)

    except Exception as e:
        print(f"[SAUCING_ONCE] safe_release_outputs failed: {e}", flush=True)


def shutdown_node(node):
    try:
        safe_release_outputs()
    except Exception:
        pass

    try:
        if node is not None:
            node.destroy_node()
    except Exception as e:
        print(f"[SAUCING_ONCE] destroy_node failed: {e}", flush=True)

    try:
        if rclpy.ok():
            rclpy.shutdown()
    except Exception as e:
        print(f"[SAUCING_ONCE] rclpy.shutdown failed: {e}", flush=True)


# ==========================================================
# 메인 task 로직
# ==========================================================

def perform_task():
    print("[SAUCING_ONCE] Saucing task started", flush=True)

    check_stop()

    pick_source()

    check_stop()

    move_to_donkatsu_center()

    check_stop()

    draw_smile_from_csv(CSV_PATH)

    check_stop()

    place_source()

    check_stop()

    print("[SAUCING_ONCE] Saucing task finished", flush=True)


# ==========================================================
# main
# ==========================================================

def main(args=None):
    global stop_requested

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    node = None

    try:
        print("[SAUCING_ONCE] rclpy.init()", flush=True)
        rclpy.init(args=args)

        print("[SAUCING_ONCE] create_node()", flush=True)
        node = rclpy.create_node("saucing_task_once", namespace=ROBOT_ID)

        DR_init.__dsr__node = node

        initialize_robot()
        check_stop()

        perform_task()

        print("[SAUCING_ONCE] Saucing task completed successfully", flush=True)

        shutdown_node(node)
        sys.exit(0)

    except StopRequestedException:
        print("[SAUCING_ONCE] Saucing task stopped by user", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except KeyboardInterrupt:
        print("[SAUCING_ONCE] KeyboardInterrupt received", flush=True)
        shutdown_node(node)
        sys.exit(130)

    except Exception as e:
        print(f"[SAUCING_ONCE] Saucing task failed: {e}", flush=True)
        traceback.print_exc()
        shutdown_node(node)
        sys.exit(1)


if __name__ == "__main__":
    main()