// src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useAuthStore } from './features/auth/store/authStore';
import { Suspense, lazy } from 'react';

// Lazy load pages
const LoginPage = lazy(() => import('./features/auth/pages/LoginPage'));
const RegisterPage = lazy(() => import('./features/auth/pages/RegisterPage'));

const StudentDashboard = lazy(() => import('./features/exam/pages/StudentDashboard'));
const ExamLobby = lazy(() => import('./features/exam/pages/ExamLobby'));
const TakeExam = lazy(() => import('./features/exam/pages/TakeExam'));
const ExamResults = lazy(() => import('./features/exam/pages/ExamResults'));

const ExaminerDashboard = lazy(() => import('./features/examiner/pages/Dashboard'));
const CreateExam = lazy(() => import('./features/examiner/pages/CreateExam'));
const ManageExams = lazy(() => import('./features/examiner/pages/ManageExams'));
const ExamAnalytics = lazy(() => import('./features/examiner/pages/ExamAnalytics'));

const NotFound = lazy(() => import('./shared/pages/NotFound'));
const Unauthorized = lazy(() => import('./shared/pages/Unauthorized'));

const ProtectedRoute = lazy(() => import('./features/auth/components/ProtectedRoute'));

// Loading spinner component
const PageLoader = () => (
  <div className="min-h-screen bg-slate-50 flex items-center justify-center">
    <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
  </div>
);

function App() {
  const { isAuthenticated, user } = useAuthStore();

  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public Routes */}
          <Route
            path="/login"
            element={
              isAuthenticated ? (
                <Navigate
                  to={user?.role === 'student' ? '/student' : '/examiner'}
                  replace
                />
              ) : (
                <LoginPage />
              )
            }
          />

          <Route path="/register" element={<RegisterPage />} />

          {/* Student Routes */}
          <Route
            path="/student"
            element={
              <ProtectedRoute allowedRoles={['student']}>
                <StudentDashboard />
              </ProtectedRoute>
            }
          />

          <Route
            path="/student/exam/:examId/lobby"
            element={
              <ProtectedRoute allowedRoles={['student']}>
                <ExamLobby />
              </ProtectedRoute>
            }
          />

          <Route
            path="/student/exam/:examId/take"
            element={
              <ProtectedRoute allowedRoles={['student']}>
                <TakeExam />
              </ProtectedRoute>
            }
          />

          <Route
            path="/student/exam/:examId/results"
            element={
              <ProtectedRoute allowedRoles={['student']}>
                <ExamResults />
              </ProtectedRoute>
            }
          />

          {/* Examiner Routes */}
          <Route
            path="/examiner"
            element={
              <ProtectedRoute allowedRoles={['examiner', 'admin']}>
                <ExaminerDashboard />
              </ProtectedRoute>
            }
          />

          <Route
            path="/examiner/exam/create"
            element={
              <ProtectedRoute allowedRoles={['examiner', 'admin']}>
                <CreateExam />
              </ProtectedRoute>
            }
          />

          <Route
            path="/examiner/exams"
            element={
              <ProtectedRoute allowedRoles={['examiner', 'admin']}>
                <ManageExams />
              </ProtectedRoute>
            }
          />

          <Route
            path="/examiner/exam/:examId/analytics"
            element={
              <ProtectedRoute allowedRoles={['examiner', 'admin']}>
                <ExamAnalytics />
              </ProtectedRoute>
            }
          />

          {/* Root Redirect */}
          <Route
            path="/"
            element={
              <Navigate
                to={
                  isAuthenticated
                    ? user?.role === 'student'
                      ? '/student'
                      : '/examiner'
                    : '/login'
                }
                replace
              />
            }
          />

          {/* Misc */}
          <Route path="/unauthorized" element={<Unauthorized />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
