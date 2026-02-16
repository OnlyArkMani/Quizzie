"""
Enhanced Face Detection System with Real-time Monitoring
Supports multiple detection modes and live health tracking
"""
import cv2
import mediapipe as mp
import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from datetime import datetime
import base64
from io import BytesIO

@dataclass
class DetectionResult:
    """Result from face detection analysis"""
    faces_detected: int
    face_present: bool
    looking_at_screen: bool
    multiple_faces: bool
    face_confidence: float
    head_pose: Dict[str, float]
    flags: List[Dict[str, any]]
    timestamp: datetime

@dataclass
class ProctoringConfig:
    """Configuration for proctoring features"""
    camera_enabled: bool = True
    microphone_enabled: bool = False
    face_detection_enabled: bool = True
    multiple_face_detection: bool = True
    head_pose_detection: bool = True
    tab_switch_detection: bool = True
    min_face_confidence: float = 0.6
    max_head_rotation: float = 30.0  # degrees
    detection_interval: int = 2  # seconds

class EnhancedFaceDetector:
    """Enhanced face detector with MediaPipe and advanced analysis"""
    
    def __init__(self, config: Optional[ProctoringConfig] = None):
        self.config = config or ProctoringConfig()
        
        # Initialize MediaPipe Face Detection
        self.mp_face_detection = mp.solutions.face_detection
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Initialize detectors
        self.face_detection = self.mp_face_detection.FaceDetection(
            model_selection=1,  # Full range detection
            min_detection_confidence=self.config.min_face_confidence
        )
        
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=3,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )
        
        # Tracking variables
        self.last_face_count = 0
        self.last_detection_time = None
        self.consecutive_violations = 0
        
    def analyze_frame(self, frame: np.ndarray) -> DetectionResult:
        """
        Analyze a video frame for proctoring violations
        
        Args:
            frame: BGR image from camera
            
        Returns:
            DetectionResult with all detection information
        """
        flags = []
        timestamp = datetime.utcnow()
        
        # Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # Detect faces
        face_results = self.face_detection.process(rgb_frame)
        mesh_results = self.face_mesh.process(rgb_frame)
        
        faces_detected = 0
        face_confidence = 0.0
        
        if face_results.detections:
            faces_detected = len(face_results.detections)
            # Get highest confidence
            face_confidence = max(
                detection.score[0] for detection in face_results.detections
            )
        
        # Check for multiple faces
        multiple_faces = faces_detected > 1
        if multiple_faces:
            flags.append({
                'type': 'multiple_faces',
                'severity': 'high',
                'count': faces_detected,
                'message': f'{faces_detected} faces detected'
            })
        
        # Check if face is present
        face_present = faces_detected >= 1
        if not face_present:
            flags.append({
                'type': 'no_face',
                'severity': 'high',
                'message': 'No face detected'
            })
        
        # Analyze head pose if face mesh is available
        head_pose = {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
        looking_at_screen = True
        
        if mesh_results.multi_face_landmarks and len(mesh_results.multi_face_landmarks) > 0:
            landmarks = mesh_results.multi_face_landmarks[0]
            head_pose = self._calculate_head_pose(landmarks, frame.shape)
            
            # Check if looking away (head rotation too much)
            max_rotation = max(
                abs(head_pose['pitch']),
                abs(head_pose['yaw']),
                abs(head_pose['roll'])
            )
            
            looking_at_screen = max_rotation < self.config.max_head_rotation
            
            if not looking_at_screen:
                flags.append({
                    'type': 'looking_away',
                    'severity': 'medium',
                    'head_pose': head_pose,
                    'message': f'Head rotation detected: {max_rotation:.1f}°'
                })
        elif face_present:
            # Face detected but no mesh - might be looking away
            looking_at_screen = False
            flags.append({
                'type': 'face_tracking_lost',
                'severity': 'medium',
                'message': 'Face tracking lost - possibly looking away'
            })
        
        return DetectionResult(
            faces_detected=faces_detected,
            face_present=face_present,
            looking_at_screen=looking_at_screen,
            multiple_faces=multiple_faces,
            face_confidence=face_confidence,
            head_pose=head_pose,
            flags=flags,
            timestamp=timestamp
        )
    
    def _calculate_head_pose(self, landmarks, image_shape) -> Dict[str, float]:
        """
        Calculate head pose (pitch, yaw, roll) from face mesh landmarks
        
        Uses perspective-n-point algorithm with key facial landmarks
        """
        h, w = image_shape[:2]
        
        # Key facial landmarks for pose estimation
        # Nose tip, chin, left eye corner, right eye corner, left mouth corner, right mouth corner
        landmark_indices = [1, 199, 33, 263, 61, 291]
        
        # 2D image points
        image_points = np.array([
            [landmarks.landmark[idx].x * w, landmarks.landmark[idx].y * h]
            for idx in landmark_indices
        ], dtype=np.float64)
        
        # 3D model points (generic face model in cm)
        model_points = np.array([
            (0.0, 0.0, 0.0),           # Nose tip
            (0.0, -33.0, -6.5),        # Chin
            (-22.5, 17.0, -14.5),      # Left eye corner
            (22.5, 17.0, -14.5),       # Right eye corner
            (-14.5, -19.0, -11.5),     # Left mouth corner
            (14.5, -19.0, -11.5)       # Right mouth corner
        ], dtype=np.float64)
        
        # Camera internals
        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1]
        ], dtype=np.float64)
        
        dist_coeffs = np.zeros((4, 1))  # Assuming no lens distortion
        
        # Solve PnP
        success, rotation_vector, translation_vector = cv2.solvePnP(
            model_points,
            image_points,
            camera_matrix,
            dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE
        )
        
        if not success:
            return {'pitch': 0.0, 'yaw': 0.0, 'roll': 0.0}
        
        # Convert rotation vector to rotation matrix
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        
        # Calculate Euler angles
        pose_mat = cv2.hconcat((rotation_matrix, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(pose_mat)
        
        pitch = euler_angles[0][0]
        yaw = euler_angles[1][0]
        roll = euler_angles[2][0]
        
        return {
            'pitch': float(pitch),
            'yaw': float(yaw),
            'roll': float(roll)
        }
    
    def draw_debug_info(self, frame: np.ndarray, result: DetectionResult) -> np.ndarray:
        """
        Draw debug information on frame for testing
        
        Args:
            frame: Original frame
            result: Detection result
            
        Returns:
            Frame with debug info drawn
        """
        debug_frame = frame.copy()
        
        # Draw face count
        cv2.putText(
            debug_frame,
            f"Faces: {result.faces_detected}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0) if result.faces_detected == 1 else (0, 0, 255),
            2
        )
        
        # Draw confidence
        cv2.putText(
            debug_frame,
            f"Confidence: {result.face_confidence:.2f}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )
        
        # Draw looking status
        status = "Looking at screen" if result.looking_at_screen else "Looking away"
        color = (0, 255, 0) if result.looking_at_screen else (0, 165, 255)
        cv2.putText(
            debug_frame,
            status,
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2
        )
        
        # Draw head pose
        pose_text = f"Pitch: {result.head_pose['pitch']:.1f}° Yaw: {result.head_pose['yaw']:.1f}°"
        cv2.putText(
            debug_frame,
            pose_text,
            (10, 120),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2
        )
        
        # Draw flags
        y_offset = 150
        for flag in result.flags:
            color_map = {'low': (0, 255, 255), 'medium': (0, 165, 255), 'high': (0, 0, 255)}
            color = color_map.get(flag['severity'], (255, 255, 255))
            cv2.putText(
                debug_frame,
                f"⚠ {flag['message']}",
                (10, y_offset),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2
            )
            y_offset += 30
        
        return debug_frame
    
    def encode_frame_to_base64(self, frame: np.ndarray) -> str:
        """
        Encode frame to base64 for transmission
        
        Args:
            frame: BGR image
            
        Returns:
            Base64 encoded JPEG string
        """
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buffer).decode('utf-8')
    
    def __del__(self):
        """Cleanup resources"""
        if hasattr(self, 'face_detection'):
            self.face_detection.close()
        if hasattr(self, 'face_mesh'):
            self.face_mesh.close()


class HealthCalculator:
    """Calculate health decrease based on violations"""
    
    # Health penalty points for different violations
    PENALTIES = {
        'no_face': 10,              # High penalty
        'multiple_faces': 15,        # Very high penalty
        'looking_away': 5,           # Medium penalty
        'face_tracking_lost': 5,     # Medium penalty
        'tab_switch': 8,             # High penalty
        'suspicious_audio': 3,       # Low penalty
        'excessive_movement': 2      # Low penalty
    }
    
    def __init__(self, initial_health: int = 100):
        self.initial_health = initial_health
        self.current_health = initial_health
        self.violation_history = []
        
    def apply_violation(self, violation_type: str, severity: str = 'medium') -> int:
        """
        Apply health penalty for a violation
        
        Args:
            violation_type: Type of violation
            severity: 'low', 'medium', 'high'
            
        Returns:
            New health value
        """
        base_penalty = self.PENALTIES.get(violation_type, 5)
        
        # Adjust by severity
        severity_multiplier = {'low': 0.5, 'medium': 1.0, 'high': 1.5}
        penalty = int(base_penalty * severity_multiplier.get(severity, 1.0))
        
        self.current_health = max(0, self.current_health - penalty)
        
        self.violation_history.append({
            'type': violation_type,
            'severity': severity,
            'penalty': penalty,
            'health_after': self.current_health,
            'timestamp': datetime.utcnow()
        })
        
        return self.current_health
    
    def get_health_status(self) -> Dict[str, any]:
        """Get current health status"""
        health_percentage = (self.current_health / self.initial_health) * 100
        
        if health_percentage > 70:
            status = 'good'
            color = 'green'
        elif health_percentage > 40:
            status = 'warning'
            color = 'yellow'
        elif health_percentage > 0:
            status = 'critical'
            color = 'red'
        else:
            status = 'failed'
            color = 'red'
        
        return {
            'current': self.current_health,
            'max': self.initial_health,
            'percentage': health_percentage,
            'status': status,
            'color': color,
            'violations_count': len(self.violation_history)
        }
    
    def reset_health(self, health: Optional[int] = None):
        """Reset health to initial or specified value"""
        self.current_health = health or self.initial_health
        self.violation_history = []


# Example usage
if __name__ == "__main__":
    # Test the detector
    detector = EnhancedFaceDetector()
    health = HealthCalculator()
    
    # Simulate camera capture
    cap = cv2.VideoCapture(0)
    
    print("Starting enhanced face detection...")
    print("Press 'q' to quit")
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        # Analyze frame
        result = detector.analyze_frame(frame)
        
        # Apply health penalties
        for flag in result.flags:
            health.apply_violation(flag['type'], flag['severity'])
        
        # Draw debug info
        debug_frame = detector.draw_debug_info(frame, result)
        
        # Draw health bar
        health_status = health.get_health_status()
        cv2.rectangle(debug_frame, (10, frame.shape[0] - 50), 
                     (10 + int(health_status['percentage'] * 3), frame.shape[0] - 30),
                     (0, 255, 0) if health_status['status'] == 'good' else (0, 0, 255), -1)
        cv2.putText(debug_frame, f"Health: {health_status['current']}/{health_status['max']}",
                   (10, frame.shape[0] - 55), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        cv2.imshow('Enhanced Proctoring', debug_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyAllWindows()