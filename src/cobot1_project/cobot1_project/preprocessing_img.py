import cv2
import numpy as np
import csv
import os


# ==========================================================
# 1. 사용자 설정 파라미터(주의! 사용자 환경에 맞게 수정 필요)
# ==========================================================

# 입력 PNG
INPUT_IMAGE = "/home/ccw/cobot_ws/src/cobot1/Smile.png" # 사용자 환경에 맞게 수정 필요

# 출력 파일
OUTPUT_CSV = "/home/ccw/cobot_ws/src/cobot1/sauce_robot_points.csv" # 사용자 환경에 맞게 수정 필요
OUTPUT_PREVIEW = "/home/ccw/cobot_ws/src/cobot1/preview_simple.png" # 사용자 환경에 맞게 수정 필요

# ----------------------------------------------------------
# 실제 작업대 / 돈까스 중심점
# ----------------------------------------------------------
# 노즐을 돈까스 중심 위에 위치시킨 뒤 현재 TCP 좌표를 읽어서 입력.
DONKATSU_CENTER_X = 312.737
DONKATSU_CENTER_Y = 50.396
DRAW_Z = 197.558

# 노즐 자세
# 지금은 좌표 CSV에는 저장만 하고, 로봇 실행 코드에서 posx 만들 때 사용하면 됨.
RX = 93.898
RY = 92.431
RZ = -87.752

# ----------------------------------------------------------
# 그림 크기 설정
# ----------------------------------------------------------
# PNG 전체 폭을 실제 돈까스 위에서 몇 mm로 그릴지
TARGET_WIDTH_MM = 80.0

# ----------------------------------------------------------
# 좌표축 방향 보정
# ----------------------------------------------------------
# 이미지 오른쪽  = 로봇 X+
# 이미지 위쪽    = 로봇 Y+
X_SIGN = 1.0
Y_SIGN = 1.0

# 만약 이미지 x축과 로봇 y축이 대응되고,
# 이미지 y축과 로봇 x축이 대응된다면 True로 바꾼다.
SWAP_XY = False

# ----------------------------------------------------------
# 경로 단순화 설정
# ----------------------------------------------------------
# 입 경로 점을 몇 픽셀 간격으로 뽑을지
MOUTH_POINT_STEP = 3

# 너무 작은 잡음 제거 기준
MIN_AREA = 20


# ==========================================================
# 2. 이미지 이진화
# ==========================================================

def load_binary_image(image_path):
    """
    PNG 이미지를 읽고 검은 그림 영역만 255로 분리한다.

    결과:
    - 검은 눈/입 영역: 255
    - 흰 배경: 0
    """

    img = cv2.imread(image_path, cv2.IMREAD_COLOR)

    if img is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없음: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 검은 그림 + 흰 배경 기준
    # 검은 부분을 255로 반전 이진화
    _, binary = cv2.threshold(
        gray,
        0,
        255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    return img, binary


# ==========================================================
# 3. 눈 2개와 입 1개 분리
# ==========================================================

def split_smile_components(binary):
    """
    connected component를 이용해서 눈 2개와 입 1개를 분리한다.

    전제:
    - 검은 영역이 3개로 분리되어 있음
      1) 왼쪽 눈
      2) 오른쪽 눈
      3) 입

    반환:
    - eye_centers_px: [(u_left, v_left), (u_right, v_right)]
    - mouth_mask: 입 영역만 남긴 이미지
    """

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        binary,
        connectivity=8
    )

    components = []

    for label in range(1, num_labels):
        area = stats[label, cv2.CC_STAT_AREA]

        if area < MIN_AREA:
            continue

        x = stats[label, cv2.CC_STAT_LEFT]
        y = stats[label, cv2.CC_STAT_TOP]
        w = stats[label, cv2.CC_STAT_WIDTH]
        h = stats[label, cv2.CC_STAT_HEIGHT]
        cx, cy = centroids[label]

        components.append({
            "label": label,
            "area": area,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "center": (cx, cy)
        })

    if len(components) < 3:
        raise RuntimeError(
            f"눈 2개와 입 1개를 찾기엔 component가 부족함: {len(components)}개"
        )

    # 면적 기준:
    # 작은 2개 = 눈
    # 가장 큰 1개 = 입
    components = sorted(components, key=lambda c: c["area"])

    eye_components = components[:2]
    mouth_component = components[-1]

    # 눈은 왼쪽 → 오른쪽 순서로 정렬
    eye_components = sorted(
        eye_components,
        key=lambda c: c["center"][0]
    )

    eye_centers_px = [
        eye_components[0]["center"],
        eye_components[1]["center"]
    ]

    mouth_mask = np.zeros_like(binary)
    mouth_mask[labels == mouth_component["label"]] = 255

    print("[Component 결과]")
    for c in components:
        print(
            f"label={c['label']}, "
            f"area={c['area']}, "
            f"bbox=({c['w']}x{c['h']}), "
            f"center=({c['center'][0]:.1f}, {c['center'][1]:.1f})"
        )

    return eye_centers_px, mouth_mask


# ==========================================================
# 4. 입 경로 추출
# ==========================================================

