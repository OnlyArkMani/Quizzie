import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Palette, AlertTriangle } from 'lucide-react';

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
  } = useExamStore();

  const [showPalette, setShowPalette] = useState(false);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [loading, setLoading] = useState(true);
  const [exam, setExam] = useState<any>(null);
  const [proctoringSettings, setProctoringSettings] = useState<any>(null);

  /* --------------------------------
     Fetch Exam + Questions
  -------------------------------- */
  useEffect(() => {
    fetchExamAndQuestions();
  }, [examId]);

  /* --------------------------------
     Fetch Proctoring Settings
  -------------------------------- */
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        // ✅ FIXED: Added /enhanced to the path
        const res = await api.get(
          `/monitor/enhanced/exam/${examId}/proctoring-settings`
        );
        setProctoringSettings(res.data);
      } catch (err) {
        console.error('Failed to fetch proctoring settings:', err);
        // Set default settings if fetch fails
        setProctoringSettings({
          camera_enabled: true,
          microphone_enabled: false,
          face_detection_enabled: true,
          multiple_face_detection: true,
          head_pose_detection: true,
          tab_switch_detection: true,
          min_face_confidence: 0.6,
          max_head_rotation: 30.0,
          detection_interval: 2,
          initial_health: 100,
          health_warning_threshold: 40,
          auto_submit_on_zero_health: true
        });
      }
    };

    if (examId) {
      fetchSettings();
    }
  }, [examId]);

  const fetchExamAndQuestions = async () => {
    try {
      const examRes = await api.get(`/exams/${examId}`);
      setExam(examRes.data);

      const questionsRes = await api.get(`/exams/${examId}/questions`);

      if (!questionsRes.data?.length) {
        alert('No questions available');
        navigate('/student');
        return;
      }

      const state = window.history.state?.usr;
      const attemptIdFromState = state?.attemptId;

      if (!attemptIdFromState) {
        alert('No attempt found. Please restart the exam.');
        navigate('/student');
        return;
      }

      initExam(
        examId!,
        questionsRes.data,
        examRes.data.duration_minutes * 60,
        attemptIdFromState
      );

      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch exam:', error);
      alert('Failed to load exam.');
      navigate('/student');
    }
  };

  /* --------------------------------
     Submission
  -------------------------------- */
  const handleSubmit = () => {
    setShowSubmitModal(true);
  };

  const confirmSubmit = async () => {
    try {
      const responses = Array.from(
        useExamStore.getState().answers.values()
      ).map(a => ({
        question_id: a.questionId,
        selected_option_ids: a.selectedOptions,
        marked_for_review: a.markedForReview,
      }));

      await api.post(`/attempts/${attemptId}/submit`, { responses });

      submitExam();
      navigate(`/student/exam/${examId}/results`, {
        state: { attemptId },
      });
    } catch (error) {
      console.error('Submit failed:', error);
      alert('Failed to submit exam.');
    }
  };

  /* --------------------------------
     Proctoring Handlers
  -------------------------------- */
  const handleHealthZero = () => {
    alert('Your exam health reached zero. Auto-submitting.');
    confirmSubmit();
  };

  const handleViolation = (violation: any) => {
    console.log('Violation detected:', violation);
    // Optional: toast / modal
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  const currentQuestion = questions[currentQuestionIndex];

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Health Bar */}
      {attemptId && (
        <HealthBar
          attemptId={attemptId}
          onHealthZero={handleHealthZero}
          showViolations
        />
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
            <ExamTimer />
            <button
              onClick={() => setShowPalette(!showPalette)}
              className="p-2 hover:bg-slate-700 rounded-lg"
            >
              <Palette className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Warning */}
      <div className="bg-amber-900/20 border-b border-amber-900/50 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center gap-2 text-amber-400 text-sm">
          <AlertTriangle className="w-4 h-4" />
          This exam is being proctored
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
        <div className="flex-1">
          <QuestionCard question={currentQuestion} />

          <div className="flex justify-between mt-8">
            <button
              onClick={prevQuestion}
              disabled={currentQuestionIndex === 0}
              className="px-6 py-2 bg-slate-700 rounded-lg disabled:opacity-50"
            >
              Previous
            </button>

            {currentQuestionIndex === questions.length - 1 ? (
              <button
                onClick={handleSubmit}
                className="px-6 py-2 bg-emerald-600 rounded-lg"
              >
                Submit Exam
              </button>
            ) : (
              <button
                onClick={nextQuestion}
                className="px-6 py-2 bg-indigo-600 rounded-lg"
              >
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
          onClose={() => setShowSubmitModal(false)}
          onConfirm={confirmSubmit}
        />
      )}
    </div>
  );
};

export default TakeExam;