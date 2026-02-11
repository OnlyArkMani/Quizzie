import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Clock } from 'lucide-react';
import { useExamStore } from '../store/examStore';

const ExamTimer = () => {
  const { timeRemaining, decrementTimer } = useExamStore();
  const [isWarning, setIsWarning] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      decrementTimer();
    }, 1000);

    return () => clearInterval(interval);
  }, [decrementTimer]);

  useEffect(() => {
    setIsWarning(timeRemaining < 300); // Less than 5 mins
  }, [timeRemaining]);

  const minutes = Math.floor(timeRemaining / 60);
  const seconds = timeRemaining % 60;

  return (
    <motion.div
      animate={isWarning ? { scale: [1, 1.05, 1] } : {}}
      transition={{ repeat: Infinity, duration: 1.5 }}
      className={`
        flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-lg font-bold transition-colors
        ${
          isWarning
            ? 'bg-rose-500 text-white'
            : 'bg-slate-800 text-slate-200'
        }
      `}
    >
      <Clock className="w-5 h-5" />
      <span>
        {String(minutes).padStart(2, '0')}:{String(seconds).padStart(2, '0')}
      </span>
    </motion.div>
  );
};

export default ExamTimer;