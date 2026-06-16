from flask import Flask, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger
import threading
import time


app = Flask(__name__)

# ==========================================================
# Flask / DB 설정
# ==========================================================
app.config['SECRET_KEY'] = 'robotics_engineer_secret_2026'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/eycho/g2_2_ws/src/cobot1_project/cobot1_project/instance/robot_proc.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(
    app,
    supports_credentials=True,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:5173",
                "http://127.0.0.1:5173"
            ]
        }
    }
)

db = SQLAlchemy(app)

def is_logged_in():
    return 'user_id' in session

# ==========================================================
# [개편됨] 사용자 선택형 비동기 DB 모델 정의
# ==========================================================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='operator')
    created_at = db.Column(db.DateTime, default=datetime.now)

class OperationSession(db.Model):
    __tablename__ = 'operation_sessions'
    session_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='ACTIVE')
    actions = db.relationship('RobotAction', backref='session', lazy=True)

class RobotAction(db.Model):
    __tablename__ = 'robot_actions'
    action_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey('operation_sessions.session_id'), nullable=False)
    action_name = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='RUNNING')
    logs = db.relationship('RobotLog', backref='action', lazy=True)

class RobotLog(db.Model):
    __tablename__ = 'robot_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    action_id = db.Column(db.Integer, db.ForeignKey('robot_actions.action_id'), nullable=False)
    log_level = db.Column(db.String(10))
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

# ==========================================================
# ROS 2 Bridge Node
# ==========================================================
class RobotBridgeNode(Node):
    def __init__(self):
        super().__init__('flask_ros_bridge')
        self.service_clients = {
            'SEASONING': self.create_client(Trigger, '/cobot/controller/seasoning/start'),
            'TENDERIZING': self.create_client(Trigger, '/cobot/controller/tenderizing/start'),
            'FRYING': self.create_client(Trigger, '/cobot/controller/frying/start'),
            'SAUCING': self.create_client(Trigger, '/cobot/controller/saucing/start'),
            'STOP': self.create_client(Trigger, '/cobot/controller/stop'),
            'RECOVERY': self.create_client(Trigger, '/cobot/controller/recovery/start'),
            'STATE': self.create_client(Trigger, '/cobot/controller/state'),
        }

    def call_controller_sync(self, command_name, timeout_sec=5.0):
        cli = self.service_clients.get(command_name)
        if cli is None:
            return False, f"Unknown controller command: {command_name}"
        if not cli.wait_for_service(timeout_sec=timeout_sec):
            return False, f"Controller service offline: {command_name}"

        req = Trigger.Request()
        future = cli.call_async(req)
        while rclpy.ok() and not future.done():
            time.sleep(0.05)
        try:
            response = future.result()
            if response is None:
                return False, f"Controller returned None: {command_name}"
            return response.success, response.message
        except Exception as e:
            return False, str(e)

ros_node = None

# ==========================================================
# API 엔드포인트
# ==========================================================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    user = User.query.filter_by(username=data.get('username')).first()
    if user and check_password_hash(user.password_hash, data.get('password', '')):
        session['user_id'] = user.id
        session['username'] = user.username
        return jsonify({"status": "success", "username": user.username})
    return jsonify({"status": "fail"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"status": "success"})

@app.route('/api/session/start', methods=['POST'])
def start_session():
    if not is_logged_in(): return jsonify({"status": "error"}), 403
    new_session = OperationSession()
    db.session.add(new_session)
    db.session.commit()
    return jsonify({"status": "success", "session_id": new_session.session_id})

@app.route('/api/action/start', methods=['POST'])
def start_action():
    if not is_logged_in(): 
        return jsonify({"status": "error", "message": "Unauthorized"}), 403
        
    data = request.json
    action_name = data.get('action_name').upper()
    session_id = data.get('session_id')

    # 1. 새로운 액션 생성 (기본 상태: RUNNING)
    new_action = RobotAction(session_id=session_id, action_name=action_name, status="RUNNING")
    db.session.add(new_action)
    db.session.commit()

    # 2. 요청 시작 로그 기록
    start_log = RobotLog(action_id=new_action.action_id, log_level="info", message=f"{action_name} 요청 전달됨")
    db.session.add(start_log)
    db.session.commit()

    # 3. ROS Bridge를 통한 로봇 제어 (동기 방식)
    if ros_node is None:
        success, msg = False, "ROS Bridge Error"
    else:
        success, msg = ros_node.call_controller_sync(action_name)

    # 4. 결과 처리
    if success:
   
        # 성공 로그 기록 및 최종 커밋
        db.session.add(RobotLog(action_id=new_action.action_id, log_level="info", message=msg))
        db.session.commit()
        
        return jsonify({
            "action_id": new_action.action_id, 
            "status": "completed", 
            "message": msg
        })
    else:
        # 실패 처리 (성공하지 못한 경우 바로 여기서 종료)
        new_action.status = "FAILED"
        new_action.end_time = datetime.now()
        
        db.session.add(RobotLog(action_id=new_action.action_id, log_level="error", message=msg))
        db.session.commit()
        
        return jsonify({
            "action_id": new_action.action_id, 
            "status": "fail", 
            "message": msg
        }), 400

