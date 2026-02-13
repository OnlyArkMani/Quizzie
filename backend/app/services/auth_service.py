from sqlalchemy.orm import Session
from app.models.user import User
from app.core.security import verify_password, get_password_hash, create_access_token
from datetime import timedelta
from app.core.config import settings
from typing import Optional

class AuthService:
    def __init__(self, db: Session):
        self.db = db
    
    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate user with email and password
        """
        user = self.db.query(User).filter(User.email == email).first()
        
        if not user:
            return None
        
        if not verify_password(password, user.password_hash):
            return None
        
        return user
    
    def create_user(self, email: str, password: str, full_name: str, role: str) -> User:
        """
        Create new user
        """
        hashed_password = get_password_hash(password)
        
        new_user = User(
            email=email,
            password_hash=hashed_password,
            full_name=full_name,
            role=role
        )
        
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        
        return new_user
    
    def generate_token(self, user: User) -> str:
        """
        Generate JWT token for user
        """
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.email},
            expires_delta=access_token_expires
        )
        return access_token
    
    def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email
        """
        return self.db.query(User).filter(User.email == email).first()
    
    def user_exists(self, email: str) -> bool:
        """
        Check if user exists
        """
        return self.db.query(User).filter(User.email == email).first() is not None