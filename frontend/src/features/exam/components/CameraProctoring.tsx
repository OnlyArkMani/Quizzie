import React, { useEffect, useRef, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Camera,
  CameraOff,
  AlertTriangle,
  CheckCircle,
  Eye,
  EyeOff,
  Loader
} from 'lucide-react';
import api from '@/lib/api';

interface CameraProctoringProps {
  attemptId: string;
  isActive: boolean;
  settings: {
    camera_enabled: boolean;
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
  flags: Array<{
    type: string;
    severity: string;
    message: string;
  }>;
}

const CameraProctoring: React.FC<CameraProctoringProps> = ({
  attemptId,
  isActive,
  settings,
  onViolation
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const detectionIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [isDetecting, setIsDetecting] = useState(false);
  const [lastDetection, setLastDetection] = useState<DetectionResult | null>(null);
  const [frameCount, setFrameCount] = useState(0);
  const [showPreview, setShowPreview] = useState(false);

  // Tab visibility detection
  useEffect(() => {
    if (!isActive || !settings.camera_enabled) return;

    const handleVisibilityChange = () => {
      if (document.hidden) {
        reportViolation({
          type: 'tab_switch',
          severity: 'high',
          message: 'Student switched to another tab or window',
          metadata: {
            timestamp: new Date().toISOString(),
            hidden_duration: 0
          }
        });
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [isActive, settings.camera_enabled]);

  // Initialize camera
  useEffect(() => {
    if (!isActive || !settings.camera_enabled) {
      stopCamera();
      return;
    }

    startCamera();

    return () => {
      stopCamera();
    };
  }, [isActive, settings.camera_enabled]);

  // Start detection loop
  useEffect(() => {
    if (!cameraReady || !isActive || !settings.face_detection_enabled) {
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current);
        detectionIntervalRef.current = null;
      }
      return;
    }

    // Start periodic detection
    const interval = settings.detection_interval * 1000; // Convert to ms
    detectionIntervalRef.current = setInterval(() => {
      captureAndAnalyzeFrame();
    }, interval);

    // Also run initial detection
    captureAndAnalyzeFrame();

    return () => {
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current);
        detectionIntervalRef.current = null;
      }
    };
  }, [cameraReady, isActive, settings.face_detection_enabled, settings.detection_interval]);

  const startCamera = async () => {
    try {
      setCameraError(null);
      
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user'
        },
        audio: false
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        
        videoRef.current.onloadedmetadata = () => {
          videoRef.current?.play();
          setCameraReady(true);
        };
      }
    } catch (error: any) {
      console.error('Camera access error:', error);
      setCameraError(error.message || 'Failed to access camera');
      setCameraReady(false);
    }
  };

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    
    if (detectionIntervalRef.current) {
      clearInterval(detectionIntervalRef.current);
      detectionIntervalRef.current = null;
    }
    
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

      // Set canvas size to match video
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;

      // Draw current frame to canvas
      context.drawImage(video, 0, 0, canvas.width, canvas.height);

      // Convert to base64
      const frameData = canvas.toDataURL('image/jpeg', 0.8);

      // Send to backend for analysis
      const response = await api.post('/monitor/analyze-frame', {
        attempt_id: attemptId,
        frame_data: frameData,
        timestamp: new Date().toISOString()
      });

      const result: DetectionResult = response.data;
      
      setLastDetection(result);
      setFrameCount(prev => prev + 1);

      // Report violations if any
      if (result.flags && result.flags.length > 0) {
        result.flags.forEach(flag => {
          reportViolation(flag);
        });
      }

    } catch (error) {
      console.error('Frame analysis error:', error);
    } finally {
      setIsDetecting(false);
    }
  }, [attemptId, isDetecting]);

  const reportViolation = async (violation: any) => {
    try {
      await api.post('/monitor/violation', {
        attempt_id: attemptId,
        event_type: 'proctoring_flag',
        flags: [violation],
        timestamp: new Date().toISOString()
      });

      if (onViolation) {
        onViolation(violation);
      }
    } catch (error) {
      console.error('Failed to report violation:', error);
    }
  };

  const getStatusColor = () => {
    if (!lastDetection) return 'text-slate-400';
    
    if (lastDetection.flags.length === 0 && lastDetection.face_present) {
      return 'text-emerald-500';
    }
    
    const hasCritical = lastDetection.flags.some(f => f.severity === 'high');
    if (hasCritical) return 'text-rose-500';
    
    return 'text-amber-500';
  };

  const getStatusMessage = () => {
    if (!cameraReady) return 'Camera initializing...';
    if (!lastDetection) return 'Waiting for first detection...';
    
    if (lastDetection.flags.length === 0 && lastDetection.face_present) {
      return 'All good - Looking at screen';
    }
    
    if (!lastDetection.face_present) {
      return '⚠️ No face detected';
    }
    
    if (lastDetection.multiple_faces) {
      return '⚠️ Multiple faces detected';
    }
    
    if (!lastDetection.looking_at_screen) {
      return '⚠️ Looking away from screen';
    }
    
    return 'Monitoring active';
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
      {/* Status Bar */}
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`relative ${getStatusColor()}`}>
              {cameraReady ? (
                <Camera className="w-6 h-6" />
              ) : (
                <Loader className="w-6 h-6 animate-spin" />
              )}
              
              {cameraReady && (
                <motion.div
                  className="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full"
                  animate={{ scale: [1, 1.2, 1] }}
                  transition={{ repeat: Infinity, duration: 2 }}
                />
              )}
            </div>
            
            <div>
              <p className="font-semibold text-slate-900">Camera Proctoring</p>
              <p className={`text-sm ${getStatusColor()}`}>
                {getStatusMessage()}
              </p>
            </div>
          </div>

          <button
            onClick={() => setShowPreview(!showPreview)}
            className="btn-secondary text-sm flex items-center gap-2"
          >
            {showPreview ? (
              <>
                <EyeOff className="w-4 h-4" />
                Hide Preview
              </>
            ) : (
              <>
                <Eye className="w-4 h-4" />
                Show Preview
              </>
            )}
          </button>
        </div>

        {/* Detection Stats */}
        {lastDetection && (
          <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-4 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {lastDetection.faces_detected}
              </p>
              <p className="text-xs text-slate-600">Faces</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {(lastDetection.face_confidence * 100).toFixed(0)}%
              </p>
              <p className="text-xs text-slate-600">Confidence</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {frameCount}
              </p>
              <p className="text-xs text-slate-600">Frames</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-slate-900">
                {lastDetection.flags.length}
              </p>
              <p className="text-xs text-slate-600">Flags</p>
            </div>
          </div>
        )}
      </div>

      {/* Camera Error */}
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
            <button
              onClick={startCamera}
              className="mt-3 text-sm font-medium text-rose-600 hover:text-rose-700"
            >
              Try Again
            </button>
          </div>
        </motion.div>
      )}

      {/* Video Preview */}
      <AnimatePresence>
        {showPreview && cameraReady && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-white rounded-lg border border-slate-200 overflow-hidden"
          >
            <div className="relative">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-auto max-h-96 object-cover bg-slate-900"
              />
              
              {/* Detection Overlay */}
              {lastDetection && (
                <div className="absolute top-3 left-3 right-3 space-y-2">
                  {lastDetection.face_present && (
                    <div className="inline-flex items-center gap-2 bg-emerald-500 text-white px-3 py-1 rounded-full text-sm font-medium">
                      <CheckCircle className="w-4 h-4" />
                      Face Detected
                    </div>
                  )}
                  
                  {lastDetection.multiple_faces && (
                    <div className="inline-flex items-center gap-2 bg-rose-500 text-white px-3 py-1 rounded-full text-sm font-medium ml-2">
                      <AlertTriangle className="w-4 h-4" />
                      Multiple Faces
                    </div>
                  )}
                  
                  {!lastDetection.looking_at_screen && lastDetection.face_present && (
                    <div className="inline-flex items-center gap-2 bg-amber-500 text-white px-3 py-1 rounded-full text-sm font-medium ml-2">
                      <AlertTriangle className="w-4 h-4" />
                      Looking Away
                    </div>
                  )}
                </div>
              )}

              {/* Processing Indicator */}
              {isDetecting && (
                <div className="absolute bottom-3 right-3">
                  <div className="bg-indigo-500 text-white px-3 py-1 rounded-full text-xs font-medium flex items-center gap-2">
                    <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                    Analyzing...
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Hidden canvas for frame capture */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Hidden video element (always active for detection) */}
      {!showPreview && (
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="hidden"
        />
      )}
    </div>
  );
};

export default CameraProctoring;