@app.route('/api/action/stop', methods=['POST'])
def stop_action():
    if not is_logged_in() or not ros_node: return jsonify({"status": "error"}), 403
    success, msg = ros_node.call_controller_sync('STOP')
    return jsonify({"status": "success" if success else "fail", "message": msg}), 200 if success else 400

@app.route('/api/recovery/start', methods=['POST'])
def start_recovery():
    if not is_logged_in() or not ros_node: return jsonify({"status": "error"}), 403
    success, msg = ros_node.call_controller_sync('RECOVERY')
    return jsonify({"status": "success" if success else "fail", "message": msg}), 200 if success else 400

@app.route('/api/system/state', methods=['GET'])
def get_system_state():
    if not is_logged_in() or not ros_node: return jsonify({"status": "error"}), 403
    success, msg = ros_node.call_controller_sync('STATE')
    parsed_state = parse_controller_state_message(msg)
    return jsonify({"status": "success" if success else "fail", **parsed_state})

def parse_controller_state_message(message):
    result = {"state": "UNKNOWN", "current_task": None, "stopped_task": None, "robot_busy": False, "last_error": "", "message": message}
    if not message: return result
    try:
        parts = [p.strip() for p in message.split(",")]
        for part in parts:
            if "=" not in part: continue
            key, value = part.split("=", 1)
            key, value = key.strip(), value.strip()
            if key == "state": result["state"] = value
            elif key == "current_task": result["current_task"] = None if value in ["None", "null", ""] else value
            elif key == "stopped_task": result["stopped_task"] = None if value in ["None", "null", ""] else value
            elif key == "robot_busy": result["robot_busy"] = value.lower() == "true"
            elif key == "last_error": result["last_error"] = value
            elif key == "message": result["message"] = value
    except Exception: pass
    return result

@app.route('/api/log', methods=['POST', 'OPTIONS'])
def add_log():
    if request.method == 'OPTIONS': return '', 200
    data = request.json
    db.session.add(RobotLog(action_id=data['action_id'], log_level=data['log_level'], message=data['message']))
    db.session.commit()
    return jsonify({"status": "log_saved"})

@app.route('/api/action/end', methods=['POST'])
def end_action():
    data = request.json
    action = RobotAction.query.get(data['action_id'])
    if action:
        action.end_time = datetime.now()
        action.status = data['status']
        db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/session/end', methods=['POST'])
def end_session():
    data = request.json
    session_obj = OperationSession.query.get(data['session_id'])
    if session_obj:
        session_obj.end_time = datetime.now()
        session_obj.status = data['status']
        db.session.commit()
    return jsonify({"status": "success"})

@app.route('/api/history', methods=['GET'])
def get_history():
    if not is_logged_in(): return jsonify({"status": "error"}), 403
    sessions = OperationSession.query.all()
    history = []
    for s in sessions:
        # 프론트엔드 LogHistory.jsx 호환성을 위해 키값을 job_id와 tasks로 매핑
        s_data = {
            "job_id": s.session_id, 
            "start_time": s.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": s.end_time.strftime("%H:%M:%S") if s.end_time else "-",
            "final_status": s.status,
            "tasks": []
        }
        for a in s.actions:
            s_data["tasks"].append({
                "task_id": a.action_id,
                "task_name": a.action_name,
                "status": a.status,
                "start_time": a.start_time.strftime("%H:%M:%S") if a.start_time else "-",
                "end_time": a.end_time.strftime("%H:%M:%S") if a.end_time else "-",
                "logs": [{"level": l.log_level, "msg": l.message, "time": l.created_at.strftime("%H:%M:%S")} for l in a.logs]
            })
        history.append(s_data)
    return jsonify(history)

def ros_spin_thread(): rclpy.spin(ros_node)

def main(args=None):
    global ros_node
    rclpy.init(args=args)
    ros_node = RobotBridgeNode()
    threading.Thread(target=ros_spin_thread, daemon=True).start()

    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            db.session.add(User(username='admin', password_hash=generate_password_hash('1234'), role='admin'))
            db.session.commit()

    try: app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
    finally:
        if ros_node: ros_node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__': main()
