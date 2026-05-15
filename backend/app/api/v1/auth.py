from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body, Request
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
from slowapi import Limiter
from slowapi.util import get_remote_address
import secrets

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, User as UserSchema
from app.api.deps import get_current_user
from app.services.email_service import send_verification_email, send_password_reset_email

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(
    request: Request,
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    if user_data.role not in ["student", "examiner"]:
        raise HTTPException(status_code=400, detail="Role must be 'student' or 'examiner'")

    token = _generate_token()
    expires = datetime.utcnow() + timedelta(hours=24)
    new_user = User(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        is_verified=False,
        verification_token=token,
        verification_token_expires=expires,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    background_tasks.add_task(send_verification_email, new_user.email, new_user.full_name, token)
    return {"message": "Registration successful! Check your email to verify.", "email": new_user.email}


@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or already-used verification link.")
    if user.verification_token_expires and user.verification_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Verification link expired.")
    if user.is_verified:
        return {"message": "Email already verified. You can log in."}
    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.commit()
    return {"message": "Email verified successfully! You can now log in."}


@router.post("/resend-verification")
@limiter.limit("3/minute")   # Rate-limited: prevents spam abuse
def resend_verification(
    request: Request,
    email: str = Body(..., embed=True),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"message": "If that email is registered, a new verification link has been sent."}
    if user.is_verified:
        return {"message": "Account already verified."}
    token = _generate_token()
    expires = datetime.utcnow() + timedelta(hours=24)
    user.verification_token = token
    user.verification_token_expires = expires
    db.commit()
    background_tasks.add_task(send_verification_email, user.email, user.full_name, token)
    return {"message": "If that email is registered, a new verification link has been sent."}


DEMO_EMAILS = {"examiner@demo.com", "student@demo.com"}


@router.post("/login")
@limiter.limit("20/minute")
def login(request: Request, credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    is_demo = credentials.email.lower() in DEMO_EMAILS
    if not user.is_verified and not is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Check your inbox.",
        )
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    role_str = user.role.value if hasattr(user.role, "value") else str(user.role)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": role_str,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat(),
        },
    }


@router.post("/forgot-password")
@limiter.limit("5/minute")
def forgot_password(
    request: Request,
    email: str = Body(..., embed=True),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if user:
        token = _generate_token()
        expires = datetime.utcnow() + timedelta(hours=1)
        user.reset_token = token
        user.reset_token_expires = expires
        db.commit()
        background_tasks.add_task(send_password_reset_email, user.email, user.full_name, token)
    return {"message": "If that email is registered, a password-reset link has been sent."}


@router.post("/reset-password")
def reset_password(
    token: str = Body(...),
    new_password: str = Body(..., min_length=8),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.reset_token == token).first()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
    user.password_hash = get_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()
    return {"message": "Password reset successfully. You can now log in."}


@router.get("/me", response_model=UserSchema)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user
