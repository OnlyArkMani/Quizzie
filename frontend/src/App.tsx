// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './features/auth/store/authStore';

// Auth Pages
import LoginPage from './features/auth/pages/LoginPage';
import RegisterPage from './features/auth/pages/RegisterPage';

// Student Pages
import StudentDashboard from './features/exam/pages/StudentDashboard';
import ExamLobby from './features/exam/pages/ExamLobby';
import TakeExam from './features/exam/pages/TakeExam';
import ExamResults from './features/exam/pages/ExamResults';

// Examiner Pages
import ExaminerDashboard from './features/examiner/pages/Dashboard';
import CreateExam from './features/examiner/pages/CreateExam';
import ExamAnalytics from './features/examiner/pages/ExamAnalytics';

// Shared
import NotFound from './shared/pages/NotFound';
import Unauthorized from './shared/pages/Unauthorized';

// Route Guards
interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles: Array<'student' | 'examiner' | 'admin'>;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ 
  children, 
  allowedRoles 
}) => {
  const { isAuthenticated, user } = useAuthStore();
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  
  if (user && !allowedRoles.includes(user.role)) {
    return <Navigate to="/unauthorized" replace />;
  }
  
  return <>{children}</>;
};

function App() {
  const { isAuthenticated, user } = useAuthStore();
  
  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route 
          path="/login" 
          element={
            isAuthenticated ? (
              <Navigate to={user?.role === 'student' ? '/student' : '/examiner'} />
            ) : (
              <LoginPage />
            )
          } 
        />
        <Route path="/register" element={<RegisterPage />} />
        
        {/* Student Routes */}
        <Route path="/student" element={
          <ProtectedRoute allowedRoles={['student']}>
            <StudentDashboard />
          </ProtectedRoute>
        } />
        <Route path="/student/exam/:examId/lobby" element={
          <ProtectedRoute allowedRoles={['student']}>
            <ExamLobby />
          </ProtectedRoute>
        } />
        <Route path="/student/exam/:examId/take" element={
          <ProtectedRoute allowedRoles={['student']}>
            <TakeExam />
          </ProtectedRoute>
        } />
        <Route path="/student/exam/:examId/results" element={
          <ProtectedRoute allowedRoles={['student']}>
            <ExamResults />
          </ProtectedRoute>
        } />
        
        {/* Examiner Routes */}
        <Route path="/examiner" element={
          <ProtectedRoute allowedRoles={['examiner', 'admin']}>
            <ExaminerDashboard />
          </ProtectedRoute>
        } />
        <Route path="/examiner/exam/create" element={
          <ProtectedRoute allowedRoles={['examiner', 'admin']}>
            <CreateExam />
          </ProtectedRoute>
        } />
        <Route path="/examiner/exam/:examId/analytics" element={
          <ProtectedRoute allowedRoles={['examiner', 'admin']}>
            <ExamAnalytics />
          </ProtectedRoute>
        } />
        
        {/* Fallback */}
        <Route path="/" element={
          <Navigate to={
            isAuthenticated 
              ? (user?.role === 'student' ? '/student' : '/examiner')
              : '/login'
          } />
        } />
        <Route path="/unauthorized" element={<Unauthorized />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;