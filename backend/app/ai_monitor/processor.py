from typing import Dict, List

from app.ai_monitor.face_detector import FaceDetector
from app.ai_monitor.audio_analyzer import AudioAnalyzer
from app.ai_monitor import scoring


class MonitoringProcessor:
    def __init__(self):
        self.face_detector = FaceDetector()
        self.audio_analyzer = AudioAnalyzer()

    def process_frame(self, image_bytes: bytes) -> Dict:
        """Process a single video frame."""
        return self.face_detector.analyze_frame(image_bytes)

    def process_audio(self, audio_bytes: bytes) -> Dict:
        """Process a single audio chunk."""
        return self.audio_analyzer.analyze_audio(audio_bytes)

    def get_severity_score(self, flags: List) -> int:
        """
        Aggregate suspicion weight for a list of flags.

        Accepts either plain flag-type strings or flag dicts
        ({'type': ..., 'severity': ...}); both are normalised via the shared
        scoring module so the weights match health and suspicion scoring.
        """
        total = 0
        for flag in flags:
            if isinstance(flag, dict):
                flag_type = flag.get("type", "")
                severity = flag.get("severity", "medium")
            else:
                flag_type = flag
                severity = "medium"
            total += scoring.suspicion_weight(flag_type) * scoring.severity_numeric(severity)
        return int(total)

    def should_flag_attempt(self, total_flags: int, severity_score: int) -> bool:
        """Determine if an attempt should be flagged for manual review."""
        return total_flags > 5 or severity_score > 30
