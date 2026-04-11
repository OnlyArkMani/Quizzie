import io
import numpy as np
from typing import Dict

class AudioAnalyzer:
    def __init__(self):
        self.sample_rate = 16000
        # RMS thresholds tuned for normalised float32 audio (-1.0 to 1.0)
        self.silence_threshold = 0.01   # below this = essentially silence
        self.loud_threshold = 0.08      # above this = voice / suspicious noise

    def analyze_audio(self, audio_bytes: bytes) -> Dict:
        """
        Analyze audio for voice activity and loud noises.
        Accepts WebM/Opus or any format that soundfile/librosa can decode.
        """
        try:
            audio_data = self._decode_audio(audio_bytes)

            if audio_data is None or len(audio_data) == 0:
                return {'flags': [], 'severity': 'low', 'rms_energy': 0}

            flags = []
            severity = 'low'

            # Compute RMS on normalised float32 samples
            rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))

            if rms > self.loud_threshold:
                flags.append('loud_noise_detected')
                severity = 'medium'

            return {
                'flags': flags,
                'severity': severity,
                'rms_energy': rms
            }

        except Exception as e:
            return {
                'flags': ['processing_error'],
                'severity': 'low',
                'rms_energy': 0,
                'error': str(e)
            }

    def _decode_audio(self, audio_bytes: bytes) -> np.ndarray | None:
        """
        Decode compressed audio (WebM/Opus/WAV/etc.) to a flat float32 array.
        Tries soundfile first (fastest), falls back to librosa.
        """
        # --- attempt 1: soundfile (handles WAV, FLAC, OGG natively) ---
        try:
            import soundfile as sf
            data, _ = sf.read(io.BytesIO(audio_bytes), dtype='float32', always_2d=False)
            # If stereo, average to mono
            if data.ndim > 1:
                data = data.mean(axis=1)
            return data
        except Exception:
            pass

        # --- attempt 2: librosa (handles WebM/Opus via ffmpeg if installed) ---
        try:
            import librosa
            data, _ = librosa.load(io.BytesIO(audio_bytes), sr=None, mono=True)
            return data
        except Exception:
            pass

        return None