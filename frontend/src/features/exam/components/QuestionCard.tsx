import { motion, AnimatePresence } from 'framer-motion';
import { Flag, BookmarkCheck } from 'lucide-react';
import { useExamStore } from '../store/examStore';

interface QuestionCardProps {
  direction: 'forward' | 'backward';
}

const QuestionCard: React.FC<QuestionCardProps> = ({ direction }) => {
  const { 
    questions, 
    currentQuestionIndex, 
    answers, 
    selectAnswer,
    toggleMarkForReview 
  } = useExamStore();

  const currentQuestion = questions[currentQuestionIndex];
  const currentAnswer = answers.get(currentQuestion?.id || '');

  if (!currentQuestion) {
    return (
      <div className="bg-white rounded-xl p-8 border border-slate-200">
        <p className="text-slate-600 text-center">Loading question...</p>
      </div>
    );
  }

  const isMultiple = currentQuestion.question_type === 'multiple';

  const variants = {
    enter: (direction: string) => ({
      x: direction === 'forward' ? 300 : -300,
      opacity: 0,
    }),
    center: {
      x: 0,
      opacity: 1,
    },
    exit: (direction: string) => ({
      x: direction === 'forward' ? -300 : 300,
      opacity: 0,
    }),
  };

  return (
    <AnimatePresence mode="wait" custom={direction}>
      <motion.div
        key={currentQuestion.id}
        custom={direction}
        variants={variants}
        initial="enter"
        animate="center"
        exit="exit"
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className="bg-white rounded-xl p-8 border border-slate-200 shadow-sm"
      >
        {/* Question Header */}
        <div className="flex items-start justify-between mb-6">
          <div>
            <span className="text-sm font-medium text-slate-500">
              Question {currentQuestionIndex + 1} of {questions.length}
            </span>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xs px-2 py-1 rounded-md bg-indigo-50 text-indigo-700 font-medium">
                {currentQuestion.marks} {currentQuestion.marks === 1 ? 'Mark' : 'Marks'}
              </span>
              {isMultiple && (
                <span className="text-xs px-2 py-1 rounded-md bg-amber-50 text-amber-700 font-medium">
                  Multiple Correct
                </span>
              )}
              {currentQuestion.topic && (
                <span className="text-xs px-2 py-1 rounded-md bg-purple-50 text-purple-700 font-medium">
                  {currentQuestion.topic}
                </span>
              )}
            </div>
          </div>

          {/* Mark for Review Button */}
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => toggleMarkForReview(currentQuestion.id)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg transition ${
              currentAnswer?.markedForReview
                ? 'bg-amber-100 text-amber-700 border border-amber-300'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            <Flag className="w-4 h-4" />
            <span className="text-sm font-medium">
              {currentAnswer?.markedForReview ? 'Marked' : 'Mark for Review'}
            </span>
          </motion.button>
        </div>

        {/* Question Text */}
        <h2 className="text-xl font-semibold text-slate-900 mb-8 leading-relaxed">
          {currentQuestion.question_text}
        </h2>

        {/* Options */}
        <div className="space-y-3">
          {currentQuestion.options.map((option, index) => {
            const isSelected = currentAnswer?.selectedOptions.includes(index);

            return (
              <motion.button
                key={option.id}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
                onClick={() => selectAnswer(currentQuestion.id, index, isMultiple)}
                className={`
                  w-full p-4 rounded-lg border-2 text-left transition-all duration-200
                  ${
                    isSelected
                      ? 'border-indigo-600 bg-indigo-50 shadow-sm'
                      : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                  }
                `}
              >
                <div className="flex items-center gap-3">
                  {/* Radio/Checkbox */}
                  <div
                    className={`
                    flex-shrink-0 w-5 h-5 ${isMultiple ? 'rounded' : 'rounded-full'} border-2 flex items-center justify-center transition
                    ${
                      isSelected
                        ? 'border-indigo-600 bg-indigo-600'
                        : 'border-slate-300 bg-white'
                    }
                  `}
                  >
                    {isSelected && (
                      <motion.div
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className={`${isMultiple ? 'w-3 h-3' : 'w-2 h-2'} ${isMultiple ? 'rounded' : 'rounded-full'} bg-white`}
                      />
                    )}
                  </div>

                  {/* Option Label */}
                  <span className="text-xs font-semibold text-slate-400 w-8">
                    {String.fromCharCode(65 + index)}
                  </span>

                  {/* Option Text */}
                  <span
                    className={`font-medium ${
                      isSelected ? 'text-indigo-900' : 'text-slate-700'
                    }`}
                  >
                    {option.option_text}
                  </span>
                </div>
              </motion.button>
            );
          })}
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default QuestionCard;