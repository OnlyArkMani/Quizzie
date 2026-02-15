import { useState, useEffect } from 'react';
import { Cloud, Check, AlertCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useExamStore } from '../store/examStore';
import api from '@/lib/api';

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

const AutoSaveIndicator = () => {
  const [status, setStatus] = useState<SaveStatus>('idle');
  const { attemptId, answers } = useExamStore();

  useEffect(() => {
    const autoSave = async () => {
      if (!attemptId || answers.size === 0) return;

      setStatus('saving');

      try {
        const responses = Array.from(answers.values()).map(answer => ({
          question_id: answer.questionId,
          selected_option_ids: answer.selectedOptions,
          marked_for_review: answer.markedForReview,
        }));

        await api.post(`/attempts/${attemptId}/auto-save`, { responses });
        
        setStatus('saved');
        setTimeout(() => setStatus('idle'), 2000);
      } catch (error) {
        console.error('Auto-save failed:', error);
        setStatus('error');
        setTimeout(() => setStatus('idle'), 3000);
      }
    };

    const interval = setInterval(autoSave, 10000); // Auto-save every 10 seconds

    return () => clearInterval(interval);
  }, [attemptId, answers]);

  return (
    <AnimatePresence mode="wait">
      {status !== 'idle' && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -10 }}
          className="flex items-center gap-2 text-sm"
        >
          {status === 'saving' && (
            <>
              <Cloud className="w-4 h-4 animate-pulse text-blue-400" />
              <span className="text-slate-400">Saving...</span>
            </>
          )}
          
          {status === 'saved' && (
            <>
              <Check className="w-4 h-4 text-emerald-400" />
              <span className="text-emerald-400">Saved</span>
            </>
          )}
          
          {status === 'error' && (
            <>
              <AlertCircle className="w-4 h-4 text-rose-400" />
              <span className="text-rose-400">Save failed</span>
            </>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default AutoSaveIndicator;