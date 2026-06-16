#!/usr/bin/env python3

import os
import signal
import subprocess
import threading
import time

import rclpy
from std_srvs.srv import Trigger
from dsr_msgs2.srv import MoveStop
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup


# ==========================================================
# 설정
# ==========================================================

ROBOT_ID = "dsr01"
TASK_PACKAGE = "cobot1_project"

TASK_CONFIG = {
    "seasoning": {
        "display_name": "시즈닝",
        "executable": "seasoning_task_once",
        "start_service": "seasoning/start",
        "stop_service": "seasoning/stop",
        "success_message": "Seasoning completed successfully",
    },
    "tenderizing": {
        "display_name": "연육",
        "executable": "tenderizing_task_once",
        "start_service": "tenderizing/start",
        "stop_service": "tenderizing/stop",
        "success_message": "Tenderizing completed successfully",
    },
    "frying": {
        "display_name": "튀김",
        "executable": "frying_task_once",
        "start_service": "frying/start",
        "stop_service": "frying/stop",
        "success_message": "Frying completed successfully",
    },
    "saucing": {
        "display_name": "소스",
        "executable": "saucing_task_once",
        "start_service": "saucing/start",
        "stop_service": "saucing/stop",
        "success_message": "Saucing completed successfully",
    },
    "recovery": {
        "display_name": "복구",
        "executable": "recovery_task_once",
        "start_service": "recovery/start",
        "stop_service": "recovery/stop",
        "success_message": "Recovery completed successfully",
    },
}


# ==========================================================
# 즉시 정지 설정
# ==========================================================

MOVE_STOP_SERVICE = "/dsr01/motion/move_stop"

# dsr_msgs2/srv/MoveStop
# Request: int32 stop_mode
# Response: bool success
MOVE_STOP_MODE = 0

MOVE_STOP_TIMEOUT = 1.0

# SIGSTOP 후 move_stop이 로봇 컨트롤러에 반영될 최소 시간
POST_FREEZE_DELAY = 0.02

# move_stop 후 SIGKILL까지 대기 시간
POST_MOVE_STOP_DELAY = 0.02

# SIGKILL 후 종료 확인 대기 시간
FORCE_KILL_TIMEOUT = 1.0


# ==========================================================
# 전역 상태
# ==========================================================

task_lock = threading.Lock()
current_process = None
current_task_key = None
stop_requested = False

move_stop_client = None


# ==========================================================
# move_stop client
# ==========================================================

def initialize_move_stop_client(node):
    """
    /dsr01/motion/move_stop service client 생성.
    STOP 요청 시 현재 로봇 컨트롤러에서 수행 중인 motion을 끊기 위해 사용한다.
    """
    global move_stop_client

    move_stop_client = node.create_client(
        MoveStop,
        MOVE_STOP_SERVICE
    )

    if move_stop_client.wait_for_service(timeout_sec=2.0):
        node.get_logger().info(
            f"[MOVE_STOP] Service ready: {MOVE_STOP_SERVICE}"
        )
    else:
        node.get_logger().warn(
            f"[MOVE_STOP] Service not ready yet: {MOVE_STOP_SERVICE}"
        )


def call_robot_move_stop(node):
    """
    현재 로봇 motion 정지 요청.

    주의:
    - move_stop은 이미 로봇 컨트롤러에 들어간 현재 motion을 멈추는 역할.
    - task_once process가 살아 있으면 다음 movej/movel을 다시 보낼 수 있으므로,
      STOP 시퀀스에서는 task process를 먼저 SIGSTOP으로 얼린 후 이 함수를 호출한다.
    """
    global move_stop_client

    if move_stop_client is None:
        node.get_logger().error("[MOVE_STOP] move_stop_client is None")
        return False

    if not move_stop_client.service_is_ready():
        node.get_logger().warn("[MOVE_STOP] Service not ready. Waiting briefly...")

        if not move_stop_client.wait_for_service(timeout_sec=0.5):
            node.get_logger().error("[MOVE_STOP] Service unavailable")
            return False

    req = MoveStop.Request()
    req.stop_mode = MOVE_STOP_MODE

    node.get_logger().warn(
        f"[MOVE_STOP] Calling {MOVE_STOP_SERVICE}, stop_mode={MOVE_STOP_MODE}"
    )

    future = move_stop_client.call_async(req)
    start_time = time.monotonic()

    while rclpy.ok():
        if future.done():
            break

        if time.monotonic() - start_time > MOVE_STOP_TIMEOUT:
            node.get_logger().error("[MOVE_STOP] Timeout waiting for response")
            return False

        time.sleep(0.01)

    if not future.done():
        node.get_logger().error("[MOVE_STOP] Future not done")
        return False

    try:
        result = future.result()

        if result is None:
            node.get_logger().error("[MOVE_STOP] Result is None")
            return False

        node.get_logger().warn(
            f"[MOVE_STOP] Response success={result.success}"
        )

        return bool(result.success)

    except Exception as e:
        node.get_logger().error(f"[MOVE_STOP] Failed: {e}")
        return False


