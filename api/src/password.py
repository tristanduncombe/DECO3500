import cv2
import mediapipe as mp
import json


def extract_hand_positions(image_path: str):
    """Use MediaPipe Hands to extract rich hand data from the image.

    Returns a list of hands where each hand is a dict:
      - handedness: 'Left' or 'Right'
      - landmarks: list of 21 (x,y,z) normalized
      - landmarks_px: list of 21 (x_px, y_px) pixel coordinates
      - bbox: [x_min, y_min, x_max, y_max] in pixel coordinates
      - score: detection score (if available)
    """
    mp_hands_module = mp.solutions.hands
    hands = mp_hands_module.Hands(static_image_mode=True, max_num_hands=2, min_detection_confidence=0.3)

    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"Could not read image at {image_path}")
    height, width = img.shape[:2]
    # Convert BGR to RGB
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    results = hands.process(rgb)
    out = []

    if results.multi_hand_landmarks:
        # results.multi_handedness aligns with multi_hand_landmarks
        for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
            handedness = None
            try:
                # get the label from multi_handedness if present
                handedness = results.multi_handedness[idx].classification[0].label
                score = results.multi_handedness[idx].classification[0].score
            except Exception:
                handedness = "Unknown"
                score = 0.0

            normalized = []
            pixel = []
            x_coords = []
            y_coords = []
            for lm in hand_landmarks.landmark:
                normalized.append((lm.x, lm.y, lm.z))
                x_px = int(lm.x * width)
                y_px = int(lm.y * height)
                pixel.append((x_px, y_px))
                x_coords.append(x_px)
                y_coords.append(y_px)

            if x_coords and y_coords:
                x_min, x_max = min(x_coords), max(x_coords)
                y_min, y_max = min(y_coords), max(y_coords)
                bbox = [x_min, y_min, x_max, y_max]
            else:
                bbox = [0, 0, 0, 0]

            out.append({
                "handedness": handedness,
                "score": float(score),
                "landmarks": normalized,
                "landmarks_px": pixel,
                "bbox": bbox,
            })

    hands.close()
    return out


def extract_body_and_hand_positions(image_path: str):
    """Extract pose key joints (limbs) and hand data, excluding face landmarks.

    Returns a dict:
      - pose: dict of joints (shoulder, elbow, wrist, hip, knee, ankle) for left/right with normalized and pixel coords
      - hands: same structure as previous extract_hand_positions (list of hand dicts)
    """
    # Use MediaPipe Pose and Hands together
    mp_pose = mp.solutions.pose
    mp_hands = mp.solutions.hands

    pose_detector = mp_pose.Pose(static_image_mode=True, model_complexity=1, enable_segmentation=False, min_detection_confidence=0.3)
    hands_detector = mp_hands.Hands(static_image_mode=True, max_num_hands=2, min_detection_confidence=0.3)

    img = cv2.imread(image_path)
    if img is None:
        raise RuntimeError(f"Could not read image at {image_path}")
    height, width = img.shape[:2]
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    pose_res = pose_detector.process(rgb)
    hands_res = hands_detector.process(rgb)

    result = {"pose": {}, "hands": []}

    # Pose joints of interest mapping from MediaPipe PoseLandmark
    joints_map = {
        "left_shoulder": mp_pose.PoseLandmark.LEFT_SHOULDER,
        "right_shoulder": mp_pose.PoseLandmark.RIGHT_SHOULDER,
        "left_elbow": mp_pose.PoseLandmark.LEFT_ELBOW,
        "right_elbow": mp_pose.PoseLandmark.RIGHT_ELBOW,
        "left_wrist": mp_pose.PoseLandmark.LEFT_WRIST,
        "right_wrist": mp_pose.PoseLandmark.RIGHT_WRIST,
        "left_hip": mp_pose.PoseLandmark.LEFT_HIP,
        "right_hip": mp_pose.PoseLandmark.RIGHT_HIP,
        "left_knee": mp_pose.PoseLandmark.LEFT_KNEE,
        "right_knee": mp_pose.PoseLandmark.RIGHT_KNEE,
        "left_ankle": mp_pose.PoseLandmark.LEFT_ANKLE,
        "right_ankle": mp_pose.PoseLandmark.RIGHT_ANKLE,
    }

    if pose_res and pose_res.pose_landmarks:
        for joint_name, lm_enum in joints_map.items():
            try:
                lm = pose_res.pose_landmarks.landmark[lm_enum]
                x_px = int(lm.x * width)
                y_px = int(lm.y * height)
                result["pose"][joint_name] = {
                    "normalized": (lm.x, lm.y, lm.z),
                    "pixel": (x_px, y_px),
                    "visibility": float(getattr(lm, 'visibility', 0.0)),
                }
            except Exception:
                result["pose"][joint_name] = None

    # Hands: reuse the hand extractor logic
    if hands_res and hands_res.multi_hand_landmarks:
        for idx, hand_landmarks in enumerate(hands_res.multi_hand_landmarks):
            handedness = None
            try:
                handedness = hands_res.multi_handedness[idx].classification[0].label
                score = hands_res.multi_handedness[idx].classification[0].score
            except Exception:
                handedness = "Unknown"
                score = 0.0

            normalized = []
            pixel = []
            x_coords = []
            y_coords = []
            for lm in hand_landmarks.landmark:
                normalized.append((lm.x, lm.y, lm.z))
                x_px = int(lm.x * width)
                y_px = int(lm.y * height)
                pixel.append((x_px, y_px))
                x_coords.append(x_px)
                y_coords.append(y_px)

            if x_coords and y_coords:
                x_min, x_max = min(x_coords), max(x_coords)
                y_min, y_max = min(y_coords), max(y_coords)
                bbox = [x_min, y_min, x_max, y_max]
            else:
                bbox = [0, 0, 0, 0]

            result["hands"].append({
                "handedness": handedness,
                "score": float(score),
                "landmarks": normalized,
                "landmarks_px": pixel,
                "bbox": bbox,
            })

    pose_detector.close()
    hands_detector.close()
    return result


