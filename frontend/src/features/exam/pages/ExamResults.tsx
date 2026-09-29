import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Trophy, TrendingUp, Clock, CheckCircle2, XCircle,
  AlertTriangle, Home, ShieldCheck, ShieldAlert, ShieldX,
} from 'lucide-react';
import api from '@/lib/api';
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer } from 'recharts';

const SuspicionBadge = ({ score, label }: { score: number; label: string }) => {
  const color =
    score < 15 ? 'bg-emerald-100 text-emerald-800 border-emerald-200' :
    score < 35 ? 'bg-amber-100  text-amber-800  border-amber-200'  :
    score < 60 ? 'bg-orange-100 text-orange-800 border-orange-200' :
                 'bg-rose-100   text-rose-800   border-rose-200';
  const Icon = score < 15 ? ShieldCheck : score < 60 ? ShieldAlert : ShieldX;
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-sm font-semibold ${color}`}>
      <Icon className="w-4 h-4" />
      Suspicion: {score}/100 — {label}
    </div>
  );
};

const ViolationHeatmap = ({ violations, durationSeconds }: { violations: any[]; durationSeconds: number }) => {
  if (!violations.length) return null;
  const SLOTS = 40;
  const slotDuration = durationSeconds / SLOTS;

  // Find exam start from earliest violation timestamp
  const timestamps = violations.map(v => new Date(v.timestamp).getTime());
  const examStart  = Math.min(...timestamps) - 30_000; // rough start = first violation minus 30 s

  const slots: { high: number; medium: number; low: number }[] = Array.from({ length: SLOTS }, () => ({ high: 0, medium: 0, low: 0 }));

  violations.forEach(v => {
    const elapsed = (new Date(v.timestamp).getTime() - examStart) / 1000;
    const idx = Math.min(SLOTS - 1, Math.max(0, Math.floor(elapsed / slotDuration)));
    const sev = (v.severity || '').toLowerCase().replace('cheatSeverity.', '');
    if (sev === 'high')   slots[idx].high   += 1;
    else if (sev === 'medium') slots[idx].medium += 1;
    else                  slots[idx].low    += 1;
  });

  return (
    <div>
      <div className="flex gap-0.5 items-end h-10">
        {slots.map((s, i) => {
          const total = s.high + s.medium + s.low;
          const bg = s.high > 0 ? 'bg-rose-500' : s.medium > 0 ? 'bg-amber-400' : s.low > 0 ? 'bg-blue-300' : 'bg-slate-100';
          const h  = total === 0 ? 'h-1' : total === 1 ? 'h-3' : total <= 3 ? 'h-6' : 'h-10';
          return <div key={i} className={`flex-1 rounded-sm ${bg} ${h} transition-all`} title={total ? `${total} violation(s)` : 'clean'} />;
        })}
      </div>
      <div className="flex justify-between text-xs text-slate-400 mt-1">
        <span>0:00</span>
        <span>{Math.floor(durationSeconds / 60)}:00</span>
      </div>
      <div className="flex items-center gap-4 mt-2 text-xs text-slate-500">
        <span className="flex items-center gap-1"><span className="w-3 h-3 bg-rose-500 rounded-sm inline-block"/> High</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 bg-amber-400 rounded-sm inline-block"/> Medium</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 bg-blue-300 rounded-sm inline-block"/> Low</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 bg-slate-100 rounded-sm inline-block"/> Clean</span>
      </div>
    </div>
  );
};

const ExamResults = () => {
  const { examId }  = useParams();
  const navigate    = useNavigate();
  const location    = useLocation();
  const attemptId   = location.state?.attemptId;

  const [results,    setResults]    = useState<any>(null);
  const [violations, setViolations] = useState<any[]>([]);
  const [suspicion,  setSuspicion]  = useState<any>(null);
  const [loading,    setLoading]    = useState(true);
  const [evaluating, setEvaluating] = useState(false);

  useEffect(() => { if (attemptId) fetchResults(); }, [attemptId]);

  // GET /results answers 202 {status: "evaluating"} while the queued evaluation
  // runs; poll with backoff instead of making the server evaluate on every hit.
  const fetchResultsWhenReady = async () => {
    let delay = 1000;
    for (let i = 0; i < 30; i++) {
      const res = await api.get(`/attempts/${attemptId}/results`);
      if (res.status !== 202 && res.data?.status !== 'evaluating') return res;
      setEvaluating(true);
      await new Promise(r => setTimeout(r, delay));
      delay = Math.min(delay * 1.5, 5000);
    }
    throw new Error('Evaluation is taking longer than expected');
  };

  const fetchResults = async () => {
    try {
      const [resultsRes, violationsRes, suspicionRes] = await Promise.allSettled([
        fetchResultsWhenReady(),
        api.get(`/monitor/enhanced/attempt/${attemptId}/violations`),
        api.get(`/monitor/enhanced/attempt/${attemptId}/suspicion-score`),
      ]);

      if (resultsRes.status === 'fulfilled') setResults(resultsRes.value.data);
      if (violationsRes.status === 'fulfilled') setViolations(violationsRes.value.data.timeline || []);
      if (suspicionRes.status === 'fulfilled') setSuspicion(suspicionRes.value.data);
    } catch (error) {
      console.error('Failed to fetch results:', error);
    } finally {
      setEvaluating(false);
      setLoading(false);
    }
  };

  if (loading) return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center justify-center gap-4">
      <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      {evaluating && <p className="text-slate-500 text-sm">Grading your answers…</p>}
    </div>
  );

  if (!results) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <p className="text-slate-600">Results not found</p>
    </div>
  );

  const isPassed  = results.score >= results.pass_percentage;
  const topicData = Object.entries(results.topic_wise || {}).map(([topic, data]: any) => ({ topic, percentage: data.percentage }));
  const examDurationSeconds = results.time_taken_seconds || 3600;

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">

        {/* Header */}
        <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
          <div className={`inline-flex items-center justify-center w-20 h-20 rounded-full mb-4 ${isPassed ? 'bg-emerald-500' : 'bg-amber-500'}`}>
            <Trophy className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-slate-900 mb-2">{isPassed ? 'Congratulations!' : 'Exam Completed'}</h1>
          <p className="text-slate-600">{isPassed ? 'You passed the exam!' : 'Keep practicing to improve your score'}</p>
          {suspicion && (
            <div className="mt-3">
              <SuspicionBadge score={suspicion.score} label={suspicion.label} />
            </div>
          )}
        </motion.div>

        {/* Score Card */}
        <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.1 }} className="card p-8 mb-8">
          <div className="text-center mb-8">
            <p className="text-sm text-slate-600 mb-2">Your Score</p>
            <div className="text-6xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">{results.score.toFixed(1)}%</div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <CheckCircle2 className="w-6 h-6 text-emerald-600 mx-auto mb-2" />
              <p className="text-sm text-slate-600">Correct</p>
              <p className="text-xl font-bold text-slate-900">{results.correct_count}</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <XCircle className="w-6 h-6 text-rose-600 mx-auto mb-2" />
              <p className="text-sm text-slate-600">Incorrect</p>
              <p className="text-xl font-bold text-slate-900">{results.total_questions - results.correct_count}</p>
            </div>
            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <Clock className="w-6 h-6 text-indigo-600 mx-auto mb-2" />
              <p className="text-sm text-slate-600">Time Taken</p>
              <p className="text-xl font-bold text-slate-900">{Math.floor(results.time_taken_seconds / 60)}m</p>
            </div>
          </div>
        </motion.div>

        {/* Topic-wise Performance */}
        {topicData.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card p-8 mb-8">
            <h2 className="text-xl font-bold text-slate-900 mb-6">Topic-wise Performance</h2>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={topicData}>
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="topic" tick={{ fill: '#64748b', fontSize: 12 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: '#64748b' }} />
                <Radar name="Accuracy" dataKey="percentage" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.6} />
              </RadarChart>
            </ResponsiveContainer>
            <div className="mt-6 space-y-3">
              {Object.entries(results.topic_wise || {}).map(([topic, data]: any) => (
                <div key={topic} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <span className="font-medium text-slate-900">{topic}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-600">{data.correct}/{data.total}</span>
                    <span className="font-semibold text-indigo-600">{data.percentage.toFixed(0)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Proctoring Report */}
        {results.cheating_flags > 0 && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="card p-6 mb-8 border-amber-200 bg-amber-50">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div className="w-full">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-semibold text-amber-900">Proctoring Report</h3>
                  {suspicion && <SuspicionBadge score={suspicion.score} label={suspicion.label} />}
                </div>
                <p className="text-sm text-amber-700 mb-4">
                  {results.cheating_flags} suspicious {results.cheating_flags === 1 ? 'event was' : 'events were'} detected during your exam.
                </p>

                {/* Suspicion score breakdown */}
                {suspicion?.breakdown && (
                  <div className="grid grid-cols-3 gap-3 mb-5">
                    {[
                      { label: 'Frequency', val: suspicion.breakdown.frequency_score, max: 60 },
                      { label: 'Clustering', val: suspicion.breakdown.clustering_score, max: 25 },
                      { label: 'Severity',   val: suspicion.breakdown.severity_score,   max: 15 },
                    ].map(({ label, val, max }) => (
                      <div key={label} className="bg-white rounded-lg p-3 border border-amber-200">
                        <p className="text-xs text-amber-600 mb-1">{label}</p>
                        <p className="text-lg font-bold text-amber-900">{val}<span className="text-xs font-normal text-amber-600">/{max}</span></p>
                        <div className="w-full bg-amber-100 rounded-full h-1.5 mt-1">
                          <div className="bg-amber-500 h-1.5 rounded-full" style={{ width: `${(val / max) * 100}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Violation heatmap timeline */}
                {violations.length > 0 && (
                  <div className="mb-5">
                    <p className="text-xs font-semibold text-amber-800 mb-2">Violation timeline</p>
                    <ViolationHeatmap violations={violations} durationSeconds={examDurationSeconds} />
                  </div>
                )}

                {/* Violation list */}
                {violations.length > 0 && (
                  <div className="space-y-2 max-h-60 overflow-y-auto pr-2 custom-scrollbar">
                    {violations.map((v: any, index: number) => (
                      <div key={v.id || index} className="text-sm text-amber-800 bg-amber-100/50 p-2 rounded flex justify-between items-center">
                        <div>
                          <span className={`uppercase text-xs font-bold mr-2 ${
                            (v.severity || '').toLowerCase().includes('high') ? 'text-rose-600' :
                            (v.severity || '').toLowerCase().includes('medium') ? 'text-amber-600' : 'text-blue-600'
                          }`}>[{(v.severity || 'low').split('.').pop()}]</span>
                          <span className="capitalize">{v.metadata?.message || v.type?.replace(/_/g, ' ')}</span>
                        </div>
                        <span className="font-medium opacity-60 ml-4 whitespace-nowrap">{new Date(v.timestamp).toLocaleTimeString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {/* Actions */}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="flex gap-4">
          <button onClick={() => navigate('/student')} className="flex-1 btn-primary py-3 flex items-center justify-center gap-2">
            <Home className="w-5 h-5" /> Back to Dashboard
          </button>
        </motion.div>
      </div>
    </div>
  );
};

export default ExamResults;
