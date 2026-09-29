import { useEffect, useRef } from 'react';
import api from '@/lib/api';
import { useAuthStore } from '@/features/auth/store/authStore';
import { useExamStore, toApiResponse, ApiResponse } from '../store/examStore';

/*
 * Durable auto-save.
 *
 * - Delta saves: only answers edited since their last acknowledged save.
 * - Debounced: waits DEBOUNCE_MS after the last edit, but never lets an edit sit
 *   unsaved longer than MAX_WAIT_MS (someone typing continuously in a coding
 *   question must still be saved).
 * - Single-flight: at most one save request in flight; edits made meanwhile are
 *   picked up by the next save. (Plus the server's client_seq guard, so even
 *   out-of-order arrivals from retries or a second tab can't lose data.)
 * - Retries with capped exponential backoff while offline, and immediately on
 *   the browser's `online` event.
 * - On tab hide/close: a best-effort `fetch(..., {keepalive: true})` flush.
 *   (sendBeacon can't send the Authorization header, which is why the old
 *   beacon never worked.)
 *
 * The old version reset its 10 s setInterval on every answer change (effect
 * deps), so an active student could go minutes without a save, and it sent
 * option *indexes* the server couldn't use. The server discarded it anyway.
 */
/*
 * Offline durability: the not-yet-acknowledged answers are also mirrored to
 * localStorage, so closing the tab (or the browser crashing) while offline
 * doesn't lose them. On the next load TakeExam calls restorePendingAnswers,
 * which re-applies only entries NEWER than the server's copy (client_seq).
 * localStorage (not IndexedDB): the data is tiny and a synchronous write on
 * every edit is exactly what we want. Every access is try/catch-ed — private
 * mode / quota errors just disable this safety net.
 */
const pendingKey = (attemptId: string) => `quizzie:pending:${attemptId}`;

function persistPending() {
  const { attemptId, dirty, answers, questions } = useExamStore.getState();
  if (!attemptId) return;
  try {
    if (dirty.size === 0) {
      localStorage.removeItem(pendingKey(attemptId));
      return;
    }
    const entries = Array.from(dirty.keys())
      .map(qid => answers.get(qid))
      .filter(Boolean)
      .map(a => toApiResponse(a!, questions));
    localStorage.setItem(pendingKey(attemptId), JSON.stringify(entries));
  } catch { /* storage unavailable — best effort */ }
}

export function restorePendingAnswers(attemptId: string): number {
  try {
    const raw = localStorage.getItem(pendingKey(attemptId));
    if (!raw) return 0;
    return useExamStore.getState().mergePending(JSON.parse(raw) as ApiResponse[]);
  } catch {
    return 0;
  }
}

export function clearPendingAnswers(attemptId: string) {
  try { localStorage.removeItem(pendingKey(attemptId)); } catch { /* ignore */ }
}

const DEBOUNCE_MS = 1500;
const MAX_WAIT_MS = 10_000;
const MAX_BACKOFF_MS = 30_000;

export function useAutoSave(onAttemptClosed: () => void) {
  const timer = useRef<number | null>(null);
  const firstDirtyAt = useRef<number | null>(null);
  const inFlight = useRef(false);
  const backoff = useRef(0);
  const closedRef = useRef(onAttemptClosed);
  closedRef.current = onAttemptClosed;

  useEffect(() => {
    const clear = () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = null;
    };

    const buildPayload = () => {
      const { dirty, answers, questions } = useExamStore.getState();
      const snapshot = new Map(dirty);
      const responses = Array.from(snapshot.keys())
        .map(qid => answers.get(qid))
        .filter(Boolean)
        .map(a => toApiResponse(a!, questions));
      return { snapshot, responses };
    };

    const save = async () => {
      timer.current = null;
      const { attemptId, isSubmitted, setSaveStatus, markSaved } = useExamStore.getState();
      if (!attemptId || isSubmitted || inFlight.current) return;
      const { snapshot, responses } = buildPayload();
      if (responses.length === 0) return;

      inFlight.current = true;
      setSaveStatus('saving');
      try {
        await api.post(`/attempts/${attemptId}/auto-save`, { responses });
        markSaved(snapshot);
        persistPending();
        setSaveStatus('saved');
        backoff.current = 0;
        firstDirtyAt.current = null;
      } catch (err: any) {
        const status = err?.response?.status;
        if (status === 409) {
          // Attempt closed server-side (deadline passed / auto-submitted).
          setSaveStatus('idle');
          closedRef.current();
          return;
        }
        setSaveStatus(navigator.onLine ? 'error' : 'offline');
        backoff.current = Math.min(backoff.current ? backoff.current * 2 : 2000, MAX_BACKOFF_MS);
      } finally {
        inFlight.current = false;
      }
      schedule();
    };

    const schedule = () => {
      const { dirty } = useExamStore.getState();
      if (dirty.size === 0) return;
      const now = Date.now();
      if (firstDirtyAt.current === null) firstDirtyAt.current = now;
      const untilMax = MAX_WAIT_MS - (now - firstDirtyAt.current);
      const wait = backoff.current || Math.max(0, Math.min(DEBOUNCE_MS, untilMax));
      clear();
      timer.current = window.setTimeout(save, wait);
    };

    // React to edits (dirty map changes) without re-rendering anything.
    const unsubscribe = useExamStore.subscribe((state, prev) => {
      if (state.dirty === prev.dirty) return;
      persistPending();
      if (state.dirty.size > 0 && !inFlight.current) schedule();
    });

    const onOnline = () => { backoff.current = 0; schedule(); };

    const flushOnHide = () => {
      if (document.visibilityState !== 'hidden') return;
      const { attemptId, isSubmitted } = useExamStore.getState();
      const { responses } = buildPayload();
      const token = useAuthStore.getState().token;
      if (!attemptId || isSubmitted || responses.length === 0 || !token) return;
      fetch(`/api/v1/attempts/${attemptId}/auto-save`, {
        method: 'POST',
        keepalive: true,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ responses }),
      }).catch(() => {});
    };

    window.addEventListener('online', onOnline);
    document.addEventListener('visibilitychange', flushOnHide);
    window.addEventListener('pagehide', flushOnHide);

    return () => {
      clear();
      unsubscribe();
      window.removeEventListener('online', onOnline);
      document.removeEventListener('visibilitychange', flushOnHide);
      window.removeEventListener('pagehide', flushOnHide);
    };
  }, []);
}
