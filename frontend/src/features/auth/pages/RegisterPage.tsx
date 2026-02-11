import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { UserPlus, Mail, Lock, User, AlertCircle } from 'lucide-react';
import api from '@/lib/api';

const registerSchema = z.object({
  full_name: z.string().min(2, 'Name must be at least 2 characters'),
  email: z.string().email('Invalid email address'),
  password: z.string().min(6, 'Password must be at least 6 characters'),
  confirmPassword: z.string(),
  role: z.enum(['student', 'examiner']),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords don't match",
  path: ["confirmPassword"],
});

type RegisterFormData = z.infer<typeof registerSchema>;

const RegisterPage = () => {
  const navigate = useNavigate();
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { register, handleSubmit, formState: { errors } } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      role: 'student',
    },
  });

  const onSubmit = async (data: RegisterFormData) => {
    setIsLoading(true);
    setError('');

    try {
      await api.post('/auth/register', {
        full_name: data.full_name,
        email: data.email,
        password: data.password,
        role: data.role,
      });
      
      // Redirect to login
      navigate('/login', { 
        state: { message: 'Registration successful! Please log in.' } 
      });
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-600 mb-4">
            <UserPlus className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-3xl font-bold text-slate-900 mb-2">Create Account</h1>
          <p className="text-slate-600">Join Quizzie today</p>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="card p-8"
        >
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
            {error && (
              <div className="flex items-center gap-3 p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-700">
                <AlertCircle className="w-5 h-5 flex-shrink-0" />
                <p className="text-sm">{error}</p>
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Full Name
              </label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  {...register('full_name')}
                  className={`input-field pl-11 ${errors.full_name ? 'border-rose-500' : ''}`}
                  placeholder="John Doe"
                />
              </div>
              {errors.full_name && (
                <p className="mt-1 text-sm text-rose-600">{errors.full_name.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Email Address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  {...register('email')}
                  type="email"
                  className={`input-field pl-11 ${errors.email ? 'border-rose-500' : ''}`}
                  placeholder="you@example.com"
                />
              </div>
              {errors.email && (
                <p className="mt-1 text-sm text-rose-600">{errors.email.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                I am a
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="relative">
                  <input
                    {...register('role')}
                    type="radio"
                    value="student"
                    className="peer sr-only"
                  />
                  <div className="card p-4 cursor-pointer peer-checked:border-indigo-600 peer-checked:bg-indigo-50 transition">
                    <p className="font-medium text-center">Student</p>
                  </div>
                </label>
                <label className="relative">
                  <input
                    {...register('role')}
                    type="radio"
                    value="examiner"
                    className="peer sr-only"
                  />
                  <div className="card p-4 cursor-pointer peer-checked:border-indigo-600 peer-checked:bg-indigo-50 transition">
                    <p className="font-medium text-center">Examiner</p>
                  </div>
                </label>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  {...register('password')}
                  type="password"
                  className={`input-field pl-11 ${errors.password ? 'border-rose-500' : ''}`}
                  placeholder="••••••••"
                />
              </div>
              {errors.password && (
                <p className="mt-1 text-sm text-rose-600">{errors.password.message}</p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                <input
                  {...register('confirmPassword')}
                  type="password"
                  className={`input-field pl-11 ${errors.confirmPassword ? 'border-rose-500' : ''}`}
                  placeholder="••••••••"
                />
              </div>
              {errors.confirmPassword && (
                <p className="mt-1 text-sm text-rose-600">{errors.confirmPassword.message}</p>
              )}
            </div>

            <motion.button
              whileHover={{ scale: 1.01 }}
              whileTap={{ scale: 0.99 }}
              type="submit"
              disabled={isLoading}
              className="w-full btn-primary py-3 text-base"
            >
              {isLoading ? 'Creating Account...' : 'Create Account'}
            </motion.button>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-slate-600">
              Already have an account?{' '}
              <Link to="/login" className="text-indigo-600 font-medium hover:text-indigo-700">
                Sign in
              </Link>
            </p>
          </div>
        </motion.div>
      </motion.div>
    </div>
  );
};

export default RegisterPage;