#  Quizzie — AI-Powered Online Examination Platform

<div align="center">

![Quizzie Logo](https://img.shields.io/badge/Quizzie-AI%20Proctoring-6366f1?style=for-the-badge&logo=react&logoColor=white)

**A production-grade online examination platform with intelligent AI proctoring, async background processing, Redis caching, Celery workers, and comprehensive analytics — engineered to support 500+ concurrent students.**

[![React](https://img.shields.io/badge/React-18-61DAFB?style=flat-square&logo=react&logoColor=black)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-5.3-37814A?style=flat-square&logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

[![GitHub stars](https://img.shields.io/github/stars/OnlyArkMani/Quizzie?style=social)](https://github.com/OnlyArkMani/Quizzie)
[![GitHub forks](https://img.shields.io/github/forks/OnlyArkMani/Quizzie?style=social)](https://github.com/OnlyArkMani/Quizzie)
[![GitHub last commit](https://img.shields.io/github/last-commit/OnlyArkMani/Quizzie)](https://github.com/OnlyArkMani/Quizzie)

[Live Demo](#) • [API Docs](#-api-documentation) • [Report Bug](https://github.com/OnlyArkMani/Quizzie/issues) • [Request Feature](https://github.com/OnlyArkMani/Quizzie/issues)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Key Features](#key-features)
- [Technology Stack](#technology-stack)
- [System Architecture](#system-architecture)
- [Scalability Design](#scalability-design)
- [Installation](#installation)
- [Usage Guide](#usage-guide)
- [API Documentation](#api-documentation)
- [AI Proctoring System](#ai-proctoring-system)
- [CI/CD Pipeline](#cicd-pipeline)
- [Project Structure](#project-structure)
- [Performance](#performance)
- [Deployment Alternatives](#deployment-alternatives)
- [Future Enhancements](#future-enhancements)
- [Contributing](#contributing)
- [Team](#team)
- [License](#license)

---

## Overview

**Quizzie** is a full-stack, production-grade online examination platform built to handle real-world academic scale. It combines a FastAPI backend, a React + TypeScript frontend, AI-powered proctoring, async Celery workers, Redis caching, and a fully automated CI/CD pipeline — all containerised and deployable with a single command.

### Project Context

- **Institution:** Manipal University Jaipur
- **Course:** Problem Based Learning (PBL)
- **Duration:** January 2026 – February 2026
- **Department:** Computer Science & Engineering
- **Scale target:** 500+ concurrent students with live AI proctoring

---

## Problem Statement

Traditional online examinations face several critical challenges:

1. **No effective proctoring at scale** — remote exams are vulnerable to malpractice and human invigilators cannot scale
2. **Synchronous AI processing blocks the API** — frame-by-frame analysis on the web server saturates CPU under concurrent load
3. **Database bottlenecks** — N+1 query patterns and missing indexes cause latency spikes as student count grows
4. **No caching layer** — every student fetching the same exam questions triggers redundant DB queries
5. **Delayed results** — synchronous evaluation blocks student response for multi-second periods
6. **No test coverage or CI/CD** — no automated gating before code reaches production

### Our Solution

Quizzie solves each of these at the architectural level:

- **Celery + Redis broker** decouples AI proctoring from the web process — frame uploads return in under 15ms regardless of MediaPipe processing time
- **Redis cache layer** with 5-minute TTL serves all 500 concurrent question fetches from a single DB query, cutting peak database load by 90%
- **Async evaluation** dispatched to a dedicated Celery queue — exam submission returns instantly, scoring happens in the background
- **SQLAlchemy `joinedload` and aggregate SQL** eliminate N+1 patterns, with 11 targeted indexes reducing query latency by 85%
- **GitHub Actions CI/CD** runs 30+ pytest cases against a real PostgreSQL + Redis stack before any deploy reaches production
- **5-service Docker Compose** (API, 2 Celery workers, Redis, PostgreSQL) with a `render.yaml` blueprint for zero-downtime rolling deploys

---

## Key Features

### Authentication and Security

- JWT-based authentication with configurable token expiry (default 120 minutes — safe for long exams)
- Email verification on registration — tokens delivered via SMTP, printed to console in dev mode
- Forgot/reset password via time-limited (1 hour) email links
- Resend verification endpoint with rate limiting (3 requests/minute via `slowapi`)
- Login rate limited to 20 requests/minute; registration to 10 requests/minute
- Bcrypt password hashing for all stored credentials
- Role-based access control — `student` and `examiner` roles enforced on every endpoint via FastAPI dependencies
- Demo accounts (`student@demo.com` / `examiner@demo.com`) bypass email verification for instant testing
- CORS configuration and SQL injection prevention via SQLAlchemy ORM
- Input validation using Pydantic v2 schemas throughout

### Async AI Proctoring (Celery-backed)

Quizzie ships a multi-layered AI proctoring engine built on MediaPipe and OpenCV. All AI processing runs inside dedicated Celery worker processes — the FastAPI web process never imports MediaPipe, keeping API memory lean and response times fast regardless of proctoring load.

#### Face Detection and Mesh Analysis
- Real-time face detection via MediaPipe FaceDetection
- Multiple person detection — flags when more than one face appears in frame (severity: `high`)
- No-face detection — ensures continuous student presence (severity: `high`)
- Head pose estimation — nose-to-eye-center deviation check for looking-away detection
- Advanced 3D head pose via PnP algorithm (pitch, yaw, roll in degrees) using 6-point facial landmark model
- Eye gaze and iris tracking using MediaPipe refined landmarks (iris indices 468 and 473) — detects gaze left/right off-screen
- Mouth movement detection — lip-gap-to-mouth-width ratio to catch whispering or talking
- Face tracking loss detection when mesh fails but a face is still present

#### Audio Analysis
- RMS energy computation on normalised float32 audio samples
- Loud noise detection with configurable threshold (default 0.08 RMS)
- Dual-decoder support: SoundFile (WAV/FLAC/OGG) with Librosa fallback (WebM/Opus via FFmpeg)
- Audio tasks enqueued to the proctoring Celery queue — non-blocking to the API

#### Health System
- Every student starts with a configurable health score (default 100)
- Each proctoring violation deducts health points based on type and severity:

| Violation Type | Base Penalty | Severity |
|---|---|---|
| `multiple_faces_detected` | 15 pts | High |
| `tab_switch` | 5–12 pts | Medium–High |
| `fullscreen_exit` | 10 pts | High |
| `no_face_detected` | 10 pts | High |
| `looking_away` | 5 pts | Medium |
| `gaze_off_screen` | 5 pts | Medium |
| `mouth_movement_detected` | 4 pts | Medium |
| `suspicious_audio` | 3 pts | Low–Medium |

- Health recovery — after 60 seconds of clean behaviour, health is partially restored
- Warning threshold — alert fired at configurable health % (default 40%)
- Auto-submit on zero health — exam submitted automatically when health reaches 0
- Health status levels: `good` (>70%) → `warning` (>40%) → `critical` (>0%) → `failed` (0%)

#### Real-Time WebSocket Proctoring
- WebSocket endpoint `/ws/proctoring/{attempt_id}` pushes live health updates to the frontend
- Sends `health_update` and `violation_alert` message types in real time
- ConnectionManager tracks all active exam sessions
- Frontend HealthBar component reflects live health changes instantly
- Initial health reconstructed from existing violation log on reconnect

#### Suspicion Score Engine
A 0–100 suspicion scoring system combining three factors:
1. Weighted frequency score (0–60) — flags weighted by type severity and occurrence count
2. Clustering score (0–25) — violations within 30-second windows scored higher
3. High-severity ratio (0–15) — proportion of `high` severity flags
- Labels: `Clean` → `Low suspicion` → `Moderate suspicion` → `High suspicion` → `Very high suspicion`

#### Live Proctoring Feed (Examiner View)
- `/monitor/enhanced/exam/{exam_id}/live-feed` returns all active attempts in real time
- Shows: student name, health %, health status, violation count, last flag with timestamp
- Sorted by violation count — most flagged students appear first
- `flagged_count` summary at the top for quick triage

#### Multi-Monitor Detection
- Detects unusually wide screens (aspect ratio > 2.5 or width > 3000px) at exam start
- Flags as `multi_monitor_detected` with medium severity

#### Per-Exam Proctoring Settings
Each exam has independently configurable proctoring via the `proctoring_settings` table:
- Toggle: camera, microphone, face detection, multiple-face detection, head-pose detection, tab-switch detection
- Tune: `min_face_confidence`, `max_head_rotation`, `detection_interval`
- Set: `initial_health`, `health_warning_threshold`, `auto_submit_on_zero_health`

### Redis Caching Layer

- Async Redis client (`redis.asyncio`) connected at startup with graceful degradation — app continues without Redis if unavailable
- Centralised key builders prevent typos across the codebase
- Cache-aside strategy: check Redis → DB query on miss → store in Redis → return

| Cache Key | TTL | Content |
|---|---|---|
| `exam:{id}:questions` | 5 min | Full question list — invalidated on exam update |
| `exam:{id}:meta` | 1 min | Exam status and configuration |
| `exam:{id}:leaderboard` | 30 sec | Top-10 leaderboard — invalidated on new submission |
| `ratelimit:{endpoint}:{ip}` | 60 sec | Rate limit counters (atomic INCR pipeline) |
| `attempt:{id}:health` | Session | Per-attempt health state |

- Eviction policy: `allkeys-lru` — Redis automatically evicts least-recently-used keys under memory pressure

### Celery Worker Architecture

Two named queues handle different task types independently:

**Proctoring queue** (`-Q proctoring`, 4 concurrent workers):
- `analyze_frame_task` — decodes base64 frame, runs MediaPipe, persists flags to DB
- `analyze_audio_task` — decodes base64 audio, runs RMS analysis, persists flags to DB
- MediaPipe and OpenCV loaded once per worker process on startup — not per request

**Evaluation queue** (`-Q evaluation`, 2 concurrent workers):
- `evaluate_attempt_task` — loads all responses + questions in a single joinedload query, computes scores, updates attempt status to `evaluated`

Worker configuration:
- `task_acks_late=True` — task requeued if a worker crashes mid-execution
- `task_reject_on_worker_lost=True` — prevents silent task loss on unexpected worker exit
- `worker_prefetch_multiplier=1` — one CPU-bound task per worker at a time, prevents queue starvation
- `task_soft_time_limit=30` / `task_time_limit=45` — prevents runaway MediaPipe processes

### Student Features

- Animated dashboard showing available live exams, personal statistics, and recent attempt history
- Exam lobby with instructions, proctoring requirements, and camera permission flow
- Fullscreen-enforced exam interface with live countdown and fullscreen-exit detection
- Auto-save every 10 seconds to prevent data loss on connection drop
- Question palette with status indicators: answered, unanswered, marked for review
- Mark-for-review functionality for revisiting questions
- In-progress attempt resume — returning within 24 hours resumes the same attempt automatically
- Live health bar updated in real time via WebSocket
- Exam pause overlay on critical proctoring violations
- Auto-submit on timer expiry or health reaching zero
- Instant results: score, marks breakdown, topic-wise performance, time taken, cheating flag count

### Examiner Features

- 3-step exam creation wizard: details → questions → review and publish
- Question bank with single and multiple-choice question types and topic tagging
- Exam status management: `draft` → `live` → `ended`
- Total marks auto-calculated from question marks when publishing
- Real-time monitoring dashboard: all active students sorted by violation count
- Live feed showing health %, violation count, and last flag per student
- Analytics dashboard: score distribution charts, topic-wise breakdowns, pass/fail rates
- Leaderboard ranked by score and time taken
- CSV export of all evaluated results (name, email, score, marks, time, flags, pass/fail)
- Per-exam proctoring settings configuration
- Suspicion score per attempt for post-exam review

### Analytics and Reporting

- Score distribution across four bands (0–40, 40–60, 60–80, 80–100) via aggregate SQL — no Python loops
- Topic-wise performance breakdown with correct/total/percentage — single JOIN query
- Per-student stats: exams taken, average score
- Per-examiner stats: total exams, live exams, total attempt count
- Suspicion score per attempt for post-exam review
- Full violation timeline with metadata per attempt
- CSV export via StreamingResponse — memory-efficient for large result sets

### Database Engineering

- 11 targeted performance indexes on the columns queried most under concurrent load: `exam_id`, `student_id`, `status`, `attempt_id`, `question_id`, `display_order`
- Connection pool configured: `pool_size=10`, `max_overflow=20`, `pool_timeout=30`, `pool_recycle=1800`
- N+1 queries eliminated in evaluation service (4,100+ round-trips reduced to 3 queries using `joinedload`)
- Alembic migrations with three versioned scripts including the performance index migration

---

## Technology Stack

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| React | 18.2.0 | UI framework |
| TypeScript | 5.0.2 | Type safety |
| Vite | 5.4.21 | Build tool |
| Tailwind CSS | 3.4.1 | Styling |
| Framer Motion | 11.0.3 | Animations |
| Zustand | 4.4.7 | State management |
| React Router | 6.21.0 | Routing |
| Recharts | 2.10.3 | Data visualisation |
| React Hook Form | 7.49.2 | Form handling |
| Zod | 3.22.4 | Schema validation |
| Axios | 1.6.2 | HTTP client |
| Lucide React | 0.263.1 | Icons |

### Backend

| Technology | Version | Purpose |
|---|---|---|
| Python | 3.11 | Runtime |
| FastAPI | 0.104.1 | Web framework + WebSocket support |
| Uvicorn | 0.24.0 | ASGI server (workers configurable via `WORKERS` env var) |
| PostgreSQL | 15 | Primary database |
| SQLAlchemy | 2.0.23 | ORM with joinedload and aggregate queries |
| Alembic | 1.12.1 | Database migrations |
| Pydantic | 2.5.0 | Data validation |
| python-jose | 3.3.0 | JWT handling |
| Passlib + Bcrypt | 1.7.4 | Password hashing |
| slowapi | 0.1.9 | Rate limiting |
| Celery | 5.3.4 | Async task queue |
| Redis (redis-py) | 5.0.1 | Cache + Celery broker/backend |
| hiredis | 2.2.3 | High-performance Redis parser |

### AI and ML Libraries

| Technology | Version | Purpose |
|---|---|---|
| MediaPipe | 0.10.9 | Face detection, face mesh, iris landmarks |
| OpenCV | 4.8.1.78 | Image processing, PnP head pose |
| NumPy | 1.26.2 | Numerical computing for audio and image data |
| SoundFile | 0.12.1 | Primary audio decoder (WAV/FLAC/OGG) |
| Librosa | 0.10.1 | Fallback audio decoder (WebM/Opus via FFmpeg) |

### Infrastructure and DevOps

| Technology | Purpose |
|---|---|
| Docker + Docker Compose | 5-service stack: PostgreSQL, Redis, FastAPI, Celery proctoring worker, Celery evaluation worker, Nginx frontend |
| Nginx | Frontend SPA serving + `/api` reverse proxy + WebSocket passthrough |
| GitHub Actions | CI/CD pipeline: pytest + frontend build gate before every deploy |
| Render.com Blueprint | `render.yaml` for one-click multi-service cloud deployment |
| Alembic | Versioned database schema migrations |

### Testing

| Technology | Purpose |
|---|---|
| pytest | Backend test runner |
| pytest-asyncio | Async test support |
| pytest-cov | Coverage reporting (XML + terminal) |
| httpx | Async HTTP client for TestClient |
| factory-boy | Test fixture factories |

---

## System Architecture

```
Browser / Student
      |
      | HTTP REST + WebSocket
      v
Load Balancer (Nginx / ALB)
      |
      +---> FastAPI #1 (5 Uvicorn workers)
      +---> FastAPI #2 (5 Uvicorn workers)   <--- horizontal scaling
      +---> FastAPI #3 (5 Uvicorn workers)
              |           |
              |           +---> Redis Cache (exam questions, leaderboard)
              |                 TTL-based: 5 min questions, 30s leaderboard
              |
              +---> Redis Broker (Celery task queue)
                         |
              +----------+----------+
              |                     |
    Celery: Proctoring (x4)   Celery: Evaluation (x2)
    MediaPipe + OpenCV         joinedload score calc
    Librosa audio RMS          async post-submit eval
              |                     |
              +----------+----------+
                         |
                    PostgreSQL
                    pool_size=10, max_overflow=20
                    11 performance indexes
                    Alembic migrations
```

### Key Data Flows

**Authentication Flow:**
```
Register --> Background email task --> Verification link
Verify email (/verify-email?token=) --> Account activated
Login --> JWT (120 min) --> Client stores token
401 response --> Auto logout + redirect to login
```

**Exam Taking Flow:**
```
Student --> Start Exam --> Create or Resume Attempt (within 24hr window)
Lobby --> Camera/Mic permissions --> Fullscreen --> Proctoring starts
Answer questions + Auto-save (10s) + WebSocket health bar (real time)
Frame upload --> POST /monitor/frame --> 202 Accepted (<15ms) --> Celery analyzes async
Submit (manual / auto on timer / auto on health=0) --> 200 instant response
Celery evaluate_attempt_task --> score computed --> status = evaluated
Student polls /results --> full breakdown returned
```

**Frame Proctoring Flow:**
```
Webcam frame --> multipart POST /monitor/frame
API: validate attempt ownership (<5ms) --> base64 encode --> enqueue to Redis broker --> return 202
Celery worker: decode base64 --> cv2.imdecode --> MediaPipe FaceMesh
  face count check  --> no_face / multiple_faces flags
  head pose (nose)  --> looking_away flag
  iris gaze         --> gaze_off_screen flag
  mouth ratio       --> mouth_movement_detected flag
Flags --> _persist_flags() --> CheatLog rows + increment cheating_flags counter
WebSocket push --> frontend HealthBar updates in real time
Health = 0 --> auto_submit_on_zero_health --> exam submitted
```

---

## Scalability Design

Quizzie is engineered to support 500+ concurrent students with active AI proctoring. The following table shows how each potential bottleneck is handled:

| Bottleneck | Problem | Solution | Result |
|---|---|---|---|
| AI proctoring CPU | MediaPipe takes 200–400ms per frame | Celery workers on separate containers; API never loads MediaPipe | Frame API latency: 2–4s → <15ms |
| API memory | MediaPipe loads 220MB at process start | Workers-only import; FastAPI process stays at ~120MB | 4x more headroom for concurrent requests |
| DB connections | Default pool exhausts under burst load | `pool_size=10`, `max_overflow=20` per replica | 3 replicas × 30 connections = 90 of 256 limit used |
| Question DB queries | 500 students × 1 query each on exam start | Redis cache, 5-min TTL | 500 students = 1 DB query, 499 cache hits |
| Evaluation blocking | Synchronous scoring delays student response | Celery evaluation queue, async dispatch | Submit returns in <100ms; score ready async |
| N+1 evaluation queries | 4,100+ round-trips per submission (nested loops) | `joinedload` + aggregate SQL | 3 queries per submission |
| Analytics queries | Per-student loops across all attempts | `func.count`, `func.avg`, `CASE WHEN` aggregates | 1 aggregate query per analytics endpoint |
| Leaderboard reads | Heavy JOIN on every request | Redis cache, 30s TTL, invalidated on new submission | No DB hit for 30 seconds regardless of readers |
| Uvicorn worker count | Hardcoded to 2 workers | `WORKERS` env var in Dockerfile, formula: (2 × CPU) + 1 | Configurable per deployment tier |

---

## Installation

### Prerequisites

- Node.js >= 18.0.0
- Python >= 3.11
- PostgreSQL >= 15.0
- Redis >= 7.0
- Docker >= 20.10 (optional but recommended)

---

### Method 1: Docker (Recommended)

Starts all 5 services (PostgreSQL, Redis, FastAPI, Celery proctoring worker, Celery evaluation worker, Nginx frontend) with a single command.

```bash
# Clone
git clone https://github.com/OnlyArkMani/Quizzie.git
cd Quizzie

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env — set SMTP credentials (leave blank to use console output in dev)

# Build and start
docker compose up --build

# Run migrations (first time only)
docker compose exec backend alembic upgrade head

# Seed sample data (optional)
docker compose exec backend python seed_data.py
```

| Service | URL |
|---|---|
| Frontend | http://localhost |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |

---

### Method 2: Local Development

```bash
git clone https://github.com/OnlyArkMani/Quizzie.git
cd Quizzie
```

**Backend:**
```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env — set DATABASE_URL, REDIS_URL, SECRET_KEY

createdb quizzie_db
alembic upgrade head
python seed_data.py

# Terminal 1: FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Celery proctoring worker
celery -A app.worker.celery_app worker -Q proctoring --concurrency=2 --loglevel=info

# Terminal 3: Celery evaluation worker
celery -A app.worker.celery_app worker -Q evaluation --concurrency=1 --loglevel=info
```

**Frontend:**
```bash
cd frontend
npm install
echo "VITE_API_URL=http://localhost:8000/api/v1" > .env
npm run dev
```

> **Note on Redis:** If Redis is not running locally, the app starts with a warning (`Redis unavailable — cache disabled`) and continues normally. Caching and Celery workers require Redis; the API and exam flow work without it in development.

---

### Running Tests

```bash
cd backend

# Full test suite with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Single file
pytest tests/test_auth.py -v

# Single class
pytest tests/test_attempts.py::TestSubmitExam -v
```

Tests use a dedicated PostgreSQL test database with per-test transaction rollback — each test starts from a clean state with no cross-test state leakage.

---

### Email Setup (Gmail)

1. Enable 2-Factor Authentication on your Google account
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Create an App Password and copy the 16-character code
4. Add to `backend/.env`:

```env
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_FROM=you@gmail.com
FRONTEND_URL=http://localhost:5173
```

If `SMTP_USERNAME` is blank, verification tokens are printed to the backend console. The app works fully without SMTP configured.

---

## Usage Guide

### For Students

1. Navigate to `/login` — demo credentials: `student@demo.com` / `pass123`
2. View dashboard: available live exams, your statistics, and recent attempts
3. Click a live exam → review instructions → grant camera and microphone permissions → enter fullscreen → begin
4. Answer questions — auto-saved every 10 seconds
5. Use the question palette to jump between questions and mark for review
6. Submit manually, or the exam auto-submits on timer expiry or health reaching zero
7. View results: percentage score, marks breakdown, topic-wise performance, and cheating flag count

### For Examiners

1. Login — demo credentials: `examiner@demo.com` / `pass123`
2. Create an exam via the 3-step wizard: details → questions → publish
3. Toggle exam status: `draft` → `live` → `ended`
4. Monitor live exams: view all active students sorted by violation count with real-time health
5. View analytics: score distribution, topic-wise performance, leaderboard, suspicion scores
6. Export results as CSV for offline analysis

---

## API Documentation

Full interactive documentation available at `http://localhost:8000/docs` (Swagger UI).

### Authentication

```http
POST /api/v1/auth/register              Register + send verification email
POST /api/v1/auth/login                 Login -> JWT token
GET  /api/v1/auth/me                    Current user profile
GET  /api/v1/auth/verify-email          Verify email via token
POST /api/v1/auth/resend-verification   Resend verification (rate-limited: 3/min)
POST /api/v1/auth/forgot-password       Send password reset link (rate-limited: 5/min)
POST /api/v1/auth/reset-password        Reset password with token
```

### Exams

```http
GET    /api/v1/exams/                      List exams (role-filtered + paginated)
POST   /api/v1/exams/                      Create exam
GET    /api/v1/exams/{exam_id}             Exam details
PUT    /api/v1/exams/{exam_id}             Update exam (invalidates Redis cache)
DELETE /api/v1/exams/{exam_id}             Delete exam
PATCH  /api/v1/exams/{exam_id}/status      Update status (draft/live/ended)
GET    /api/v1/exams/{exam_id}/questions   Questions (Redis-cached, 5-min TTL)
```

### Attempts

```http
POST /api/v1/attempts/start                    Start or resume attempt
POST /api/v1/attempts/{attempt_id}/submit      Submit -> Celery evaluation enqueued
POST /api/v1/attempts/{attempt_id}/auto-save   Save current responses
GET  /api/v1/attempts/{attempt_id}/results     Results (polling until evaluated)
GET  /api/v1/attempts/my-attempts              Student attempt history
```

### Analytics

```http
GET /api/v1/analytics/exam/{exam_id}/summary       Aggregate stats (single query)
GET /api/v1/analytics/exam/{exam_id}/leaderboard   Ranked leaderboard (Redis-cached)
GET /api/v1/analytics/student/me/stats             Student performance stats
GET /api/v1/analytics/examiner/stats               Examiner overview
GET /api/v1/analytics/exam/{exam_id}/export        CSV export (StreamingResponse)
```

### Monitoring

```http
POST /api/v1/monitor/frame                                           Upload frame -> Celery (202)
POST /api/v1/monitor/audio                                           Upload audio -> Celery (202)
GET  /api/v1/monitor/flags/{attempt_id}                              All cheat flags

POST /api/v1/monitor/enhanced/violation                              Report violation + update health
POST /api/v1/monitor/enhanced/recover                                Health recovery after clean period
GET  /api/v1/monitor/enhanced/attempt/{attempt_id}/health            Current health status
GET  /api/v1/monitor/enhanced/attempt/{attempt_id}/violations        Full violation timeline
GET  /api/v1/monitor/enhanced/attempt/{attempt_id}/suspicion-score   Computed suspicion score
GET  /api/v1/monitor/enhanced/exam/{exam_id}/live-feed               Live student feed (examiner)
POST /api/v1/monitor/enhanced/exam/{exam_id}/proctoring-settings     Configure proctoring
GET  /api/v1/monitor/enhanced/exam/{exam_id}/proctoring-settings     Get proctoring config

WS   /ws/proctoring/{attempt_id}   Real-time health updates and violation alerts
```

All protected endpoints require:
```http
Authorization: Bearer <jwt_token>
```

---

## AI Proctoring System

### Face Detection Pipeline

```python
# 1. Decode JPEG/PNG frame from uploaded bytes (inside Celery worker)
image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

# 2. MediaPipe Face Detection — count faces
num_faces = len(face_detection.process(rgb_frame).detections)

# 3. Face Mesh — 478 landmarks (refine_landmarks=True for iris)
lm = face_mesh.process(rgb_frame).multi_face_landmarks[0].landmark

# 4. Head pose — nose x vs eye-center x deviation
deviation = abs(lm[1].x - (lm[33].x + lm[263].x) / 2)
if deviation > 0.15: flag("looking_away", "medium")

# 5. Iris gaze tracking — normalised offset within each eye
l_offset = (lm[468].x - min(lm[133].x, lm[33].x)) / eye_width
if avg_offset < 0.22 or avg_offset > 0.78: flag("gaze_off_screen", "medium")

# 6. Mouth detection — lip gap / mouth width ratio
ratio = abs(lm[14].y - lm[13].y) / abs(lm[291].x - lm[61].x)
if ratio > 0.35: flag("mouth_movement_detected", "medium")
```

### Cheat Detection Flags

| Flag Type | Description | Severity |
|---|---|---|
| `no_face_detected` | No face visible in frame | High |
| `multiple_faces_detected` | More than one person detected | High |
| `looking_away` | Head turned away from screen | Medium |
| `gaze_off_screen` | Eyes tracking off screen | Medium |
| `mouth_movement_detected` | Mouth open — possible whispering | Medium |
| `loud_noise_detected` | Suspicious audio activity | Medium |
| `tab_switch` | Browser tab changed | High |
| `fullscreen_exit` | Fullscreen lost | High |
| `multi_monitor_detected` | Unusually wide screen detected | Medium |
| `face_tracking_lost` | Face present but mesh failed | Medium |

### Processing Performance

| Operation | Latency (in worker) | API Latency (to student) |
|---|---|---|
| Frame upload + enqueue | — | <15ms (202 Accepted) |
| MediaPipe FaceMesh | 200–400ms | async — not felt by student |
| Audio RMS analysis | ~15ms | async — not felt by student |
| Suspicion score calculation | <5ms | on-demand endpoint |

---

## CI/CD Pipeline

```
Push to main branch
      |
      +---> GitHub Actions triggers
              |
              +---> JOB 1: test-backend (parallel)
              |       Services: PostgreSQL 15 + Redis 7 (Docker)
              |       Steps:
              |         1. Install Python 3.11 + system deps (ffmpeg, libsndfile1)
              |         2. pip install -r requirements.txt
              |         3. pytest tests/ --cov=app (30+ test cases)
              |         4. Upload coverage.xml artifact
              |
              +---> JOB 2: test-frontend (parallel)
                      Steps:
                        1. npm ci (reproducible install from package-lock.json)
                        2. tsc --noEmit (TypeScript type check)
                        3. npm run build (Vite production build)
              |
              +---> JOB 3: deploy (only if JOB 1 + JOB 2 pass, only on main)
                      1. curl RENDER_BACKEND_DEPLOY_HOOK
                      2. curl RENDER_FRONTEND_DEPLOY_HOOK
                      -> Zero-downtime rolling deploy on Render
```

GitHub Secrets required:
- `RENDER_BACKEND_DEPLOY_HOOK` — from Render Dashboard → quizzie-api → Settings → Deploy Hook
- `RENDER_FRONTEND_DEPLOY_HOOK` — from Render Dashboard → quizzie-frontend → Settings → Deploy Hook

---

## Project Structure

```
Quizzie/
├── .github/
│   └── workflows/
│       └── ci-cd.yml                # GitHub Actions: test + deploy pipeline
│
├── frontend/
│   ├── src/
│   │   ├── features/
│   │   │   ├── auth/pages/          # Login, Register, Verify, Forgot, Reset
│   │   │   ├── exam/
│   │   │   │   ├── pages/           # StudentDashboard, ExamLobby, TakeExam, Results
│   │   │   │   ├── components/      # QuestionCard, Palette, Timer, HealthBar, Camera
│   │   │   │   ├── store/           # Zustand exam state (examStore.ts)
│   │   │   │   └── hooks/
│   │   │   └── examiner/
│   │   │       ├── pages/           # Dashboard, CreateExam (3-step), ManageExams, Analytics
│   │   │       └── store/
│   │   ├── shared/                  # Reusable components, Toast
│   │   ├── lib/api.ts               # Axios instance + JWT interceptors
│   │   └── types/                   # TypeScript interfaces
│   ├── Dockerfile                   # Multi-stage: Node build -> Nginx
│   └── nginx.conf                   # SPA routing + /api proxy + WebSocket
│
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── auth.py              # Auth endpoints with slowapi rate limiting
│   │   │   ├── exams.py             # CRUD + Redis cache on questions
│   │   │   ├── questions.py         # Question and option management
│   │   │   ├── attempts.py          # Start, auto-save, submit (Celery dispatch), results
│   │   │   ├── analytics.py         # Aggregate SQL analytics + CSV export
│   │   │   ├── monitoring.py        # Frame/audio upload -> Celery (202 Accepted)
│   │   │   └── enhanced_monitoring.py # Health system, WebSocket, suspicion score, live feed
│   │   ├── worker/
│   │   │   ├── celery_app.py        # Celery config: two queues, reliability settings
│   │   │   └── tasks/
│   │   │       ├── proctoring_tasks.py  # analyze_frame_task, analyze_audio_task
│   │   │       └── evaluation_tasks.py  # evaluate_attempt_task
│   │   ├── ai_monitor/
│   │   │   ├── face_detector.py         # MediaPipe face + mesh + iris + mouth
│   │   │   ├── enhanced_face_detector.py # PnP head pose + HealthCalculator
│   │   │   └── audio_analyzer.py        # RMS audio analysis
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   ├── schemas/                 # Pydantic v2 schemas
│   │   ├── services/
│   │   │   ├── evaluation_service.py # N+1-free joinedload scoring
│   │   │   └── email_service.py      # SMTP + HTML templates
│   │   └── core/
│   │       ├── config.py            # Pydantic settings (env-driven)
│   │       ├── cache.py             # Async Redis layer + key builders
│   │       ├── database.py          # SQLAlchemy engine (pool_size=10)
│   │       └── security.py          # JWT + bcrypt
│   ├── alembic/versions/
│   │   ├── 001_add_proctoring.py
│   │   ├── add_email_verification.py
│   │   └── 003_add_performance_indexes.py  # 11 indexes for concurrent load
│   ├── tests/
│   │   ├── conftest.py              # Fixtures, TestClient, per-test rollback
│   │   ├── test_auth.py             # 7 auth tests
│   │   ├── test_exams.py            # 8 exam CRUD tests
│   │   ├── test_attempts.py         # 9 attempt lifecycle tests
│   │   ├── test_analytics.py        # 7 analytics + export tests
│   │   └── test_evaluation.py       # 3 scoring unit tests
│   ├── pytest.ini
│   └── Dockerfile                   # WORKERS env var configurable
│
├── docker-compose.yml               # 6 services: postgres, redis, backend,
│                                    # celery_proctoring, celery_evaluation, frontend
├── render.yaml                      # Render.com multi-service deploy blueprint
├── DEPLOYMENT.md                    # Full deployment guide (Railway, Fly.io, AWS)
└── Makefile                         # Dev shortcut commands
```

---

## Performance

### API Response Times

| Endpoint | Without Cache | With Redis Cache |
|---|---|---|
| GET /exams/{id}/questions | 80–150ms | <10ms |
| GET /analytics/exam/{id}/leaderboard | 200–400ms | <10ms |
| POST /monitor/frame (frame upload) | 2000–4000ms (old) | <15ms (202 + async) |
| POST /attempts/{id}/submit | 350–500ms (old sync eval) | <100ms (async eval) |

### Database

- Average query time: <50ms
- Connection pool: 10 base + 20 overflow per API replica
- N+1 eliminated: 4,100+ queries per evaluation reduced to 3
- Indexes added: 11 across 5 tables

### Test Coverage

- Total test cases: 30+
- Test categories: auth (7), exams (8), attempts (9), analytics (7), evaluation (3)
- Test DB strategy: real PostgreSQL, per-test transaction rollback

---

## Deployment Alternatives

For production scale beyond Render's free tier:

| Platform | Concurrent Students (with proctoring) | Monthly Cost | Notes |
|---|---|---|---|
| Render Starter | 15–20 | ~$13 (API + DB) | Recommended starting point |
| Railway | 200–400 | ~$20–40 | Auto-detects docker-compose.yml |
| Fly.io | 400–600 | ~$25–50 | Global low-latency, no cold starts |
| DigitalOcean App Platform | 300–500 | ~$25–50 | Predictable pricing |
| AWS ECS + Fargate | 1000+ | ~$60–150 | Enterprise scale |
| GCP Cloud Run | 1000+ | ~$0–80 | Pay-per-request, auto-scale |

See [DEPLOYMENT.md](DEPLOYMENT.md) for step-by-step guides for Railway, Fly.io, and AWS ECS including Terraform snippets.

---

## Useful Commands

```bash
make up             # Start all services
make down           # Stop all services
make build          # Rebuild images
make logs           # Tail all logs
make migrate        # Run alembic upgrade head
make shell-backend  # Bash into backend container
make shell-db       # psql into postgres
make clean          # Remove containers and volumes
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `SECRET_KEY` | — | JWT signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `120` | JWT lifetime in minutes |
| `WORKERS` | `4` | Uvicorn worker count |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated allowed origins |
| `FRONTEND_URL` | `http://localhost:5173` | Used in email links |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | — | Sender email (blank = skip sending) |
| `SMTP_PASSWORD` | — | SMTP app password |
| `EMAIL_FROM` | — | From address in emails |
| `ENVIRONMENT` | `development` | `development` or `production` |
| `CACHE_TTL_EXAM_QUESTIONS` | `300` | Question cache TTL in seconds |
| `CACHE_TTL_LEADERBOARD` | `30` | Leaderboard cache TTL in seconds |

---

## Future Enhancements

### Phase 1 — Short-term
- Question randomisation per attempt
- Partial credit scoring for multiple-choice
- Mobile app (React Native)
- Multi-language support
- Push and in-app notifications

### Phase 2 — Mid-term
- Live proctoring dashboard with WebRTC video stream
- Voice recognition for identity verification
- LMS integration (Moodle, Canvas)
- Timed sections within a single exam
- Prometheus metrics endpoint + Grafana dashboard

### Phase 3 — Long-term
- AI-generated question creation
- Adaptive testing (difficulty adjustment per student)
- Plagiarism detection for short-answer questions
- Blockchain-based certificate verification
- Multi-tenant SaaS architecture

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/FeatureName`
3. Commit your changes: `git commit -m 'Add FeatureName'`
4. Push to the branch: `git push origin feature/FeatureName`
5. Open a Pull Request

### Standards
- Follow PEP 8 for Python; use the project ESLint config for TypeScript
- Write tests for new features — PRs without tests will not be merged
- Update this README for any new endpoints, environment variables, or architectural changes

---

## Team

**Project Guide**

Mr. Sachin Gupta — Project Guide and Mentor, Department of CSE, Manipal University Jaipur

**Development Team**

**Ark Mani** — Full Stack Developer and AI Integration
- Registration: 23FE10CSE00793
- [arkmanimishra@gmail.com](mailto:arkmanimishra@gmail.com)
- [linkedin.com/in/ark-mani-924694200](https://www.linkedin.com/in/ark-mani-924694200/)
- [@OnlyArkMani](https://github.com/OnlyArkMani)

**Rishabh Jain** — Backend Developer and Database Design
- Registration: 23FE10CSE00784
- Department: B.Tech Computer Science Engineering, 3rd Year (6th Semester)

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- Manipal University Jaipur — for resources and academic guidance
- Mr. Sachin Gupta — for mentorship throughout the project
- MediaPipe Team (Google) — for the open-source computer vision toolkit
- FastAPI, Celery, and Redis communities — for excellent documentation
- React and Vite communities — for a fast and productive frontend ecosystem

---

<div align="center">

**Project Link:** [https://github.com/OnlyArkMani/Quizzie](https://github.com/OnlyArkMani/Quizzie)

Built by Ark Mani and Rishabh Jain

[![GitHub issues](https://img.shields.io/github/issues/OnlyArkMani/Quizzie)](https://github.com/OnlyArkMani/Quizzie/issues)
[![GitHub pull requests](https://img.shields.io/github/issues-pr/OnlyArkMani/Quizzie)](https://github.com/OnlyArkMani/Quizzie/pulls)

</div>
