from fastapi import FastAPI
from contextlib import asynccontextmanager

from starlette.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import connect_to_mongo, close_mongo_connection
from api.endpoints import auth, applications, verifications

# --- Application Lifespan Context Manager ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles startup and shutdown events for the application.
    - Startup: Connect to MongoDB Atlas.
    - Shutdown: Close MongoDB connection.
    """
    print("Application Startup: Connecting to MongoDB Atlas...")
    await connect_to_mongo()

    yield  # Application runs here

    print("Application Shutdown: Closing MongoDB Atlas connection...")
    await close_mongo_connection()


# --- FastAPI Application Initialization ---

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    # Use the lifespan manager to handle DB connection
    lifespan=lifespan,
    # Optional: Add tags/description for better OpenAPI/Swagger UI documentation
    openapi_tags=[
        {"name": "auth", "description": "User registration and authentication."},
        {"name": "applications", "description": "Solar subsidy application submission and management."},
    ]
)
origins = [
    "http://localhost",
    "http://localhost:8081",  # Standard Expo web port
    "http://127.0.0.1:8081",
    # Add the specific IP address of your development machine if testing on a physical device over LAN
    # e.g., "http://192.168.1.10:8081"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For development, use ["*"]. Replace with 'origins' list for production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include Routers (API Endpoints) ---

app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(applications.router, prefix=f"{settings.API_V1_STR}/applications", tags=["applications"])
app.include_router(verifications.router, prefix=f"{settings.API_V1_STR}/verifications", tags=["verifications"])

# Add other routers here as they are created (e.g., verifications)


# --- Root Endpoint (Optional Health Check) ---

@app.get("/")
def health_check():
    """Simple endpoint to confirm the API is running."""
    return {"status": "ok", "project": settings.PROJECT_NAME, "version": settings.VERSION}

# To run the application:
# uvicorn main:app --reload --port 8000