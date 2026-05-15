# Quizzie — Deployment Alternatives & System Design Guide

## Cloud Deployment Options (Render alternatives)

| Platform | Best for | Concurrent students (proctoring) | Monthly cost | Cold starts |
|---|---|---|---|---|
| **Railway** | Fastest setup after Render | 200–400 | ~$20–40 | No |
| **Fly.io** | Global low-latency | 400–600 | ~$25–50 | No (machines stay warm) |
| **DigitalOcean App Platform** | Predictable pricing | 300–500 | ~$25–50 | No |
| **AWS ECS + Fargate** | True production scale (1000+) | 1000+ | ~$60–150 | No |
| **GCP Cloud Run** | Pay-per-request, auto-scale | 1000+ | ~$0–80 (usage-based) | Yes (< 1s) |
| **Azure Container Apps** | Enterprise + AD integration | 1000+ | ~$30–100 | No |

### Recommended for Quizzie at 500 students
**Fly.io** or **Railway** for fast, affordable deployment.  
**AWS ECS** or **GCP Cloud Run** when you need to scale beyond 500.

---

## Deployment: Railway (Simplest after Render)

Railway auto-detects your `docker-compose.yml`. Steps:

```bash
npm install -g @railway/cli
railway login
railway init          # inside C:\Projects\Quizzie
railway up
```

Railway reads `docker-compose.yml` and spins up:
- `postgres` → managed PostgreSQL
- `redis` → managed Redis
- `backend` → FastAPI container
- `celery_proctoring` → AI worker
- `celery_evaluation` → evaluation worker
- `frontend` → Nginx container

Set env vars in Railway dashboard under each service.

---

## Deployment: Fly.io (Best performance/price for 500 students)

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Deploy backend
cd backend
fly launch --name quizzie-api --dockerfile Dockerfile
fly scale vm shared-cpu-2x    # 2 shared vCPU, 1 GB RAM — handles 500 students

# Deploy Celery proctoring worker
fly launch --name quizzie-proctoring --dockerfile Dockerfile
fly scale vm dedicated-cpu-1x  # dedicated CPU for MediaPipe
fly deploy --config fly-proctoring.toml

# Create managed Postgres
fly postgres create --name quizzie-db --vm-size shared-cpu-1x --volume-size 10

# Create managed Redis (Upstash — free 10k req/day)
fly redis create --name quizzie-redis
```

`fly.toml` for the backend:
```toml
app = "quizzie-api"
kill_signal = "SIGINT"
kill_timeout = 30

[build]
  dockerfile = "Dockerfile"

[env]
  WORKERS = "5"
  ENVIRONMENT = "production"

[[services]]
  http_checks = []
  internal_port = 8000
  protocol = "tcp"

  [[services.ports]]
    handlers = ["http"]
    port = 80
  [[services.ports]]
    handlers = ["tls", "http"]
    port = 443

  [services.concurrency]
    type = "connections"
    hard_limit = 600      # 500 students + headroom
    soft_limit = 500
```

---

## Deployment: AWS ECS + Fargate (1000+ students)

Architecture for enterprise scale:

```
Route 53 (DNS)
    → CloudFront CDN (frontend static files + API cache headers)
        → ALB (Application Load Balancer)
            → ECS Service: FastAPI (3 tasks × 2 vCPU, 4 GB)
            → ECS Service: Celery Proctoring (4 tasks × 1 vCPU, 2 GB)
            → ECS Service: Celery Evaluation (2 tasks × 0.5 vCPU, 1 GB)
    → RDS PostgreSQL (db.t3.medium, multi-AZ)
    → ElastiCache Redis (cache.t3.micro, cluster mode)
```

Terraform snippet (ECS task for FastAPI):
```hcl
resource "aws_ecs_task_definition" "quizzie_api" {
  family                   = "quizzie-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048   # 2 vCPU
  memory                   = 4096   # 4 GB

  container_definitions = jsonencode([{
    name  = "quizzie-api"
    image = "${aws_ecr_repository.quizzie.repository_url}:latest"
    portMappings = [{ containerPort = 8000 }]
    environment = [
      { name = "WORKERS", value = "5" },
      { name = "ENVIRONMENT", value = "production" }
    ]
    secrets = [
      { name = "DATABASE_URL",  valueFrom = aws_ssm_parameter.db_url.arn },
      { name = "REDIS_URL",     valueFrom = aws_ssm_parameter.redis_url.arn },
      { name = "SECRET_KEY",    valueFrom = aws_ssm_parameter.secret_key.arn }
    ]
  }])
}
```

---

## System Design: Quizzie at 500 Concurrent Students

### Architecture Overview

```
[Browser / Student]
        │
        ▼
