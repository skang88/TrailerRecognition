import cv2
import sys
import time
from ultralytics import YOLO
from collections import defaultdict
import numpy as np

# --- 설정값 ---
RTSP_URL = "rtsp://admin:1q2w3e4r@172.16.222.44:554"
RESIZE_DIM = (960, 540)
STOPPED_THRESHOLD_FRAMES = 30  # 30프레임 (약 1.5초) 동안 움직임이 없으면 '정차'로 판단
STOPPED_PIXEL_TOLERANCE = 5   # 위치 변화 허용 오차 (픽셀)
PROCESS_EVERY_N_FRAMES = 5  # 🚀 5프레임마다 한 번씩만 탐지 및 추적을 수행합니다.

# --- 게이트 정의 ---
GATES = {
    "Gate_1": [75, 97, 265, 270],
    "Gate_2": [435, 100, 570, 275]
}
# ---

model = YOLO('yolov8n.pt')
class_names = model.names
cap = None
frame_counter = 0

# --- 객체 추적 정보 및 화면에 그릴 정보를 저장할 변수 ---
# key: track_id, value: {'box': [x1,y1,x2,y2], 'class_name': 'truck', 'center': (cx,cy), 'stop_count': int, 'notified': bool, 'last_seen_frame': int}
tracked_objects_data = defaultdict(lambda: {
    'box': None, 'class_name': None, 'center': None,
    'stop_count': 0, 'notified': False, 'last_seen_frame': 0
})

# --- 마지막으로 화면에 그릴 객체 ID 목록 (사라진 객체를 정리하기 위함) ---
current_frame_detected_ids = set()


# --- 카메라 연결 시도 함수 (재사용을 위해 분리) ---
def try_connect_camera(url, attempt_delay=5):
    print("🔌 카메라 연결을 시도합니다...")
    while True:
        cap_obj = cv2.VideoCapture(url)
        if cap_obj.isOpened():
            print("✅ 카메라에 성공적으로 연결되었습니다.")
            return cap_obj
        else:
            print(f"🚨 연결 실패. {attempt_delay}초 후 재시도합니다.")
            time.sleep(attempt_delay)