def serialize_positions(positions: object) -> str:
    """Serialize positions dict to compact JSON string for storage."""
    try:
        return json.dumps(positions, separators=(',', ':'))
    except Exception:
        return json.dumps({}, separators=(',', ':'))


def sanitize_positions(positions: object) -> dict:
    """Remove pixel coordinates and other potentially identifying info from positions.

    Keeps only normalized coordinates and visibility/score where applicable so the
    stored positions are less likely to contain recoverable image-level PII.
    """
    if not positions or not isinstance(positions, dict):
        return {}

    out = {"pose": {}, "hands": []}

    pose = positions.get("pose", {}) or {}
    for joint, val in pose.items():
        if not val:
            out["pose"][joint] = None
            continue
        # keep only normalized coords and visibility
        out["pose"][joint] = {
            "normalized": val.get("normalized"),
            "visibility": float(val.get("visibility", 0.0)),
        }

    hands = positions.get("hands", []) or []
    for h in hands:
        if not isinstance(h, dict):
            continue
        sanitized_hand = {
            "handedness": h.get("handedness"),
            "score": float(h.get("score", 0.0)),
            # keep normalized landmarks only (no pixel coords)
            "landmarks": h.get("landmarks"),
        }
        out["hands"].append(sanitized_hand)

    return out


def build_fingerprint(positions: dict) -> list:
    """Create a fingerprint vector from positions dict.

    Strategy:
      - use hips midpoint as origin
      - use distance between hips as scale
      - pick joints: left_shoulder, right_shoulder, left_elbow, right_elbow, left_wrist, right_wrist
      - for each joint use normalized (x,y) relative to origin and scaled by torso length
    Returns a flat list of floats.
    """
    try:
        pose = positions.get("pose", {})
        left_hip = pose.get("left_hip")
        right_hip = pose.get("right_hip")
        if not left_hip or not right_hip:
            return []

        # pixel coords are (x_px, y_px)
        lx, ly = left_hip["pixel"]
        rx, ry = right_hip["pixel"]
        origin_x = (lx + rx) / 2.0
        origin_y = (ly + ry) / 2.0
        torso_len = ((lx - rx) ** 2 + (ly - ry) ** 2) ** 0.5
        if torso_len == 0:
            torso_len = 1.0

        joints = [
            "left_shoulder",
            "right_shoulder",
            "left_elbow",
            "right_elbow",
            "left_wrist",
            "right_wrist",
        ]

        vec = []
        for j in joints:
            v = pose.get(j)
            if not v:
                vec.extend([0.0, 0.0])
                continue
            x_px, y_px = v["pixel"]
            nx = (x_px - origin_x) / torso_len
            ny = (y_px - origin_y) / torso_len
            vec.extend([float(nx), float(ny)])
        return vec
    except Exception:
        return []


def compare_fingerprints(a: list, b: list) -> float:
    """Return a similarity score in [0,1] (1 == identical) using normalized L2 distance."""
    try:
        if not a or not b or len(a) != len(b):
            return 0.0
        # L2 distance
        dist = sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)) ** 0.5
        # normalize: maximum reasonable distance ~ sqrt(len) * 2 -> map to [0,1]
        max_dist = (len(a) ** 0.5) * 2.0
        score = max(0.0, 1.0 - (dist / max_dist))
        return float(score)
    except Exception:
        return 0.0
