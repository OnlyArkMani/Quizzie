from typing import Dict, List
from app.ai_monitor.face_detector import FaceDetector
from app.ai_monitor.audio_analyzer import AudioAnalyzer

class MonitoringProcessor:
    def __init__(self):
        self.face_detector = FaceDetector()
        self.audio_analyzer = AudioAnalyzer()
    
    def process_frame(self, image_bytes: bytes) -> Dict:
        """
        Process video frame
        """
        return self.face_detector.analyze_frame(image_bytes)
    
    def process_audio(self, audio_bytes: bytes) -> Dict:
        """
        Process audio chunk
        """
        return self.audio_analyzer.analyze_audio(audio_bytes)
    
    def get_severity_score(self, flags: List[str]) -> int:
        """
        Calculate severity score based on flags
        """
        severity_weights = {
            'no_face_detected': 10,
            'multiple_faces_detected': 10,
            'looking_away': 5,
            'loud_noise_detected': 3,
            'multiple_voices_detected': 8,
            'tab_switch': 7,
        }
        
        total_score = sum(severity_weights.get(flag, 1) for flag in flags)
        return total_score
    
    def should_flag_attempt(self, total_flags: int, severity_score: int) -> bool:
        """
        Determine if attempt should be flagged for review
        """
        # Flag if more than 5 incidents or severity score > 30
        return total_flags > 5 or severity_score > 30