import { motion } from 'framer-motion';
import { CheckCircle2, Circle, Flag } from 'lucide-react';
import { useExamStore } from '../store/examStore';

const QuestionPalette = () => {
  const {
    questions,
    answers,
    currentQuestionIndex,
    navigateToQuestion,
    getAnsweredCount,
    getMarkedCount,
    getUnansweredCount,
  } = useExamStore();

  const answeredCount = getAnsweredCount();
  const markedCount = getMarkedCount();
  const unansweredCount = getUnansweredCount();

  const getQuestionStatus = (questionId: string, index: number) => {
    const answer = answers.get(questionId);
    const isAnswered = answer?.selectedOptions.length ?? 0 > 0;
    const isMarked = answer?.markedForReview ?? false;
    const isCurrent = index === currentQuestionIndex;

    if (isCurrent) return 'current';
    if (isMarked) return 'marked';
    if (isAnswered) return 'answered';
    if (answer?.visited) return 'visited';
    return 'unanswered';
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'current':
        return 'bg-indigo-600 text-white border-indigo-600';
      case 'answered':
        return 'bg-emerald-500 text-white border-emerald-500';
      case 'marked':
        return 'bg-amber-500 text-white border-amber-500';
      case 'visited':
        return 'bg-slate-300 text-slate-700 border-slate-300';
      default:
        return 'bg-white text-slate-700 border-slate-300 hover:border-slate-400';
    }
  };

  return (
    <div className="h-full flex flex-col bg-slate-800 p-6">
      {/* Stats */}
      <div className="mb-6">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">Question Status</h3>
        <div className="space-y-2 text-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-slate-300">Answered</span>
            </div>
            <span className="font-semibold text-white">{answeredCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Circle className="w-4 h-4 text-slate-400" />
              <span className="text-slate-300">Unanswered</span>
            </div>
            <span className="font-semibold text-white">{unansweredCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Flag className="w-4 h-4 text-amber-400" />
              <span className="text-slate-300">Marked</span>
            </div>
            <span className="font-semibold text-white">{markedCount}</span>
          </div>
        </div>
      </div>

      <div className="h-px bg-slate-700 mb-6" />

      {/* Question Grid */}
      <div className="flex-1 overflow-y-auto">
        <h3 className="text-sm font-semibold text-slate-300 mb-4">All Questions</h3>
        <div className="grid grid-cols-4 gap-2">
          {questions.map((question, index) => {
            const status = getQuestionStatus(question.id, index);
            const statusColor = getStatusColor(status);

            return (
              <motion.button
                key={question.id}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                onClick={() => navigateToQuestion(index)}
                className={`
                  aspect-square rounded-lg border-2 font-semibold text-sm
                  transition-all duration-200 ${statusColor}
                `}
              >
                {index + 1}
              </motion.button>
            );
          })}
        </div>
      </div>

      {/* Legend */}
      <div className="mt-6 pt-6 border-t border-slate-700">
        <h3 className="text-xs font-semibold text-slate-400 mb-3">Legend</h3>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-emerald-500" />
            <span className="text-slate-300">Answered</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-white" />
            <span className="text-slate-300">Not Visited</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-amber-500" />
            <span className="text-slate-300">Marked</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-4 h-4 rounded bg-indigo-600" />
            <span className="text-slate-300">Current</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default QuestionPalette;