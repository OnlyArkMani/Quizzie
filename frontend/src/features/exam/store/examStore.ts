import { create } from 'zustand';
import { Question, Answer, AttemptState } from '@/types';

/*
 * Exam-taking state.
 *
 * Two ideas drive this store:
 *  1. The SERVER owns the clock. We store the attempt's deadline and the
 *     offset between the server's clock and ours, and derive "time remaining"
 *     from them on every tick. A paused JS thread, a sleeping laptop or a
 *     tampered system clock can't give anyone extra time — the server rejects
 *     late writes anyway; this just keeps the display honest.
 *  2. Answers are durable. Every edit bumps a monotonic `clientSeq` and marks
 *     the question dirty; the auto-saver (useAutoSave) sends dirty answers and
 *     clears them only once the server has acknowledged that exact seq.
 */

let lastSeq = 0;
/** Strictly increasing within a tab, roughly wall-clock ordered across tabs. */
export const nextSeq = () => {
  lastSeq = Math.max(Date.now(), lastSeq + 1);
  return lastSeq;
};

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error' | 'offline';

interface ExamState {
  examId: string | null;
  questions: Question[];
  answers: Map<string, Answer>;
  currentQuestionIndex: number;
  timeRemaining: number; // seconds, derived from deadline + server clock offset
  deadlineMs: number | null;       // server deadline, epoch ms
  serverOffsetMs: number;          // serverNow - clientNow at load
  isSubmitted: boolean;
  attemptId: string | null;

  // Auto-save bookkeeping
  dirty: Map<string, number>;      // questionId -> clientSeq not yet acknowledged
  saveStatus: SaveStatus;
  lastSavedAt: number | null;

  // Actions
  initExam: (examId: string, questions: Question[], attemptId: string, state: AttemptState) => void;
  selectAnswer: (questionId: string, optionIndex: number, isMultiple: boolean) => void;
  setTextAnswer: (questionId: string, text: string) => void;
  toggleMarkForReview: (questionId: string) => void;
  navigateToQuestion: (index: number) => void;
  nextQuestion: () => void;
  prevQuestion: () => void;
  tick: () => void;
  submitExam: () => void;
  resetExam: () => void;
  markSaved: (acked: Map<string, number>) => void;
  mergePending: (pending: ApiResponse[]) => number;
  setSaveStatus: (s: SaveStatus) => void;

  // Computed
  getAnsweredCount: () => number;
  getMarkedCount: () => number;
  getUnansweredCount: () => number;
  getCurrentAnswer: () => Answer | undefined;
}

const remainingFrom = (deadlineMs: number | null, offsetMs: number) =>
  deadlineMs === null ? 0 : Math.max(0, Math.floor((deadlineMs - (Date.now() + offsetMs)) / 1000));

