from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from jose import JWTError, jwt

from core.config import settings

# Password Hashing context (bcrypt is secure and industry standard)
# NOTE: 'bcrypt' is specified here.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme for dependency injection
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")


# --- Password Hashing Functions ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hashes a password.
    FIX: Truncates password to 72 bytes (the maximum limit for bcrypt)
    to prevent ValueError crash during registration.
    """
    # 1. Encode the password string to bytes
    password_bytes = password.encode('utf-8')

    # 2. Truncate if necessary (72 bytes is the limit)
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]

    # 3. Hash the byte string
    # The traceback shows the call failing on the line that previously only called pwd_context.hash(password)
    return pwd_context.hash(password_bytes)


# --- JWT Token Functions ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()

    # Ensure the 'sub' field (which holds the user ID) is stored as a string
    if 'sub' in to_encode and not isinstance(to_encode['sub'], str):
        to_encode['sub'] = str(to_encode['sub'])

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Use config expiration time
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def get_user_id_from_token(token: str) -> str:
    """
    Decodes the JWT token and extracts the user_id (str).
    Raises HTTPException on invalid or expired token.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")  # 'sub' is standard for subject (user ID)
        if user_id is None:
            raise credentials_exception
        return user_id
    except JWTError:
        raise credentials_exception


# --- Dependency for Protected Endpoints ---

async def get_current_user_id(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    """Dependency that returns the current authenticated user's ID."""
    user_id = get_user_id_from_token(token)
    return user_id