def extract_mouth_centerline(mouth_mask):
    """
    입 영역에서 중심 경로를 단순하게 추출한다.

    방식:
    - 입 영역의 각 x좌표 column을 확인
    - 해당 column에 흰 픽셀이 있으면
    - 그 픽셀들의 평균 y값을 중심선으로 사용

    장점:
    - skeletonize보다 훨씬 단순함
    - 현재 웃는 입 PNG에는 잘 맞음

    단점:
    - 복잡한 그림, 폐곡선, 세로선 많은 그림에는 약함
    """

    h, w = mouth_mask.shape

    path_px = []

    # 입이 존재하는 x 범위 찾기
    ys, xs = np.where(mouth_mask > 0)

    if len(xs) == 0:
        raise RuntimeError("입 영역 픽셀이 없음")

    x_min = int(np.min(xs))
    x_max = int(np.max(xs))

    # x 방향으로 훑으면서 중앙 y 추출
    for u in range(x_min, x_max + 1, MOUTH_POINT_STEP):
        column_ys = np.where(mouth_mask[:, u] > 0)[0]

        if len(column_ys) == 0:
            continue

        # 해당 x열에서 입 두께의 중앙
        v_center = int(np.mean(column_ys))

        path_px.append((u, v_center))

    if len(path_px) < 2:
        raise RuntimeError("입 경로 점이 너무 적음")

    return path_px


# ==========================================================
# 5. PNG 픽셀 좌표 → 돈까스 중심 기준 상대좌표
# ==========================================================

def pixel_to_relative_mm(u, v, image_shape):
    """
    PNG 픽셀 좌표를 돈까스 중심 기준 상대 mm 좌표로 변환한다.

    핵심:
    - PNG 중심점이 돈까스 중심점과 일치한다고 가정
    - 이미지 오른쪽: +x_rel
    - 이미지 위쪽: +y_rel

    이미지 좌표계:
    - u: 오른쪽으로 증가
    - v: 아래쪽으로 증가

    로봇/작업평면 상대좌표:
    - x_rel: 오른쪽 +
    - y_rel: 위쪽 +
    """

    h, w = image_shape[:2]

    png_center_u = w / 2.0
    png_center_v = h / 2.0

    # PNG 전체 폭을 TARGET_WIDTH_MM로 맞춤
    scale = TARGET_WIDTH_MM / float(w)

    x_rel = (u - png_center_u) * scale
    y_rel = -(v - png_center_v) * scale

    return x_rel, y_rel, scale


# ==========================================================
# 6. 상대좌표 → 실제 로봇 좌표
# ==========================================================

def relative_mm_to_robot_xy(x_rel, y_rel):
    """
    돈까스 중심 기준 상대좌표를 실제 로봇 XY 좌표로 변환한다.

    DONKATSU_CENTER_X, DONKATSU_CENTER_Y:
    - 실제 작업대 위 돈까스 중심의 로봇 좌표

    X_SIGN, Y_SIGN:
    - 축 방향 반전 보정용

    SWAP_XY:
    - 이미지 x/y축과 로봇 x/y축이 서로 바뀌었을 때 사용
    """

    if not SWAP_XY:
        robot_x = DONKATSU_CENTER_X + X_SIGN * x_rel
        robot_y = DONKATSU_CENTER_Y + Y_SIGN * y_rel
    else:
        robot_x = DONKATSU_CENTER_X + X_SIGN * y_rel
        robot_y = DONKATSU_CENTER_Y + Y_SIGN * x_rel

    return robot_x, robot_y


# ==========================================================
# 7. 최종 명령 좌표 생성
# ==========================================================

def make_draw_commands(eye_centers_px, mouth_path_px, image_shape):
    """
    눈 중심점과 입 경로를 최종 로봇 좌표 명령으로 변환한다.

    반환 commands:
    [
        {
            "type": "dot",
            "name": "eye_left",
            "point_id": 0,
            "x_rel": ...,
            "y_rel": ...,
            "robot_x": ...,
            "robot_y": ...,
            "robot_z": ...
        },
        {
            "type": "path",
            "name": "mouth",
            "point_id": 0,
            ...
        },
        ...
    ]
    """

    commands = []
    scale = None

    # ------------------------------
    # 눈 2개: dot 명령
    # ------------------------------
    for i, (u, v) in enumerate(eye_centers_px):
        x_rel, y_rel, scale = pixel_to_relative_mm(u, v, image_shape)
        robot_x, robot_y = relative_mm_to_robot_xy(x_rel, y_rel)

        eye_name = "eye_left" if i == 0 else "eye_right"

        commands.append({
            "type": "dot",
            "name": eye_name,
            "point_id": 0,
            "x_rel": x_rel,
            "y_rel": y_rel,
            "robot_x": robot_x,
            "robot_y": robot_y,
            "robot_z": DRAW_Z,
            "rx": RX,
            "ry": RY,
            "rz": RZ
        })

    # ------------------------------
    # 입: path 명령
    # ------------------------------
    for point_id, (u, v) in enumerate(mouth_path_px):
        x_rel, y_rel, scale = pixel_to_relative_mm(u, v, image_shape)
        robot_x, robot_y = relative_mm_to_robot_xy(x_rel, y_rel)

        commands.append({
            "type": "path",
            "name": "mouth",
            "point_id": point_id,
            "x_rel": x_rel,
            "y_rel": y_rel,
            "robot_x": robot_x,
            "robot_y": robot_y,
            "robot_z": DRAW_Z,
            "rx": RX,
            "ry": RY,
            "rz": RZ
        })

    return commands, scale


