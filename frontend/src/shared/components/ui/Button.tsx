import React from 'react';
import { motion } from 'framer-motion';
import { Loader2 } from 'lucide-react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  children: React.ReactNode;
}

const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  children,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed';
  
  const variants = {
    primary: 'bg-indigo-600 text-white hover:bg-indigo-700 active:scale-95',
    secondary: 'bg-white text-slate-700 border-2 border-slate-300 hover:bg-slate-50 active:scale-95',
    danger: 'bg-rose-600 text-white hover:bg-rose-700 active:scale-95',
    ghost: 'text-slate-700 hover:bg-slate-100 active:scale-95',
  };
  
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2 text-base',
    lg: 'px-6 py-3 text-lg',
  };

  // FIX: Spreading React.ButtonHTMLAttributes directly onto motion.button causes a type
  // conflict between React's AnimationEventHandler<HTMLButtonElement> (for onAnimationStart)
  // and framer-motion's own AnimationDefinition-based onAnimationStart prop.
  // Solution: cast the native HTML props to `object` before spreading so TypeScript accepts
  // the merge. framer-motion's own motion props (whileHover, whileTap) are typed separately
  // and remain fully type-safe. Runtime behaviour is identical.
  const nativeProps = props as object;

  return (
    <motion.button
      whileHover={{ scale: disabled || isLoading ? 1 : 1.02 }}
      whileTap={{ scale: disabled || isLoading ? 1 : 0.98 }}
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || isLoading}
      {...nativeProps}
    >
      {isLoading && <Loader2 className="w-4 h-4 animate-spin" />}
      {children}
    </motion.button>
  );
};

export default Button;
