#!/usr/bin/env python3

import time
import threading
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup


class CentralControllerNode(Node):
    """
    [개편됨] 사용자 선택형 비동기 중앙 컨트롤러
    - 순서 강제 없음. 시스템이 준비(IDLE/READY_TO_RETRY)되어 있다면 어떤 공정이든 즉시 허용.
    """
    def __init__(self):
        super().__init__("central_controller_node")
        self.callback_group = ReentrantCallbackGroup()

        self.state_lock = threading.Lock()
        self.current_state = "IDLE"
        self.current_task = None
        self.stopped_task = None
        self.robot_busy = False
        self.stop_requested_by_user = False
        self.last_error = ""
        self.last_message = "Controller initialized"

        self.task_thread = None
        self.recovery_thread = None

        self.task_start_clients = {
            "SEASONING": self.create_client(Trigger, "/dsr01/seasoning/start", callback_group=self.callback_group),
            "TENDERIZING": self.create_client(Trigger, "/dsr01/tenderizing/start", callback_group=self.callback_group),
            "FRYING": self.create_client(Trigger, "/dsr01/frying/start", callback_group=self.callback_group),
            "SAUCING": self.create_client(Trigger, "/dsr01/saucing/start", callback_group=self.callback_group),
        }
        self.task_stop_clients = {
            "SEASONING": self.create_client(Trigger, "/dsr01/seasoning/stop", callback_group=self.callback_group),
            "TENDERIZING": self.create_client(Trigger, "/dsr01/tenderizing/stop", callback_group=self.callback_group),
            "FRYING": self.create_client(Trigger, "/dsr01/frying/stop", callback_group=self.callback_group),
            "SAUCING": self.create_client(Trigger, "/dsr01/saucing/stop", callback_group=self.callback_group),
        }
        self.recovery_client = self.create_client(Trigger, "/dsr01/recovery/start", callback_group=self.callback_group)

        self.create_service(Trigger, "/cobot/controller/seasoning/start", self.handle_start_seasoning, callback_group=self.callback_group)
        self.create_service(Trigger, "/cobot/controller/tenderizing/start", self.handle_start_tenderizing, callback_group=self.callback_group)
        self.create_service(Trigger, "/cobot/controller/frying/start", self.handle_start_frying, callback_group=self.callback_group)
        self.create_service(Trigger, "/cobot/controller/saucing/start", self.handle_start_saucing, callback_group=self.callback_group)
        self.create_service(Trigger, "/cobot/controller/stop", self.handle_stop, callback_group=self.callback_group)
        self.create_service(Trigger, "/cobot/controller/recovery/start", self.handle_recovery, callback_group=self.callback_group)
        self.create_service(Trigger, "/cobot/controller/state", self.handle_state, callback_group=self.callback_group)

        self.get_logger().info("Central Controller Node is ready (On-Demand Mode).")

    def handle_start_seasoning(self, request, response): return self.handle_start_task("SEASONING", response)
    def handle_start_tenderizing(self, request, response): return self.handle_start_task("TENDERIZING", response)
    def handle_start_frying(self, request, response): return self.handle_start_task("FRYING", response)
    def handle_start_saucing(self, request, response): return self.handle_start_task("SAUCING", response)

    def handle_start_task(self, task_name, response):
        with self.state_lock:
            allowed, reason = self.can_start_task(task_name)
            if not allowed:
                response.success = False
                response.message = reason
                return response

            if self.current_state == "READY_TO_RETRY":
                self.stopped_task = None # 이전 정지 기억 포맷 후 새 공정 시작

            self.current_state = "TASK_RUNNING"
            self.current_task = task_name
            self.robot_busy = True
            self.stop_requested_by_user = False
            self.last_error = ""
            self.last_message = f"{task_name} task started"

        self.task_thread = threading.Thread(target=self.run_task_worker, args=(task_name,), daemon=True)
        self.task_thread.start()

        response.success = True
        response.message = f"{task_name} task accepted by controller"
        return response

    def can_start_task(self, task_name):
        if task_name not in self.task_start_clients: return False, f"Unknown task: {task_name}"
        if self.current_state in ["TASK_RUNNING", "STOP_REQUESTED", "RECOVERY_RUNNING"]: return False, "System is currently busy."
        if self.current_state == "STOPPED": return False, "Recovery is required before starting."
        if self.current_state == "ERROR": return False, f"System is in ERROR state: {self.last_error}"
        
        # IDLE 또는 READY_TO_RETRY 이면 어떤 공정이든 무조건 허용
        return True, "Allowed"

    def run_task_worker(self, task_name):
        success, msg = self.call_service_sync(self.task_start_clients[task_name], service_name=f"/dsr01/{task_name.lower()}/start")
        with self.state_lock:
            self.robot_busy = False
            self.current_task = None

            if success:
                self.current_state = "IDLE"
                self.last_error = ""
                self.last_message = f"{task_name} completed"
            else:
                if self.stop_requested_by_user:
                    self.current_state = "STOPPED"
                    self.stopped_task = task_name
                    self.last_message = f"{task_name} stopped by user."
                else:
                    self.current_state = "ERROR"
                    self.last_error = f"{task_name} failed: {msg}"
                    self.last_message = self.last_error

    def handle_stop(self, request, response):
        with self.state_lock:
            if self.current_state != "TASK_RUNNING" or not self.current_task:
                response.success = False; response.message = "No running task to stop."
                return response
            task_name = self.current_task
            self.current_state = "STOP_REQUESTED"
            self.stop_requested_by_user = True

        stop_client = self.task_stop_clients.get(task_name)
        success, msg = self.call_service_sync(stop_client, service_name=f"/dsr01/{task_name.lower()}/stop", timeout_sec=3.0)
        
        if not success:
            with self.state_lock:
                self.current_state = "ERROR"
                self.robot_busy = False
                self.current_task = None
                self.last_error = f"Failed to stop {task_name}"
            response.success = False; response.message = self.last_error
            return response

        response.success = True; response.message = f"STOP request sent to {task_name}"
        return response

    def handle_recovery(self, request, response):
        with self.state_lock:
            if self.current_state not in ["STOPPED", "ERROR"]:
                response.success = False; response.message = "Recovery only allowed in STOPPED/ERROR state."
                return response
            self.current_state = "RECOVERY_RUNNING"
            self.robot_busy = True

        self.recovery_thread = threading.Thread(target=self.run_recovery_worker, daemon=True)
        self.recovery_thread.start()

        response.success = True; response.message = "Recovery accepted"
        return response

    def run_recovery_worker(self):
        success, msg = self.call_service_sync(self.recovery_client, service_name="/dsr01/recovery/start")
        with self.state_lock:
            self.robot_busy = False
            if success:
                self.current_state = "READY_TO_RETRY"
                self.last_error = ""
                self.last_message = "Recovery done. Ready for any task."
            else:
                self.current_state = "ERROR"
                self.last_error = f"Recovery failed: {msg}"
                self.last_message = self.last_error

    def handle_state(self, request, response):
        with self.state_lock:
            response.success = True
            response.message = f"state={self.current_state}, current_task={self.current_task}, stopped_task={self.stopped_task}, robot_busy={self.robot_busy}, last_error={self.last_error}, message={self.last_message}"
        return response

    def call_service_sync(self, client, service_name="", timeout_sec=5.0):
        if not client.wait_for_service(timeout_sec=timeout_sec): return False, f"Offline: {service_name}"
        req = Trigger.Request(); future = client.call_async(req)
        while rclpy.ok() and not future.done(): time.sleep(0.05)
        try:
            result = future.result()
            return (result.success, result.message) if result else (False, "None returned")
        except Exception as e:
            return False, str(e)

def main(args=None):
    rclpy.init(args=args)
    node = CentralControllerNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try: executor.spin()
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()