# 메인 루프 시작
while True:
    try:
        # 카메라 연결이 없으면 새로 시도
        if cap is None or not cap.isOpened():
            cap = try_connect_camera(RTSP_URL)
            # 연결에 성공하면 모든 추적 정보 초기화 (새로운 스트림이므로)
            tracked_objects_data.clear()
            current_frame_detected_ids.clear()
            frame_counter = 0

        ret, frame = cap.read()
        if not ret:
            print("⚠️ 프레임을 읽을 수 없습니다. 연결을 재설정합니다...")
            cap.release()
            cap = None # None으로 설정하여 다음 루프에서 재연결 시도
            time.sleep(2)
            continue

        frame = cv2.resize(frame, RESIZE_DIM)
        frame_counter += 1
        current_frame_detected_ids.clear() # 현재 프레임에서 탐지된 ID 목록 초기화


        # --- N 프레임마다 한 번씩만 탐지 수행하여 추적 정보 업데이트 ---
        if frame_counter % PROCESS_EVERY_N_FRAMES == 0:
            results = model.track(frame, persist=True, verbose=False)
            
            if results[0].boxes.id is not None:
                boxes = results[0].boxes.xyxy.cpu().numpy().astype(int)
                track_ids = results[0].boxes.id.cpu().numpy().astype(int)
                class_ids = results[0].boxes.cls.cpu().numpy().astype(int)

                for box, track_id, cls_id in zip(boxes, track_ids, class_ids):
                    class_name = class_names[cls_id]

                    # 여기서 'truck'이 아닌 'person'도 필터링할 수 있지만, 일단 'truck'만 처리
                    # 그리고 게이트 자체를 truck으로 오인식하는 문제를 보완하기 위해 최소 크기 제한
                    # bounding box의 넓이가 너무 작으면 무시 (오인식 가능성 감소)
                    box_width = box[2] - box[0]
                    box_height = box[3] - box[1]
                    if class_name == 'truck' and (box_width < 30 or box_height < 30): # 최소 30x30 픽셀 이상만 유효하다고 가정
                        continue


                    current_frame_detected_ids.add(track_id) # 현재 프레임에 탐지된 ID 기록

                    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
                    
                    # 추적 데이터 업데이트
                    tracked_objects_data[track_id].update({
                        'box': box,
                        'class_name': class_name,
                        'center': (cx, cy),
                        'last_seen_frame': frame_counter # 마지막으로 본 프레임 번호
                    })

        # --- 화면 그리기 및 정차 로직 (매 프레임 실행) ---
        # 게이트 구역 시각화
        for name, (x1, y1, x2, y2) in GATES.items():
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, name, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

        # tracked_objects_data를 순회하며 화면에 그리기
        # (객체가 사라졌을 경우 정리 로직 포함)
        ids_to_remove = []
        for track_id, obj_data in tracked_objects_data.items():
            # 마지막으로 탐지된지 50프레임(2.5초, 20FPS 기준)이 넘었으면 사라진 것으로 간주
            if frame_counter - obj_data['last_seen_frame'] > PROCESS_EVERY_N_FRAMES * 10: # 예를 들어 10번의 탐지 주기동안 안보이면 삭제
                ids_to_remove.append(track_id)
                continue # 그리지 않고 다음 객체로 넘어감

            # 'truck' 클래스만 처리 (혹시 모를 다른 객체 필터링)
            if obj_data['class_name'] == 'truck':
                box = obj_data['box']
                cx, cy = obj_data['center']
                
                # 게이트 진입 여부 확인 (이전과 동일)
                current_gate = None
                for name, (gx1, gy1, gx2, gy2) in GATES.items():
                    if gx1 < cx < gx2 and gy1 < cy < gy2:
                        current_gate = name
                        break
                
                if current_gate:
                    # 정차 로직 업데이트 (매 프레임 실행)
                    last_pos = obj_data['center'] # 현재 중심점을 마지막 위치로 사용
                    stop_count = obj_data['stop_count']
                    notified = obj_data['notified']

                    if tracked_objects_data[track_id]['box'] is not None: # 박스 정보가 있을 때만 거리 계산
                        # 현재 프레임의 박스 중심과 이전 프레임의 박스 중심 비교
                        current_cx, current_cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
                        
                        if obj_data['center'] is not None: # 이전에 중심점이 있었으면
                            distance = np.sqrt((current_cx - obj_data['center'][0])**2 + (current_cy - obj_data['center'][1])**2)
                            if distance < STOPPED_PIXEL_TOLERANCE:
                                stop_count += 1
                            else:
                                stop_count = 0
                                notified = False
                        else: # 처음 진입 시
                            stop_count = 0
                            notified = False

                    tracked_objects_data[track_id]['stop_count'] = stop_count
                    tracked_objects_data[track_id]['notified'] = notified
                    tracked_objects_data[track_id]['center'] = (current_cx, current_cy) # 현재 중심점으로 업데이트

                    # --- 시각화 및 Webhook 전송 ---
                    label = f"ID:{track_id}@{current_gate}"
                    color = (0, 255, 0)
                    
                    if stop_count > STOPPED_THRESHOLD_FRAMES:
                        label += " [STOPPED]"
                        color = (0, 0, 255)
                        
                        if not notified:
                            print(f"🚀 Webhook Event: Truck ID {track_id} stopped at {current_gate}")
                            # send_webhook("stopped", track_id, current_gate)
                            tracked_objects_data[track_id]['notified'] = True
                    
                    cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), color, 2)
                    cv2.putText(frame, label, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
                else:
                    # 게이트 밖으로 나간 경우 정차 정보 초기화 및 알림 상태 리셋
                    if tracked_objects_data[track_id]['notified']: # 게이트 밖으로 나갔는데 정차 알림이 갔었으면
                        print(f"◀️ Truck ID {track_id} left the gate area. Resetting status.")
                    tracked_objects_data[track_id]['stop_count'] = 0
                    tracked_objects_data[track_id]['notified'] = False
                    # 게이트 밖에 있는 트럭은 그냥 초록색으로 그리기
                    cv2.rectangle(frame, (box[0], box[1]), (box[2], box[3]), (0, 255, 0), 2)
                    cv2.putText(frame, f"ID:{track_id}", (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            else:
                # 'truck'이 아닌 다른 클래스인데 추적 중인 경우
                pass # 지금은 다른 클래스는 그리지 않음

        # 사라진 객체는 tracked_objects_data에서 제거
        for track_id in ids_to_remove:
            print(f"🗑️ Truck ID {track_id} has disappeared and removed from tracking.")
            del tracked_objects_data[track_id]


        cv2.imshow("Trailer Detection System", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            print(" 'q' 키가 입력되어 프로그램을 안전하게 종료합니다.")
            break
            
    except Exception as e:
        print(f"💥 예상치 못한 오류 발생: {e}")
        break

if cap is not None:
    cap.release()
cv2.destroyAllWindows()
print(" 프로그램이 종료되었습니다.")