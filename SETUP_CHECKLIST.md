# ✅ Quizzie Setup Checklist

Use this checklist to get your Quizzie app running:

## 📋 Pre-Flight Checklist

### System Requirements
- [ ] Node.js v18+ installed (`node --version`)
- [ ] Python 3.10+ installed (`python --version`)
- [ ] PostgreSQL installed and running
- [ ] Git installed (for version control)

### Database Setup
- [ ] PostgreSQL service is running
- [ ] Database created: `quizzie_db` (or as configured)
- [ ] Database user created with proper permissions
- [ ] Can connect to database using psql or pgAdmin

### Backend Configuration
- [ ] Navigate to `C:\Projects\Quizzie\backend`
- [ ] `.env` file exists (copy from `.env.example` if needed)
- [ ] DATABASE_URL configured correctly
- [ ] SECRET_KEY set (generate with: `openssl rand -hex 32`)
- [ ] Other environment variables configured

### Frontend Configuration
- [ ] Navigate to `C:\Projects\Quizzie\frontend`
- [ ] `.env` file exists with:
  - [ ] `VITE_API_URL=http://localhost:8000/api/v1`
  - [ ] `VITE_WS_URL=ws://localhost:8000/ws`

---

## 🚀 First Time Setup

### Backend (One-time setup)
```bash
cd C:\Projects\Quizzie\backend

# 1. Create virtual environment
python -m venv venv

# 2. Activate virtual environment
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run migrations
alembic upgrade head

# 5. (Optional) Seed sample data
python seed_data.py
```

### Frontend (One-time setup)
```bash
cd C:\Projects\Quizzie\frontend

# Install dependencies
npm install
```

---

## 🏃 Running the Application

### Every time you want to run the app:

#### Terminal 1 - Backend
```bash
cd C:\Projects\Quizzie\backend
venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

#### Terminal 2 - Frontend
```bash
cd C:\Projects\Quizzie\frontend
npm run dev
```

---

## 🔍 Verification Steps

After starting both servers, verify:

- [ ] Backend running: Open http://localhost:8000/docs
  - Should see FastAPI Swagger documentation
  
- [ ] Frontend running: Open http://localhost:5173
  - Should see Quizzie login page
  
- [ ] Backend logs show no errors
  
- [ ] Frontend logs show no errors
  
- [ ] Browser console (F12) shows no errors

---

## 🧪 Testing the Fix

To verify the null reference error is fixed:

1. [ ] Start both backend and frontend
2. [ ] Log in as a student
3. [ ] Navigate to student dashboard
4. [ ] Check "Recent Activity" section on the right
5. [ ] Verify you see either:
   - Score percentages (e.g., "85%") for evaluated exams
   - "In Progress" for ongoing exams
   - "Pending" for submitted but not evaluated exams
6. [ ] No errors in browser console
7. [ ] No "Cannot read properties of null" errors

---

## 📊 Sample Data (Optional)

If you ran `seed_data.py`, you should have:

### Sample Users
- **Admin**: admin@example.com / admin123
- **Examiner**: examiner@example.com / exam123
- **Student**: student@example.com / student123

(Check seed_data.py for actual credentials)

---

## 🐛 Troubleshooting

### Backend won't start
```bash
# Check if port 8000 is in use
netstat -ano | findstr :8000

# Kill process if needed
taskkill /PID <PID> /F

# Check PostgreSQL is running
# Services → PostgreSQL

# Verify .env file
type .env
```

### Frontend won't start
```bash
# Clear node_modules and reinstall
rm -rf node_modules package-lock.json
npm install

# Check if port 5173 is in use
netstat -ano | findstr :5173

# Clear browser cache and localStorage
# F12 → Application → Clear storage
```

### Database connection errors
```bash
# Test database connection
psql -U your_username -d quizzie_db

# If connection fails, check:
# - PostgreSQL is running
# - Database exists
# - Credentials in .env are correct
```

---

## 📁 Important Files

### Must Check These Files
- `backend/.env` - Backend configuration
- `frontend/.env` - Frontend configuration
- `backend/app/main.py` - Backend entry point
- `frontend/src/App.tsx` - Frontend entry point

### Recently Fixed
- ✅ `frontend/src/features/exam/pages/StudentDashboard.tsx`

---

## 📚 Documentation Files

Created for you:
- 📘 `FIX_SUMMARY.md` - What was fixed and why
- 📗 `START_GUIDE.md` - Quick start instructions
- 📕 `CODEBASE_GUIDE.md` - Complete codebase documentation
- 📋 `SETUP_CHECKLIST.md` - This file!

---

## 🎯 Next Steps After Setup

Once everything is running:

1. [ ] Explore the student dashboard
2. [ ] Try taking a sample exam
3. [ ] Check the examiner portal
4. [ ] Review the codebase structure
5. [ ] Plan your feature additions
6. [ ] Read the CODEBASE_GUIDE.md for architecture details

---

## ✅ Success Criteria

You know everything is working when:

- ✅ Backend API docs load at http://localhost:8000/docs
- ✅ Frontend loads at http://localhost:5173
- ✅ You can log in as a student
- ✅ Dashboard displays without errors
- ✅ Recent activity shows scores/status correctly
- ✅ No console errors in browser
- ✅ No errors in backend terminal

---

## 🆘 Still Stuck?

If you're still having issues:

1. Check the error message carefully
2. Look in browser console (F12)
3. Check backend terminal logs
4. Review the troubleshooting section above
5. Verify all checklist items are complete
6. Check FIX_SUMMARY.md for common issues

---

**Remember**: You need BOTH backend AND frontend running simultaneously!

Good luck! 🚀
