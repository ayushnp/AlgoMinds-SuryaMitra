from fastapi import APIRouter, HTTPException, status, Depends
from bson import ObjectId
from typing import Annotated

from ...core.database import get_application_collection
from ...api.dependencies import DBSession, CurrentUser
from ...models.application import ApplicationModel, VerificationReport
from ...models.user import UserModel  # Used for CurrentUser type hinting

router = APIRouter()


@router.get(
    "/{application_id}/report",
    response_model=VerificationReport,
    tags=["verifications"]
)
async def get_verification_report(
        application_id: str,
        current_user: Annotated[UserModel, Depends(CurrentUser)],
        db_client: DBSession,
):
    """
    Retrieves the detailed verification report for a specific application
    if the status is 'approved', 'rejected', or 'manual_review'.
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

    # Convert the document to the full ApplicationModel for status check
    application = ApplicationModel(**app_doc)

    # Check if verification is complete
    if application.status in ["submitted", "verifying"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Verification for this application is still in progress. Current status: {application.status}"
        )

    # Return the embedded report
    if application.verification_report is None:
        # Should not happen if status is final, but acts as a safeguard
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Final status reached, but report content is missing."
        )

    return application.verification_report