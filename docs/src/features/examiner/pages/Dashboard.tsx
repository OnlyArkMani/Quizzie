import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  PlusCircle,
  FileText,
  Users,
  TrendingUp,
  Clock,
  BarChart3,
} from 'lucide-react';
import { useAuthStore } from '@/features/auth/store/authStore';
import api from '@/lib/api';
import { Exam } from '@/types';

const ExaminerDashboard = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const [exams, setExams] = useState<Exam[]>([]);
  const [stats, setStats] = useState({
    totalExams: 0,
    liveExams: 0,
    totalAttempts: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      const [examsRes, statsRes] = await Promise.all([
        api.get('/exams'),
        api.get('/analytics/examiner/stats'),
      ]);

      setExams(examsRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const badges = {
      draft: 'bg-slate-100 text-slate-700',
      live: 'bg-emerald-100 text-emerald-700',
      ended: 'bg-rose-100 text-rose-700',
    };
    return badges[status as keyof typeof badges] || badges.draft;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                Examiner Dashboard
              </h1>
              <p className="text-slate-600 mt-1">Manage exams and view analytics</p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => navigate('/examiner/exam/create')}
                className="btn-primary flex items-center gap-2"
              >
                <PlusCircle className="w-5 h-5" />
                Create Exam
              </button>
              <button onClick={logout} className="btn-secondary">
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="card p-6"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-indigo-100 flex items-center justify-center">
                <FileText className="w-6 h-6 text-indigo-600" />
              </div>
              <div>
                <p className="text-sm text-slate-600">Total Exams</p>
                <p className="text-2xl font-bold text-slate-900">{stats.totalExams}</p>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card p-6"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-emerald-100 flex items-center justify-center">
                <Clock className="w-6 h-6 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm text-slate-600">Live Exams</p>
                <p className="text-2xl font-bold text-slate-900">{stats.liveExams}</p>
              </div>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="card p-6"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-purple-100 flex items-center justify-center">
                <Users className="w-6 h-6 text-purple-600" />
              </div>
              <div>
                <p className="text-sm text-slate-600">Total Attempts</p>
                <p className="text-2xl font-bold text-slate-900">{stats.totalAttempts}</p>
              </div>
            </div>
          </motion.div>
        </div>

        {/* Recent Exams */}
        <div>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-slate-900">Your Exams</h2>
            <button
              onClick={() => navigate('/examiner/exams')}
              className="text-indigo-600 hover:text-indigo-700 font-medium text-sm"
            >
              View All
            </button>
          </div>

          {exams.length === 0 ? (
            <div className="card p-12 text-center">
              <FileText className="w-12 h-12 text-slate-300 mx-auto mb-4" />
              <p className="text-slate-600 mb-4">No exams created yet</p>
              <button
                onClick={() => navigate('/examiner/exam/create')}
                className="btn-primary inline-flex items-center gap-2"
              >
                <PlusCircle className="w-5 h-5" />
                Create Your First Exam
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {exams.slice(0, 6).map((exam, index) => (
                <motion.div
                  key={exam.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.1 }}
                  className="card p-6 hover:shadow-md transition-shadow cursor-pointer group"
                  onClick={() => navigate(`/examiner/exam/${exam.id}/analytics`)}
                >
                  <div className="flex items-start justify-between mb-4">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${getStatusBadge(exam.status)}`}>
                      {exam.status.charAt(0).toUpperCase() + exam.status.slice(1)}
                    </span>
                    <BarChart3 className="w-5 h-5 text-slate-400 group-hover:text-indigo-600 transition" />
                  </div>

                  <h3 className="font-semibold text-slate-900 mb-2 group-hover:text-indigo-600 transition">
                    {exam.title}
                  </h3>
                  <p className="text-sm text-slate-600 line-clamp-2 mb-4">
                    {exam.description}
                  </p>

                  <div className="flex items-center justify-between text-sm text-slate-600">
                    <span>{exam.duration_minutes} mins</span>
                    <span>{exam.total_marks} marks</span>
                  </div>
                </motion.div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ExaminerDashboard;