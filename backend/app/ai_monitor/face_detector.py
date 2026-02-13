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
        Analyze webcam frame for face detection and head pose
        """
        try:
            # Decode image
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                return {'flags': ['invalid_image'], 'severity': 'high', 'num_faces': 0}
            
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Detect faces
            detection_results = self.face_detection.process(image_rgb)
            mesh_results = self.face_mesh.process(image_rgb)
            
            flags = []
            severity = 'low'
            num_faces = 0
            
            # Check number of faces
            if detection_results.detections:
                num_faces = len(detection_results.detections)
                
                if num_faces == 0:
                    flags.append('no_face_detected')
                    severity = 'high'
                elif num_faces > 1:
                    flags.append('multiple_faces_detected')
                    severity = 'high'
            else:
                flags.append('no_face_detected')
                severity = 'high'
            
            # Check head pose (looking away)
            if mesh_results.multi_face_landmarks:
                for face_landmarks in mesh_results.multi_face_landmarks:
                    # Calculate head pose using nose tip and eye landmarks
                    nose_tip = face_landmarks.landmark[1]
                    left_eye = face_landmarks.landmark[33]
                    right_eye = face_landmarks.landmark[263]
                    
                    # Simple heuristic: if nose is too far from center
                    eye_center_x = (left_eye.x + right_eye.x) / 2
                    deviation = abs(nose_tip.x - eye_center_x)
                    
                    if deviation > 0.15:  # Threshold
                        flags.append('looking_away')
                        severity = 'medium' if severity == 'low' else severity
            
            return {
                'flags': flags,
                'severity': severity,
                'num_faces': num_faces
            }
        
        except Exception as e:
            return {
                'flags': ['processing_error'],
                'severity': 'low',
                'num_faces': 0,
                'error': str(e)
            }
    
    def __del__(self):
        try:
            self.face_detection.close()
            self.face_mesh.close()
        except:
            pass