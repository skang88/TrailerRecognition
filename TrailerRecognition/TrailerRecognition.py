import cv2
import sys
import os
import time
import datetime
from ultralytics import YOLO
from collections import defaultdict
import numpy as np
import requests
import threading
import PySimpleGUI as sg

# --- UI 연동을 위한 기본 설정값 ---
SETTINGS = {
    "stop_time_sec": 10.0,  # 정차 판단 시간 (초)
    "pixel_tolerance": 5,   # 움직임 허용 오차 (픽셀)
    "process_interval": 5,  # 프레임 처리 간격
    "gate_cooldown": 30     # 게이트 재작동 방지 시간 (초)
}
CAMERA_FPS = 25  # 카메라의 초당 프레임 (가정치)

# --- 고정 설정값 ---
RTSP_URL = "rtsp://admin:1q2w3e4r@172.16.222.45:554/Streaming/Channels/102"
RESIZE_DIM = (960, 540)
API_BASE_URL = "https://seohanga.com/api"
TARGET_CLASSES = {'car', 'truck', 'bus', 'motorcycle'}
# 로그를 보니 1분으로 테스트하신 것 같아 60으로 설정합니다. 10분으로 하시려면 600으로 변경하세요.
RECONNECT_INTERVAL =  600 # 5분(초 단위)마다 재연결 

# --- 게이트 정의 ---
GATES = {
    # "Gate_1": [620, 10, 850, 400],
    "Gate_2": [190, 20, 420, 210]
}
GATES_CONFIG = {
    # "Gate_1": {"name": "Visitor Entrance", "shelly_id": 3},
    "Gate_2": {"name": "Visitor Exit", "shelly_id": 4}
}

def is_within_operating_hours():
    """새벽 3시부터 저녁 7시까지인지 확인합니다."""
    now = datetime.datetime.now()
    #is_weekday = now.weekday() < 5
    start_time = datetime.time(3, 0)
    end_time = datetime.time(19, 0)
    is_in_time_window = start_time <= now.time() <= end_time
    return is_in_time_window # and is_weekday

