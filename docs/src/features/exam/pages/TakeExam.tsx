import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Palette, AlertTriangle } from 'lucide-react';
import { useExamStore } from '../store/examStore';
import QuestionCard from '../components/QuestionCard';
import QuestionPalette from '../components/QuestionPalette';
import ExamTimer from '../components/ExamTimer';
import AutoSaveIndicator from '../components/AutoSaveIndicator';
import SubmitModal from '../components/SubmitModal';
import api from '@/lib/api';

const TakeExam = () => {
  const { examId } = useParams();
  const navigate = useNavigate();
  const videoRef = useRef<HTMLVideoElement>(null);
  
  const {
    questions,
    currentQuestionIndex,
    timeRemaining,
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

  useEffect(() => {
    fetchExamAndQuestions();
    setupCamera();
    
    return () => {
      // Cleanup camera
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach(track => track.stop());
      }
    };
  }, [examId]);

  const fetchExamAndQuestions = async () => {
    try {
      // Fetch exam details
      const examRes = await api.get(`/exams/${examId}`);
      setExam(examRes.data);

      // Fetch questions
      const questionsRes = await api.get(`/exams/${examId}/questions`);
      
      if (!questionsRes.data || questionsRes.data.length === 0) {
        alert('No questions available for this exam');
        navigate('/student');
        return;
      }

      // Get attempt ID from state (passed from ExamLobby)
      const state = window.history.state?.usr;
      const attemptIdFromState = state?.attemptId;

      if (!attemptIdFromState) {
        alert('No attempt found. Please start the exam again.');
        navigate('/student');
        return;
      }

      // Initialize exam in store
      initExam(
        examId!,
        questionsRes.data,
        examRes.data.duration_minutes * 60,
        attemptIdFromState
      );

      setLoading(false);
    } catch (error) {
      console.error('Failed to fetch exam:', error);
      alert('Failed to load exam. Please try again.');
      navigate('/student');
    }
  };

  const setupCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      // Start monitoring (send frames every 5 seconds)
      setInterval(() => {
        captureAndSendFrame();
      }, 5000);
    } catch (error) {
      console.error('Camera setup failed:', error);
    }
  };

  const captureAndSendFrame = async () => {
    if (!videoRef.current || !attemptId) return;

    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const ctx = canvas.getContext('2d');

    if (ctx) {
      ctx.drawImage(videoRef.current, 0, 0);
      canvas.toBlob(async (blob) => {
        if (blob) {
          const formData = new FormData();
          formData.append('file', blob, 'frame.jpg');
          formData.append('attempt_id', attemptId);

          try {
            await api.post('/monitor/frame', formData, {
              headers: { 'Content-Type': 'multipart/form-data' },
            });
          } catch (error) {
            console.error('Failed to send frame:', error);
          }
        }
      }, 'image/jpeg');
    }
  };

  const handleSubmit = () => {
    setShowSubmitModal(true);
  };

  const confirmSubmit = async () => {
    try {
      // Get all responses
      const responses = Array.from(useExamStore.getState().answers.values()).map(answer => ({
        question_id: answer.questionId,
        selected_option_ids: answer.selectedOptions,
        marked_for_review: answer.markedForReview,
      }));

      // Submit to backend
      await api.post(`/attempts/${attemptId}/submit`, { responses });

      submitExam();
      navigate(`/student/exam/${examId}/results`, {
        state: { attemptId },
      });
    } catch (error) {
      console.error('Failed to submit exam:', error);
      alert('Failed to submit exam. Please try again.');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!questions || questions.length === 0) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-center text-white">
          <p>No questions available</p>
          <button
            onClick={() => navigate('/student')}
            className="mt-4 px-6 py-2 bg-indigo-600 rounded-lg"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const currentQuestion = questions[currentQuestionIndex];

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Hidden video for camera */}
      <video ref={videoRef} autoPlay muted className="hidden" />

      {/* Header */}
      <header className="sticky top-0 z-50 bg-slate-800/80 backdrop-blur-md border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-bold">{exam?.title}</h1>
            <div className="flex items-center gap-4">
              <span className="text-sm text-slate-400">
                Question {currentQuestionIndex + 1} of {questions.length}
              </span>
              <AutoSaveIndicator />
              <ExamTimer />
              <button
                onClick={() => setShowPalette(!showPalette)}
                className="p-2 hover:bg-slate-700 rounded-lg transition"
              >
                <Palette className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Warning Banner */}
      <div className="bg-amber-900/20 border-b border-amber-900/50 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center gap-2 text-amber-400 text-sm">
          <AlertTriangle className="w-4 h-4" />
          <span>This exam is being proctored. Your camera feed is being monitored.</span>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-8 flex gap-8">
        {/* Question Area */}
        <div className="flex-1">
          <QuestionCard question={currentQuestion} />

          {/* Navigation */}
          <div className="flex justify-between mt-8">
            <button
              onClick={prevQuestion}
              disabled={currentQuestionIndex === 0}
              className="px-6 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition"
            >
              Previous
            </button>

            {currentQuestionIndex === questions.length - 1 ? (
              <button
                onClick={handleSubmit}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 rounded-lg transition"
              >
                Submit Exam
              </button>
            ) : (
              <button
                onClick={nextQuestion}
                className="px-6 py-2 bg-indigo-600 hover:bg-indigo-700 rounded-lg transition"
              >
                Next
              </button>
            )}
          </div>
        </div>

        {/* Question Palette Sidebar */}
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

      {/* Submit Modal */}
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