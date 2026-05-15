"""
Auth endpoint tests — registration, login, JWT, rate limiting.
"""
import pytest


class TestRegister:
    def test_register_student_success(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "new@test.com",
            "password": "password123",
            "full_name": "New User",
            "role": "student",
        })
        assert r.status_code == 201
        assert "email" in r.json()

    def test_register_duplicate_email(self, client, student_user):
        r = client.post("/api/v1/auth/register", json={
            "email": "student@test.com",
            "password": "password123",
            "full_name": "Dup User",
            "role": "student",
        })
        assert r.status_code == 400
        assert "already registered" in r.json()["detail"]

    def test_register_invalid_role(self, client):
        r = client.post("/api/v1/auth/register", json={
            "email": "admin@test.com",
            "password": "password123",
            "full_name": "Admin",
            "role": "admin",
        })
        assert r.status_code == 400


class TestLogin:
    def test_login_success(self, client, student_user):
        r = client.post("/api/v1/auth/login", json={
            "email": "student@test.com",
            "password": "password123",
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["role"] == "student"

    def test_login_wrong_password(self, client, student_user):
        r = client.post("/api/v1/auth/login", json={
            "email": "student@test.com",
            "password": "wrongpassword",
        })
        assert r.status_code == 401

    def test_login_nonexistent_user(self, client):
        r = client.post("/api/v1/auth/login", json={
            "email": "nobody@test.com",
            "password": "password123",
        })
        assert r.status_code == 401

    def test_login_unverified_user(self, client, db):
        from app.models.user import User, UserRole
        from app.core.security import get_password_hash
        unverified = User(
            email="unverified@test.com",
            password_hash=get_password_hash("password123"),
            full_name="Unverified",
            role=UserRole.STUDENT,
            is_verified=False,
        )
        db.add(unverified)
        db.commit()

        r = client.post("/api/v1/auth/login", json={
            "email": "unverified@test.com",
            "password": "password123",
        })
        assert r.status_code == 403

    def test_get_me(self, client, student_headers):
        r = client.get("/api/v1/auth/me", headers=student_headers)
        assert r.status_code == 200
        assert r.json()["email"] == "student@test.com"

    def test_me_without_token(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401
