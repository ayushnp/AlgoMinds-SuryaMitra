import os
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, Form, UploadFile
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from ...core.database import get_application_collection
from ...core.config import settings
from ...api.dependencies import DBSession, CurrentUser
from ...models.user import UserModel
from ...models.application import ApplicationModel, ApplicationCreate
from ...services.ml_pipeline import run_verification_pipeline
from ...services.storage import save_uploaded_files, get_storage_path  # We'll implement services later

router = APIRouter()


# --- Utility to handle file uploads and form data in one endpoint ---

@router.post("/submit", status_code=status.HTTP_202_ACCEPTED)
async def submit_application(
        background_tasks: BackgroundTasks,
        current_user: CurrentUser,
        # Installation Details (from form data)
        address: Annotated[str, Form()],
        registered_lat: Annotated[float, Form()],
        registered_lon: Annotated[float, Form()],
        system_capacity_kw: Annotated[float, Form()],
        declared_panel_count: Annotated[int, Form()],

        # Photo Files (from form data)
        wide_rooftop_photo: UploadFile,
        serial_number_photo: UploadFile,
        inverter_photo: UploadFile,

        db_client: DBSession,
):
    """
    Submits a new rooftop solar application along with mandatory photos.
    Triggers the intensive AI verification pipeline asynchronously.
    """
    app_collection = get_application_collection()
    user_id_str = str(current_user.id)

    # 1. Validate Form Data (Pydantic validation for the Form fields)
    try:
        ApplicationCreate(
            address=address,
            registered_lat=registered_lat,
            registered_lon=registered_lon,
            system_capacity_kw=system_capacity_kw,
            declared_panel_count=declared_panel_count
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid form data: {e}"
        )

    # 2. Save Files to Storage (S3 or Local)
    try:
        # Save all files and get their keys/paths
        file_keys = await save_uploaded_files(
            user_id_str=user_id_str,
            files={
                "wide_rooftop": wide_rooftop_photo,
                "serial_number": serial_number_photo,
                "inverter": inverter_photo,
            }
        )
    except Exception as e:
        print(f"File upload failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save uploaded files."
        )

    # 3. Create the Database Document (Initial State)
    app_doc = {
        "user_id": current_user.id,  # Use PyObjectId here
        "address": address,
        "registered_lat": registered_lat,
        "registered_lon": registered_lon,
        "system_capacity_kw": system_capacity_kw,
        "declared_panel_count": declared_panel_count,
        "wide_rooftop_photo": {"s3_key": file_keys["wide_rooftop"]},
        "serial_number_photo": {"s3_key": file_keys["serial_number"]},
        "inverter_photo": {"s3_key": file_keys["inverter"]},
        "status": "submitted",
        "submission_date": datetime.now().isoformat(),
        "verification_report": None,
    }

    insert_result = await app_collection.insert_one(app_doc)
    app_id = str(insert_result.inserted_id)

    # 4. 🚀 Trigger Asynchronous Verification Pipeline
    # This task will run after the HTTP response is sent.
    background_tasks.add_task(
        run_verification_pipeline,
        app_id,
        app_doc,  # Pass the document structure including file keys
        current_user.email
    )

    return {
        "application_id": app_id,
        "message": "Application submitted successfully. Verification is running in the background."
    }


# --- Optional: Endpoint to retrieve application status/report ---

@router.get("/{application_id}", response_model=ApplicationModel)
async def get_application_details(
        application_id: str,
        current_user: CurrentUser,
        db_client: DBSession,
):
    """
    Retrieves the status and verification report for a specific application.
    """
    app_collection = get_application_collection()

    try:
        app_object_id = ObjectId(application_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Application ID format.")

    # Query by ID and ensure it belongs to the current user
    app_doc = await app_collection.find_one(
        {"_id": app_object_id, "user_id": current_user.id}
    )

    if app_doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")

    return ApplicationModel(**app_doc)