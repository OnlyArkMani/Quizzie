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

  useEffect(() => {
    if (!examId) return;
    fetchExamDetails();
    checkPermissions();
  }, [examId]);

  // ✅ Fetch exam safely
  const fetchExamDetails = async () => {
    try {
      const response = await api.get(`/exams/${examId}`);
      setExam(response.data ?? null);
    } catch (error: any) {
      console.error(
        'Failed to fetch exam:',
        error?.response?.data || error.message
      );
    } finally {
      setLoading(false);
    }
  };

  // ✅ Camera & mic permission check
  const checkPermissions = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      });

      setCameraAccessGranted(true);
      setMicAccessGranted(true);

      // stop camera after check
      stream.getTracks().forEach((track) => track.stop());
    } catch (error) {
      console.error('Permission denied:', error);
      setCameraAccessGranted(false);
      setMicAccessGranted(false);
    }
  };

  // ✅ Start exam + guaranteed attemptId passing
  const handleStartExam = async () => {
    if (!cameraAccessGranted || !agreedToTerms || !examId) return;

    setStarting(true);

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
      alert('Failed to start exam. Please try again.');
    } finally {
      setStarting(false);
    }
  };

  // ✅ Loading UI
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  // ✅ Exam not found
  if (!exam) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-600">Exam not found</p>
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
            {/* Camera */}
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

            {/* Mic */}
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
