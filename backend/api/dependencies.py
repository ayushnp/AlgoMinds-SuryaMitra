from typing import Annotated
from fastapi import Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorClient
from core.database import get_database, get_user_collection
from core.security import get_current_user_id
from models.user import UserModel, PyObjectId


# --- Database Dependencies ---

def get_db_client() -> AsyncIOMotorClient:
    """Dependency to provide the MongoDB client instance."""
    return get_database()


# --- Authentication Dependencies ---

async def get_current_user(user_id: Annotated[str, Depends(get_current_user_id)]) -> UserModel:
    """
    Dependency that fetches the full UserModel for the currently authenticated user.
    Requires a valid JWT token.
    """
    user_collection = get_user_collection()

    # We must ensure the user_id from the token is a valid ObjectId for MongoDB query
    try:
        object_id = PyObjectId(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject format",
        )

    # Fetch user document from MongoDB
    user_doc = await user_collection.find_one({"_id": object_id})

    if user_doc is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or credentials invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Convert MongoDB document to Pydantic model
    return UserModel(**user_doc)


# Reusable dependencies for endpoints
DBSession = Annotated[AsyncIOMotorClient, Depends(get_db_client)]
CurrentUser = Annotated[UserModel, Depends(get_current_user)]