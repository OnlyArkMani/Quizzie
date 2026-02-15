import { motion } from 'framer-motion';
import { ShieldAlert, Home } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/features/auth/store/authStore';

const Unauthorized = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  const handleGoHome = () => {
    if (user?.role === 'student') {
      navigate('/student');
    } else if (user?.role === 'examiner') {
      navigate('/examiner');
    } else {
      navigate('/');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-rose-50 via-white to-orange-50 flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <motion.div
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.2 }}
          className="w-24 h-24 bg-rose-100 rounded-full flex items-center justify-center mx-auto mb-8"
        >
          <ShieldAlert className="w-12 h-12 text-rose-600" />
        </motion.div>

        <h2 className="text-3xl font-bold text-slate-900 mb-4">Access Denied</h2>
        <p className="text-slate-600 mb-8 max-w-md mx-auto">
          You don't have permission to access this page. Please contact your administrator if you
          believe this is a mistake.
        </p>

        <motion.button
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          onClick={handleGoHome}
          className="btn-primary flex items-center gap-2 mx-auto"
        >
          <Home className="w-5 h-5" />
          Go to Dashboard
        </motion.button>
      </motion.div>
    </div>
  );
};

export default Unauthorized;