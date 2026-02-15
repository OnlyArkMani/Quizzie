# 🚀 Quick Start Guide - Quizzie

## ✅ Error Status: FIXED ✓

The null reference error in `StudentDashboard.tsx` has been fixed!

---

## 🏃 Quick Start Commands

### Start Backend (Terminal 1)
```bash
cd C:\Projects\Quizzie\backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Start Frontend (Terminal 2)
```bash
cd C:\Projects\Quizzie\frontend
npm install
npm run dev
```

### Access Application
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

---

## 🔍 What Was Fixed?

### Original Error:
```
StudentDashboard.tsx:230 Uncaught TypeError: 
Cannot read properties of null (reading 'toFixed')
```

### Root Cause:
The code was calling `.toFixed()` on `attempt.score` which could be `null` when:
- Exam hasn't been evaluated yet
- Exam is in progress
- Backend returns incomplete data

### Fix Applied:
```typescript
// OLD CODE (Error):
{attempt.score.toFixed(0)}%

// NEW CODE (Fixed):
{attempt.score !== undefined && attempt.score !== null ? (
  attempt.score.toFixed(0) + '%'
) : (
  attempt.status === 'in_progress' ? 'In Progress' : 'Pending'
)}
```

Also fixed `stats.averageScore` to handle null values.

---

## 🔧 Pre-Flight Checklist

Before running, ensure:

- [ ] PostgreSQL is installed and running
- [ ] Node.js (v18+) is installed
- [ ] Python (3.10+) is installed
- [ ] `.env` files are configured:

**Backend `.env`** (C:\Projects\Quizzie\backend\.env):
```env
DATABASE_URL=postgresql://user:password@localhost/quizzie_db
SECRET_KEY=your-secret-key-here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

**Frontend `.env`** (C:\Projects\Quizzie\frontend\.env):
```env
VITE_API_URL=http://localhost:8000/api/v1
VITE_WS_URL=ws://localhost:8000/ws
```

---

## 🐛 If Backend Won't Start

### Check Database Connection
```bash
# Make sure PostgreSQL is running
# Windows: Check Services
# Or create database:
createdb quizzie_db
```

### Run Migrations
```bash
cd backend
alembic upgrade head
```

### Seed Initial Data (Optional)
```bash
python seed_data.py
```

---

## 🌐 If Frontend Shows Errors

### Clear Cache
```bash
cd frontend
rm -rf node_modules
npm install
```

### Check API Connection
1. Verify backend is running: http://localhost:8000/docs
2. Check browser console for network errors
3. Verify CORS settings in backend

---

## 📊 Test the Fix

1. Start both backend and frontend
2. Login as a student
3. Navigate to dashboard
4. Check "Recent Activity" section
5. You should see:
   - Scores for completed exams
   - "In Progress" for ongoing exams
   - "Pending" for submitted but not evaluated exams
   - No errors in console!

---

## 🎯 Next Development Tasks

Now that the app is running, you can:

1. **Add Features**:
   - Export results as PDF
   - Real-time exam timer
   - Question bookmarking
   - Exam review mode

2. **Improve UX**:
   - Add loading skeletons
   - Better error messages
   - Toast notifications
   - Confirm dialogs

3. **Security**:
   - Add rate limiting
   - Improve input validation
   - Add CSRF protection
   - Enhance proctoring

4. **Testing**:
   - Add unit tests
   - Integration tests
   - E2E tests with Cypress

---

## 📚 Documentation

Full documentation: `CODEBASE_GUIDE.md`

---

## ⚡ Pro Tips

1. **Keep both terminals open** - Backend and frontend need to run simultaneously
2. **Check logs** - Errors usually appear in terminal or browser console
3. **Use API docs** - http://localhost:8000/docs to test endpoints
4. **Hot reload works** - Changes auto-refresh (no need to restart)

---

## 🆘 Still Having Issues?

1. Check browser console (F12)
2. Check backend terminal logs
3. Verify .env files are correct
4. Ensure PostgreSQL is running
5. Try restarting both servers

---

Happy coding! 🎉
