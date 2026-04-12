from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Body
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import secrets

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.core.config import settings
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, User as UserSchema
from app.api.deps import get_current_user
from app.services.email_service import send_verification_email, send_password_reset_email

router = APIRouter()


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Register a new user and send a verification email."""
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if user_data.role not in ["student", "examiner"]:
        raise HTTPException(status_code=400, detail="Role must be 'student' or 'examiner'")

    token   = _generate_token()
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

    background_tasks.add_task(
        send_verification_email, new_user.email, new_user.full_name, token
    )

    return {
        "message": "Registration successful! Please check your email to verify your account.",
        "email": new_user.email,
    }


# ---------------------------------------------------------------------------
# Verify email
# ---------------------------------------------------------------------------

@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    """Verify a user's email using the token from the verification link."""

    # First check if any account with this token exists
    user = db.query(User).filter(User.verification_token == token).first()

    if not user:
        # Token not found — could mean already verified (token was cleared) or truly invalid.
        # Check if a verified user exists whose token was cleared after using this link.
        # We can't recover the token after clearing, so we return a helpful message.
        raise HTTPException(
            status_code=400,
            detail="This verification link has already been used or is invalid. If your account is not yet active, please request a new verification email."
        )

    # Token expired?
    if user.verification_token_expires and user.verification_token_expires < datetime.utcnow():
        raise HTTPException(
            status_code=400,
            detail="Verification link has expired. Please request a new one.",
        )

    # Already verified (shouldn't normally happen since we clear the token, but guard it)
    if user.is_verified:
        return {"message": "Email already verified. You can log in."}

    # Mark verified and clear the token
    user.is_verified = True
    user.verification_token = None
    user.verification_token_expires = None
    db.commit()

    return {"message": "Email verified successfully! You can now log in."}


# ---------------------------------------------------------------------------
# Resend verification
# ---------------------------------------------------------------------------

@router.post("/resend-verification")
def resend_verification(
    email: str = Body(..., embed=True),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Resend the verification email (rate-limit this in production)."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        # Don't reveal whether the email exists
        return {"message": "If that email is registered, a new verification link has been sent."}

    if user.is_verified:
        return {"message": "Account is already verified. You can log in."}

    token   = _generate_token()
    expires = datetime.utcnow() + timedelta(hours=24)
    user.verification_token = token
    user.verification_token_expires = expires
    db.commit()

    background_tasks.add_task(send_verification_email, user.email, user.full_name, token)
    return {"message": "If that email is registered, a new verification link has been sent."}


# ---------------------------------------------------------------------------
# Demo accounts — always allowed to log in without email verification
# ---------------------------------------------------------------------------

DEMO_EMAILS = {"examiner@demo.com", "student@demo.com"}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@router.post("/login")
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and return a JWT access token."""
    user = db.query(User).filter(User.email == credentials.email).first()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Demo accounts bypass email verification so they always work out of the box
    is_demo = credentials.email.lower() in DEMO_EMAILS

    if not user.is_verified and not is_demo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your email address has not been verified. "
                "Please check your inbox or request a new verification email."
            ),
        )

    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )

    # Normalise role to its string value (SQLAlchemy Enum can return the member object)
    role_str = user.role.value if hasattr(user.role, 'value') else str(user.role)

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


# ---------------------------------------------------------------------------
# Forgot password
# ---------------------------------------------------------------------------

@router.post("/forgot-password")
def forgot_password(
    email: str = Body(..., embed=True),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Send a password-reset link (always returns 200 to prevent email enumeration)."""
    user = db.query(User).filter(User.email == email).first()

    if user:
        token   = _generate_token()
        expires = datetime.utcnow() + timedelta(hours=1)
        user.reset_token = token
        user.reset_token_expires = expires
        db.commit()
        background_tasks.add_task(send_password_reset_email, user.email, user.full_name, token)

    return {"message": "If that email is registered, a password-reset link has been sent."}


# ---------------------------------------------------------------------------
# Reset password
# ---------------------------------------------------------------------------

@router.post("/reset-password")
def reset_password(
    token: str = Body(...),
    new_password: str = Body(..., min_length=8),
    db: Session = Depends(get_db),
):
    """Reset the user's password using a valid reset token."""
    user = db.query(User).filter(User.reset_token == token).first()

    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")

    user.password_hash = get_password_hash(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.commit()

    return {"message": "Password reset successfully. You can now log in."}


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------

@router.get("/me", response_model=UserSchema)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return current_user
