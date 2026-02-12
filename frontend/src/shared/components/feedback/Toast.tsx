import { motion, AnimatePresence } from 'framer-motion';
import { CheckCircle, XCircle, AlertCircle, X } from 'lucide-react';
import { create } from 'zustand';

interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'warning';
}

interface ToastStore {
  toasts: Toast[];
  addToast: (message: string, type: Toast['type']) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  addToast: (message, type) => {
    const id = Math.random().toString(36).substr(2, 9);
    set((state) => ({
      toasts: [...state.toasts, { id, message, type }],
    }));
    setTimeout(() => {
      set((state) => ({
        toasts: state.toasts.filter((t) => t.id !== id),
      }));
    }, 5000);
  },
  removeToast: (id) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },
}));

const ToastContainer = () => {
  const { toasts, removeToast } = useToastStore();

  const icons = {
    success: <CheckCircle className="w-5 h-5 text-emerald-600" />,
    error: <XCircle className="w-5 h-5 text-rose-600" />,
    warning: <AlertCircle className="w-5 h-5 text-amber-600" />,
  };

  const styles = {
    success: 'bg-emerald-50 border-emerald-200 text-emerald-900',
    error: 'bg-rose-50 border-rose-200 text-rose-900',
    warning: 'bg-amber-50 border-amber-200 text-amber-900',
  };

  return (
    <div className="fixed top-4 right-4 z-[100] space-y-2">
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, x: 100 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 100 }}
            className={`flex items-center gap-3 p-4 rounded-lg border shadow-lg ${styles[toast.type]} min-w-[300px]`}
          >
            {icons[toast.type]}
            <p className="flex-1 text-sm font-medium">{toast.message}</p>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-slate-500 hover:text-slate-700"
            >
              <X className="w-4 h-4" />
            </button>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
};

export default ToastContainer;