# ==========================================================
# subprocess 관리
# ==========================================================

def build_task_command(task_key):
    executable = TASK_CONFIG[task_key]["executable"]

    return [
        "ros2",
        "run",
        TASK_PACKAGE,
        executable
    ]


def is_process_running():
    global current_process

    return current_process is not None and current_process.poll() is None


def kill_process_group(sig, sig_name):
    global current_process

    if current_process is None:
        return False

    if current_process.poll() is not None:
        return False

    try:
        pgid = os.getpgid(current_process.pid)
        print(f"[PROCESS] Sending {sig_name} to process group pgid={pgid}", flush=True)
        os.killpg(pgid, sig)
        return True

    except ProcessLookupError:
        print("[PROCESS] Process group already gone", flush=True)
        return False

    except Exception as e:
        print(f"[PROCESS] Failed to send {sig_name}: {e}", flush=True)
        return False


def wait_process_exit(timeout_sec):
    global current_process

    if current_process is None:
        return True

    try:
        current_process.wait(timeout=timeout_sec)
        return True

    except subprocess.TimeoutExpired:
        return False


def terminate_current_process():
    """
    일반 종료용 함수.

    서버 Ctrl+C, 예외 종료 등에서는 부드럽게 종료해도 되므로 기존 방식 유지.
    사용자 STOP 버튼에서는 이 함수를 쓰지 않고 force_stop_current_task()를 사용한다.
    """
    global current_process

    if current_process is None:
        print("[TERMINATE] No current process", flush=True)
        return

    if current_process.poll() is not None:
        print("[TERMINATE] Process already exited", flush=True)
        return

    print("[TERMINATE] Terminating current task process group...", flush=True)

    kill_process_group(signal.SIGINT, "SIGINT")

    if wait_process_exit(timeout_sec=3.0):
        print("[TERMINATE] Process group stopped by SIGINT", flush=True)
        return

    kill_process_group(signal.SIGTERM, "SIGTERM")

    if wait_process_exit(timeout_sec=3.0):
        print("[TERMINATE] Process group terminated by SIGTERM", flush=True)
        return

    kill_process_group(signal.SIGKILL, "SIGKILL")

    if wait_process_exit(timeout_sec=2.0):
        print("[TERMINATE] Process group killed by SIGKILL", flush=True)
        return

    print("[TERMINATE] WARNING: process group may still be alive", flush=True)


def freeze_current_process_group():
    """
    STOP 버튼을 누르는 즉시 task_once process group을 얼린다.

    SIGSTOP은 Python 코드에서 잡거나 무시할 수 없는 OS 레벨 정지 신호다.
    따라서 task_once가 다음 movej/movel/move_periodic 명령을 보내기 전에
    process를 강제로 정지시킬 수 있다.
    """
    global current_process

    if current_process is None:
        print("[STOP] No current process to freeze", flush=True)
        return False

    if current_process.poll() is not None:
        print("[STOP] Process already exited before freeze", flush=True)
        return False

    return kill_process_group(signal.SIGSTOP, "SIGSTOP")


def force_kill_current_process():
    """
    STOP 버튼용 강제 종료 함수.

    SIGSTOP으로 얼려둔 task_once process group을 SIGKILL로 제거한다.
    SIGKILL은 process가 잡거나 무시할 수 없다.
    """
    global current_process

    if current_process is None:
        print("[STOP] No current process to kill", flush=True)
        return

    if current_process.poll() is not None:
        print("[STOP] Process already exited before SIGKILL", flush=True)
        return

    print("[STOP] Force killing current task process group...", flush=True)

    kill_process_group(signal.SIGKILL, "SIGKILL")

    if wait_process_exit(timeout_sec=FORCE_KILL_TIMEOUT):
        print("[STOP] Process group killed by SIGKILL", flush=True)
        return

    print("[STOP] WARNING: process group may still be alive after SIGKILL", flush=True)


