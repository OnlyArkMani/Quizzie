import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Palette, AlertTriangle, Maximize, ShieldAlert } from 'lucide-react';
import { useToastStore } from '@/shared/components/feedback/Toast';

import { useExamStore } from '../store/examStore';
import QuestionCard from '../components/QuestionCard';
import QuestionPalette from '../components/QuestionPalette';
import ExamTimer from '../components/ExamTimer';
import AutoSaveIndicator from '../components/AutoSaveIndicator';
import SubmitModal from '../components/SubmitModal';
import HealthBar from '../components/HealthBar';
import CameraProctoring from '../components/CameraProctoring';

import api from '@/lib/api';

const TakeExam = () => {
  const { examId } = useParams();
  const navigate = useNavigate();

  const {
    questions,
    currentQuestionIndex,
    isSubmitted,
    attemptId,
    initExam,
    nextQuestion,
    prevQuestion,
    submitExam,
    answers,
  } = useExamStore();

  const { addToast } = useToastStore();

  const [showPalette, setShowPalette]           = useState(false);
  const [showSubmitModal, setShowSubmitModal]   = useState(false);
  const [loading, setLoading]                   = useState(true);
  const [exam, setExam]                         = useState<any>(null);
  const [proctoringSettings, setProctoringSettings] = useState<any>(null);
  const [examError, setExamError]               = useState<string | null>(null);
  const [slideDirection, setSlideDirection]     = useState<'forward' | 'backward'>('forward');
  const [isSubmitting, setIsSubmitting]         = useState(false);
  const [isHealthZero, setIsHealthZero]         = useState(false);
  const [isFullscreenStart, setIsFullscreenStart] = useState(false);

  // Fullscreen countdown modal
  const [fsCountdown, setFsCountdown]           = useState<number | null>(null);
  const fsCountdownRef                          = useRef<ReturnType<typeof setInterval> | null>(null);

  // Exam pause overlay on critical violation
  const [examPaused, setExamPaused]             = useState(false);
  const [pauseReason, setPauseReason]           = useState('');
  const examPausedRef                           = useRef(false);

  const hasSubmittedRef = useRef(false);
  const healthZeroTriggeredRef = useRef(false);
  const answersRef      = useRef(answers);

  useEffect(() => { answersRef.current = answers; }, [answers]);

  const handleNextQuestion = () => { setSlideDirection('forward');  nextQuestion(); };
  const handlePrevQuestion = () => { setSlideDirection('backward'); prevQuestion(); };

  /* ----------------------------------------------------------------
     Multi-monitor detection (runs once on exam start)
  ---------------------------------------------------------------- */
  useEffect(() => {
    if (!isFullscreenStart || !attemptId) return;
    const sw = window.screen.width;
    const sh = window.screen.height;
    const aspectRatio = sw / sh;
    if (aspectRatio > 2.5 || sw > 3000) {
      api.post('/monitor/enhanced/violation', {
        attempt_id: attemptId,
        event_type: 'proctoring_flag',
        flags: [{
          type: 'multi_monitor_detected',
          severity: 'medium',
          message: `Unusually wide screen detected (${sw}x${sh}) - possible second monitor`,
          metadata: { screen_width: sw, screen_height: sh }
        }],
        timestamp: new Date().toISOString()
      }).catch(() => {});
      addToast(`Warning: Wide screen detected (${sw}px). Second monitors are not allowed.`, 'warning');
    }
  }, [isFullscreenStart, attemptId]);

  /* ----------------------------------------------------------------
     Fullscreen exit -> 5s countdown modal, then penalty
  ---------------------------------------------------------------- */
  useEffect(() => {
    const handleFullscreenChange = () => {
      if (!document.fullscreenElement && isFullscreenStart && !hasSubmittedRef.current) {
        setFsCountdown(5);
        let remaining = 5;
        fsCountdownRef.current = setInterval(() => {
          remaining -= 1;
          setFsCountdown(remaining);
          if (remaining <= 0) {
            clearInterval(fsCountdownRef.current!);
            fsCountdownRef.current = null;
            setFsCountdown(null);
            if (!document.fullscreenElement) {
              api.post('/monitor/enhanced/violation', {
                attempt_id: attemptId,
                event_type: 'proctoring_flag',
                flags: [{
                  type: 'fullscreen_exit',
                  severity: 'high',
                  message: 'Student exited full-screen and did not return within 5 seconds',
                  metadata: { timestamp: new Date().toISOString() }
                }]
              }).catch(() => {});
              addToast('VIOLATION: Fullscreen exit recorded and reported.', 'error');
            }
          }
        }, 1000);
      } else if (document.fullscreenElement && fsCountdownRef.current) {
        clearInterval(fsCountdownRef.current);
        fsCountdownRef.current = null;
        setFsCountdown(null);
        addToast('Good - you returned to fullscreen. No penalty applied.', 'success');
      }
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, [isFullscreenStart, attemptId]);

  /* ----------------------------------------------------------------
     Copy-paste: block + log as violation
  ---------------------------------------------------------------- */
  useEffect(() => {
    if (!isFullscreenStart || !attemptId) return;

    const handleCopyPaste = (e: ClipboardEvent) => {
      e.preventDefault();
      const action = e.type === 'copy' ? 'copy' : 'paste';
      addToast(`${action === 'copy' ? 'Copying' : 'Pasting'} is strictly prohibited during the exam.`, 'warning');
      api.post('/monitor/enhanced/violation', {
        attempt_id: attemptId,
        event_type: 'proctoring_flag',
        flags: [{
          type: 'copy_paste_attempt',
          severity: 'medium',
          message: `Student attempted to ${action} text during exam`,
          metadata: { action, timestamp: new Date().toISOString() }
        }]
      }).catch(() => {});
    };

    const preventContextMenu = (e: MouseEvent) => e.preventDefault();

    document.addEventListener('copy',  handleCopyPaste as EventListener);
    document.addEventListener('paste', handleCopyPaste as EventListener);
    document.addEventListener('contextmenu', preventContextMenu);

    return () => {
      document.removeEventListener('copy',  handleCopyPaste as EventListener);
      document.removeEventListener('paste', handleCopyPaste as EventListener);
      document.removeEventListener('contextmenu', preventContextMenu);
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    };
  }, [isFullscreenStart, attemptId]);

  /* ----------------------------------------------------------------
     Before-unload beacon
  ---------------------------------------------------------------- */
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (!hasSubmittedRef.current && attemptId && exam) {
        const responses = Array.from(answersRef.current.values()).map((a: any) => ({
          question_id: a.questionId,
          selected_option_ids: [],
          answer_text: a.textAnswer || null,
          marked_for_review: a.markedForReview,
        }));
        navigator.sendBeacon(
          `http://localhost:8000/api/v1/attempts/${attemptId}/submit`,
          new Blob([JSON.stringify({ responses })], { type: 'application/json' })
        );
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [attemptId, exam]);

  /* ----------------------------------------------------------------
     Exam pause on critical violation
  ---------------------------------------------------------------- */
  const handleCriticalViolation = useCallback((violation: any) => {
    if (examPausedRef.current) return;
    if (violation?.severity === 'high') {
      examPausedRef.current = true;
      setExamPaused(true);
      setPauseReason(violation.message || 'A critical violation was detected.');
    }
  }, []);

  const dismissPause = () => {
    examPausedRef.current = false;
    setExamPaused(false);
    setPauseReason('');
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    }
  };

  /* ----------------------------------------------------------------
     Fetch exam + questions
  ---------------------------------------------------------------- */
  useEffect(() => { fetchExamAndQuestions(); }, [examId]);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await api.get(`/monitor/enhanced/exam/${examId}/proctoring-settings`);
        setProctoringSettings(res.data);
      } catch {
        setProctoringSettings({
          camera_enabled: true, microphone_enabled: false, face_detection_enabled: true,
          multiple_face_detection: true, head_pose_detection: true, tab_switch_detection: true,
          min_face_confidence: 0.6, max_head_rotation: 30.0, detection_interval: 2,
          initial_health: 100, health_warning_threshold: 40, auto_submit_on_zero_health: true
        });
      }
    };
    if (examId) fetchSettings();
  }, [examId]);

  const fetchExamAndQuestions = async () => {
    try {
      const examRes      = await api.get(`/exams/${examId}`);
      const questionsRes = await api.get(`/exams/${examId}/questions`);
      setExam(examRes.data);

      if (!questionsRes.data?.length) {
        setExamError('No questions available in this exam.');
        setLoading(false);
        return;
      }

      const attemptIdFromState = window.history.state?.usr?.attemptId;
      if (!attemptIdFromState) {
        alert('No attempt found. Please restart the exam.');
        navigate('/student');
        return;
      }

      initExam(examId!, questionsRes.data, examRes.data.duration_minutes * 60, attemptIdFromState);
      setLoading(false);
    } catch {
      alert('Failed to load exam.');
      navigate('/student');
    }
  };

  /* ----------------------------------------------------------------
     Submission
  ---------------------------------------------------------------- */
  const handleSubmit = () => setShowSubmitModal(true);

  const confirmSubmit = async () => {
    if (hasSubmittedRef.current) return;
    hasSubmittedRef.current = true;
    setIsSubmitting(true);
    setShowSubmitModal(false);
    try {
      const responses = Array.from(useExamStore.getState().answers.values()).map(a => {
        const question = questions.find(q => q.id === a.questionId);
        const mappedOptionIds = a.selectedOptions.map(idx => question?.options[idx]?.id).filter(Boolean);
        return {
          question_id: a.questionId,
          selected_option_ids: mappedOptionIds as string[],
          answer_text: a.textAnswer || null,
          marked_for_review: a.markedForReview,
        };
      });
      await api.post(`/attempts/${attemptId}/submit`, { responses });
      submitExam();
      navigate(`/student/exam/${examId}/results`, { state: { attemptId } });
    } catch (error: any) {
      if (error?.response?.status === 400 && error.response.data?.detail === "Attempt already submitted") {
        submitExam();
        navigate(`/student/exam/${examId}/results`, { state: { attemptId } });
        return;
      }
      addToast(error?.response?.data?.detail || 'Failed to submit exam.', 'error');
      hasSubmittedRef.current = false;
      setIsSubmitting(false);
      // We don't reset health zero, to prevent infinite loops from the websocket
    }
  };

  const handleHealthZero = () => {
    if (healthZeroTriggeredRef.current) return;
    healthZeroTriggeredRef.current = true;
    setIsHealthZero(true);
    addToast('Your exam health reached zero. Auto-submitting.', 'error');
    confirmSubmit();
  };

  const handleViolation = (violation: any) => handleCriticalViolation(violation);

  /* ----------------------------------------------------------------
     Render guards
  ---------------------------------------------------------------- */
  if (examError) return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center text-white p-6 text-center">
      <AlertTriangle className="w-16 h-16 text-amber-500 mb-4" />
      <h2 className="text-2xl font-bold mb-2">Exam Error</h2>
      <p className="text-slate-400 mb-8">{examError}</p>
      <button onClick={() => navigate('/student')} className="px-6 py-3 bg-indigo-600 rounded-lg font-semibold hover:bg-indigo-700 transition">
        Return to Dashboard
      </button>
    </div>
  );

  if (loading) return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center">
      <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (isHealthZero || isSubmitting) return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center text-white p-6 text-center fixed inset-0 z-[9999]">
      <AlertTriangle className="w-16 h-16 text-rose-500 mb-4 animate-pulse" />
      <h2 className="text-3xl font-bold mb-4">{isHealthZero ? 'Exam Terminated' : 'Submitting Exam...'}</h2>
      <p className="text-slate-300 mb-8 max-w-lg">
        {isHealthZero
          ? 'Your exam health has depleted entirely due to repeated violations.'
          : 'Please wait while your responses are securely saved.'}
      </p>
      <div className="w-12 h-12 border-4 border-rose-500 border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!isFullscreenStart) return (
    <div className="min-h-screen bg-slate-900 flex flex-col items-center justify-center text-white p-6 text-center">
      <AlertTriangle className="w-16 h-16 text-indigo-500 mb-4" />
      <h2 className="text-3xl font-bold mb-4">Exam Mode Strict Enforcement</h2>
      <p className="text-slate-300 mb-8 max-w-lg">
        This assessment requires a full-screen environment. Leaving full-screen, switching tabs,
        or opening other applications will result in penalties.
      </p>
      <button
        onClick={async () => {
          try {
            await document.documentElement.requestFullscreen();
            setIsFullscreenStart(true);
          } catch {
            addToast('Could not enter fullscreen. Please allow it in your browser.', 'error');
          }
        }}
        className="px-8 py-4 bg-indigo-600 rounded-lg font-bold text-lg hover:bg-indigo-700 transition shadow-lg shadow-indigo-600/20"
      >
        Enter Fullscreen & Begin Exam
      </button>
    </div>
  );

  if (!exam || questions.length === 0) return null;

  return (
    <div className="min-h-screen bg-slate-900 text-white">

      {/* Fullscreen countdown modal */}
      <AnimatePresence>
        {fsCountdown !== null && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[9998] bg-black/80 flex items-center justify-center"
          >
            <motion.div
              initial={{ scale: 0.9 }} animate={{ scale: 1 }} exit={{ scale: 0.9 }}
              className="bg-slate-800 border border-rose-500 rounded-2xl p-10 text-center max-w-md w-full mx-4"
            >
              <Maximize className="w-12 h-12 text-rose-400 mx-auto mb-4" />
              <h2 className="text-2xl font-bold text-white mb-2">Fullscreen Exited!</h2>
              <p className="text-slate-300 mb-6 text-sm">
                Return to fullscreen within{' '}
                <span className="text-rose-400 font-bold text-lg">{fsCountdown}s</span>
                {' '}or this will be recorded as a violation.
              </p>
              <div className="w-full bg-slate-700 rounded-full h-2 mb-6">
                <motion.div
                  className="bg-rose-500 h-2 rounded-full"
                  animate={{ width: `${(fsCountdown / 5) * 100}%` }}
                  transition={{ duration: 0.9, ease: 'linear' }}
                />
              </div>
              <button
                onClick={() => document.documentElement.requestFullscreen().catch(() => {})}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 rounded-lg font-semibold transition"
              >
                Return to Fullscreen
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Critical violation pause overlay */}
      <AnimatePresence>
        {examPaused && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-[9997] bg-black/85 flex items-center justify-center"
          >
            <motion.div
              initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9 }}
              className="bg-slate-800 border-2 border-rose-500 rounded-2xl p-10 text-center max-w-lg w-full mx-4"
            >
              <ShieldAlert className="w-16 h-16 text-rose-400 mx-auto mb-4 animate-pulse" />
              <h2 className="text-2xl font-bold text-white mb-2">Exam Paused</h2>
              <p className="text-slate-300 mb-2 text-sm">A critical violation was detected. Your exam timer has been paused.</p>
              <p className="text-rose-300 text-sm mb-8 bg-rose-900/30 rounded-lg px-4 py-2">{pauseReason}</p>
              <p className="text-slate-400 text-xs mb-6">
                Please face the camera directly and click the button below to resume.
                This incident has been reported to the examiner.
              </p>
              <button
                onClick={dismissPause}
                className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 rounded-lg font-semibold transition"
              >
                I understand - Resume Exam
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Health Bar */}
      {attemptId && (
        <HealthBar attemptId={attemptId} onHealthZero={handleHealthZero} showViolations />
      )}

      {/* Header */}
      <header className="sticky top-0 z-50 bg-slate-800/80 backdrop-blur-md border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between">
          <h1 className="text-xl font-bold">{exam?.title}</h1>
          <div className="flex items-center gap-4">
            <span className="text-sm text-slate-400">
              Question {currentQuestionIndex + 1} of {questions.length}
            </span>
            <AutoSaveIndicator />
            <ExamTimer paused={examPaused} />
            <button onClick={() => setShowPalette(!showPalette)} className="p-2 hover:bg-slate-700 rounded-lg">
              <Palette className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Warning banner */}
      <div className="bg-amber-900/20 border-b border-amber-900/50 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center gap-2 text-amber-400 text-sm">
          <AlertTriangle className="w-4 h-4" />
          This exam is being proctored - camera, audio, and browser activity are monitored
        </div>
      </div>

      {/* Camera Proctoring */}
      {proctoringSettings && attemptId && (
        <div className="max-w-7xl mx-auto px-6 py-4">
          <CameraProctoring
            attemptId={attemptId}
            isActive
            settings={proctoringSettings}
            onViolation={handleViolation}
          />
        </div>
      )}

      {/* Content */}
      <div className="max-w-7xl mx-auto px-6 py-8 flex gap-8">
        <div className="flex-1 max-w-4xl max-h-full overflow-y-auto px-8 py-6 custom-scrollbar relative">
          <QuestionCard direction={slideDirection} />
          <div className="mt-6 flex items-center justify-between">
            <button
              onClick={handlePrevQuestion}
              disabled={currentQuestionIndex === 0}
              className="px-6 py-2 bg-slate-700 rounded-lg disabled:opacity-50"
            >
              Previous
            </button>
            {currentQuestionIndex === questions.length - 1 ? (
              <button onClick={handleSubmit} className="px-6 py-2 bg-emerald-600 rounded-lg">
                Submit Exam
              </button>
            ) : (
              <button onClick={handleNextQuestion} className="px-6 py-2 bg-indigo-600 rounded-lg">
                Next
              </button>
            )}
          </div>
        </div>

        <AnimatePresence>
          {showPalette && (
            <motion.div
              initial={{ x: 300, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: 300, opacity: 0 }}
              className="w-80"
            >
              <QuestionPalette />
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {showSubmitModal && (
        <SubmitModal
          isOpen
          onClose={() => setShowSubmitModal(false)}
          onConfirm={confirmSubmit}
        />
      )}
    </div>
  );
};

export default TakeExam;
