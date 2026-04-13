import React, { useEffect, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Camera,
  CameraOff,
  AlertTriangle,
  CheckCircle,
  Eye,
  EyeOff,
  Loader,
  Mic,
  Shield
} from 'lucide-react';
import api from '@/lib/api';

interface CameraProctoringProps {
  attemptId: string;
  isActive: boolean;
  settings: {
    camera_enabled: boolean;
    microphone_enabled: boolean;
    face_detection_enabled: boolean;
    detection_interval: number;
  };
  onViolation?: (violation: any) => void;
}

interface DetectionResult {
  faces_detected: number;
  face_present: boolean;
  looking_at_screen: boolean;
  multiple_faces: boolean;
  face_confidence: number;
  mouth_open: boolean;
  gaze_off_screen: boolean;
  flags: Array<{
    type: string;
    severity: string;
    message: string;
  }>;
}

// Strike system: tracks per-violation-type consecutive hits
// First hit = warning only (no health loss), second+ = full penalty
const GRACE_PERIOD_MS = 15_000;  // 15 s no monitoring after exam starts
const RECOVERY_INTERVAL_MS = 60_000; // recover health every 60 s of clean behaviour

const CameraProctoring: React.FC<CameraProctoringProps> = ({
  attemptId,
  isActive,
  settings,
  onViolation
}) => {
  const videoRef    = useRef<HTMLVideoElement>(null);
  const canvasRef   = useRef<HTMLCanvasElement>(null);
  const streamRef   = useRef<MediaStream | null>(null);
  const detectionIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recoveryIntervalRef  = useRef<ReturnType<typeof setInterval> | null>(null);

  // Strike tracking: maps violation type -> consecutive count
  const strikesRef  = useRef<Record<string, number>>({});
  const gracePeriodActiveRef = useRef(true);
  const cleanStreakRef = useRef(0); // frames with zero flags in a row

  const [cameraReady, setCameraReady]   = useState(false);
  const [cameraError, setCameraError]   = useState<string | null>(null);
  const [isDetecting, setIsDetecting]   = useState(false);
  const [lastDetection, setLastDetection] = useState<DetectionResult | null>(null);
  const [frameCount, setFrameCount]     = useState(0);
  const [showPreview, setShowPreview]   = useState(false);
  const [audioDetecting, setAudioDetecting] = useState(false);

  // Warning overlay state
  const [warningOverlay, setWarningOverlay] = useState<{ message: string; type: string } | null>(null);
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);

  // ── Grace period: disable monitoring for first 15 s ──────────────────────
  useEffect(() => {
    if (!isActive) return;
    gracePeriodActiveRef.current = true;
    const t = setTimeout(() => {
      gracePeriodActiveRef.current = false;
    }, GRACE_PERIOD_MS);
    return () => clearTimeout(t);
  }, [isActive]);

  // ── Health recovery: restore 3 HP every 60 s of clean behaviour ───────
  useEffect(() => {
    if (!isActive || !attemptId) return;
    recoveryIntervalRef.current = setInterval(async () => {
      if (cleanStreakRef.current >= 3) {  // at least 3 clean frames in row
        try {
          await api.post('/monitor/enhanced/recover', { attempt_id: attemptId, amount: 3 });
        } catch { /* silent — recovery is best-effort */ }
      }
    }, RECOVERY_INTERVAL_MS);
    return () => {
      if (recoveryIntervalRef.current) clearInterval(recoveryIntervalRef.current);
    };
  }, [isActive, attemptId]);

  // ── Tab / blur detection ───────────────────────────────────────
  useEffect(() => {
    if (!isActive) return;
    const handleViolation = () => {
      if (gracePeriodActiveRef.current) return;
      handleStrike({
        type: 'tab_switch',
        severity: 'high',
        message: 'Student switched tabs or lost window focus',
      });
    };
    const onVisibility = () => { if (document.hidden) handleViolation(); };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('blur', handleViolation);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('blur', handleViolation);
    };
  }, [isActive]);

  // ── Camera init ────────────────────────────────────────────────
  useEffect(() => {
    let isMounted = true;
    if (!isActive || (!settings.camera_enabled && !settings.microphone_enabled)) {
      stopCamera();
      return;
    }
    startCamera(isMounted);
    return () => { isMounted = false; stopCamera(); };
  }, [isActive, settings.camera_enabled, settings.microphone_enabled]);

  // ── Detection loop ─────────────────────────────────────────────
  useEffect(() => {
    if (!cameraReady || !isActive || !settings.face_detection_enabled) {
      if (detectionIntervalRef.current) { clearInterval(detectionIntervalRef.current); detectionIntervalRef.current = null; }
      return;
    }
    const interval = settings.detection_interval * 1000;
    detectionIntervalRef.current = setInterval(() => captureAndAnalyzeFrame(), interval);
    captureAndAnalyzeFrame();
    return () => { if (detectionIntervalRef.current) { clearInterval(detectionIntervalRef.current); detectionIntervalRef.current = null; } };
  }, [cameraReady, isActive, settings.face_detection_enabled, settings.detection_interval]);

  // ── Strike system ──────────────────────────────────────────────
  const handleStrike = useCallback((violation: { type: string; severity: string; message: string }) => {
    if (gracePeriodActiveRef.current) return;

    const strikes = strikesRef.current;
    const prev = strikes[violation.type] ?? 0;
    strikes[violation.type] = prev + 1;

    if (prev === 0) {
      // First offence: show warning, reset clean streak, do NOT penalise health
      cleanStreakRef.current = 0;
      showWarning(violation);
    } else {
      // Second+ offence: full penalty
      cleanStreakRef.current = 0;
      showWarning(violation, true);
      reportViolation(violation);
    }
  }, []);

  const showWarning = (violation: { type: string; message: string }, isPenalty = false) => {
    if (warningTimerRef.current) clearTimeout(warningTimerRef.current);
    setWarningOverlay({
      message: isPenalty
        ? `⚠️ Penalty applied: ${violation.message}`
        : `⚠️ Warning: ${violation.message} — next time will be penalised`,
      type: isPenalty ? 'penalty' : 'warning',
    });
    warningTimerRef.current = setTimeout(() => setWarningOverlay(null), 4000);
  };

  // ── Camera helpers ─────────────────────────────────────────────
  const startCamera = async (isMounted = true) => {
    try {
      setCameraError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: settings.camera_enabled ? { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'user' } : false,
        audio: settings.microphone_enabled
      });
      if (!isMounted) { stream.getTracks().forEach(t => t.stop()); return; }

      if (videoRef.current && settings.camera_enabled) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => { videoRef.current?.play(); setCameraReady(true); };
      } else if (!settings.camera_enabled && settings.microphone_enabled) {
        setCameraReady(true);
      }
      streamRef.current = stream;

      if (settings.microphone_enabled) {
        const recorder = new MediaRecorder(stream);
        mediaRecorderRef.current = recorder;
        recorder.ondataavailable = async (e) => {
          if (e.data.size > 0 && !audioDetecting) {
            setAudioDetecting(true);
            try {
              const formData = new FormData();
              formData.append('attempt_id', attemptId);
              formData.append('file', e.data, 'audio.webm');
              const res = await api.post('/monitor/audio', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
              if (res.data.flags?.length > 0) {
                res.data.flags.forEach((flag: any) => {
                  const v = typeof flag === 'string'
                    ? { type: flag, severity: 'medium', message: flag.replace(/_/g, ' ') }
                    : flag;
                  handleStrike(v);
                });
              }
            } catch { /* silent */ } finally { setAudioDetecting(false); }
          }
        };
        recorder.start(settings.detection_interval * 1000);
      }
    } catch (error: any) {
      setCameraError(error.message || 'Failed to access camera/microphone');
      setCameraReady(false);
    }
  };

  const stopCamera = () => {
    if (mediaRecorderRef.current?.state !== 'inactive') mediaRecorderRef.current?.stop();
    streamRef.current?.getTracks().forEach(t => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    if (detectionIntervalRef.current) { clearInterval(detectionIntervalRef.current); detectionIntervalRef.current = null; }
    setCameraReady(false);
  };

  const captureAndAnalyzeFrame = useCallback(async () => {
    if (!videoRef.current || !canvasRef.current || isDetecting) return;
    try {
      setIsDetecting(true);
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d');
      if (!context) return;
      canvas.width  = video.videoWidth;
      canvas.height = video.videoHeight;
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      canvas.toBlob(async (blob) => {
        if (!blob) return;
        try {
          const formData = new FormData();
          formData.append('attempt_id', attemptId);
          formData.append('file', blob, 'frame.jpg');
          const response = await api.post('/monitor/frame', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
          const result: DetectionResult = response.data;
          setLastDetection(result);
          setFrameCount(prev => prev + 1);

          if (result.flags?.length > 0) {
            // Don't monitor during grace period
            if (!gracePeriodActiveRef.current) {
              result.flags.forEach(flag => handleStrike(flag));
            }
            cleanStreakRef.current = 0;
          } else {
            // No flags this frame — increment clean streak, also reset strikes on prolonged clean run
            cleanStreakRef.current += 1;
            if (cleanStreakRef.current >= 5) {
              strikesRef.current = {};
            }
          }
        } catch { /* silent */ } finally { setIsDetecting(false); }
      }, 'image/jpeg', 0.8);
    } catch { setIsDetecting(false); }
  }, [attemptId, isDetecting, handleStrike]);

  const reportViolation = async (violation: { type: string; severity: string; message: string }) => {
    try {
      await api.post('/monitor/enhanced/violation', {
        attempt_id: attemptId,
        event_type: 'proctoring_flag',
        flags: [{ ...violation, metadata: { timestamp: new Date().toISOString() } }],
        timestamp: new Date().toISOString()
      });
      if (onViolation) onViolation(violation);
    } catch { /* silent */ }
  };

  // ── UI helpers ───────────────────────────────────────────────
  const getStatusColor = () => {
    if (!lastDetection) return 'text-slate-400';
    if (!lastDetection.face_present) return 'text-rose-500';
    if (lastDetection.flags.length === 0) return 'text-emerald-500';
    const hasCritical = lastDetection.flags.some(f => f.severity === 'high');
    return hasCritical ? 'text-rose-500' : 'text-amber-500';
  };

  const getStatusMessage = () => {
    if (gracePeriodActiveRef.current) return '⏳ Grace period — monitoring starts shortly...';
    if (!cameraReady) return 'Camera initializing...';
    if (!lastDetection) return 'Waiting for first detection...';
    if (!lastDetection.face_present) return '⚠️ No face detected';
    if (lastDetection.multiple_faces) return '⚠️ Multiple faces detected';
    if (lastDetection.gaze_off_screen) return '⚠️ Eyes looking off screen';
    if (lastDetection.mouth_open) return '⚠️ Mouth movement detected';
    if (!lastDetection.looking_at_screen) return '⚠️ Looking away from screen';
    return '✅ All good — monitoring active';
  };

  if (!settings.camera_enabled) {
    return (
      <div className="bg-slate-100 rounded-lg p-6 text-center">
        <CameraOff className="w-12 h-12 text-slate-400 mx-auto mb-3" />
        <p className="text-slate-600">Camera monitoring is disabled for this exam</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">

      {/* Warning / Penalty Overlay */}
      <AnimatePresence>
        {warningOverlay && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            className={`flex items-start gap-3 px-4 py-3 rounded-lg border ${
              warningOverlay.type === 'penalty'
                ? 'bg-rose-50 border-rose-300 text-rose-800'
                : 'bg-amber-50 border-amber-300 text-amber-800'
            }`}
          >
            <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-sm">
                {warningOverlay.type === 'penalty' ? 'Penalty applied' : 'First warning'}
              </p>
              <p className="text-xs mt-0.5">{warningOverlay.message}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Status Bar */}
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`relative ${getStatusColor()}`}>
              {cameraReady ? <Camera className="w-6 h-6" /> : <Loader className="w-6 h-6 animate-spin" />}
              {cameraReady && (
                <motion.div
                  className="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full"
                  animate={{ scale: [1, 1.2, 1] }}
                  transition={{ repeat: Infinity, duration: 2 }}
                />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p className="font-semibold text-slate-900">Camera Proctoring</p>
                {gracePeriodActiveRef.current && (
                  <span className="text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-medium">
                    Grace period
                  </span>
                )}
              </div>
              <p className={`text-sm ${getStatusColor()}`}>{getStatusMessage()}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {settings.microphone_enabled && (
              <div className={`p-1.5 rounded-lg ${audioDetecting ? 'bg-rose-100' : 'bg-slate-100'}`}>
                <Mic className={`w-4 h-4 ${audioDetecting ? 'text-rose-500' : 'text-slate-400'}`} />
              </div>
            )}
            <button
              onClick={() => setShowPreview(!showPreview)}
              className="text-sm flex items-center gap-2 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
            >
              {showPreview ? <><EyeOff className="w-4 h-4" /> Hide</> : <><Eye className="w-4 h-4" /> Preview</>}
            </button>
          </div>
        </div>

        {lastDetection && (
          <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-5 gap-3 text-center">
            <div>
              <p className="text-xl font-bold text-slate-900">{lastDetection.faces_detected}</p>
              <p className="text-xs text-slate-500">Faces</p>
            </div>
            <div>
              <p className="text-xl font-bold text-slate-900">{(lastDetection.face_confidence * 100).toFixed(0)}%</p>
              <p className="text-xs text-slate-500">Confidence</p>
            </div>
            <div>
              <p className="text-xl font-bold text-slate-900">{frameCount}</p>
              <p className="text-xs text-slate-500">Frames</p>
            </div>
            <div>
              <p className={`text-xl font-bold ${lastDetection.gaze_off_screen ? 'text-amber-500' : 'text-emerald-500'}`}>
                {lastDetection.gaze_off_screen ? 'Off' : 'On'}
              </p>
              <p className="text-xs text-slate-500">Gaze</p>
            </div>
            <div>
              <p className={`text-xl font-bold ${lastDetection.mouth_open ? 'text-amber-500' : 'text-emerald-500'}`}>
                {lastDetection.mouth_open ? 'Yes' : 'No'}
              </p>
              <p className="text-xs text-slate-500">Mouth</p>
            </div>
          </div>
        )}
      </div>

      {cameraError && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-rose-50 border border-rose-200 rounded-lg p-4 flex items-start gap-3"
        >
          <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-rose-900">Camera Access Error</p>
            <p className="text-sm text-rose-700 mt-1">{cameraError}</p>
            <button onClick={() => startCamera()} className="mt-3 text-sm font-medium text-rose-600 hover:text-rose-700">Try Again</button>
          </div>
        </motion.div>
      )}

      <div className={showPreview && cameraReady ? 'bg-white rounded-lg border border-slate-200 overflow-hidden relative' : 'hidden'}>
        <video ref={videoRef} autoPlay playsInline muted className="w-full h-auto max-h-96 object-cover bg-slate-900" />
        <AnimatePresence>
          {showPreview && cameraReady && lastDetection && (
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="absolute top-3 left-3 right-3 flex flex-wrap gap-2 pointer-events-none"
            >
              {lastDetection.face_present && !lastDetection.multiple_faces && !lastDetection.gaze_off_screen && !lastDetection.mouth_open && lastDetection.looking_at_screen && (
                <div className="inline-flex items-center gap-2 bg-emerald-500 text-white px-3 py-1 rounded-full text-sm font-medium">
                  <CheckCircle className="w-4 h-4" /> Face OK
                </div>
              )}
              {lastDetection.multiple_faces && (
                <div className="inline-flex items-center gap-2 bg-rose-500 text-white px-3 py-1 rounded-full text-sm font-medium">
                  <AlertTriangle className="w-4 h-4" /> Multiple Faces
                </div>
              )}
              {!lastDetection.looking_at_screen && lastDetection.face_present && (
                <div className="inline-flex items-center gap-2 bg-amber-500 text-white px-3 py-1 rounded-full text-sm font-medium">
                  <Eye className="w-4 h-4" /> Looking Away
                </div>
              )}
              {lastDetection.gaze_off_screen && (
                <div className="inline-flex items-center gap-2 bg-amber-500 text-white px-3 py-1 rounded-full text-sm font-medium">
                  <Eye className="w-4 h-4" /> Gaze Off Screen
                </div>
              )}
              {lastDetection.mouth_open && (
                <div className="inline-flex items-center gap-2 bg-amber-500 text-white px-3 py-1 rounded-full text-sm font-medium">
                  <Mic className="w-4 h-4" /> Mouth Moving
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
        <AnimatePresence>
          {showPreview && cameraReady && isDetecting && (
            <motion.div
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}
              className="absolute bottom-3 right-3"
            >
              <div className="bg-indigo-500 text-white px-3 py-1 rounded-full text-xs font-medium flex items-center gap-2">
                <div className="w-2 h-2 bg-white rounded-full animate-pulse" /> Analyzing...
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <canvas ref={canvasRef} className="hidden" />
    </div>
  );
};

export default CameraProctoring;

