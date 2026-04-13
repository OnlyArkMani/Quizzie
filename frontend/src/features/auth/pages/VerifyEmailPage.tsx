import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { CheckCircle, XCircle, Loader2, Mail } from 'lucide-react';
import api from '@/lib/api';

type Status = 'loading' | 'success' | 'error' | 'expired';

const VerifyEmailPage = () => {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';

  const [status, setStatus]   = useState<Status>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setMessage('No verification token found in the link. Please use the link from your email.');
      return;
    }

    api
      .get(`/auth/verify-email?token=${encodeURIComponent(token)}`)
      .then((res) => {
        setStatus('success');
        setMessage(res.data.message ?? 'Email verified successfully!');
      })
      .catch((err) => {
        const detail: string = err.response?.data?.detail ?? 'Verification failed.';
        if (detail.toLowerCase().includes('expired')) {
          setStatus('expired');
          setMessage(detail);
        } else if (
          detail.toLowerCase().includes('already been used') ||
          detail.toLowerCase().includes('already verified')
        ) {
          // Token was already consumed — account IS verified, treat as success
          setStatus('success');
          setMessage('Your email is already verified. You can log in now.');
        } else {
          setStatus('error');
          setMessage(detail);
        }
      });
  }, [token]);

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
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1 }}
          className="card p-10 text-center"
        >
          {/* Loading */}
          {status === 'loading' && (
            <div className="space-y-4">
              <Loader2 className="w-16 h-16 text-indigo-500 animate-spin mx-auto" />
              <p className="text-slate-600 text-lg font-medium">Verifying your email…</p>
            </div>
          )}

          {/* Success */}
          {status === 'success' && (
            <div className="space-y-5">
              <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: 'spring', stiffness: 200 }}>
                <CheckCircle className="w-20 h-20 text-emerald-500 mx-auto" />
              </motion.div>
              <h2 className="text-2xl font-bold text-slate-800">Email Verified!</h2>
              <p className="text-slate-500">{message}</p>
              <Link
                to="/login"
                className="inline-block mt-2 btn-primary px-8 py-3 text-base"
              >
                Go to Login
              </Link>
            </div>
          )}

          {/* Expired */}
          {status === 'expired' && (
            <div className="space-y-5">
              <Mail className="w-20 h-20 text-amber-400 mx-auto" />
              <h2 className="text-2xl font-bold text-slate-800">Link Expired</h2>
              <p className="text-slate-500">{message}</p>
              <Link
                to="/resend-verification"
                className="inline-block mt-2 btn-primary px-8 py-3 text-base"
              >
                Resend Verification Email
              </Link>
            </div>
          )}

          {/* Error */}
          {status === 'error' && (
            <div className="space-y-5">
              <XCircle className="w-20 h-20 text-rose-500 mx-auto" />
              <h2 className="text-2xl font-bold text-slate-800">Verification Failed</h2>
              <p className="text-slate-500">{message}</p>
              <Link
                to="/login"
                className="inline-block mt-2 text-indigo-600 font-medium hover:text-indigo-700"
              >
                Back to Login
              </Link>
            </div>
          )}
        </motion.div>
      </motion.div>
    </div>
  );
};

export default VerifyEmailPage;
