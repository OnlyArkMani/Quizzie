import { create } from 'zustand';
import { Exam, Question } from '@/types';

interface ExamDraft {
  title: string;
  description: string;
  duration_minutes: number;
  total_marks: number;
  pass_percentage: number;
  questions: Array<{
    question_text: string;
    question_type: 'single' | 'multiple';
    marks: number;
    topic?: string;
    options: Array<{
      option_text: string;
      is_correct: boolean;
    }>;
  }>;
}

interface ExaminerState {
  currentDraft: ExamDraft;
  currentStep: number;
  
  updateDraftDetails: (details: Partial<ExamDraft>) => void;
  addQuestion: (question: ExamDraft['questions'][0]) => void;
  updateQuestion: (index: number, question: ExamDraft['questions'][0]) => void;
  removeQuestion: (index: number) => void;
  setStep: (step: number) => void;
  resetDraft: () => void;
}

const initialDraft: ExamDraft = {
  title: '',
  description: '',
  duration_minutes: 60,
  total_marks: 0,
  pass_percentage: 40,
  questions: [],
};

export const useExaminerStore = create<ExaminerState>((set) => ({
  currentDraft: initialDraft,
  currentStep: 1,
  
  updateDraftDetails: (details) => {
    set((state) => ({
      currentDraft: { ...state.currentDraft, ...details },
    }));
  },
  
  addQuestion: (question) => {
    set((state) => ({
      currentDraft: {
        ...state.currentDraft,
        questions: [...state.currentDraft.questions, question],
        total_marks: state.currentDraft.total_marks + question.marks,
      },
    }));
  },
  
  updateQuestion: (index, question) => {
    set((state) => {
      const newQuestions = [...state.currentDraft.questions];
      const oldMarks = newQuestions[index]?.marks || 0;
      newQuestions[index] = question;
      
      return {
        currentDraft: {
          ...state.currentDraft,
          questions: newQuestions,
          total_marks: state.currentDraft.total_marks - oldMarks + question.marks,
        },
      };
    });
  },
  
  removeQuestion: (index) => {
    set((state) => {
      const question = state.currentDraft.questions[index];
      return {
        currentDraft: {
          ...state.currentDraft,
          questions: state.currentDraft.questions.filter((_, i) => i !== index),
          total_marks: state.currentDraft.total_marks - (question?.marks || 0),
        },
      };
    });
  },
  
  setStep: (step) => {
    set({ currentStep: step });
  },
  
  resetDraft: () => {
    set({ currentDraft: initialDraft, currentStep: 1 });
  },
}));