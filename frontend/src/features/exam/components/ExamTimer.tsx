import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Clock, PauseCircle } from 'lucide-react';
import { useExamStore } from '../store/examStore';

interface ExamTimerProps {
  /** Visual only: the server's deadline keeps running while the exam is "paused". */
  paused?: boolean;
}

/*
 * Display-only countdown. Each tick RECOMPUTES remaining time from the server
 * deadline (store.tick) instead of decrementing a counter, so a throttled
 * background tab or a sleeping laptop can't drift the timer.
 */
const ExamTimer = ({ paused = false }: ExamTimerProps) => {
  const { timeRemaining, tick } = useExamStore();
  const [isWarning, setIsWarning] = useState(false);

  useEffect(() => {
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [tick]);

  useEffect(() => { setIsWarning(timeRemaining < 300); }, [timeRemaining]);

  const minutes = Math.floor(timeRemaining / 60);
  const seconds = timeRemaining % 60;

  return (
    <motion.div
      animate={isWarning && !paused ? { scale: [1, 1.05, 1] } : {}}
      transition={{ repeat: Infinity, duration: 1.5 }}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg font-mono text-lg font-bold transition-colors ${
        paused
          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
          : isWarning
          ? 'bg-rose-500 text-white'
          : 'bg-slate-800 text-slate-200'
      }`}
    >
      {paused ? <PauseCircle className="w-5 h-5" /> : <Clock className="w-5 h-5" />}
      <span>{String(minutes).padStart(2, '0')}:{String(seconds).padStart(2, '0')}</span>
      {paused && <span className="text-xs font-normal ml-1">PAUSED</span>}
    </motion.div>
  );
};

export default ExamTimer;