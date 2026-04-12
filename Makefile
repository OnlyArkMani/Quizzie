# Quizzie – Developer Makefile
# Usage: make <target>
# Requires: Docker + Docker Compose

.PHONY: help up down build logs migrate shell-backend shell-db clean

# ── Default ────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Quizzie Developer Commands"
	@echo "  ─────────────────────────────────────────────"
	@echo "  make up            Start all services (detached)"
	@echo "  make down          Stop all services"
	@echo "  make build         Rebuild all Docker images"
	@echo "  make logs          Tail logs from all services"
	@echo "  make migrate       Run Alembic DB migrations"
	@echo "  make shell-backend Open a shell inside the backend container"
	@echo "  make shell-db      Open psql inside the DB container"
	@echo "  make clean         Remove containers, images and volumes (DESTRUCTIVE)"
	@echo ""

# ── Docker Compose ─────────────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

# ── Database ───────────────────────────────────────────────────────────────────
migrate:
	docker compose exec backend alembic upgrade head

shell-backend:
	docker compose exec backend bash

shell-db:
	docker compose exec postgres psql -U postgres -d quizzie_db

# ── Cleanup ────────────────────────────────────────────────────────────────────
clean:
	docker compose down --rmi all --volumes --remove-orphans
