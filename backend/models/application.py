from typing import List, Optional, Dict

from bson import ObjectId
from pydantic import BaseModel, Field, conint, confloat
from models.user import PyObjectId  # Import custom ObjectId


# --- Sub-Models for Verification Report ---

class MetricScore(BaseModel):
    """Standard structure for a single verification metric."""
    score: confloat(ge=0.0, le=1.0) = Field(..., description="Confidence score from 0.0 to 1.0.")
    details: str = Field(..., description="Detailed explanation of the check result.")


class PhotoMetadata(BaseModel):
    """Stores extracted EXIF and analysis data for one photo."""
    s3_key: str = Field(..., description="Key/Path to the stored file.")
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    capture_time: Optional[str] = None  # ISO format string


class ShadowAnalysisResult(MetricScore):
    """Result of the shadow analysis."""
    expected_sun_azimuth: Optional[float] = None
    expected_sun_elevation: Optional[float] = None
    detected_shadow_angle: Optional[float] = None


class SatelliteAnalysisResult(MetricScore):
    """Result of the satellite and YOLO analysis."""
    pre_install_panel_count: Optional[conint(ge=0)] = 0
    post_install_panel_count: Optional[conint(ge=0)] = 0
    yolo_confidence: Optional[float] = None


class EquipmentCheckResult(MetricScore):
    """Result of OCR and ALMM database check."""
    detected_serials: List[str] = Field(default_factory=list)
    verified_serials: List[str] = Field(default_factory=list)


class EnergyPrediction(BaseModel):
    """Expected vs Actual energy metrics."""
    expected_annual_kwh: Optional[float] = None
    actual_monthly_kwh: Optional[Dict[str, float]] = None  # For future monitoring


class VerificationReport(BaseModel):
    """The complete result and decision summary."""
    # Individual Checks
    gps_check: MetricScore
    shadow_analysis: ShadowAnalysisResult
    satellite_analysis: SatelliteAnalysisResult
    equipment_check: EquipmentCheckResult

    # Summary & Decision
    confidence_score: confloat(ge=0.0, le=1.0)
    decision: str = Field(..., description="Auto-approve, manual_review, or auto-reject.")
    reasoning: str = Field(..., description="Summary explanation of the final decision.")


# --- Main Application Model ---

class ApplicationModel(BaseModel):
    """Model for a rooftop solar installation application in the database."""
    id: Optional[PyObjectId] = Field(alias="_id", default=None)
    user_id: PyObjectId

    # Installation Details
    address: str
    registered_lat: float
    registered_lon: float
    system_capacity_kw: float
    declared_panel_count: conint(ge=1)

    # Photo Details
    wide_rooftop_photo: PhotoMetadata
    serial_number_photo: PhotoMetadata
    inverter_photo: PhotoMetadata

    # Status and Verification
    status: str = Field("submitted", description="e.g., submitted, verifying, approved, rejected, manual_review")
    submission_date: str = Field(default_factory=lambda: str(datetime.now(pytz.timezone('Asia/Kolkata'))))

    # Report (only present after verification is complete)
    verification_report: Optional[VerificationReport] = None

    class Config:
        allow_population_by_field_name = True
        json_encoders = {ObjectId: str}
        # Use str() for ObjectId to handle serialization to JSON
        # Allow extra fields temporarily if needed for future expansion
        extra = "allow"


from datetime import datetime
import pytz


class ApplicationCreate(BaseModel):
    """Input model for creating a new application."""
    # File uploads will be handled separately in the FastAPI endpoint using UploadFile
    # These fields are the JSON part of the form data
    address: str
    registered_lat: float
    registered_lon: float
    system_capacity_kw: float
    declared_panel_count: conint(ge=1)