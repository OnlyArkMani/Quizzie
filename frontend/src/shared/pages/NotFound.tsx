import { motion } from 'framer-motion';
import { Home, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const NotFound = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <motion.div
          initial={{ scale: 0.8 }}
          animate={{ scale: 1 }}
          transition={{ delay: 0.2 }}
          className="mb-8"
        >
          <h1 className="text-9xl font-bold text-indigo-600">404</h1>
          <div className="h-2 w-32 bg-indigo-600 mx-auto mt-4 rounded-full" />
        </motion.div>

        <h2 className="text-3xl font-bold text-slate-900 mb-4">Page Not Found</h2>
        <p className="text-slate-600 mb-8 max-w-md mx-auto">
          The page you're looking for doesn't exist or has been moved.
        </p>

        <div className="flex items-center justify-center gap-4">
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => navigate(-1)}
            className="btn-secondary flex items-center gap-2"
          >
            <ArrowLeft className="w-5 h-5" />
            Go Back
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => navigate('/')}
            className="btn-primary flex items-center gap-2"
          >
            <Home className="w-5 h-5" />
            Home
          </motion.button>
        </div>
      </motion.div>
    </div>
  );
};

export default NotFound;