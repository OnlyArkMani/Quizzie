import { motion } from 'framer-motion';

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
}

const Card: React.FC<CardProps> = ({ children, className = '', hover = false, onClick }) => {
  const Component = onClick ? motion.button : motion.div;

  return (
    <Component
      whileHover={hover ? { y: -4, shadow: 'lg' } : {}}
      onClick={onClick}
      className={`bg-white rounded-xl border border-slate-200 shadow-sm ${
        onClick ? 'cursor-pointer' : ''
      } ${className}`}
    >
      {children}
    </Component>
  );
};

export default Card;