def log_message(message):
    """메시지에 현재 시간을 붙여 출력합니다."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def try_connect_camera(url, attempt_delay=5):
    log_message("🔌 카메라 연결을 시도합니다...")
    while True:
        cap_obj = cv2.VideoCapture(url)
        if cap_obj.isOpened():
            log_message("✅ 카메라에 성공적으로 연결되었습니다.")
            return cap_obj
        else:
            log_message(f"🚨 연결 실패. {attempt_delay}초 후 재시도합니다.")
            time.sleep(attempt_delay)

def send_shelly_webhook(shelly_id):
    try:
        on_url = f"{API_BASE_URL}/shelly/on/{shelly_id}"
        off_url = f"{API_BASE_URL}/shelly/off/{shelly_id}"
        log_message(f"⚡️ Shelly ON Request: ID {shelly_id}")
        requests.post(on_url, timeout=5)
        time.sleep(1)
        log_message(f"⚡️ Shelly OFF Request: ID {shelly_id}")
        requests.post(off_url, timeout=5)
        log_message(f"✅ Shelly ID {shelly_id} 제어 완료.")
    except requests.exceptions.RequestException as e:
        log_message(f"🚨 Webhook Error (Shelly ID: {shelly_id}): {e}")

def create_control_window():
    layout = [
        [sg.Text("실시간 제어 패널", font=("Helvetica", 16))],
        [sg.HorizontalSeparator()],
        [sg.Text("정차 판단 시간 (초)", size=(20, 1)),
         sg.Slider(range=(1.0, 20.0), default_value=SETTINGS["stop_time_sec"], resolution=0.5, orientation='h', key='-STOP_TIME-', enable_events=True)],
        [sg.Text("움직임 허용 오차 (픽셀)", size=(20, 1)),
         sg.Slider(range=(1, 20), default_value=SETTINGS["pixel_tolerance"], orientation='h', key='-PIXEL_TOL-', enable_events=True)],
        [sg.Text("프레임 처리 간격", size=(20, 1)),
         sg.Slider(range=(1, 10), default_value=SETTINGS["process_interval"], orientation='h', key='-PROC_INTERVAL-', enable_events=True)],
        [sg.Text("게이트 재작동 방지 (초)", size=(20, 1)),
         sg.Slider(range=(5, 120), default_value=SETTINGS["gate_cooldown"], orientation='h', key='-COOLDOWN-', enable_events=True)],
        [sg.Button("종료", button_color=('white', 'firebrick3'), size=(10, 1))]
    ]
    return sg.Window("제어 패널", layout, finalize=True, keep_on_top=True)

def main():
    model_path = resource_path("yolov8n.pt")
    model = YOLO(model_path)
    class_names = model.names
    
    tracked_objects_data = defaultdict(lambda: {
        'box': None, 'class_name': None, 'center': None, 'prev_center': None,
        'stop_count': 0, 'notified': False, 'last_seen_frame': 0, 'current_gate': None
    })
    gate_last_triggered = {gate_name: 0 for gate_name in GATES}
    
    window = create_control_window()
    cap = None
    frame_counter = 0
    last_reconnect_time = time.time()

    while True:
        event, values = window.read(timeout=1)
        
        if event == sg.WIN_CLOSED or event == "종료":
            log_message("프로그램을 종료합니다.")
            break
        
        if event == '-STOP_TIME-': SETTINGS["stop_time_sec"] = values['-STOP_TIME-']
        if event == '-PIXEL_TOL-': SETTINGS["pixel_tolerance"] = int(values['-PIXEL_TOL-'])
        if event == '-PROC_INTERVAL-': SETTINGS["process_interval"] = int(values['-PROC_INTERVAL-'])
        if event == '-COOLDOWN-': SETTINGS["gate_cooldown"] = int(values['-COOLDOWN-'])

        if time.time() - last_reconnect_time > RECONNECT_INTERVAL:
            log_message(f"⏳ 주기적인 카메라 재연결을 시작합니다 ({RECONNECT_INTERVAL // 60}분 경과).")
            if cap:
                cap.release()
            cap = None
            last_reconnect_time = time.time() # 무한 루프 방지를 위해 타이머 즉시 갱신
            continue

        stop_threshold_frames = int((SETTINGS["stop_time_sec"] * CAMERA_FPS) / SETTINGS["process_interval"])
        process_every_n_frames = SETTINGS["process_interval"]
        stopped_pixel_tolerance = SETTINGS["pixel_tolerance"]
        gate_cooldown_seconds = SETTINGS["gate_cooldown"]

        try:
            if cap is None or not cap.isOpened():
                if cap: cap.release()
                cap = try_connect_camera(RTSP_URL)
                tracked_objects_data.clear()
                frame_counter = 0
                last_reconnect_time = time.time()

            ret, frame = cap.read()
            if not ret:
                log_message("⚠️ 프레임을 읽을 수 없습니다. 연결을 재설정합니다...")
                if cap: cap.release()
                cap = None
                time.sleep(2)
                continue

            frame = cv2.resize(frame, RESIZE_DIM)
            frame_counter += 1
            
            if frame_counter % process_every_n_frames == 0:
                results = model.track(frame, persist=True, verbose=False)
                if results and results[0].boxes.id is not None:
                    boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
                    track_ids = results[0].boxes.id.cpu().numpy().astype(int)
                    class_ids = results[0].boxes.cls.cpu().numpy().astype(int)

                    for box, track_id, cls_id in zip(boxes, track_ids, class_ids):
                        class_name = class_names[cls_id]
                        if class_name in TARGET_CLASSES:
                            cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
                            obj_data = tracked_objects_data[track_id]
                            if obj_data['center']: obj_data['prev_center'] = obj_data['center']
                            obj_data.update({
                                'box': box, 'class_name': class_name, 'center': (cx, cy),
                                'last_seen_frame': frame_counter
                            })

            for name, (x1, y1, x2, y2) in GATES.items():
                cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
                cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            for track_id, obj_data in list(tracked_objects_data.items()):
                if frame_counter - obj_data['last_seen_frame'] > process_every_n_frames * 10:
                    del tracked_objects_data[track_id]
                    continue

                if obj_data.get('center'):
                    box, cx, cy = obj_data['box'], obj_data['center'][0], obj_data['center'][1]
                    current_gate = None
                    for name, (gx1, gy1, gx2, gy2) in GATES.items():
                        if gx1 < cx < gx2 and gy1 < cy < gy2:
                            current_gate = name
                            break

                    prev_gate = obj_data.get('current_gate')
                    if current_gate and not prev_gate:
                        log_message(f"➡️  ID {track_id} 차량 '{current_gate}' 진입. 카운트 초기화.")
                        obj_data['stop_count'] = 0
                    obj_data['current_gate'] = current_gate

                    if current_gate:
                        distance = 0
                        if obj_data['prev_center']:
                            distance = np.linalg.norm(np.array(obj_data['center']) - np.array(obj_data['prev_center']))

                        if distance < stopped_pixel_tolerance:
                            obj_data['stop_count'] += 1
                        else:
                            obj_data['stop_count'] = 0
                            obj_data['notified'] = False

                        label = f"{obj_data['class_name']}:{track_id}"
                        color = (0, 255, 0)

                        if obj_data['stop_count'] > stop_threshold_frames:
                            label += " [STOPPED]"
                            color = (0, 0, 255)
                            if not obj_data['notified']:
                                current_time = time.time()
                                if current_time - gate_last_triggered.get(current_gate, 0) > gate_cooldown_seconds:
                                    if is_within_operating_hours():
                                        log_message(f"🚀 정차 감지 (운영 시간): {obj_data['class_name']} ID {track_id} at {current_gate}. 게이트를 작동합니다.")
                                        if current_gate in GATES_CONFIG:
                                            shelly_id = GATES_CONFIG[current_gate]['shelly_id']
                                            threading.Thread(target=send_shelly_webhook, args=(shelly_id,)).start()
                                        gate_last_triggered[current_gate] = current_time
                                    else:
                                        log_message(f"📦 정차 감지 (운영 시간 아님): {obj_data['class_name']} ID {track_id} at {current_gate}. 게이트를 작동하지 않습니다.")
                                    
                                    obj_data['notified'] = True
                        
                        cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
                        cv2.putText(frame, label, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            cv2.imshow("Vehicle Detection System", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        
        except Exception as e:
            log_message(f"💥 메인 루프 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            if cap: cap.release()
            cap = None
            time.sleep(5) 

    window.close()
    if cap: cap.release()
    cv2.destroyAllWindows()
    log_message("프로그램이 완전히 종료되었습니다.")

if __name__ == '__main__':
    main()