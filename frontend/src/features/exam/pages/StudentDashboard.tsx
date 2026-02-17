import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, Trophy, TrendingUp, ArrowRight, Clock, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';
import api from '@/lib/api';
import { useAuthStore } from '@/features/auth/store/authStore';

interface Exam {
  id: string;
  title: string;
  description: string;
  duration_minutes: number;
  total_marks: number;
  status: string;
}

interface Attempt {
  id: string;
  exam_id: string;
  exam_title: string;   // FIX Issue 3: backend now returns this
  started_at: string;
  submitted_at: string | null;
  score: number | null;
  status: string;
  cheating_flags: number;
}

interface Stats {
  totalExams: number;
  averageScore: number;
  examsTaken: number;
}

const StudentDashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const [availableExams, setAvailableExams] = useState<Exam[]>([]);
  const [recentAttempts, setRecentAttempts] = useState<Attempt[]>([]);
  const [stats, setStats] = useState<Stats>({ totalExams: 0, averageScore: 0, examsTaken: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [examsRes, attemptsRes, statsRes] = await Promise.allSettled([
        api.get('/exams/'),
        api.get('/attempts/my-attempts?limit=5'),
        api.get('/analytics/student/me/stats'),
      ]);

      // Handle exams
      if (examsRes.status === 'fulfilled') {
        setAvailableExams(examsRes.value.data || []);
      }

      // Handle attempts - FIX Issue 3: now includes exam_title
      if (attemptsRes.status === 'fulfilled') {
        setRecentAttempts(attemptsRes.value.data || []);
      }

      // Handle stats
      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value.data);
      }

    } catch (err: any) {
      console.error('Failed to fetch dashboard data:', err);
      setError('Failed to load dashboard data.');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const s = status.toLowerCase();
    if (s === 'evaluated') {
      return <span className="text-xs px-2 py-1 bg-emerald-100 text-emerald-700 rounded-full font-medium">Completed</span>;
    }
    if (s === 'in_progress') {
      return <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded-full font-medium">In Progress</span>;
    }
    if (s === 'submitted') {
      return <span className="text-xs px-2 py-1 bg-amber-100 text-amber-700 rounded-full font-medium">Submitted</span>;
    }
    return <span className="text-xs px-2 py-1 bg-slate-100 text-slate-600 rounded-full font-medium">{status}</span>;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 px-6 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Welcome back, {user?.full_name}!
          </h1>
          <p className="text-slate-500 text-sm mt-1">Track your progress and take exams</p>
        </div>
        <button
          onClick={() => {
            useAuthStore.getState().logout();
            navigate('/login');
          }}
          className="px-4 py-2 border border-slate-300 rounded-lg text-slate-600 hover:bg-slate-50 transition"
        >
          Logout
        </button>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-lg flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-rose-600" />
            <p className="text-rose-700">{error}</p>
            <button onClick={fetchDashboardData} className="ml-auto text-sm text-rose-600 underline">
              Retry
            </button>
          </div>
        )}

        {/* Stats Cards */}
        <div className="grid grid-cols-3 gap-6 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="bg-white rounded-xl border border-slate-200 p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-indigo-100 rounded-lg flex items-center justify-center">
                <BookOpen className="w-5 h-5 text-indigo-600" />
              </div>
              <span className="text-slate-500 text-sm">Total Exams</span>
            </div>
            {/* FIX Issue 2: Show available exams count from live exams */}
            <p className="text-3xl font-bold text-slate-900">{availableExams.length}</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="bg-white rounded-xl border border-slate-200 p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-emerald-100 rounded-lg flex items-center justify-center">
                <Trophy className="w-5 h-5 text-emerald-600" />
              </div>
              <span className="text-slate-500 text-sm">Average Score</span>
            </div>
            <p className="text-3xl font-bold text-slate-900">{stats.averageScore.toFixed(1)}%</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="bg-white rounded-xl border border-slate-200 p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 bg-purple-100 rounded-lg flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-purple-600" />
              </div>
              <span className="text-slate-500 text-sm">Exams Taken</span>
            </div>
            <p className="text-3xl font-bold text-slate-900">{stats.examsTaken}</p>
          </motion.div>
        </div>

        {/* Main Content */}
        <div className="grid grid-cols-3 gap-6">
          {/* Available Exams - takes 2 columns */}
          <div className="col-span-2">
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Available Exams</h2>

            {availableExams.length === 0 ? (
              <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
                <BookOpen className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <p className="text-slate-500">No exams available at the moment</p>
                <p className="text-slate-400 text-sm mt-1">Check back later for live exams</p>
              </div>
            ) : (
              <div className="space-y-3">
                {availableExams.map((exam, i) => (
                  <motion.div
                    key={exam.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="bg-white rounded-xl border border-slate-200 p-5 hover:border-indigo-300 hover:shadow-sm transition cursor-pointer group"
                    onClick={() => navigate(`/student/exam/${exam.id}`)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <h3 className="font-semibold text-slate-900 group-hover:text-indigo-600 transition">
                          {exam.title}
                        </h3>
                        {exam.description && (
                          <p className="text-sm text-slate-500 mt-1">{exam.description}</p>
                        )}
                        <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {exam.duration_minutes} minutes
                          </span>
                          <span>{exam.total_marks} marks</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs px-2 py-1 bg-emerald-100 text-emerald-700 rounded-full font-medium">
                          Live
                        </span>
                        <ArrowRight className="w-5 h-5 text-slate-400 group-hover:text-indigo-600 transition" />
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Activity */}
          <div>
            <h2 className="text-lg font-semibold text-slate-900 mb-4">Recent Activity</h2>

            {recentAttempts.length === 0 ? (
              <div className="bg-white rounded-xl border border-slate-200 p-8 text-center">
                <CheckCircle className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                <p className="text-slate-500 text-sm">No recent attempts</p>
              </div>
            ) : (
              <div className="space-y-3">
                {recentAttempts.map((attempt, i) => (
                  <motion.div
                    key={attempt.id}
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.05 }}
                    className="bg-white rounded-xl border border-slate-200 p-4 hover:border-indigo-200 transition cursor-pointer"
                    onClick={() => {
                      if (attempt.status === 'evaluated') {
                        navigate(`/student/exam/${attempt.exam_id}/results`, {
                          state: { attemptId: attempt.id }
                        });
                      }
                    }}
                  >
                    {/* FIX Issue 3: Show exam_title instead of UUID */}
                    <p className="font-medium text-slate-900 text-sm truncate">
                      {attempt.exam_title}
                    </p>
                    <p className="text-xs text-slate-400 mt-1">
                      {new Date(attempt.started_at).toLocaleDateString()}
                    </p>
                    <div className="flex items-center justify-between mt-2">
                      {getStatusBadge(attempt.status)}
                      {attempt.score !== null && (
                        <span className="text-sm font-semibold text-slate-700">
                          {attempt.score.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default StudentDashboard;