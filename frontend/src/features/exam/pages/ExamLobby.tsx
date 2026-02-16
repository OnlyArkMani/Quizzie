import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Clock,
  FileText,
  AlertTriangle,
  Check,
  Camera,
  Mic,
  ArrowRight,
} from 'lucide-react';
import api from '@/lib/api';
import { Exam } from '@/types';

const ExamLobby = () => {
  const { examId } = useParams();
  const navigate = useNavigate();

  const [exam, setExam] = useState<Exam | null>(null);
  const [loading, setLoading] = useState(true);

  const [agreedToTerms, setAgreedToTerms] = useState(false);
  const [cameraAccessGranted, setCameraAccessGranted] = useState(false);
  const [micAccessGranted, setMicAccessGranted] = useState(false);

  const [starting, setStarting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!examId) return;
    fetchExamDetails();
    checkPermissions();
  }, [examId]);

  const fetchExamDetails = async () => {
    try {
      const response = await api.get(`/exams/${examId}`);
      setExam(response.data ?? null);
    } catch (error: any) {
      console.error(
        'Failed to fetch exam:',
        error?.response?.data || error.message
      );
      setErrorMessage('Failed to load exam details');
    } finally {
      setLoading(false);
    }
  };

  const checkPermissions = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      });

      setCameraAccessGranted(true);
      setMicAccessGranted(true);

      stream.getTracks().forEach((track) => track.stop());
    } catch (error) {
      console.error('Permission denied:', error);
      setCameraAccessGranted(false);
      setMicAccessGranted(false);
    }
  };

  const handleStartExam = async () => {
    if (!cameraAccessGranted || !agreedToTerms || !examId) return;

    setStarting(true);
    setErrorMessage(null);

    try {
      const response = await api.post('/attempts/start', {
        exam_id: examId,
      });

      const attemptId = response?.data?.id;

      if (!attemptId) throw new Error('Attempt ID missing from response');

      navigate(`/student/exam/${examId}/take`, {
        state: { attemptId },
      });
    } catch (error: any) {
      console.error(
        'Failed to start exam:',
        error?.response?.data || error.message
      );
      
      const errorDetail = error?.response?.data?.detail;
      
      // ✅ Handle "already attempted" error
      if (errorDetail === 'You have already attempted this exam') {
        setErrorMessage('You have already taken this exam. Please check your results in the dashboard.');
      } else {
        setErrorMessage(errorDetail || 'Failed to start exam. Please try again.');
      }
    } finally {
      setStarting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!exam) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-slate-600 mb-4">Exam not found</p>
          <button
            onClick={() => navigate('/student')}
            className="px-6 py-2 bg-indigo-600 text-white rounded-lg"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const canStart = agreedToTerms && cameraAccessGranted && !starting;

  return (
    <div className="min-h-screen bg-slate-50 py-12 px-4">
      <div className="max-w-3xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="card p-8">

          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-slate-900 mb-2">
              {exam.title}
            </h1>
            <p className="text-slate-600">{exam.description}</p>
          </div>

          {/* Error Message */}
          {errorMessage && (
            <div className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-lg">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="font-semibold text-rose-900">Error</p>
                  <p className="text-sm text-rose-700 mt-1">{errorMessage}</p>
                  {errorMessage.includes('already taken') && (
                    <button
                      onClick={() => navigate('/student')}
                      className="mt-3 text-sm text-rose-600 hover:text-rose-700 underline"
                    >
                      Go to Dashboard
                    </button>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Exam Details */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="card p-4 bg-slate-50 flex items-center gap-3">
              <Clock className="w-5 h-5 text-indigo-600" />
              <div>
                <p className="text-xs text-slate-600">Duration</p>
                <p className="font-semibold text-slate-900">
                  {exam.duration_minutes} minutes
                </p>
              </div>
            </div>

            <div className="card p-4 bg-slate-50 flex items-center gap-3">
              <FileText className="w-5 h-5 text-indigo-600" />
              <div>
                <p className="text-xs text-slate-600">Total Marks</p>
                <p className="font-semibold text-slate-900">
                  {exam.total_marks}
                </p>
              </div>
            </div>
          </div>

          {/* Permissions */}
          <div className="mb-8 space-y-3">
            <div className={`flex items-center gap-3 p-4 rounded-lg border ${
              cameraAccessGranted
                ? 'bg-emerald-50 border-emerald-200'
                : 'bg-rose-50 border-rose-200'
            }`}>
              <Camera className={`w-5 h-5 ${
                cameraAccessGranted ? 'text-emerald-600' : 'text-rose-600'
              }`} />
              <span className="flex-1 font-medium">
                Camera Access {cameraAccessGranted ? 'Granted' : 'Required'}
              </span>
              {cameraAccessGranted && <Check className="w-5 h-5 text-emerald-600" />}
            </div>

            <div className={`flex items-center gap-3 p-4 rounded-lg border ${
              micAccessGranted
                ? 'bg-emerald-50 border-emerald-200'
                : 'bg-amber-50 border-amber-200'
            }`}>
              <Mic className={`w-5 h-5 ${
                micAccessGranted ? 'text-emerald-600' : 'text-amber-600'
              }`} />
              <span className="flex-1 font-medium">
                Microphone {micAccessGranted ? 'Granted' : 'Recommended'}
              </span>
              {micAccessGranted && <Check className="w-5 h-5 text-emerald-600" />}
            </div>
          </div>

          {/* Agreement */}
          <label className="flex gap-3 p-4 card bg-slate-50 cursor-pointer mb-8">
            <input
              type="checkbox"
              checked={agreedToTerms}
              onChange={(e) => setAgreedToTerms(e.target.checked)}
              className="mt-1"
            />
            <p className="text-sm text-slate-700">
              I agree to the exam rules and understand this exam is proctored.
            </p>
          </label>

          {/* Start Button */}
          <motion.button
            whileHover={canStart ? { scale: 1.02 } : {}}
            whileTap={canStart ? { scale: 0.98 } : {}}
            onClick={handleStartExam}
            disabled={!canStart}
            className={`w-full py-4 rounded-lg font-semibold text-lg flex items-center justify-center gap-2 transition ${
              canStart
                ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            {starting ? (
              <>
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Starting Exam...
              </>
            ) : (
              <>
                Start Exam <ArrowRight className="w-5 h-5" />
              </>
            )}
          </motion.button>

        </motion.div>
      </div>
    </div>
  );
};

export default ExamLobby;