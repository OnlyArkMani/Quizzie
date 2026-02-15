import { useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Trophy,
  TrendingUp,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Home,
} from 'lucide-react';
import api from '@/lib/api';
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer } from 'recharts';

const ExamResults = () => {
  const { examId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const attemptId = location.state?.attemptId;

  const [results, setResults] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (attemptId) {
      fetchResults();
    }
  }, [attemptId]);

  const fetchResults = async () => {
    try {
      const response = await api.get(`/attempts/${attemptId}/results`);
      setResults(response.data);
    } catch (error) {
      console.error('Failed to fetch results:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!results) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <p className="text-slate-600">Results not found</p>
      </div>
    );
  }

  const isPassed = results.score >= results.pass_percentage;
  const topicData = Object.entries(results.topic_wise || {}).map(([topic, data]: any) => ({
    topic,
    percentage: data.percentage,
  }));

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 py-12 px-4">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center mb-8"
        >
          <div className={`inline-flex items-center justify-center w-20 h-20 rounded-full mb-4 ${
            isPassed ? 'bg-emerald-500' : 'bg-amber-500'
          }`}>
            <Trophy className="w-10 h-10 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-slate-900 mb-2">
            {isPassed ? 'Congratulations!' : 'Exam Completed'}
          </h1>
          <p className="text-slate-600">
            {isPassed ? 'You passed the exam!' : 'Keep practicing to improve your score'}
          </p>
        </motion.div>

        {/* Score Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="card p-8 mb-8"
        >
          <div className="text-center mb-8">
            <p className="text-sm text-slate-600 mb-2">Your Score</p>
            <div className="text-6xl font-bold bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-transparent">
              {results.score.toFixed(1)}%
            </div>
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
              <p className="text-xl font-bold text-slate-900">
                {results.total_questions - results.correct_count}
              </p>
            </div>

            <div className="text-center p-4 bg-slate-50 rounded-lg">
              <Clock className="w-6 h-6 text-indigo-600 mx-auto mb-2" />
              <p className="text-sm text-slate-600">Time Taken</p>
              <p className="text-xl font-bold text-slate-900">
                {Math.floor(results.time_taken_seconds / 60)}m
              </p>
            </div>
          </div>
        </motion.div>

        {/* Topic-wise Performance */}
        {topicData.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="card p-8 mb-8"
          >
            <h2 className="text-xl font-bold text-slate-900 mb-6">Topic-wise Performance</h2>
            
            <ResponsiveContainer width="100%" height={300}>
              <RadarChart data={topicData}>
                <PolarGrid stroke="#e2e8f0" />
                <PolarAngleAxis dataKey="topic" tick={{ fill: '#64748b', fontSize: 12 }} />
                <PolarRadiusAxis angle={90} domain={[0, 100]} tick={{ fill: '#64748b' }} />
                <Radar
                  name="Accuracy"
                  dataKey="percentage"
                  stroke="#4f46e5"
                  fill="#4f46e5"
                  fillOpacity={0.6}
                />
              </RadarChart>
            </ResponsiveContainer>

            <div className="mt-6 space-y-3">
              {Object.entries(results.topic_wise || {}).map(([topic, data]: any) => (
                <div key={topic} className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                  <span className="font-medium text-slate-900">{topic}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-slate-600">
                      {data.correct}/{data.total}
                    </span>
                    <span className="font-semibold text-indigo-600">
                      {data.percentage.toFixed(0)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </motion.div>
        )}

        {/* Cheating Flags (if any) */}
        {results.cheating_flags > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="card p-6 mb-8 border-amber-200 bg-amber-50"
          >
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="font-semibold text-amber-900 mb-1">Suspicious Activity Detected</h3>
                <p className="text-sm text-amber-700">
                  {results.cheating_flags} suspicious {results.cheating_flags === 1 ? 'behavior was' : 'behaviors were'} flagged during your exam. 
                  This may be reviewed by your examiner.
                </p>
              </div>
            </div>
          </motion.div>
        )}

        {/* Actions */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="flex gap-4"
        >
          <button
            onClick={() => navigate('/student')}
            className="flex-1 btn-primary py-3 flex items-center justify-center gap-2"
          >
            <Home className="w-5 h-5" />
            Back to Dashboard
          </button>
        </motion.div>
      </div>
    </div>
  );
};

export default ExamResults;