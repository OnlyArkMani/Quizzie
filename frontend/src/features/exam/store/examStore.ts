import { create } from 'zustand';
import { Question, Answer } from '@/types';

interface ExamState {
  examId: string | null;
  questions: Question[];
  answers: Map<string, Answer>;
  currentQuestionIndex: number;
  timeRemaining: number; // in seconds
  isSubmitted: boolean;
  attemptId: string | null;

  // Actions
  initExam: (examId: string, questions: Question[], durationSeconds: number, attemptId: string) => void;
  selectAnswer: (questionId: string, optionIndex: number, isMultiple: boolean) => void;
  toggleMarkForReview: (questionId: string) => void;
  navigateToQuestion: (index: number) => void;
  nextQuestion: () => void;
  prevQuestion: () => void;
  decrementTimer: () => void;
  submitExam: () => void;
  resetExam: () => void;

  // Computed
  getAnsweredCount: () => number;
  getMarkedCount: () => number;
  getUnansweredCount: () => number;
  getCurrentAnswer: () => Answer | undefined;
}

export const useExamStore = create<ExamState>((set, get) => ({
  examId: null,
  questions: [],
  answers: new Map(),
  currentQuestionIndex: 0,
  timeRemaining: 0,
  isSubmitted: false,
  attemptId: null,

  initExam: (examId, questions, durationSeconds, attemptId) => {
    const initialAnswers = new Map<string, Answer>();
    questions.forEach(q => {
      initialAnswers.set(q.id, {
        questionId: q.id,
        selectedOptions: [],
        markedForReview: false,
        visited: false,
      });
    });

    set({
      examId,
      questions,
      answers: initialAnswers,
      // FIX Bug 5: durationSeconds is already in seconds (TakeExam passes
      // duration_minutes * 60 before calling initExam), so store it as-is.
      // Old code had `duration * 60` here which doubled the time.
      timeRemaining: durationSeconds,
      currentQuestionIndex: 0,
      isSubmitted: false,
      attemptId,
    });
  },

  selectAnswer: (questionId, optionIndex, isMultiple) => {
    set((state) => {
      const newAnswers = new Map(state.answers);
      const current = newAnswers.get(questionId);
      if (!current) return state;

      let selectedOptions: number[];
      if (isMultiple) {
        selectedOptions = current.selectedOptions.includes(optionIndex)
          ? current.selectedOptions.filter(i => i !== optionIndex)
          : [...current.selectedOptions, optionIndex];
      } else {
        selectedOptions = [optionIndex];
      }

      newAnswers.set(questionId, { ...current, selectedOptions, visited: true });
      return { answers: newAnswers };
    });
  },

  toggleMarkForReview: (questionId) => {
    set((state) => {
      const newAnswers = new Map(state.answers);
      const current = newAnswers.get(questionId);
      if (!current) return state;
      newAnswers.set(questionId, { ...current, markedForReview: !current.markedForReview });
      return { answers: newAnswers };
    });
  },

  navigateToQuestion: (index) => {
    const { questions, answers } = get();
    const question = questions[index];
    if (question) {
      const newAnswers = new Map(answers);
      const current = newAnswers.get(question.id);
      if (current) newAnswers.set(question.id, { ...current, visited: true });
      set({ currentQuestionIndex: index, answers: newAnswers });
    }
  },

  nextQuestion: () => {
    const { currentQuestionIndex, questions } = get();
    if (currentQuestionIndex < questions.length - 1) {
      get().navigateToQuestion(currentQuestionIndex + 1);
    }
  },

  prevQuestion: () => {
    const { currentQuestionIndex } = get();
    if (currentQuestionIndex > 0) {
      get().navigateToQuestion(currentQuestionIndex - 1);
    }
  },

  decrementTimer: () => {
    set((state) => {
      const newTime = state.timeRemaining - 1;
      if (newTime <= 0) return { timeRemaining: 0, isSubmitted: true };
      return { timeRemaining: newTime };
    });
  },

  submitExam: () => set({ isSubmitted: true }),

  resetExam: () => set({
    examId: null,
    questions: [],
    answers: new Map(),
    currentQuestionIndex: 0,
    timeRemaining: 0,
    isSubmitted: false,
    attemptId: null,
  }),

  getAnsweredCount: () => {
    const { answers } = get();
    return Array.from(answers.values()).filter(a => a.selectedOptions.length > 0).length;
  },

  getMarkedCount: () => {
    const { answers } = get();
    return Array.from(answers.values()).filter(a => a.markedForReview).length;
  },

  getUnansweredCount: () => {
    const { questions, answers } = get();
    return questions.length - Array.from(answers.values()).filter(a => a.selectedOptions.length > 0).length;
  },

  getCurrentAnswer: () => {
    const { questions, currentQuestionIndex, answers } = get();
    const currentQuestion = questions[currentQuestionIndex];
    return currentQuestion ? answers.get(currentQuestion.id) : undefined;
  },
}));