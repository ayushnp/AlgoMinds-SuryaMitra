from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta
from typing import Annotated

from core.database import get_user_collection
from core.security import get_password_hash, verify_password, create_access_token
from core.config import settings
from models.user import UserCreate, UserOut
from api.dependencies import DBSession
# Add import for ObjectId which is used in the database query
from bson import ObjectId

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register_user(
        user_in: UserCreate,
        db_client: DBSession
):
    """
    Allows a new user (installer/applicant) to register.
    """
    users_collection = get_user_collection()

    # Check if user already exists
    existing_user = await users_collection.find_one({"email": user_in.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists"
        )

    # Hash the password
    # NOTE: Password truncation must be handled inside get_password_hash
    hashed_password = get_password_hash(user_in.password)

    # Create the user document
    user_doc = {
        "email": user_in.email,
        "hashed_password": hashed_password,
        "full_name": user_in.full_name,
        "phone_number": user_in.phone_number,
        "is_active": True
    }

    # Insert into MongoDB
    insert_result = await users_collection.insert_one(user_doc)

    # Fetch the inserted document to return the Pydantic model
    new_user = await users_collection.find_one({"_id": insert_result.inserted_id})

    # FIX: Use Pydantic V2's model_validate with from_attributes=True
    # to correctly convert the MongoDB ObjectId to a string.
    return UserOut.model_validate(new_user, from_attributes=True)


@router.post("/token")
async def login_for_access_token(
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
        db_client: DBSession
):
    """
    Authenticate user and return an access token (JWT).
    Uses the standard OAuth2PasswordRequestForm fields: username (used as email) and password.
    """
    users_collection = get_user_collection()

    user_doc = await users_collection.find_one({"email": form_data.username})

    if user_doc is None or not verify_password(form_data.password, user_doc["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # User authenticated, create token
    user_id = str(user_doc["_id"])
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(
        data={"sub": user_id}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user_id
    }