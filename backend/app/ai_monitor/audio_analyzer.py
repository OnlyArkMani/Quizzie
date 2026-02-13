import numpy as np
from typing import Dict

class AudioAnalyzer:
    def __init__(self):
        self.sample_rate = 16000
        self.silence_threshold = 0.02
    
    def analyze_audio(self, audio_bytes: bytes) -> Dict:
        """
        Analyze audio for voice activity and loud noises
        """
        try:
            # Convert bytes to numpy array
            audio_data = np.frombuffer(audio_bytes, dtype=np.float32)
            
            if len(audio_data) == 0:
                return {'flags': [], 'severity': 'low', 'rms_energy': 0}
            
            flags = []
            severity = 'low'
            
            # Calculate RMS energy
            rms = np.sqrt(np.mean(audio_data**2))
            
            if rms > self.silence_threshold:
                # Voice activity detected
                if rms > 0.1:  # Loud noise threshold
                    flags.append('loud_noise_detected')
                    severity = 'medium'
            
            return {
                'flags': flags,
                'severity': severity,
                'rms_energy': float(rms)
            }
        
        except Exception as e:
            return {
                'flags': ['processing_error'],
                'severity': 'low',
                'rms_energy': 0,
                'error': str(e)
            }