import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, X } from 'lucide-react';
import { useExamStore } from '../store/examStore';

interface SubmitModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

const SubmitModal: React.FC<SubmitModalProps> = ({ isOpen, onClose, onConfirm }) => {
  const { getAnsweredCount, getUnansweredCount, questions } = useExamStore();

  const answeredCount = getAnsweredCount();
  const unansweredCount = getUnansweredCount();

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4"
          >
            <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6">
              {/* Header */}
              <div className="flex items-start justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-full bg-amber-100 flex items-center justify-center">
                    <AlertTriangle className="w-6 h-6 text-amber-600" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-slate-900">Submit Exam?</h2>
                    <p className="text-sm text-slate-600">This action cannot be undone</p>
                  </div>
                </div>
                <button
                  onClick={onClose}
                  className="text-slate-400 hover:text-slate-600 transition"
                >
                  <X className="w-6 h-6" />
                </button>
              </div>

              {/* Stats */}
              <div className="bg-slate-50 rounded-lg p-4 mb-6">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-slate-600 mb-1">Total Questions</p>
                    <p className="text-2xl font-bold text-slate-900">{questions.length}</p>
                  </div>
                  <div>
                    <p className="text-sm text-slate-600 mb-1">Answered</p>
                    <p className="text-2xl font-bold text-emerald-600">{answeredCount}</p>
                  </div>
                </div>

                {unansweredCount > 0 && (
                  <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                    <p className="text-sm text-amber-800">
                      <span className="font-semibold">{unansweredCount}</span> questions remain unanswered
                    </p>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={onClose}
                  className="flex-1 px-4 py-3 rounded-lg border-2 border-slate-300 font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Review Answers
                </button>
                <button
                  onClick={onConfirm}
                  className="flex-1 px-4 py-3 rounded-lg bg-indigo-600 font-semibold text-white hover:bg-indigo-700 transition"
                >
                  Submit Now
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
};

export default SubmitModal;