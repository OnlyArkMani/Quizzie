import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle, Loader } from 'lucide-react';
import api from '@/lib/api';

interface GradeItem {
  response_id: string;
  question_id: string;
  question_text: string;
  question_type: 'coding' | 'subjective';
  language?: string | null;
  reference_answer?: string | null;
  max_marks: number;
  answer_text: string;
  marks_awarded: number | null;
}

const GradeAttempt = () => {
  const { attemptId } = useParams();
  const navigate = useNavigate();

  const [items, setItems] = useState<GradeItem[]>([]);
  const [marks, setMarks] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get(`/attempts/${attemptId}/grading`);
        if (cancelled) return;
        const data = res.data;
        setItems(data.items || []);
        const initial: Record<string, string> = {};
        (data.items || []).forEach((it: GradeItem) => {
          initial[it.response_id] = it.marks_awarded != null ? String(it.marks_awarded) : '';
        });
        setMarks(initial);
      } catch (e: any) {
        setError(e?.response?.data?.detail || 'Failed to load answers for grading.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [attemptId]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const grades = items
        .filter((it) => marks[it.response_id] !== '' && marks[it.response_id] != null)
        .map((it) => ({
          response_id: it.response_id,
          marks_awarded: Number(marks[it.response_id]),
        }));
      await api.post(`/attempts/${attemptId}/grade`, { grades });
      setSaved(true);
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to save grades.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader className="w-8 h-8 text-indigo-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="max-w-3xl mx-auto px-4">
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-slate-600 hover:text-slate-900 mb-4 flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>

        <h1 className="text-2xl font-bold text-slate-900 mb-1">Grade Answers</h1>
        <p className="text-sm text-slate-600 mb-6">
          Manually graded coding &amp; subjective answers for this attempt.
        </p>

        {error && (
          <div className="bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-lg p-3 mb-4">
            {error}
          </div>
        )}

        {items.length === 0 ? (
          <div className="card p-8 text-center text-slate-600">
            Nothing to grade — this attempt has no coding or subjective answers.
          </div>
        ) : (
          <div className="space-y-6">
            {items.map((it, idx) => (
              <div key={it.response_id} className="card p-6">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-semibold text-slate-900">Q{idx + 1}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
                    {it.max_marks} {it.max_marks === 1 ? 'mark' : 'marks'}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-sky-100 text-sky-700">
                    {it.question_type}{it.language ? ` · ${it.language}` : ''}
                  </span>
                </div>
                <p className="text-slate-900 font-medium mb-4">{it.question_text}</p>

                <p className="text-xs font-semibold text-slate-500 mb-1">Student answer</p>
                <pre className="bg-slate-900 text-slate-100 text-sm rounded-lg p-4 overflow-x-auto whitespace-pre-wrap mb-4">
                  {it.answer_text || '(no answer submitted)'}
                </pre>

                {it.reference_answer && (
                  <details className="mb-4">
                    <summary className="text-xs font-semibold text-slate-500 cursor-pointer">
                      Model answer / rubric
                    </summary>
                    <pre className="bg-slate-50 text-slate-700 text-sm rounded-lg p-4 overflow-x-auto whitespace-pre-wrap mt-2">
                      {it.reference_answer}
                    </pre>
                  </details>
                )}

                <div className="flex items-center gap-3">
                  <label className="text-sm font-medium text-slate-700">Marks</label>
                  <input
                    type="number"
                    min={0}
                    max={it.max_marks}
                    step="0.5"
                    value={marks[it.response_id] ?? ''}
                    onChange={(e) =>
                      setMarks((m) => ({ ...m, [it.response_id]: e.target.value }))
                    }
                    className="input-field w-24"
                  />
                  <span className="text-sm text-slate-500">/ {it.max_marks}</span>
                </div>
              </div>
            ))}

            <div className="flex items-center justify-end gap-3">
              {saved && (
                <span className="text-sm text-emerald-600 flex items-center gap-1">
                  <CheckCircle className="w-4 h-4" /> Saved
                </span>
              )}
              <button onClick={handleSave} disabled={saving} className="btn-primary">
                {saving ? 'Saving...' : 'Save grades'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default GradeAttempt;
