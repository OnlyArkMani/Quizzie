import cv2
import mediapipe as mp
import numpy as np
from typing import Dict

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
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
    
    def analyze_frame(self, image_bytes: bytes) -> Dict:
        """
        Analyze webcam frame for face detection and head pose.
        Returns a dict compatible with the frontend DetectionResult interface.
        """
        try:
            # Decode image
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                return self._error_result('invalid_image')
            
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Detect faces
            detection_results = self.face_detection.process(image_rgb)
            mesh_results = self.face_mesh.process(image_rgb)
            
            flags = []
            severity = 'low'
            num_faces = 0
            face_confidence = 0.0
            looking_at_screen = True

            # --- Face count ---
            if detection_results.detections:
                num_faces = len(detection_results.detections)
                face_confidence = max(
                    d.score[0] for d in detection_results.detections
                )

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

            # --- Head pose (looking away) ---
            if mesh_results.multi_face_landmarks:
                landmarks = mesh_results.multi_face_landmarks[0]
                nose_tip   = landmarks.landmark[1]
                left_eye   = landmarks.landmark[33]
                right_eye  = landmarks.landmark[263]

                eye_center_x = (left_eye.x + right_eye.x) / 2
                deviation = abs(nose_tip.x - eye_center_x)

                if deviation > 0.15:
                    looking_at_screen = False
                    flags.append({
                        'type': 'looking_away',
                        'severity': 'medium',
                        'message': f'Head turned away (deviation {deviation:.2f})'
                    })
                    if severity == 'low':
                        severity = 'medium'
            elif face_present:
                # Face detected but mesh failed — likely looking away
                looking_at_screen = False

            # Return the full structure the frontend expects
            return {
                'flags': flags,
                'severity': severity,
                'num_faces': num_faces,
                # Fields expected by frontend DetectionResult interface:
                'faces_detected': num_faces,
                'face_present': face_present,
                'looking_at_screen': looking_at_screen,
                'multiple_faces': num_faces > 1,
                'face_confidence': face_confidence,
            }
        
        except Exception as e:
            return self._error_result('processing_error', str(e))

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