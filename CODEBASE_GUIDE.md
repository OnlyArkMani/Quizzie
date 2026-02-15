# Quizzie - Quiz Application Codebase Guide

## 🔍 Project Overview

Quizzie is a full-stack quiz/exam application with:
- **Frontend**: React + TypeScript + Vite
- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL
- **Features**: 
  - Student exam taking with proctoring
  - Examiner exam creation and management
  - Real-time monitoring
  - Analytics and leaderboards

---

## 📁 Project Structure

```
Quizzie/
├── frontend/          # React TypeScript frontend
│   ├── src/
│   │   ├── features/  # Feature-based modules
│   │   │   ├── auth/  # Authentication
│   │   │   └── exam/  # Exam features
│   │   ├── lib/       # Utilities (API client)
│   │   ├── types/     # TypeScript types
│   │   └── App.tsx    # Main app component
│   ├── .env           # Environment variables
│   └── package.json   # Dependencies
│
└── backend/           # FastAPI Python backend
    ├── app/
    │   ├── api/       # API routes
    │   ├── models/    # Database models
    │   ├── schemas/   # Pydantic schemas
    │   └── services/  # Business logic
    ├── .env           # Environment variables
    └── requirements.txt
```

---

## 🐛 Error Fixed

### Issue: `Cannot read properties of null (reading 'toFixed')`

**Location**: `StudentDashboard.tsx:230`

**Root Cause**: 
- The `attempt.score` field can be `null` or `undefined` when:
  - Exam hasn't been evaluated yet
  - Exam is still in progress
  - Backend returns incomplete data

**Solution Applied**:
1. Added null checks: `attempt.score !== undefined && attempt.score !== null`
2. Added fallback UI showing status ("In Progress" or "Pending")
3. Fixed `stats.averageScore` to handle null values

**Code Changes**:
```typescript
// Before (causing error):
{attempt.score !== undefined && (
  <span>{attempt.score.toFixed(0)}%</span>
)}

// After (fixed):
{attempt.score !== undefined && attempt.score !== null ? (
  <span>{attempt.score.toFixed(0)}%</span>
) : (
  <span>{attempt.status === 'in_progress' ? 'In Progress' : 'Pending'}</span>
)}
```

---

## 🚀 How to Run the Application

### Prerequisites
- Node.js (v18+)
- Python (3.10+)
- PostgreSQL database

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up .env file (copy from .env.example)
# Configure DATABASE_URL, SECRET_KEY, etc.

# Run database migrations
alembic upgrade head

# Optional: Seed initial data
python seed_data.py

# Start backend server
uvicorn app.main:app --reload --port 8000
```

**Backend will run on**: `http://localhost:8000`

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Verify .env file exists with:
# VITE_API_URL=http://localhost:8000/api/v1
# VITE_WS_URL=ws://localhost:8000/ws

# Start development server
npm run dev
```

**Frontend will run on**: `http://localhost:5173`

---

## 🔑 Key Components

### Frontend

#### `StudentDashboard.tsx` (FIXED)
- Displays available exams
- Shows recent exam attempts
- Displays student statistics
- **Fixed**: Handles null scores properly

#### `api.ts`
- Axios instance for API calls
- JWT token management
- Request/response interceptors
- Base URL: `http://localhost:8000/api/v1`

#### Type Definitions (`types/index.ts`)
```typescript
interface ExamAttempt {
  id: string;
  exam_id: string;
  student_id: string;
  started_at: string;
  submitted_at?: string;
  score?: number;  // Can be null/undefined!
  status: 'in_progress' | 'submitted' | 'evaluated';
}
```

### Backend

#### Main Endpoints
- `/api/v1/exams/` - Exam management
- `/api/v1/attempts/` - Exam attempts
- `/api/v1/analytics/` - Statistics
- `/api/v1/auth/` - Authentication

---

## 🔧 Common Issues & Solutions

### Issue 1: Backend Not Starting
**Error**: `ModuleNotFoundError` or database connection errors

**Solution**:
1. Check virtual environment is activated
2. Verify all dependencies installed: `pip install -r requirements.txt`
3. Check PostgreSQL is running
4. Verify `.env` file has correct `DATABASE_URL`

### Issue 2: Frontend Can't Connect to Backend
**Error**: Network errors or CORS issues

**Solution**:
1. Ensure backend is running on port 8000
2. Check `frontend/.env` has correct `VITE_API_URL`
3. Verify CORS settings in `backend/app/main.py`

### Issue 3: Null/Undefined Errors (FIXED)
**Error**: `Cannot read properties of null`

**Solution**: 
- Always check for null/undefined before calling methods like `.toFixed()`
- Use optional chaining: `value?.toFixed()`
- Provide fallback values: `value ?? 0`

---

## 📊 Data Flow

### Student Taking Exam:
1. Student logs in → JWT token stored
2. Fetches available exams → `/api/v1/exams/?status=live`
3. Starts exam → Creates attempt → `/api/v1/attempts/`
4. Submits answers → Updates attempt
5. View results → `/api/v1/attempts/my-attempts`

### Dashboard Statistics:
1. Fetch exams, attempts, stats in parallel
2. Handle null values gracefully
3. Display with proper loading states

---

## 🛠️ Development Tips

### Debugging API Calls
```typescript
// In api.ts, check console for:
console.log('Request:', config);
console.log('Response:', response);
```

### Testing Backend
```bash
# Access API docs at:
http://localhost:8000/docs
```

### Hot Reload
- Frontend: Auto-reloads on file changes
- Backend: Use `--reload` flag with uvicorn

---

## 🎯 Next Steps / Features to Add

Based on your codebase, you could add:

1. **Error Boundaries** - Wrap components to catch React errors
2. **Retry Logic** - Retry failed API calls
3. **Offline Support** - Cache data with service workers
4. **Real-time Updates** - WebSocket for live exam updates
5. **Better Error Messages** - User-friendly error displays
6. **Loading Skeletons** - Better UX during data fetch
7. **Exam Timer** - Countdown timer during exams
8. **Question Navigation** - Jump to specific questions
9. **Review Mode** - Review answers before submission
10. **Export Results** - Download exam results as PDF

---

## 📝 TypeScript Types Reference

```typescript
// User roles
type UserRole = 'student' | 'examiner' | 'admin';

// Exam status
type ExamStatus = 'draft' | 'live' | 'ended';

// Attempt status
type AttemptStatus = 'in_progress' | 'submitted' | 'evaluated';

// Question types
type QuestionType = 'single' | 'multiple';

// Severity levels
type Severity = 'low' | 'medium' | 'high';
```

---

## 🔐 Authentication Flow

1. User logs in → `/api/v1/auth/login`
2. Backend returns JWT token
3. Token stored in `localStorage` (key: 'auth-storage')
4. Token sent in `Authorization` header for all requests
5. 401 response → Auto-logout and redirect to login

---

## 📧 Contact & Support

For issues or questions:
1. Check browser console for errors
2. Check backend logs for API errors
3. Verify database connections
4. Review this guide for common solutions

Good luck with your development! 🚀
