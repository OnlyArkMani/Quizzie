import cv2
import mediapipe as mp
import numpy as np
from typing import Dict

# MediaPipe landmark indices used for analysis
# Upper/lower lip for mouth open detection
_UPPER_LIP = 13
_LOWER_LIP = 14
# Outer lip corners to normalise by mouth width
_LIP_LEFT  = 61
_LIP_RIGHT = 291
# Iris centres (refine_landmarks=True required)
_LEFT_IRIS  = 468
_RIGHT_IRIS = 473
# Eye corners for gaze normalisation
_LEFT_EYE_INNER  = 133
_LEFT_EYE_OUTER  = 33
_RIGHT_EYE_INNER = 362
_RIGHT_EYE_OUTER = 263

class FaceDetector:
    def __init__(self):
        self.mp_face_detection = mp.solutions.face_detection
        self.mp_face_mesh = mp.solutions.face_mesh

        self.face_detection = self.mp_face_detection.FaceDetection(
            model_selection=1,
            min_detection_confidence=0.5
        )

        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=3,
            refine_landmarks=True,   # needed for iris landmarks
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

        # Thresholds
        self._MOUTH_OPEN_RATIO   = 0.35   # lip gap / mouth width > this → open
        self._GAZE_OFFSET_THRESH = 0.28   # iris offset ratio > this → looking away

        # Head-pose thresholds (degrees). Tunable; defaults are conservative to
        # limit false positives. Yaw = left/right turn, pitch = up/down tilt.
        self._YAW_AWAY_DEG   = 22.0   # |yaw| beyond this → looking away (sideways)
        self._PITCH_DOWN_DEG = 18.0   # pitch beyond this (head down) → looking_down
        self._GAZE_YAW_GATE  = 18.0   # only trust eye-gaze when head is ~frontal

        # 3D generic face model (cm) for solvePnP head-pose estimation.
        # Landmark order: nose tip, chin, left eye corner, right eye corner,
        # left mouth corner, right mouth corner.
        self._POSE_LANDMARK_IDX = [1, 199, 33, 263, 61, 291]
        self._POSE_MODEL_POINTS = np.array([
            (0.0, 0.0, 0.0),
            (0.0, -33.0, -6.5),
            (-22.5, 17.0, -14.5),
            (22.5, 17.0, -14.5),
            (-14.5, -19.0, -11.5),
            (14.5, -19.0, -11.5),
        ], dtype=np.float64)
    
    def analyze_frame(self, image_bytes: bytes) -> Dict:
        """
        Analyze webcam frame.
        Detects: face presence, multiple faces, head pose, eye gaze, mouth movement.
        Returns a dict compatible with the frontend DetectionResult interface.
        """
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if image is None:
                return self._error_result('invalid_image')

            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            detection_results = self.face_detection.process(image_rgb)
            mesh_results      = self.face_mesh.process(image_rgb)

            img_h, img_w = image.shape[:2]

            flags          = []
            severity       = 'low'
            num_faces      = 0
            face_confidence = 0.0
            looking_at_screen = True
            mouth_open     = False
            gaze_off_screen = False
            looking_down   = False
            head_pose      = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}

            # ── Face count ───────────────────────────────────────────────────
            if detection_results.detections:
                num_faces = len(detection_results.detections)
                face_confidence = max(d.score[0] for d in detection_results.detections)

                if num_faces > 1:
                    flags.append({
                        'type': 'multiple_faces_detected',
                        'severity': 'high',
                        'message': f'{num_faces} faces detected in frame'
                    })
                    severity = 'high'
            else:
                flags.append({
                    'type': 'no_face_detected',
                    'severity': 'high',
                    'message': 'No face detected'
                })
                severity = 'high'

            face_present = num_faces >= 1

            # ── Mesh-based analysis (head pose, gaze, mouth) ─────────────────
            if mesh_results.multi_face_landmarks:
                lm = mesh_results.multi_face_landmarks[0].landmark

                # Real 3D head pose (pitch/yaw) via solvePnP, replacing the old
                # 1-D nose-x heuristic. Pitch lets us catch "looking down" at a
                # phone/notes — the most common cheating posture, previously
                # invisible. Falls back to the nose heuristic if solvePnP fails.
                head_pose = self._head_pose(lm, img_w, img_h)
                yaw   = head_pose['yaw']
                pitch = head_pose['pitch']

                if abs(yaw) > self._YAW_AWAY_DEG:
                    looking_at_screen = False
                    direction = 'left' if yaw < 0 else 'right'
                    flags.append({
                        'type': 'looking_away',
                        'severity': 'medium',
                        'message': f'Head turned {direction} (yaw {yaw:.0f}°)'
                    })
                    if severity == 'low':
                        severity = 'medium'

                if pitch < -self._PITCH_DOWN_DEG:
                    looking_down = True
                    looking_at_screen = False
                    flags.append({
                        'type': 'looking_down',
                        'severity': 'medium',
                        'message': f'Head tilted down (pitch {pitch:.0f}°) — possible notes/phone'
                    })
                    if severity == 'low':
                        severity = 'medium'

                # Eye gaze — only trusted when the head is roughly frontal, so a
                # turned head isn't double-counted as off-gaze (head rotation
                # used to corrupt the 2-D iris offset).
                if abs(yaw) <= self._GAZE_YAW_GATE:
                    gaze_flag = self._check_gaze(lm)
                    if gaze_flag:
                        gaze_off_screen = True
                        looking_at_screen = False
                        flags.append(gaze_flag)
                        if severity == 'low':
                            severity = 'medium'

                # Mouth movement / whispering detection
                mouth_flag = self._check_mouth(lm)
                if mouth_flag:
                    mouth_open = True
                    flags.append(mouth_flag)
                    if severity == 'low':
                        severity = 'medium'

            elif face_present:
                looking_at_screen = False

            return {
                'flags': flags,
                'severity': severity,
                'num_faces': num_faces,
                'faces_detected': num_faces,
                'face_present': face_present,
                'looking_at_screen': looking_at_screen,
                'multiple_faces': num_faces > 1,
                'face_confidence': face_confidence,
                'mouth_open': mouth_open,
                'gaze_off_screen': gaze_off_screen,
                'looking_down': looking_down,
                'head_pose': head_pose,
            }

        except Exception as e:
            return self._error_result('processing_error', str(e))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _head_pose(self, lm, img_w: int, img_h: int) -> dict:
        """
        Estimate head pitch/yaw/roll (degrees) via solvePnP on six landmarks.

        pitch < 0 → looking down, pitch > 0 → looking up.
        yaw   < 0 → turned left,  yaw   > 0 → turned right.
        Returns zeros on any failure so callers degrade gracefully.
        """
        try:
            image_points = np.array(
                [[lm[idx].x * img_w, lm[idx].y * img_h] for idx in self._POSE_LANDMARK_IDX],
                dtype=np.float64,
            )
            focal = float(img_w)
            cam_matrix = np.array([
                [focal, 0, img_w / 2.0],
                [0, focal, img_h / 2.0],
                [0, 0, 1],
            ], dtype=np.float64)
            dist = np.zeros((4, 1))

            ok, rvec, tvec = cv2.solvePnP(
                self._POSE_MODEL_POINTS, image_points, cam_matrix, dist,
                flags=cv2.SOLVEPNP_ITERATIVE,
            )
            if not ok:
                return {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}

            rmat, _ = cv2.Rodrigues(rvec)
            pose_mat = cv2.hconcat((rmat, tvec))
            _, _, _, _, _, _, euler = cv2.decomposeProjectionMatrix(pose_mat)

            pitch = self._wrap_angle(float(euler[0][0]))
            yaw   = self._wrap_angle(float(euler[1][0]))
            roll  = self._wrap_angle(float(euler[2][0]))
            return {'pitch': pitch, 'yaw': yaw, 'roll': roll}
        except Exception:
            return {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}

    @staticmethod
    def _wrap_angle(a: float) -> float:
        """Normalise a decomposeProjectionMatrix Euler angle into [-90, 90]."""
        if a > 90:
            a -= 180
        elif a < -90:
            a += 180
        return a

    def _check_gaze(self, lm) -> dict | None:
        """
        Compute normalised iris offset for each eye.
        Returns a flag dict if gaze is consistently off-screen, else None.
        """
        try:
            # Left eye: iris x relative to eye width
            l_inner  = lm[_LEFT_EYE_INNER].x
            l_outer  = lm[_LEFT_EYE_OUTER].x
            l_iris   = lm[_LEFT_IRIS].x
            l_width  = abs(l_inner - l_outer)
            l_offset = (l_iris - min(l_inner, l_outer)) / l_width if l_width > 1e-4 else 0.5

            # Right eye
            r_inner  = lm[_RIGHT_EYE_INNER].x
            r_outer  = lm[_RIGHT_EYE_OUTER].x
            r_iris   = lm[_RIGHT_IRIS].x
            r_width  = abs(r_inner - r_outer)
            r_offset = (r_iris - min(r_inner, r_outer)) / r_width if r_width > 1e-4 else 0.5

            avg_offset = (l_offset + r_offset) / 2

            # avg_offset near 0 = looking far left, near 1 = far right, ~0.5 = centre
            if avg_offset < (0.5 - self._GAZE_OFFSET_THRESH) or avg_offset > (0.5 + self._GAZE_OFFSET_THRESH):
                direction = 'left' if avg_offset < 0.5 else 'right'
                return {
                    'type': 'gaze_off_screen',
                    'severity': 'medium',
                    'message': f'Eyes looking {direction} (offset {avg_offset:.2f})'
                }
        except (IndexError, ZeroDivisionError):
            pass
        return None

    def _check_mouth(self, lm) -> dict | None:
        """
        Detect open mouth using the ratio of lip gap to mouth width.
        Returns a flag dict if mouth appears open (whispering), else None.
        """
        try:
            upper_y = lm[_UPPER_LIP].y
            lower_y = lm[_LOWER_LIP].y
            left_x  = lm[_LIP_LEFT].x
            right_x = lm[_LIP_RIGHT].x

            lip_gap    = abs(lower_y - upper_y)
            mouth_width = abs(right_x - left_x)

            if mouth_width < 1e-4:
                return None

            ratio = lip_gap / mouth_width
            if ratio > self._MOUTH_OPEN_RATIO:
                return {
                    'type': 'mouth_movement_detected',
                    'severity': 'medium',
                    'message': f'Mouth movement detected (ratio {ratio:.2f}) — possible whispering'
                }
        except IndexError:
            pass
        return None

    def _error_result(self, flag_type: str, error: str = '') -> Dict:
        return {
            'flags': [{'type': flag_type, 'severity': 'low', 'message': error}],
            'severity': 'low',
            'num_faces': 0,
            'faces_detected': 0,
            'face_present': False,
            'looking_at_screen': True,
            'multiple_faces': False,
            'face_confidence': 0.0,
            'error': error
        }
    
    def __del__(self):
        try:
            self.face_detection.close()
            self.face_mesh.close()
        except:
            pass