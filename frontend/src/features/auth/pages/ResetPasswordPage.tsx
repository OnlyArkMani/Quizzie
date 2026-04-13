import { useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { Lock, AlertCircle, CheckCircle, Eye, EyeOff } from 'lucide-react';
import api from '@/lib/api';

const schema = z
  .object({
    new_password: z.string().min(8, 'Password must be at least 8 characters'),
    confirm:      z.string(),
  })
  .refine((d) => d.new_password === d.confirm, {
    message: "Passwords don't match",
    path: ['confirm'],
  });

type FormData = z.infer<typeof schema>;

const ResetPasswordPage = () => {
  const [searchParams] = useSearchParams();
  const navigate       = useNavigate();
  const token          = searchParams.get('token') ?? '';

  const [success, setSuccess]   = useState(false);
  const [error, setError]       = useState('');
  const [loading, setLoading]   = useState(false);
  const [showPwd, setShowPwd]   = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
  });

  if (!token) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
        <div className="card p-10 text-center max-w-md w-full space-y-4">
          <AlertCircle className="w-16 h-16 text-rose-500 mx-auto" />
          <h2 className="text-xl font-bold text-slate-800">Invalid Reset Link</h2>
          <p className="text-slate-500 text-sm">No token found. Please use the link from your email.</p>
          <Link to="/forgot-password" className="text-indigo-600 font-medium hover:text-indigo-700 text-sm">
            Request a new reset link
          </Link>
        </div>
      </div>
    );
  }

  const onSubmit = async (data: FormData) => {
    setLoading(true);
    setError('');
    try {
      await api.post('/auth/reset-password', { token, new_password: data.new_password });
      setSuccess(true);
      setTimeout(() => navigate('/login'), 3000);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? 'Something went wrong. The link may have expired.');
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
          <p className="text-slate-500 font-medium mt-2">Choose a new password</p>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="card p-8"
        >
          {success ? (
            <div className="text-center space-y-5">
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 200 }}>
                <CheckCircle className="w-20 h-20 text-emerald-500 mx-auto" />
              </motion.div>
              <h2 className="text-2xl font-bold text-slate-800">Password Updated!</h2>
              <p className="text-slate-500 text-sm">
                Your password has been reset. Redirecting to login…
              </p>
            </div>
          ) : (
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              {error && (
                <div className="flex items-center gap-3 p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-700">
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  <p className="text-sm">{error}</p>
                </div>
              )}

              {/* New Password */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">New Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    {...register('new_password')}
                    type={showPwd ? 'text' : 'password'}
                    className={`input-field pl-11 pr-11 ${errors.new_password ? 'border-rose-500' : ''}`}
                    placeholder="Min. 8 characters"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd(!showPwd)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                  >
                    {showPwd ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
                {errors.new_password && <p className="mt-1 text-sm text-rose-600">{errors.new_password.message}</p>}
              </div>

              {/* Confirm Password */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">Confirm Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input
                    {...register('confirm')}
                    type={showPwd ? 'text' : 'password'}
                    className={`input-field pl-11 ${errors.confirm ? 'border-rose-500' : ''}`}
                    placeholder="Repeat password"
                  />
                </div>
                {errors.confirm && <p className="mt-1 text-sm text-rose-600">{errors.confirm.message}</p>}
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
                    Resetting…
                  </span>
                ) : (
                  'Reset Password'
                )}
              </motion.button>
            </form>
          )}
        </motion.div>
      </motion.div>
    </div>
  );
};

export default ResetPasswordPage;