export const useExamStore = create<ExamState>((set, get) => {
  /** Apply an edit to one answer: new seq + mark dirty. */
  const edit = (questionId: string, fn: (a: Answer) => Partial<Answer>) =>
    set((state) => {
      const current = state.answers.get(questionId);
      if (!current || state.isSubmitted) return state;
      const seq = nextSeq();
      const answers = new Map(state.answers);
      answers.set(questionId, { ...current, ...fn(current), clientSeq: seq });
      const dirty = new Map(state.dirty);
      dirty.set(questionId, seq);
      return { answers, dirty };
    });

  return {
    examId: null,
    questions: [],
    answers: new Map(),
    currentQuestionIndex: 0,
    timeRemaining: 0,
    deadlineMs: null,
    serverOffsetMs: 0,
    isSubmitted: false,
    attemptId: null,
    dirty: new Map(),
    saveStatus: 'idle',
    lastSavedAt: null,

    initExam: (examId, questions, attemptId, state) => {
      // Rebuild answers from what the server has durably saved (resume after
      // reload/crash), translating option UUIDs back to option indexes.
      const saved = new Map(state.responses.map(r => [r.question_id, r]));
      const answers = new Map<string, Answer>();
      questions.forEach(q => {
        const r = saved.get(q.id);
        const selectedOptions = r
          ? r.selected_option_ids
              .map(id => q.options.findIndex(o => o.id === id))
              .filter(i => i >= 0)
          : [];
        answers.set(q.id, {
          questionId: q.id,
          selectedOptions,
          textAnswer: r?.answer_text ?? undefined,
          markedForReview: r?.marked_for_review ?? false,
          visited: !!r,
          clientSeq: r?.client_seq ?? 0,
        });
        if (r) lastSeq = Math.max(lastSeq, r.client_seq);
      });

      const serverOffsetMs = new Date(state.server_now).getTime() - Date.now();
      const deadlineMs = state.deadline ? new Date(state.deadline).getTime() : null;

      set({
        examId,
        questions,
        answers,
        attemptId,
        deadlineMs,
        serverOffsetMs,
        timeRemaining: remainingFrom(deadlineMs, serverOffsetMs),
        currentQuestionIndex: 0,
        isSubmitted: state.status !== 'in_progress',
        dirty: new Map(),
        saveStatus: 'idle',
        lastSavedAt: null,
      });
    },

    selectAnswer: (questionId, optionIndex, isMultiple) =>
      edit(questionId, (current) => ({
        selectedOptions: isMultiple
          ? current.selectedOptions.includes(optionIndex)
            ? current.selectedOptions.filter(i => i !== optionIndex)
            : [...current.selectedOptions, optionIndex]
          : [optionIndex],
        visited: true,
      })),

    setTextAnswer: (questionId, text) =>
      edit(questionId, () => ({ textAnswer: text, visited: true })),

    toggleMarkForReview: (questionId) =>
      edit(questionId, (current) => ({ markedForReview: !current.markedForReview })),

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

    tick: () => {
      const { deadlineMs, serverOffsetMs } = get();
      set({ timeRemaining: remainingFrom(deadlineMs, serverOffsetMs) });
    },

    submitExam: () => set({ isSubmitted: true }),

    markSaved: (acked) =>
      set((state) => {
        // Only clear an entry if it wasn't edited again while the save was in
        // flight (its seq would be higher than the one the server acked).
        const dirty = new Map(state.dirty);
        acked.forEach((seq, qid) => {
          if ((dirty.get(qid) ?? 0) <= seq) dirty.delete(qid);
        });
        return { dirty, lastSavedAt: Date.now() };
      }),

    setSaveStatus: (saveStatus) => set({ saveStatus }),

    mergePending: (pending) => {
      // Edits that were made but never reached the server (tab closed while
      // offline). Re-apply those NEWER than what the server has, mark them dirty,
      // and the auto-saver sends them. Returns how many were restored.
      let restored = 0;
      set((state) => {
        const answers = new Map(state.answers);
        const dirty = new Map(state.dirty);
        for (const r of pending) {
          const current = answers.get(r.question_id);
          const q = state.questions.find(x => x.id === r.question_id);
          if (!current || !q || r.client_seq <= current.clientSeq) continue;
          answers.set(r.question_id, {
            ...current,
            selectedOptions: r.selected_option_ids
              .map(id => q.options.findIndex(o => o.id === id))
              .filter(i => i >= 0),
            textAnswer: r.answer_text ?? undefined,
            markedForReview: r.marked_for_review,
            visited: true,
            clientSeq: r.client_seq,
          });
          dirty.set(r.question_id, r.client_seq);
          lastSeq = Math.max(lastSeq, r.client_seq);
          restored++;
        }
        return restored ? { answers, dirty } : state;
      });
      return restored;
    },

    resetExam: () => set({
      examId: null,
      questions: [],
      answers: new Map(),
      currentQuestionIndex: 0,
      timeRemaining: 0,
      deadlineMs: null,
      serverOffsetMs: 0,
      isSubmitted: false,
      attemptId: null,
      dirty: new Map(),
      saveStatus: 'idle',
      lastSavedAt: null,
    }),

    getAnsweredCount: () => {
      const { answers } = get();
      return Array.from(answers.values()).filter(
        a => a.selectedOptions.length > 0 || (a.textAnswer && a.textAnswer.trim() !== '')
      ).length;
    },

    getMarkedCount: () => {
      const { answers } = get();
      return Array.from(answers.values()).filter(a => a.markedForReview).length;
    },

    getUnansweredCount: () => {
      const { questions, answers } = get();
      const answered = Array.from(answers.values()).filter(
        a => a.selectedOptions.length > 0 || (a.textAnswer && a.textAnswer.trim() !== '')
      ).length;
      return questions.length - answered;
    },

    getCurrentAnswer: () => {
      const { questions, currentQuestionIndex, answers } = get();
      const currentQuestion = questions[currentQuestionIndex];
      return currentQuestion ? answers.get(currentQuestion.id) : undefined;
    },
  };
});

export interface ApiResponse {
  question_id: string;
  selected_option_ids: string[];
  answer_text: string | null;
  marked_for_review: boolean;
  client_seq: number;
}

/** Map a store answer to the API's response shape (option indexes -> UUIDs). */
export const toApiResponse = (a: Answer, questions: Question[]): ApiResponse => {
  const question = questions.find(q => q.id === a.questionId);
  return {
    question_id: a.questionId,
    selected_option_ids: a.selectedOptions
      .map(idx => question?.options[idx]?.id)
      .filter(Boolean) as string[],
    answer_text: a.textAnswer || null,
    marked_for_review: a.markedForReview,
    client_seq: a.clientSeq,
  };
};
