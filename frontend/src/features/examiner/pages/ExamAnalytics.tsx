import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Users, TrendingUp, Award, Download, AlertTriangle,
  ShieldAlert, Activity, RefreshCw, Heart
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
} from 'recharts';
import api from '@/lib/api';

const LiveFeed = ({ examId }: { examId: string }) => {
  const [feed, setFeed]             = useState<any>(null);
  const [loading, setLoading]       = useState(true);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  const fetchFeed = async () => {
    try {
      const res = await api.get(`/monitor/enhanced/exam/${examId}/live-feed`);
      setFeed(res.data);
    } catch {
      // exam might not be live yet
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFeed();
    const t = setInterval(() => { fetchFeed(); setLastRefresh(new Date()); }, 10_000);
    return () => clearInterval(t);
  }, [examId]);

  if (loading) return <div className="animate-pulse h-24 bg-slate-100 rounded-xl mb-8" />;

  if (!feed || feed.active_count === 0) return (
    <div className="card p-6 mb-8 flex items-center gap-3 text-slate-500">
      <Activity className="w-5 h-5" />
      <span className="text-sm">No students are currently taking this exam.</span>
    </div>
  );

  return (
    <div className="card p-6 mb-8">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <h2 className="text-lg font-bold text-slate-900">Live Proctoring Feed</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">Updated {lastRefresh.toLocaleTimeString()}</span>
          <button
            onClick={() => { setLoading(true); fetchFeed(); }}
            className="p-1.5 hover:bg-slate-100 rounded-lg transition"
          >
            <RefreshCw className="w-4 h-4 text-slate-500" />
          </button>
        </div>
      </div>

      {/* Summary pills */}
      <div className="flex gap-3 mb-5">
        <div className="flex items-center gap-2 bg-slate-50 rounded-lg px-4 py-2">
          <Users className="w-4 h-4 text-indigo-600" />
          <span className="text-sm font-semibold text-slate-900">{feed.active_count} active</span>
        </div>
        <div className="flex items-center gap-2 bg-rose-50 rounded-lg px-4 py-2">
          <ShieldAlert className="w-4 h-4 text-rose-600" />
          <span className="text-sm font-semibold text-rose-700">{feed.flagged_count} flagged</span>
        </div>
      </div>

      {/* Student rows */}
      <div className="space-y-2">
        {feed.students.map((s: any) => {
          const hpct = Math.round(s.health_percentage);
          const barColor = hpct > 70 ? 'bg-emerald-500' : hpct > 40 ? 'bg-amber-500' : 'bg-rose-500';
          return (
            <div key={s.attempt_id} className="flex items-center gap-4 p-3 rounded-lg bg-slate-50 hover:bg-slate-100 transition">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-900 truncate">{s.student_name}</p>
                <p className="text-xs text-slate-400 truncate">{s.student_email}</p>
              </div>
              <div className="w-28 flex-shrink-0">
                <div className="flex items-center justify-between mb-0.5">
                  <Heart className="w-3 h-3 text-slate-400" />
                  <span className="text-xs text-slate-500">{hpct}%</span>
                </div>
                <div className="w-full bg-slate-200 rounded-full h-1.5">
                  <div
                    className={`${barColor} h-1.5 rounded-full transition-all`}
                    style={{ width: `${hpct}%` }}
                  />
                </div>
              </div>
              <div className="w-16 text-center flex-shrink-0">
                <p className={`text-sm font-bold ${s.violation_count > 0 ? 'text-rose-600' : 'text-emerald-600'}`}>
                  {s.violation_count}
                </p>
                <p className="text-xs text-slate-400">flags</p>
              </div>
              <div className="w-36 flex-shrink-0">
                {s.last_flag ? (
                  <div className={`text-xs px-2 py-1 rounded-full truncate ${
                    s.last_flag.severity === 'high'   ? 'bg-rose-100 text-rose-700'   :
                    s.last_flag.severity === 'medium' ? 'bg-amber-100 text-amber-700' :
                                                        'bg-blue-100 text-blue-700'
                  }`}>
                    {s.last_flag.type.replace(/_/g, ' ')}
                  </div>
                ) : (
                  <span className="text-xs text-slate-400">no flags</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const ExamAnalytics = () => {
  const { examId } = useParams();
  const navigate   = useNavigate();
  const [analytics, setAnalytics] = useState<any>(null);
  const [loading, setLoading]     = useState(true);

  useEffect(() => { fetchAnalytics(); }, [examId]);

  const fetchAnalytics = async () => {
    try {
      const response = await api.get(`/analytics/exam/${examId}/summary`);
      setAnalytics(response.data);
    } catch (error) {
      console.error('Failed to fetch analytics:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = async () => {
    try {
      const response = await api.get(`/analytics/exam/${examId}/export`, { responseType: 'blob' });
      const url  = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href  = url;
      link.setAttribute('download', `exam_${examId}_results.csv`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      console.error('Export failed:', error);
    }
  };

  if (loading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  );

  if (!analytics) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <p className="text-slate-600">Analytics not available</p>
    </div>
  );

  const topicData         = Object.entries(analytics.topic_wise_stats || {}).map(([topic, stats]: any) => ({ topic, percentage: stats.percentage }));
  const scoreDistribution = analytics.score_distribution || [];

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <button onClick={() => navigate('/examiner')} className="text-sm text-slate-600 hover:text-slate-900 mb-2">
                &larr; Back to Dashboard
              </button>
              <h1 className="text-2xl font-bold text-slate-900">Exam Analytics</h1>
            </div>
            <button onClick={handleExportCSV} className="btn-secondary flex items-center gap-2">
              <Download className="w-5 h-5" /> Export CSV
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">

        {/* Live proctoring feed */}
        {examId && <LiveFeed examId={examId} />}

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="card p-6">
            <div className="flex items-center gap-3 mb-2">
              <Users className="w-5 h-5 text-indigo-600" />
              <p className="text-sm text-slate-600">Total Attempts</p>
            </div>
            <p className="text-3xl font-bold text-slate-900">{analytics.total_attempts}</p>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="card p-6">
            <div className="flex items-center gap-3 mb-2">
              <TrendingUp className="w-5 h-5 text-emerald-600" />
              <p className="text-sm text-slate-600">Average Score</p>
            </div>
            <p className="text-3xl font-bold text-slate-900">{analytics.average_score.toFixed(1)}%</p>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }} className="card p-6">
            <div className="flex items-center gap-3 mb-2">
              <Award className="w-5 h-5 text-amber-600" />
              <p className="text-sm text-slate-600">Highest Score</p>
            </div>
            <p className="text-3xl font-bold text-slate-900">{analytics.highest_score.toFixed(1)}%</p>
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="card p-6">
            <div className="flex items-center gap-3 mb-2">
              <AlertTriangle className="w-5 h-5 text-rose-600" />
              <p className="text-sm text-slate-600">Pass Rate</p>
            </div>
            <p className="text-3xl font-bold text-slate-900">{analytics.pass_percentage.toFixed(1)}%</p>
          </motion.div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="card p-8">
            <h2 className="text-xl font-bold text-slate-900 mb-6">Score Distribution</h2>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={scoreDistribution}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="range" tick={{ fill: '#64748b', fontSize: 12 }} />
                <YAxis tick={{ fill: '#64748b', fontSize: 12 }} />
                <Tooltip contentStyle={{ backgroundColor: '#fff', border: '1px solid #e2e8f0', borderRadius: '8px' }} />
                <Bar dataKey="count" fill="#4f46e5" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="card p-8">
            <h2 className="text-xl font-bold text-slate-900 mb-6">Topic-wise Accuracy</h2>
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={topicData}>
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="topic" tick={{ fill: '#64748b', fontSize: 12 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: '#64748b' }} />
                <Radar name="Accuracy" dataKey="percentage" stroke="#10b981" fill="#10b981" fillOpacity={0.6} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-8 mt-8">
          <h2 className="text-xl font-bold text-slate-900 mb-6">Top Performers</h2>
          <div className="space-y-3">
            {analytics.leaderboard?.slice(0, 10).map((entry: any, index: number) => (
              <div key={index} className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
                <div className="flex items-center gap-4">
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${
                    index === 0 ? 'bg-amber-100 text-amber-700'  :
                    index === 1 ? 'bg-slate-200 text-slate-700'  :
                    index === 2 ? 'bg-orange-100 text-orange-700' :
                                  'bg-slate-100 text-slate-600'
                  }`}>
                    {index + 1}
                  </div>
                  <p className="font-medium text-slate-900">{entry.student_name}</p>
                </div>
                <div className="flex items-center gap-6">
                  <span className="text-sm text-slate-600">
                    {Math.floor(entry.time_taken_seconds / 60)}m {entry.time_taken_seconds % 60}s
                  </span>
                  <span className="font-bold text-indigo-600">{entry.score.toFixed(1)}%</span>
                  {entry.attempt_id && (
                    <button
                      onClick={() => navigate(`/examiner/attempt/${entry.attempt_id}/grade`)}
                      className="text-sm font-medium text-indigo-600 hover:text-indigo-700"
                    >
                      Grade
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
};

export default ExamAnalytics;