def force_stop_current_task(node):
    """
    사용자 STOP 버튼용 즉시 정지 시퀀스.

    핵심 순서:
    1. SIGSTOP
       - task_once process를 먼저 얼림
       - task_once가 다음 movej/movel을 보내지 못하게 차단

    2. /dsr01/motion/move_stop
       - 이미 로봇 컨트롤러에 들어간 현재 motion 정지

    3. SIGKILL
       - 얼려둔 task_once process group 제거
    """
    freeze_success = freeze_current_process_group()

    if freeze_success:
        node.get_logger().warn("[STOP] Task process frozen by SIGSTOP")
    else:
        node.get_logger().error(
            "[STOP] Failed to freeze task process. "
            "move_stop will still be called."
        )

    time.sleep(POST_FREEZE_DELAY)

    move_stop_success = call_robot_move_stop(node)

    if move_stop_success:
        node.get_logger().warn("[STOP] Robot move_stop success")
    else:
        node.get_logger().error(
            "[STOP] Robot move_stop failed or timeout. "
            "SIGKILL will still be sent."
        )

    time.sleep(POST_MOVE_STOP_DELAY)

    force_kill_current_process()

    return freeze_success, move_stop_success


def cleanup_leftover_processes():
    """
    이전 테스트에서 남은 task_once 프로세스를 정리한다.
    서버 시작 시 1회 수행.
    """
    print("[CLEANUP] Checking leftover task_once processes...", flush=True)

    patterns = [
        "seasoning_task_once",
        "tenderizing_task_once",
        "frying_task_once",
        "saucing_task_once",
        "recovery_task_once",
        "ros2 run cobot1_project seasoning_task_once",
        "ros2 run cobot1_project tenderizing_task_once",
        "ros2 run cobot1_project frying_task_once",
        "ros2 run cobot1_project saucing_task_once",
        "ros2 run cobot1_project recovery_task_once",
    ]

    for pattern in patterns:
        try:
            subprocess.run(
                ["pkill", "-f", pattern],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(f"[CLEANUP] pkill failed for pattern={pattern}: {e}", flush=True)

    time.sleep(0.5)
    print("[CLEANUP] Cleanup done", flush=True)


# ==========================================================
# Service callback factory
# ==========================================================

def make_start_callback(task_key):
    def start_callback(request, response):
        global current_process, current_task_key, stop_requested

        config = TASK_CONFIG[task_key]
        display_name = config["display_name"]

        print(f"[SERVICE] /{ROBOT_ID}/{config['start_service']} request received", flush=True)

        if not task_lock.acquire(blocking=False):
            response.success = False
            response.message = f"로봇이 이미 다른 작업을 수행 중입니다. current_task={current_task_key}"
            print(f"[SERVICE] Rejected: current_task={current_task_key}", flush=True)
            return response

        stop_requested = False
        current_process = None
        current_task_key = task_key

        try:
            task_command = build_task_command(task_key)

            print(f"[SERVICE] Starting {display_name} subprocess...", flush=True)
            print(f"[SERVICE] Command: {' '.join(task_command)}", flush=True)

            current_process = subprocess.Popen(
                task_command,
                stdout=None,
                stderr=None,
                stdin=subprocess.DEVNULL,
                start_new_session=True
            )

            while True:
                ret = current_process.poll()

                if ret is not None:
                    break

                time.sleep(0.1)

            print(f"[SERVICE] {display_name} subprocess finished. returncode={ret}", flush=True)

            if stop_requested:
                response.success = False
                response.message = "STOPPED_BY_USER"
                print(f"[SERVICE] {display_name} stopped by user", flush=True)

            elif ret == 0:
                response.success = True
                response.message = config["success_message"]
                print(f"[SERVICE] {display_name} completed successfully", flush=True)

            elif ret in [-signal.SIGINT, -signal.SIGTERM, -signal.SIGKILL, 130, 143]:
                response.success = False
                response.message = "STOPPED_BY_USER"
                print(f"[SERVICE] {display_name} interrupted/killed", flush=True)

            else:
                response.success = False
                response.message = f"{display_name} failed. returncode={ret}"
                print(f"[SERVICE] {display_name} failed. returncode={ret}", flush=True)

        except Exception as e:
            response.success = False
            response.message = f"{display_name} service error: {e}"
            print(f"[SERVICE] Exception in {display_name}: {e}", flush=True)

        finally:
            current_process = None
            current_task_key = None
            stop_requested = False

            if task_lock.locked():
                task_lock.release()

            print("[SERVICE] Ready for next task request", flush=True)

        return response

    return start_callback


def make_stop_callback(task_key, node):
    def stop_callback(request, response):
        global stop_requested

        config = TASK_CONFIG[task_key]
        display_name = config["display_name"]

        print(f"[SERVICE] /{ROBOT_ID}/{config['stop_service']} request received", flush=True)

        if not task_lock.locked() or not is_process_running():
            response.success = False
            response.message = f"현재 실행 중인 {display_name} 작업이 없습니다."
            print(f"[SERVICE] STOP rejected: no running {display_name} task", flush=True)
            return response

        if current_task_key != task_key:
            response.success = False
            response.message = f"현재 실행 중인 작업은 {current_task_key}입니다. {task_key} stop은 거부됩니다."
            print(
                f"[SERVICE] STOP rejected: requested={task_key}, current={current_task_key}",
                flush=True
            )
            return response

        # start_callback이 결과를 STOPPED_BY_USER로 해석하도록 플래그 설정
        stop_requested = True

        # ==================================================
        # 핵심 수정:
        # SIGSTOP → move_stop → SIGKILL
        # ==================================================
        freeze_success, move_stop_success = force_stop_current_task(node)

        if is_process_running():
            response.success = False
            response.message = "STOP_FAILED_PROCESS_STILL_RUNNING"
            print("[SERVICE] STOP failed: process still running", flush=True)
            return response

        response.success = True
        response.message = "STOP_REQUESTED"
        print(
            f"[SERVICE] STOP completed for {display_name} | "
            f"freeze_success={freeze_success}, "
            f"move_stop_success={move_stop_success}",
            flush=True
        )

        return response

    return stop_callback


def heartbeat_callback():
    running = is_process_running()
    print(
        f"[HEARTBEAT] all_task_service_server alive | "
        f"task_running={running} | current_task={current_task_key}",
        flush=True
    )


# ==========================================================
# main
# ==========================================================

def main(args=None):
    rclpy.init(args=args)

    node = rclpy.create_node("all_task_service_server", namespace=ROBOT_ID)

    callback_group = ReentrantCallbackGroup()

    try:
        initialize_move_stop_client(node)

        cleanup_leftover_processes()

        # 모든 task start/stop service 생성
        for task_key, config in TASK_CONFIG.items():
            node.create_service(
                Trigger,
                config["start_service"],
                make_start_callback(task_key),
                callback_group=callback_group
            )

            node.create_service(
                Trigger,
                config["stop_service"],
                make_stop_callback(task_key, node),
                callback_group=callback_group
            )

        node.heartbeat_timer = node.create_timer(
            2.0,
            heartbeat_callback,
            callback_group=callback_group
        )

        print("#" * 60, flush=True)
        print("All task subprocess service server is ready.", flush=True)
        print("Services:", flush=True)

        for task_key, config in TASK_CONFIG.items():
            print(f"  /{ROBOT_ID}/{config['start_service']}", flush=True)
            print(f"  /{ROBOT_ID}/{config['stop_service']}", flush=True)

        print("Service type: std_srvs/srv/Trigger", flush=True)
        print(f"Move stop service: {MOVE_STOP_SERVICE}", flush=True)
        print("Move stop type: dsr_msgs2/srv/MoveStop", flush=True)
        print("STOP sequence: SIGSTOP -> move_stop -> SIGKILL", flush=True)
        print("#" * 60, flush=True)

        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        executor.spin()

    except KeyboardInterrupt:
        print("\nInterrupted by user", flush=True)

        if is_process_running():
            terminate_current_process()

    except Exception as e:
        print(f"Error: {e}", flush=True)

        if is_process_running():
            terminate_current_process()

    finally:
        if is_process_running():
            terminate_current_process()

        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()