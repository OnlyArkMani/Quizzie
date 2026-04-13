import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Mail, AlertCircle, CheckCircle, ArrowLeft } from 'lucide-react';
import api from '@/lib/api';

const schema = z.object({
  email: z.string().email('Invalid email address'),
});
type FormData = z.infer<typeof schema>;

const ForgotPasswordPage = () => {
  const [sent, setSent]       = useState(false);
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    setError('');
    try {
      await api.post('/auth/forgot-password', { email: data.email });
      setSent(true);
    } catch {
      setError('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-8">
          <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-500 tracking-tight">
            Quizzie
          </h1>
          <p className="text-slate-500 font-medium mt-2">Reset your password</p>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="card p-8"
        >
          {sent ? (
            <div className="text-center space-y-5">
              <CheckCircle className="w-16 h-16 text-emerald-500 mx-auto" />
              <h2 className="text-xl font-bold text-slate-800">Check your inbox</h2>
              <p className="text-slate-500 text-sm">
                If that email is registered with Quizzie, we've sent a password-reset link.
                It expires in <strong>1 hour</strong>.
              </p>
              <Link to="/login" className="inline-flex items-center gap-1 text-indigo-600 font-medium hover:text-indigo-700 text-sm">
                <ArrowLeft className="w-4 h-4" /> Back to Login
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <p className="text-slate-600 text-sm">
                Enter the email address linked to your account and we'll send a reset link.
              </p>

              {error && (
                <div className="flex items-center gap-3 p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-700">
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  <p className="text-sm">{error}</p>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Email Address</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    {...register('email')}
                    type="email"
                    className={`input-field pl-11 ${errors.email ? 'border-rose-500' : ''}`}
                    placeholder="you@example.com"
                  />
                </div>
                {errors.email && <p className="mt-1 text-sm text-rose-600">{errors.email.message}</p>}
              </div>

              <motion.button
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
                type="submit"
                disabled={loading}
                className="w-full btn-primary py-3 text-base"
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Sending…
                  </span>
                ) : (
                  'Send Reset Link'
                )}
              </motion.button>

              <div className="text-center">
                <Link to="/login" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-indigo-600">
                  <ArrowLeft className="w-4 h-4" /> Back to Login
                </Link>
              </div>
            </form>
          )}
        </motion.div>
      </motion.div>
    </div>
  );
};

export default ForgotPasswordPage;
