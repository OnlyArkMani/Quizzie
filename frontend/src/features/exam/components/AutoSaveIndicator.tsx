import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CloudUpload, Check, CloudOff } from 'lucide-react';
import { useExamStore } from '../store/examStore';
import api from '@/lib/api';

const AutoSaveIndicator = () => {
  const { answers, attemptId } = useExamStore();
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  useEffect(() => {
    // Auto-save every 10 seconds
    const interval = setInterval(() => {
      saveProgress();
    }, 10000);

    return () => clearInterval(interval);
  }, [answers, attemptId]);

  const saveProgress = async () => {
    if (!attemptId) return;

    setStatus('saving');

    try {
      // Convert answers Map to array for API
      const responsesData = Array.from(answers.entries()).map(([questionId, answer]) => ({
        question_id: questionId,
        selected_options: answer.selectedOptions,
        marked_for_review: answer.markedForReview,
      }));

      await api.post(`/attempts/${attemptId}/auto-save`, {
        responses: responsesData,
      });

      setStatus('saved');
      setTimeout(() => setStatus('idle'), 2000);
    } catch (error) {
      console.error('Auto-save failed:', error);
      setStatus('error');
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  return (
    <AnimatePresence>
      {status !== 'idle' && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
            status === 'saving'
              ? 'bg-blue-500/20 text-blue-200'
              : status === 'saved'
              ? 'bg-emerald-500/20 text-emerald-200'
              : 'bg-rose-500/20 text-rose-200'
          }`}
        >
          {status === 'saving' && (
            <>
              <CloudUpload className="w-4 h-4 animate-pulse" />
              <span>Saving...</span>
            </>
          )}
          {status === 'saved' && (
            <>
              <Check className="w-4 h-4" />
              <span>Saved</span>
            </>
          )}
          {status === 'error' && (
            <>
              <CloudOff className="w-4 h-4" />
              <span>Save failed</span>
            </>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default AutoSaveIndicator;