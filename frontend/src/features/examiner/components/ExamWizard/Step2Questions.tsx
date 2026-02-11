import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion, AnimatePresence } from 'framer-motion';
import {
  PlusCircle,
  Trash2,
  Edit2,
  ArrowRight,
  ArrowLeft,
  X,
} from 'lucide-react';
import { useExaminerStore } from '../../store/examinerStore';

const questionSchema = z.object({
  question_text: z.string().min(10, 'Question must be at least 10 characters'),
  question_type: z.enum(['single', 'multiple']),
  marks: z.number().min(1, 'Minimum 1 mark'),
  topic: z.string().optional(),
  options: z
    .array(
      z.object({
        option_text: z.string().min(1, 'Option cannot be empty'),
        is_correct: z.boolean(),
      })
    )
    .min(2, 'At least 2 options required'),
});

type QuestionFormData = z.infer<typeof questionSchema>;

const Step2Questions = () => {
  const { currentDraft, addQuestion, removeQuestion, setStep } = useExaminerStore();
  const [showQuestionForm, setShowQuestionForm] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    watch,
    setValue,
    reset,
  } = useForm<QuestionFormData>({
    resolver: zodResolver(questionSchema),
    defaultValues: {
      question_type: 'single',
      marks: 1,
      options: [
        { option_text: '', is_correct: false },
        { option_text: '', is_correct: false },
      ],
    },
  });

  const options = watch('options');

  const addOption = () => {
    setValue('options', [...options, { option_text: '', is_correct: false }]);
  };

  const removeOption = (index: number) => {
    if (options.length > 2) {
      setValue(
        'options',
        options.filter((_, i) => i !== index)
      );
    }
  };

  const toggleCorrect = (index: number) => {
    const newOptions = [...options];
    const questionType = watch('question_type');

    if (questionType === 'single') {
      // For single correct, uncheck all others
      newOptions.forEach((opt, i) => {
        opt.is_correct = i === index;
      });
    } else {
      // For multiple correct, toggle
      newOptions[index].is_correct = !newOptions[index].is_correct;
    }

    setValue('options', newOptions);
  };

  const onSubmit = (data: QuestionFormData) => {
    // Validate at least one correct answer
    const hasCorrect = data.options.some((opt) => opt.is_correct);
    if (!hasCorrect) {
      alert('Please mark at least one correct answer');
      return;
    }

    addQuestion(data);
    reset();
    setShowQuestionForm(false);
  };

  const handleNext = () => {
    if (currentDraft.questions.length === 0) {
      alert('Please add at least one question');
      return;
    }
    setStep(3);
  };

  return (
    <div className="space-y-6">
      {/* Questions List */}
      <div className="card p-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-slate-900">Questions</h2>
            <p className="text-sm text-slate-600 mt-1">
              {currentDraft.questions.length} questions • {currentDraft.total_marks} total marks
            </p>
          </div>
          <button
            onClick={() => setShowQuestionForm(true)}
            className="btn-primary flex items-center gap-2"
          >
            <PlusCircle className="w-5 h-5" />
            Add Question
          </button>
        </div>

        {currentDraft.questions.length === 0 ? (
          <div className="text-center py-12 bg-slate-50 rounded-lg">
            <p className="text-slate-600 mb-4">No questions added yet</p>
            <button
              onClick={() => setShowQuestionForm(true)}
              className="btn-secondary inline-flex items-center gap-2"
            >
              <PlusCircle className="w-5 h-5" />
              Add Your First Question
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {currentDraft.questions.map((question, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="card p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-sm font-semibold text-slate-900">
                        Q{index + 1}
                      </span>
                      <span className="text-xs px-2 py-1 rounded-full bg-indigo-100 text-indigo-700">
                        {question.marks} {question.marks === 1 ? 'mark' : 'marks'}
                      </span>
                      {question.question_type === 'multiple' && (
                        <span className="text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-700">
                          Multiple Correct
                        </span>
                      )}
                      {question.topic && (
                        <span className="text-xs px-2 py-1 rounded-full bg-purple-100 text-purple-700">
                          {question.topic}
                        </span>
                      )}
                    </div>
                    <p className="text-slate-900 font-medium mb-3">{question.question_text}</p>
                    <div className="grid grid-cols-2 gap-2">
                      {question.options.map((option, optIdx) => (
                        <div
                          key={optIdx}
                          className={`text-sm p-2 rounded ${
                            option.is_correct
                              ? 'bg-emerald-50 text-emerald-900 border border-emerald-200'
                              : 'bg-slate-50 text-slate-700'
                          }`}
                        >
                          {String.fromCharCode(65 + optIdx)}. {option.option_text}
                        </div>
                      ))}
                    </div>
                  </div>
                  <button
                    onClick={() => removeQuestion(index)}
                    className="ml-4 p-2 text-rose-600 hover:bg-rose-50 rounded-lg transition"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button onClick={() => setStep(1)} className="btn-secondary flex items-center gap-2">
          <ArrowLeft className="w-5 h-5" />
          Previous
        </button>
        <button
          onClick={handleNext}
          className="btn-primary flex items-center gap-2"
          disabled={currentDraft.questions.length === 0}
        >
          Next: Settings
          <ArrowRight className="w-5 h-5" />
        </button>
      </div>

      {/* Question Form Modal */}
      <AnimatePresence>
        {showQuestionForm && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setShowQuestionForm(false)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
            />

            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto"
            >
              <div className="bg-white rounded-2xl shadow-2xl max-w-3xl w-full p-8 my-8">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-2xl font-bold text-slate-900">Add Question</h3>
                  <button
                    onClick={() => setShowQuestionForm(false)}
                    className="text-slate-400 hover:text-slate-600"
                  >
                    <X className="w-6 h-6" />
                  </button>
                </div>

                <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
                  {/* Question Text */}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-2">
                      Question *
                    </label>
                    <textarea
                      {...register('question_text')}
                      rows={3}
                      className={`input-field resize-none ${
                        errors.question_text ? 'border-rose-500' : ''
                      }`}
                      placeholder="Enter your question here..."
                    />
                    {errors.question_text && (
                      <p className="mt-1 text-sm text-rose-600">
                        {errors.question_text.message}
                      </p>
                    )}
                  </div>

                  {/* Question Type, Marks, Topic */}
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-2">
                        Type *
                      </label>
                      <select {...register('question_type')} className="input-field">
                        <option value="single">Single Correct</option>
                        <option value="multiple">Multiple Correct</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-2">
                        Marks *
                      </label>
                      <input
                        {...register('marks', { valueAsNumber: true })}
                        type="number"
                        min="1"
                        className={`input-field ${errors.marks ? 'border-rose-500' : ''}`}
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-2">
                        Topic (Optional)
                      </label>
                      <input
                        {...register('topic')}
                        type="text"
                        className="input-field"
                        placeholder="e.g., Arrays"
                      />
                    </div>
                  </div>

                  {/* Options */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <label className="text-sm font-medium text-slate-700">Options *</label>
                      <button
                        type="button"
                        onClick={addOption}
                        className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
                      >
                        + Add Option
                      </button>
                    </div>

                    <div className="space-y-3">
                      {options.map((option, index) => (
                        <div key={index} className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={() => toggleCorrect(index)}
                            className={`flex-shrink-0 w-6 h-6 rounded-full border-2 transition ${
                              option.is_correct
                                ? 'bg-emerald-500 border-emerald-500'
                                : 'border-slate-300 hover:border-slate-400'
                            }`}
                          >
                            {option.is_correct && (
                              <motion.div
                                initial={{ scale: 0 }}
                                animate={{ scale: 1 }}
                                className="w-full h-full flex items-center justify-center"
                              >
                                <span className="text-white text-xs">✓</span>
                              </motion.div>
                            )}
                          </button>

                          <input
                            {...register(`options.${index}.option_text`)}
                            type="text"
                            className="input-field flex-1"
                            placeholder={`Option ${String.fromCharCode(65 + index)}`}
                          />

                          {options.length > 2 && (
                            <button
                              type="button"
                              onClick={() => removeOption(index)}
                              className="flex-shrink-0 p-2 text-rose-600 hover:bg-rose-50 rounded-lg"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                    <p className="text-xs text-slate-500 mt-2">
                      Click the circle to mark correct answer(s)
                    </p>
                  </div>

                  {/* Submit */}
                  <div className="flex gap-3 pt-4">
                    <button
                      type="button"
                      onClick={() => setShowQuestionForm(false)}
                      className="flex-1 btn-secondary"
                    >
                      Cancel
                    </button>
                    <button type="submit" className="flex-1 btn-primary">
                      Add Question
                    </button>
                  </div>
                </form>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Step2Questions;