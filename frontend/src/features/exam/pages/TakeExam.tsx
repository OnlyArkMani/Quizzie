import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, ChevronLeft, ChevronRight, Send } from 'lucide-react';
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
  const location = useLocation();
  const attemptId = location.state?.attemptId;

  const [showPalette, setShowPalette] = useState(true);
  const [direction, setDirection] = useState<'forward' | 'backward'>('forward');
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [examData, setExamData] = useState<any>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const {
    questions,
    currentQuestionIndex,
    nextQuestion,
    prevQuestion,
    initExam,
    submitExam,
    isSubmitted,
    answers,
  } = useExamStore();

  useEffect(() => {
    fetchExamData();
    setupCamera();

    return () => {
      // Cleanup camera
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach(track => track.stop());
      }
    };
  }, [examId]);

  useEffect(() => {
    if (isSubmitted && attemptId) {
      handleFinalSubmit();
    }
  }, [isSubmitted]);

  const fetchExamData = async () => {
    try {
      const response = await api.get(`/exams/${examId}/questions`);
      const exam = response.data;
      
      setExamData(exam);
      initExam(
        exam.id,
        exam.questions,
        exam.duration_minutes,
        attemptId
      );
    } catch (error) {
      console.error('Failed to fetch exam:', error);
    }
  };

  const setupCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: true,
        audio: true 
      });
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      // Start monitoring
      startMonitoring(stream);
    } catch (error) {
      console.error('Camera setup failed:', error);
    }
  };

  const startMonitoring = (stream: MediaStream) => {
    // Send frames every 5 seconds
    const interval = setInterval(async () => {
      if (videoRef.current) {
        const canvas = document.createElement('canvas');
        canvas.width = videoRef.current.videoWidth;
        canvas.height = videoRef.current.videoHeight;
        const ctx = canvas.getContext('2d');
        ctx?.drawImage(videoRef.current, 0, 0);
        
        canvas.toBlob(async (blob) => {
          if (blob) {
            const formData = new FormData();
            formData.append('file', blob);
            formData.append('attempt_id', attemptId);
            
            try {
              await api.post('/monitor/frame', formData);
            } catch (error) {
              console.error('Monitoring error:', error);
            }
          }
        });
      }
    }, 5000);

    return () => clearInterval(interval);
  };

  const handleFinalSubmit = async () => {
    try {
      // Prepare responses
      const responses = Array.from(answers.entries()).map(([questionId, answer]) => ({
        question_id: questionId,
        selected_option_ids: questions
          .find(q => q.id === questionId)
          ?.options
          .filter((_, idx) => answer.selectedOptions.includes(idx))
          .map(opt => opt.id) || [],
        marked_for_review: answer.markedForReview,
      }));

      await api.post(`/attempts/${attemptId}/submit`, { responses });
      
      navigate(`/student/exam/${examId}/results`, {
        state: { attemptId }
      });
    } catch (error) {
      console.error('Submit failed:', error);
    }
  };

  const handleNext = () => {
    setDirection('forward');
    nextQuestion();
  };

  const handlePrev = () => {
    setDirection('backward');
    prevQuestion();
  };

  if (!examData) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-indigo-400 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Hidden Camera Feed */}
      <video
        ref={videoRef}
        autoPlay
        muted
        className="hidden"
      />

      {/* Sticky Header */}
      <header className="sticky top-0 z-50 backdrop-blur-md bg-slate-900/90 border-b border-slate-700">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold">{examData.title}</h1>
              <p className="text-sm text-slate-400">Question {currentQuestionIndex + 1} of {questions.length}</p>
            </div>

            <div className="flex items-center gap-6">
              <AutoSaveIndicator />
              <ExamTimer />
              
              <button
                onClick={() => setShowPalette(!showPalette)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 transition text-sm"
              >
                {showPalette ? 'Hide' : 'Show'} Palette
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Warning Banner */}
      <div className="bg-amber-900/20 border-b border-amber-700/50">
        <div className="max-w-7xl mx-auto px-6 py-3">
          <div className="flex items-center gap-3 text-amber-200">
            <AlertTriangle className="w-4 h-4" />
            <p className="text-sm">This exam is being proctored. Stay focused and avoid suspicious behavior.</p>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex max-w-7xl mx-auto">
        {/* Question Area */}
        <div className="flex-1 p-6">
          <QuestionCard direction={direction} />

          {/* Navigation */}
          <div className="flex items-center justify-between mt-6">
            <button
              onClick={handlePrev}
              disabled={currentQuestionIndex === 0}
              className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              <ChevronLeft className="w-5 h-5" />
              Previous
            </button>

            {currentQuestionIndex === questions.length - 1 ? (
              <button
                onClick={() => setShowSubmitModal(true)}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 font-medium transition"
              >
                Submit Exam
                <Send className="w-5 h-5" />
              </button>
            ) : (
              <button
                onClick={handleNext}
                className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 transition"
              >
                Next
                <ChevronRight className="w-5 h-5" />
              </button>
            )}
          </div>
        </div>

        {/* Question Palette Sidebar */}
        <AnimatePresence>
          {showPalette && (
            <motion.aside
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 320, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.3 }}
              className="border-l border-slate-700 overflow-hidden"
            >
              <QuestionPalette />
            </motion.aside>
          )}
        </AnimatePresence>
      </div>

      {/* Submit Modal */}
      <SubmitModal
        isOpen={showSubmitModal}
        onClose={() => setShowSubmitModal(false)}
        onConfirm={() => {
          submitExam();
          setShowSubmitModal(false);
        }}
      />
    </div>
  );
};

export default TakeExam;