
import cv2

# --- 설정 (기존 코드와 동일하게 맞춰주세요) ---
RTSP_URL = "rtsp://admin:1q2w3e4r@172.16.222.45:554"
RESIZE_DIM = (960, 540)
# ---

# 마우스 클릭 이벤트를 처리할 함수
def get_coords(event, x, y, flags, param):
    # 왼쪽 마우스 버튼을 클릭했을 때
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"Clicked Coordinates: (x={x}, y={y})")

# 비디오 캡처 시작
cap = cv2.VideoCapture(RTSP_URL)

if not cap.isOpened():
    print("🚨 카메라에 연결할 수 없습니다. RTSP 주소를 확인해주세요.")
else:
    # 첫 프레임만 성공적으로 읽어옴
    ret, frame = cap.read()
    if ret:
        # 기존 코드와 동일한 크기로 리사이즈 (좌표 일치를 위해 필수!)
        frame = cv2.resize(frame, RESIZE_DIM)
        
        window_name = 'Click to get coordinates'
        cv2.namedWindow(window_name)
        
        # 마우스 이벤트 콜백 함수 연결
        cv2.setMouseCallback(window_name, get_coords)
        
        print("✅ 프레임이 나타났습니다. 좌표를 확인할 지점을 클릭하세요.")
        print("   (창을 닫으려면 아무 키나 누르세요)")
        
        # 사용자가 키를 누를 때까지 이미지 표시
        cv2.imshow(window_name, frame)
        cv2.waitKey(0) # 키 입력이 있을 때까지 무한 대기
        
    else:
        print("⚠️ 프레임을 읽어올 수 없습니다.")

# 자원 해제
cap.release()
cv2.destroyAllWindows()