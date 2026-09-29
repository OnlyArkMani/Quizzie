import { useEffect, useState } from 'react';
import { Cloud, Check, AlertCircle, WifiOff } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useExamStore } from '../store/examStore';

/** Pure view of the auto-saver's status (the saving itself lives in useAutoSave). */
const AutoSaveIndicator = () => {
  const saveStatus = useExamStore(s => s.saveStatus);
  const pending = useExamStore(s => s.dirty.size);
  const [status, setStatus] = useState(saveStatus);

  useEffect(() => {
    setStatus(saveStatus);
    if (saveStatus === 'saved') {
      const t = window.setTimeout(() => setStatus('idle'), 2000);
      return () => window.clearTimeout(t);
    }
  }, [saveStatus]);

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
              <span className="text-rose-400">Save failed — retrying ({pending} unsaved)</span>
            </>
          )}

          {status === 'offline' && (
            <>
              <WifiOff className="w-4 h-4 text-amber-400" />
              <span className="text-amber-400">Offline — {pending} answer(s) will sync when you reconnect</span>
            </>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export default AutoSaveIndicator;