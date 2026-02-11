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
  ArrowRight
} from 'lucide-react';
import api from '@/lib/api';
import { Exam } from '@/types';

const ExamLobby = () => {
  const { examId } = useParams();
  const navigate = useNavigate();
  const [exam, setExam] = useState<Exam | null>(null);
  const [loading, setLoading] = useState(true);
  const [agreed, setAgreed] = useState(false);
  const [cameraAllowed, setCameraAllowed] = useState(false);
  const [micAllowed, setMicAllowed] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    fetchExamDetails();
    checkPermissions();
  }, [examId]);

  const fetchExamDetails = async () => {
    try {
      const response = await api.get(`/exams/${examId}`);
      setExam(response.data);
    } catch (error) {
      console.error('Failed to fetch exam:', error);
    } finally {
      setLoading(false);
    }
  };

  const checkPermissions = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: true, 
        audio: true 
      });
      setCameraAllowed(true);
      setMicAllowed(true);
      stream.getTracks().forEach(track => track.stop());
    } catch (error) {
      console.error('Permission denied:', error);
    }
  };

  const handleStartExam = async () => {
    if (!agreed || !cameraAllowed) return;

    setStarting(true);
    try {
      // Create exam attempt
      const response = await api.post('/attempts/start', {
        exam_id: examId,
      });

      navigate(`/student/exam/${examId}/take`, {
        state: { attemptId: response.data.id }
      });
    } catch (error) {
      console.error('Failed to start exam:', error);
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
          <p className="text-slate-600">Exam not found</p>
        </div>
      </div>
    );
  }

  const canStart = agreed && cameraAllowed;

  return (
    <div className="min-h-screen bg-slate-50 py-12 px-4">
      <div className="max-w-3xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="card p-8"
        >
          {/* Header */}
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-slate-900 mb-2">
              {exam.title}
            </h1>
            <p className="text-slate-600">{exam.description}</p>
          </div>

          {/* Exam Details */}
          <div className="grid grid-cols-2 gap-4 mb-8">
            <div className="card p-4 bg-slate-50">
              <div className="flex items-center gap-3">
                <Clock className="w-5 h-5 text-indigo-600" />
                <div>
                  <p className="text-xs text-slate-600">Duration</p>
                  <p className="font-semibold text-slate-900">{exam.duration_minutes} minutes</p>
                </div>
              </div>
            </div>

            <div className="card p-4 bg-slate-50">
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-indigo-600" />
                <div>
                  <p className="text-xs text-slate-600">Total Marks</p>
                  <p className="font-semibold text-slate-900">{exam.total_marks}</p>
                </div>
              </div>
            </div>
          </div>

          {/* System Checks */}
          <div className="mb-8">
            <h2 className="font-semibold text-slate-900 mb-4">System Requirements</h2>
            <div className="space-y-3">
              <div className={`flex items-center gap-3 p-4 rounded-lg ${
                cameraAllowed ? 'bg-emerald-50 border border-emerald-200' : 'bg-rose-50 border border-rose-200'
              }`}>
                <Camera className={`w-5 h-5 ${cameraAllowed ? 'text-emerald-600' : 'text-rose-600'}`} />
                <div className="flex-1">
                  <p className={`font-medium ${cameraAllowed ? 'text-emerald-900' : 'text-rose-900'}`}>
                    Camera Access
                  </p>
                  <p className={`text-sm ${cameraAllowed ? 'text-emerald-600' : 'text-rose-600'}`}>
                    {cameraAllowed ? 'Granted' : 'Required for proctoring'}
                  </p>
                </div>
                {cameraAllowed && <Check className="w-5 h-5 text-emerald-600" />}
              </div>

              <div className={`flex items-center gap-3 p-4 rounded-lg ${
                micAllowed ? 'bg-emerald-50 border border-emerald-200' : 'bg-amber-50 border border-amber-200'
              }`}>
                <Mic className={`w-5 h-5 ${micAllowed ? 'text-emerald-600' : 'text-amber-600'}`} />
                <div className="flex-1">
                  <p className={`font-medium ${micAllowed ? 'text-emerald-900' : 'text-amber-900'}`}>
                    Microphone Access
                  </p>
                  <p className={`text-sm ${micAllowed ? 'text-emerald-600' : 'text-amber-600'}`}>
                    {micAllowed ? 'Granted' : 'Recommended for audio monitoring'}
                  </p>
                </div>
                {micAllowed && <Check className="w-5 h-5 text-emerald-600" />}
              </div>
            </div>
          </div>

          {/* Instructions */}
          <div className="mb-8">
            <h2 className="font-semibold text-slate-900 mb-4">Instructions</h2>
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
              <div className="flex gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                <ul className="space-y-2 text-sm text-amber-900">
                  <li>• Ensure you are in a quiet, well-lit environment</li>
                  <li>• Do not switch tabs or windows during the exam</li>
                  <li>• Keep your face visible to the camera at all times</li>
                  <li>• Timer will start immediately after clicking "Start Exam"</li>
                  <li>• Exam will auto-submit when time expires</li>
                </ul>
              </div>
            </div>
          </div>

          {/* Agreement Checkbox */}
          <label className="flex items-start gap-3 p-4 card bg-slate-50 cursor-pointer mb-8">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-1 w-4 h-4 text-indigo-600 rounded focus:ring-2 focus:ring-indigo-500"
            />
            <p className="text-sm text-slate-700">
              I agree to the exam rules and understand that this exam is proctored. 
              I will not engage in any form of academic dishonesty.
            </p>
          </label>

          {/* Start Button */}
          <motion.button
            whileHover={canStart ? { scale: 1.02 } : {}}
            whileTap={canStart ? { scale: 0.98 } : {}}
            onClick={handleStartExam}
            disabled={!canStart || starting}
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
                Start Exam
                <ArrowRight className="w-5 h-5" />
              </>
            )}
          </motion.button>
        </motion.div>
      </div>
    </div>
  );
};

export default ExamLobby;