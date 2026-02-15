import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { 
  BookOpen, 
  Clock, 
  Trophy, 
  TrendingUp,
  ChevronRight,
  Calendar,
  Target
} from 'lucide-react';
import { useAuthStore } from '@/features/auth/store/authStore';
import api from '@/lib/api';
import { Exam, ExamAttempt } from '@/types';

const StudentDashboard = () => {
  const navigate = useNavigate();
  const { user, logout } = useAuthStore();
  const [availableExams, setAvailableExams] = useState<Exam[]>([]);
  const [recentAttempts, setRecentAttempts] = useState<ExamAttempt[]>([]);
  const [stats, setStats] = useState({
    totalExams: 0,
    averageScore: 0,
    examsTaken: 0,
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
  try {
    const [examsRes, attemptsRes, statsRes] = await Promise.all([
      api.get('/exams/?status=live'),  // Note the trailing slash
      api.get('/attempts/my-attempts?limit=5'),
      api.get('/analytics/student/me/stats'),
    ]);

    setAvailableExams(examsRes.data);
    setRecentAttempts(attemptsRes.data);
    setStats(statsRes.data);
  } catch (error) {
    console.error('Failed to fetch dashboard data:', error);
  } finally {
    setLoading(false);
  }
};

  const handleStartExam = (examId: string) => {
    navigate(`/student/exam/${examId}/lobby`);
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
                Welcome back, {user?.full_name}!
              </h1>
              <p className="text-slate-600 mt-1">Track your progress and take exams</p>
            </div>
            <button
              onClick={logout}
              className="btn-secondary"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            className="card p-6"
          >
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-indigo-100 flex items-center justify-center">
                <BookOpen className="w-6 h-6 text-indigo-600" />
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
                <Trophy className="w-6 h-6 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm text-slate-600">Average Score</p>
                <p className="text-2xl font-bold text-slate-900">
                  {stats.averageScore != null ? stats.averageScore.toFixed(1) : '0.0'}%
                </p>
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
                <TrendingUp className="w-6 h-6 text-purple-600" />
              </div>
              <div>
                <p className="text-sm text-slate-600">Exams Taken</p>
                <p className="text-2xl font-bold text-slate-900">{stats.examsTaken}</p>
              </div>
            </div>
          </motion.div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Available Exams */}
          <div className="lg:col-span-2">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-slate-900">Available Exams</h2>
            </div>

            {availableExams.length === 0 ? (
              <div className="card p-12 text-center">
                <Calendar className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <p className="text-slate-600">No exams available at the moment</p>
              </div>
            ) : (
              <div className="space-y-4">
                {availableExams.map((exam, index) => (
                  <motion.div
                    key={exam.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className="card p-6 hover:shadow-md transition-shadow cursor-pointer group"
                    onClick={() => handleStartExam(exam.id)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h3 className="text-lg font-semibold text-slate-900 group-hover:text-indigo-600 transition">
                          {exam.title}
                        </h3>
                        <p className="text-sm text-slate-600 mt-1 line-clamp-2">
                          {exam.description}
                        </p>
                        
                        <div className="flex items-center gap-6 mt-4">
                          <div className="flex items-center gap-2 text-sm text-slate-600">
                            <Clock className="w-4 h-4" />
                            <span>{exam.duration_minutes} minutes</span>
                          </div>
                          <div className="flex items-center gap-2 text-sm text-slate-600">
                            <Target className="w-4 h-4" />
                            <span>{exam.total_marks} marks</span>
                          </div>
                        </div>
                      </div>

                      <motion.div
                        whileHover={{ x: 5 }}
                        className="flex-shrink-0 ml-4"
                      >
                        <div className="w-10 h-10 rounded-lg bg-indigo-100 flex items-center justify-center group-hover:bg-indigo-600 transition">
                          <ChevronRight className="w-5 h-5 text-indigo-600 group-hover:text-white transition" />
                        </div>
                      </motion.div>
                    </div>
                  </motion.div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Activity */}
          <div>
            <h2 className="text-xl font-bold text-slate-900 mb-6">Recent Activity</h2>
            
            {recentAttempts.length === 0 ? (
              <div className="card p-8 text-center">
                <BookOpen className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                <p className="text-sm text-slate-600">No recent attempts</p>
              </div>
            ) : (
              <div className="space-y-3">
                {recentAttempts.map((attempt, index) => (
                  <motion.div
                    key={attempt.id}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className="card p-4"
                  >
                    <div className="flex items-center justify-between mb-2">
                      <p className="text-sm font-medium text-slate-900">
                        Exam #{attempt.exam_id.slice(0, 8)}
                      </p>
                      {attempt.score !== undefined && attempt.score !== null ? (
                        <span className={`text-sm font-semibold ${
                          attempt.score >= 70 ? 'text-emerald-600' : 
                          attempt.score >= 40 ? 'text-amber-600' : 
                          'text-rose-600'
                        }`}>
                          {attempt.score.toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500 bg-slate-100 px-2 py-1 rounded">
                          {attempt.status === 'in_progress' ? 'In Progress' : 'Pending'}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500">
                      {new Date(attempt.started_at).toLocaleDateString()}
                    </p>
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