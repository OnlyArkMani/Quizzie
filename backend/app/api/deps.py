import json
import uuid as _uuid
from datetime import datetime

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import Optional
from app.core.config import settings
from app.core.database import get_db, release_connection
from app.core.redis_client import get_sync_redis, mark_failed
from app.core.security import decode_access_token
from app.models.user import User, UserRole


# ── Auth user cache (cache-aside) ──────────────────────────────────────────────
# Every authenticated request used to run SELECT * FROM users WHERE email=...
# At exam start that is the single most frequent query in the system. We cache
# just the fields request handlers use, for CACHE_TTL_USER seconds.
#
# Trade-off: a role change or account deletion takes up to one TTL to apply
# (writes to the user row call ``invalidate_user_cache`` to shrink that to ~0
# for the flows we have). The alternative — putting role/id in JWT claims —
# removes the lookup entirely but makes such changes wait for token expiry
# (up to 120 min), which is worse.



def _user_key(email: str) -> str:
    return f"user:{email.lower()}"


def _detached(d: dict) -> User:
    # A transient (session-less) User: handlers only read id/role/email.
    return User(
        id=_uuid.UUID(d["id"]),
        email=d["email"],
        full_name=d["full_name"],
        role=UserRole(d["role"]),
        is_verified=d["is_verified"],
        created_at=datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None,
        token_version=d.get("token_version", 0),
    )


def _to_dict(user: User) -> dict:
    role = user.role.value if hasattr(user.role, "value") else str(user.role)
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": role,
        "is_verified": bool(user.is_verified),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "token_version": user.token_version or 0,
    }


def _cache_get_user(email: str) -> Optional[User]:
    client = get_sync_redis()
    if client is None:
        return None
    try:
        raw = client.get(_user_key(email))
    except Exception:
        mark_failed()
        return None
    return _detached(json.loads(raw)) if raw else None


def _cache_put_user(payload: dict) -> None:
    client = get_sync_redis()
    if client is None:
        return
    try:
        client.set(_user_key(payload["email"]), json.dumps(payload), ex=settings.CACHE_TTL_USER)
    except Exception:
        mark_failed()


def invalidate_user_cache(email: str) -> None:
    client = get_sync_redis()
    if client is None:
        return
    try:
        client.delete(_user_key(email))
    except Exception:
        mark_failed()

def _check_token_version(user: User, token_version: int) -> None:
    """Tokens issued before the last logout / password reset are dead."""
    if (token_version or 0) != (user.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> User:
    """
    Validate JWT token and return current user
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode token
    payload = decode_access_token(token)
    
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
    
    token_version = payload.get("tv", 0)

    cached = _cache_get_user(email)
    if cached is not None:
        _check_token_version(cached, token_version)
        return cached

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    payload = _to_dict(user)
    _check_token_version(user, token_version)
    # Give the pooled connection back before the route body runs — async
    # routes may await for a while (see release_connection). Both the cache
    # path and this path return the same detached snapshot.
    release_connection(db)
    _cache_put_user(payload)
    return _detached(payload)

def require_role(allowed_roles: list):
    """
    Dependency to check if user has required role.
    Handles both raw string roles and SQLAlchemy Enum members.
    """
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        # current_user.role may be a UserRole enum member OR a plain string
        # normalise to the string value so comparisons always work
        role_value = current_user.role.value if hasattr(current_user.role, 'value') else str(current_user.role)
        if role_value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return current_user
    return role_checker