# ==========================================================
# 8. CSV 저장
# ==========================================================

def save_commands_to_csv(commands, output_csv):
    """
    최종 좌표를 CSV로 저장한다.

    x_rel, y_rel:
    - 돈까스 중심 기준 상대좌표

    robot_x, robot_y, robot_z:
    - 실제 로봇에 넣을 좌표
    """

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "type",
            "name",
            "point_id",
            "x_rel_mm",
            "y_rel_mm",
            "robot_x",
            "robot_y",
            "robot_z",
            "rx",
            "ry",
            "rz"
        ])

        for cmd in commands:
            writer.writerow([
                cmd["type"],
                cmd["name"],
                cmd["point_id"],
                round(cmd["x_rel"], 3),
                round(cmd["y_rel"], 3),
                round(cmd["robot_x"], 3),
                round(cmd["robot_y"], 3),
                round(cmd["robot_z"], 3),
                round(cmd["rx"], 3),
                round(cmd["ry"], 3),
                round(cmd["rz"], 3)
            ])


# ==========================================================
# 9. Preview 저장
# ==========================================================

def save_preview(original_img, eye_centers_px, mouth_path_px, output_path):
    """
    추출된 눈 중심과 입 경로를 이미지에 표시해서 저장한다.

    - 눈 중심: 초록 점
    - 입 경로: 빨간 선
    - 입 시작점: 파란 점
    """

    preview = original_img.copy()

    # 입 경로 표시
    for i in range(len(mouth_path_px) - 1):
        cv2.line(
            preview,
            mouth_path_px[i],
            mouth_path_px[i + 1],
            (0, 0, 255),
            1
        )

    if len(mouth_path_px) > 0:
        cv2.circle(
            preview,
            mouth_path_px[0],
            5,
            (255, 0, 0),
            -1
        )

    # 눈 중심 표시
    for u, v in eye_centers_px:
        cv2.circle(
            preview,
            (int(round(u)), int(round(v))),
            6,
            (0, 255, 0),
            -1
        )

    cv2.imwrite(output_path, preview)


# ==========================================================
# 10. 메인
# ==========================================================

def main():
    if not os.path.exists(INPUT_IMAGE):
        raise FileNotFoundError(f"입력 이미지 없음: {INPUT_IMAGE}")

    # 1. 이미지 읽기 + 검은 영역 분리
    original_img, binary = load_binary_image(INPUT_IMAGE)

    # 2. 눈과 입 분리
    eye_centers_px, mouth_mask = split_smile_components(binary)

    # 3. 입 중심 경로 추출
    mouth_path_px = extract_mouth_centerline(mouth_mask)

    # 4. 최종 로봇 좌표 명령 생성
    commands, scale = make_draw_commands(
        eye_centers_px,
        mouth_path_px,
        original_img.shape
    )

    # 5. CSV 저장
    save_commands_to_csv(commands, OUTPUT_CSV)

    # 6. Preview 저장
    save_preview(
        original_img,
        eye_centers_px,
        mouth_path_px,
        OUTPUT_PREVIEW
    )

    # 7. 결과 출력
    print("\n전처리 완료")
    print(f"입력 이미지: {INPUT_IMAGE}")
    print(f"CSV 저장: {OUTPUT_CSV}")
    print(f"Preview 저장: {OUTPUT_PREVIEW}")
    print(f"PNG 전체 폭 기준 scale: 1px = {scale:.4f} mm")

    print("\n[실제 작업 기준 파라미터]")
    print(f"DONKATSU_CENTER_X = {DONKATSU_CENTER_X}")
    print(f"DONKATSU_CENTER_Y = {DONKATSU_CENTER_Y}")
    print(f"DRAW_Z = {DRAW_Z}")
    print(f"TARGET_WIDTH_MM = {TARGET_WIDTH_MM}")
    print(f"X_SIGN = {X_SIGN}, Y_SIGN = {Y_SIGN}, SWAP_XY = {SWAP_XY}")

    print("\n[최종 명령 일부 출력]")
    for cmd in commands[:10]:
        print(
            f"{cmd['type']:4s} | "
            f"{cmd['name']:9s} | "
            f"id={cmd['point_id']:3d} | "
            f"rel=({cmd['x_rel']:.2f}, {cmd['y_rel']:.2f}) mm | "
            f"robot=({cmd['robot_x']:.2f}, {cmd['robot_y']:.2f}, {cmd['robot_z']:.2f})"
        )

    print(f"\n총 명령 점 개수: {len(commands)}")
    print("dot  = 눈 위치에서 짧게 소스 사출")
    print("path = 입 경로를 따라 연속 소스 사출")


if __name__ == "__main__":
    main()