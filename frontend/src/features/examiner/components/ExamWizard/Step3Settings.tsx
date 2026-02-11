import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowLeft, Send, CheckCircle } from 'lucide-react';
import { useExaminerStore } from '../../store/examinerStore';
import api from '@/lib/api';

const Step3Settings = () => {
  const navigate = useNavigate();
  const { currentDraft, setStep, resetDraft } = useExaminerStore();
  const [status, setStatus] = useState<'draft' | 'live'>('draft');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handlePublish = async () => {
    setIsSubmitting(true);

    try {
      // Create exam
      const examPayload = {
        title: currentDraft.title,
        description: currentDraft.description,
        duration_minutes: currentDraft.duration_minutes,
        total_marks: currentDraft.total_marks,
        pass_percentage: currentDraft.pass_percentage,
        status,
      };

      const examResponse = await api.post('/exams', examPayload);
      const examId = examResponse.data.id;

      // Add questions
      for (let i = 0; i < currentDraft.questions.length; i++) {
        const question = currentDraft.questions[i];
        await api.post(`/exams/${examId}/questions`, {
          ...question,
          display_order: i,
        });
      }

      // Success
      resetDraft();
      navigate('/examiner', {
        state: { message: 'Exam created successfully!' },
      });
    } catch (error) {
      console.error('Failed to create exam:', error);
      alert('Failed to create exam. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="card p-8">
        <h2 className="text-2xl font-bold text-slate-900 mb-6">Review & Publish</h2>

        {/* Exam Summary */}
        <div className="bg-slate-50 rounded-lg p-6 mb-6">
          <h3 className="font-semibold text-slate-900 mb-4">Exam Summary</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-slate-600">Title</p>
              <p className="font-medium text-slate-900">{currentDraft.title}</p>
            </div>
            <div>
              <p className="text-sm text-slate-600">Duration</p>
              <p className="font-medium text-slate-900">{currentDraft.duration_minutes} minutes</p>
            </div>
            <div>
              <p className="text-sm text-slate-600">Total Questions</p>
              <p className="font-medium text-slate-900">{currentDraft.questions.length}</p>
            </div>
            <div>
              <p className="text-sm text-slate-600">Total Marks</p>
              <p className="font-medium text-slate-900">{currentDraft.total_marks}</p>
            </div>
            <div>
              <p className="text-sm text-slate-600">Pass Percentage</p>
              <p className="font-medium text-slate-900">{currentDraft.pass_percentage}%</p>
            </div>
          </div>
        </div>

        {/* Status Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-3">
            Publish Status
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="relative cursor-pointer">
              <input
                type="radio"
                name="status"
                value="draft"
                checked={status === 'draft'}
                onChange={(e) => setStatus(e.target.value as 'draft' | 'live')}
                className="peer sr-only"
              />
              <div className="card p-6 peer-checked:border-indigo-600 peer-checked:bg-indigo-50 transition">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-semibold text-slate-900">Save as Draft</h4>
                  <div className="w-5 h-5 rounded-full border-2 border-slate-300 peer-checked:border-indigo-600 peer-checked:bg-indigo-600 flex items-center justify-center">
                    {status === 'draft' && <CheckCircle className="w-4 h-4 text-white" />}
                  </div>
                </div>
                <p className="text-sm text-slate-600">Save for later. Students won't see it yet.</p>
              </div>
            </label>

            <label className="relative cursor-pointer">
              <input
                type="radio"
                name="status"
                value="live"
                checked={status === 'live'}
                onChange={(e) => setStatus(e.target.value as 'draft' | 'live')}
                className="peer sr-only"
              />
              <div className="card p-6 peer-checked:border-emerald-600 peer-checked:bg-emerald-50 transition">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="font-semibold text-slate-900">Publish Now</h4>
                  <div className="w-5 h-5 rounded-full border-2 border-slate-300 peer-checked:border-emerald-600 peer-checked:bg-emerald-600 flex items-center justify-center">
                    {status === 'live' && <CheckCircle className="w-4 h-4 text-white" />}
                  </div>
                </div>
                <p className="text-sm text-slate-600">Make it available to students immediately.</p>
              </div>
            </label>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button onClick={() => setStep(2)} className="btn-secondary flex items-center gap-2">
          <ArrowLeft className="w-5 h-5" />
          Previous
        </button>
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handlePublish}
          disabled={isSubmitting}
          className={`btn-primary flex items-center gap-2 ${
            status === 'live' ? 'bg-emerald-600 hover:bg-emerald-700' : ''
          }`}
        >
          {isSubmitting ? (
            <>
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Creating...
            </>
          ) : (
            <>
              <Send className="w-5 h-5" />
              {status === 'draft' ? 'Save as Draft' : 'Publish Exam'}
            </>
          )}
        </motion.button>
      </div>
    </div>
  );
};

export default Step3Settings;