[CloudFlare / CDN]          ← serves React SPA, caches static assets
        │
        ├──→ GET /assets/*   → CDN cache (no hit to origin)
        │
        └──→ /api/v1/*  ────→ [Load Balancer]
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              [FastAPI #1]    [FastAPI #2]    [FastAPI #3]
              (Uvicorn 5w)    (Uvicorn 5w)    (Uvicorn 5w)
                    │               │               │
                    └───────────────┴───────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              [Redis Cache]   [PostgreSQL]   [Redis Broker]
                                                    │
                                    ┌───────────────┼───────────┐
                                    ▼               ▼           ▼
                            [Celery Worker  [Celery Worker  [Celery Worker
                             Proctoring×4]   Proctoring×4]  Evaluation×2]
                                    │
                                    ▼
                            [MediaPipe / OpenCV / Librosa]
                                    │
                                    ▼
                            [PostgreSQL: cheat_logs]
```

### Request Flow: Student Taking an Exam

```
1. Student opens exam
   Browser → CDN → React SPA (no API hit)

2. Student logs in
   POST /api/v1/auth/login
   → FastAPI → DB (user lookup) → JWT issued
   Response: < 50ms

3. Student loads questions
   GET /api/v1/exams/{id}/questions
   → FastAPI → Redis cache HIT (if exam already loaded by someone)
   → Response: < 10ms (cache hit) or < 100ms (DB + cache miss)
   → All 500 students hitting at once = 1 DB query, 499 cache hits

4. Student answers + auto-saves
   POST /api/v1/attempts/{id}/auto-save
   → FastAPI → lightweight DB write (responses array)
   → Response: < 30ms

5. Webcam frame upload (every 5 seconds)
   POST /api/v1/monitor/frame  (multipart/form-data)
   → FastAPI validates attempt ownership (< 5ms)
   → Enqueues to Redis broker (< 5ms)
   → Returns 202 Accepted immediately
   → Celery worker picks up task, runs MediaPipe (200-400ms on dedicated CPU)
   → Writes flags to DB if detected
   Total API latency for student: < 15ms

6. Student submits exam
   POST /api/v1/attempts/{id}/submit
   → FastAPI saves all responses → marks attempt SUBMITTED → returns 200
   → Enqueues evaluate_attempt_task to evaluation queue
   → Response: < 100ms (student doesn't wait for scoring)
   → Celery worker evaluates, marks EVALUATED, updates score

7. Student views results
   GET /api/v1/attempts/{id}/results
   → If status=evaluating: returns {status: "evaluating"} immediately
   → If status=evaluated: returns full result object
   → Frontend polls every 2 seconds (max 30s) until evaluated
```

### How 500 students is handled

| Bottleneck | Solution | Capacity |
|---|---|---|
| Question DB query on exam start | Redis cache (5 min TTL) | 500 students = 1 DB query |
| Frame AI analysis blocks API | Celery + Redis queue | API returns in 15ms; workers process async |
| MediaPipe memory (220 MB each) | Workers in separate containers | API process never loads MediaPipe |
| DB connection exhaustion | pool_size=10, max_overflow=20 per worker | 3 API replicas × 30 = 90 connections |
| JWT verification overhead | Stateless JWT (no DB hit) | O(1) per request |
| Leaderboard recalculation | Redis cache (30s TTL) | 1 query per 30s regardless of readers |
| Exam submission evaluation | Celery evaluation queue | Non-blocking; student gets result async |

### Celery Queue Design

```
Redis Broker
├── Queue: proctoring  (high volume, latency-tolerant)
│   ├── Workers: 4–8 processes × N machines
│   ├── Task: analyze_frame_task  (200–400ms, CPU-bound)
│   └── Task: analyze_audio_task  (100–200ms, CPU-bound)
│
└── Queue: evaluation  (low volume, must complete)
    ├── Workers: 2 processes × 1 machine
    └── Task: evaluate_attempt_task  (50–200ms, DB-bound)
```

- `worker_prefetch_multiplier=1` → each worker takes ONE task at a time
  (prevents a single worker grabbing 4 tasks, processing the 4th 30 seconds late)
- `task_acks_late=True` → if a worker crashes mid-frame, the task is requeued
- `task_time_limit=45` → if MediaPipe hangs, the worker is killed and restarted

### Redis Cache Design

```
Key pattern            TTL      Content
─────────────────────────────────────────────────
exam:{id}:questions    5 min    Full question list (JSON) — invalidated on exam update
exam:{id}:meta         1 min    Exam status, duration, pass_percentage
exam:{id}:leaderboard  30 sec   Top-10 scores — invalidated on new submission
user:{id}              5 min    User profile — invalidated on profile update
ratelimit:{endpoint}:{ip}  60s  Request counter for slowapi
```

Cache strategy: **Cache-aside** (read-through)
1. Request comes in → check Redis
2. Cache HIT → return immediately
3. Cache MISS → query DB → store in Redis → return

Eviction policy: `allkeys-lru` — when Redis is full, evicts least-recently-used keys automatically.

### Database Indexing (add to next Alembic migration)

```sql
-- These are missing and will cause full table scans at 500 students
CREATE INDEX idx_attempts_student_id ON exam_attempts(student_id);
CREATE INDEX idx_attempts_exam_id ON exam_attempts(exam_id);
CREATE INDEX idx_attempts_status ON exam_attempts(status);
CREATE INDEX idx_responses_attempt_id ON responses(attempt_id);
CREATE INDEX idx_responses_question_id ON responses(question_id);
CREATE INDEX idx_cheat_logs_attempt_id ON cheat_logs(attempt_id);
CREATE INDEX idx_questions_exam_id ON questions(exam_id);
CREATE INDEX idx_users_email ON users(email);  -- already likely exists via UNIQUE
```

---

## CI/CD Pipeline Explained

```
Developer pushes to GitHub
        │
        ▼
GitHub Actions triggers on push/PR
        │
        ├──→ JOB 1: test-backend
        │         Services: PostgreSQL + Redis (Docker)
        │         Steps:
        │           1. Checkout code
        │           2. Install Python 3.11 + system deps (ffmpeg, libsndfile1)
        │           3. pip install -r requirements.txt
        │           4. pytest tests/ --cov=app
        │         Result: Pass / Fail + coverage.xml artifact
        │
        ├──→ JOB 2: test-frontend  (runs in parallel with JOB 1)
        │         Steps:
        │           1. Checkout code
        │           2. npm ci (uses package-lock.json for reproducible install)
        │           3. tsc --noEmit (TypeScript type check)
        │           4. npm run build (Vite production build)
        │         Result: Pass / Fail
        │
        └──→ JOB 3: deploy  (only if JOB 1 + JOB 2 both pass, only on main branch)
                  Steps:
                    1. curl RENDER_BACKEND_DEPLOY_HOOK  → triggers Render redeploy
                    2. curl RENDER_FRONTEND_DEPLOY_HOOK → triggers Render redeploy
                  Result: New containers deployed with zero downtime (Render rolling deploy)

GitHub Secrets required:
  RENDER_BACKEND_DEPLOY_HOOK   → from Render Dashboard → quizzie-api → Settings → Deploy Hook
  RENDER_FRONTEND_DEPLOY_HOOK  → from Render Dashboard → quizzie → Settings → Deploy Hook
```

Pipeline characteristics:
- **No secrets in code** — all via GitHub Secrets
- **Parallel jobs** — backend + frontend test simultaneously (~4 min total)
- **Gate on tests** — deploy only if ALL tests pass
- **Branch protection** — PRs to main require passing CI
- **Coverage tracked** — uploaded as artifact every run

---

## Environment Variables Reference

### Backend `.env` (development)
```env
DATABASE_URL=postgresql://postgres:postgres123@localhost:5432/quizzie_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-256-bit-random-secret-here
ENVIRONMENT=development
WORKERS=2

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@gmail.com
SMTP_PASSWORD=your-app-password
EMAIL_FROM=your@gmail.com

FRONTEND_URL=http://localhost:5173
ACCESS_TOKEN_EXPIRE_MINUTES=120

CACHE_TTL_EXAM_QUESTIONS=300
CACHE_TTL_EXAM_META=60
CACHE_TTL_LEADERBOARD=30
```

### Production (Render / Railway / Fly.io)
Same keys, different values — never commit production secrets to Git.

---

## Running Locally (Full Stack)

```bash
# Start all services
docker-compose up --build

# Or start services individually for development:
cd backend

# Terminal 1: FastAPI
uvicorn app.main:app --reload --port 8000

# Terminal 2: Celery proctoring worker
celery -A app.worker.celery_app worker -Q proctoring --concurrency=2 --loglevel=info

# Terminal 3: Celery evaluation worker
celery -A app.worker.celery_app worker -Q evaluation --concurrency=1 --loglevel=info

# Terminal 4: Frontend
cd ../frontend && npm run dev
```

## Running Tests

```bash
cd backend

# All tests with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Specific test file
pytest tests/test_auth.py -v

# Specific test class
pytest tests/test_attempts.py::TestSubmitExam -v

# Skip slow tests
pytest tests/ -v -m "not slow"
```
