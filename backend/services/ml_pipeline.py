import httpx
from bson import ObjectId
from typing import Dict, Any

from core.database import get_application_collection, get_user_collection
from core.config import settings
from models.application import ApplicationModel, VerificationReport, MetricScore, EnergyPrediction
from services.photo_forensics import gps_check, shadow_analysis_check
from services.satellite_analysis import satellite_verification
from services.equipment_check import equipment_verification
from services.notification import send_expo_push_notification

PVWATTS_API_URL = "https://developer.nrel.gov/api/pvwatts/v8.json"


async def calculate_expected_energy(lat: float, lon: float, system_capacity_kw: float) -> EnergyPrediction:
    """
    Queries the NREL PVWatts API for expected annual energy generation.
    """
    params = {
        'api_key': settings.NREL_PVWATTS_API_KEY,
        'lat': lat,
        'lon': lon,
        'system_capacity': system_capacity_kw,
        'dataset': 'intl',  # Use international dataset
        'module_type': 0,  # Standard
        'array_type': 1,  # Fixed open rack
        'tilt': 20,  # Placeholder (should ideally be input by user)
        'azimuth': 180,  # Placeholder (South facing in Northern Hemisphere)
        'losses': 14.0,
        'timeframe': 'annual',
        'format': 'json'
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(PVWATTS_API_URL, params=params, timeout=10.0)
            response.raise_for_status()

            data = response.json()
            annual_kwh = data['outputs']['ac_annual']

            return EnergyPrediction(
                expected_annual_kwh=annual_kwh,
                actual_monthly_kwh=None  # Monitoring part is future scope
            )

    except httpx.HTTPStatusError as e:
        print(f"PVWatts API HTTP error: {e.response.text}")
        return EnergyPrediction(expected_annual_kwh=None)
    except Exception as e:
        print(f"PVWatts API Request error: {e}")
        return EnergyPrediction(expected_annual_kwh=None)


async def run_verification_pipeline(app_id: str, app_doc: Dict[str, Any], user_email: str):
    """
    🚀 THE ASYNCHRONOUS ORCHESTRATOR 🚀
    Executes the entire verification process in the background.
    """
    app_collection = get_application_collection()
    user_collection = get_user_collection()

    # 1. Update status to 'verifying'
    await app_collection.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": {"status": "verifying"}}
    )
    print(f"Verification started for App ID: {app_id}")

    # Extract necessary inputs
    lat, lon = app_doc['registered_lat'], app_doc['registered_lon']
    capacity = app_doc['system_capacity_kw']
    panel_count = app_doc['declared_panel_count']
    wide_key = app_doc['wide_rooftop_photo']['s3_key']
    serial_key = app_doc['serial_number_photo']['s3_key']
    submission_date = app_doc['submission_date']

    # --- 2. Run Individual Checks (Concurrent execution is possible here) ---

    # GPS Check
    gps_metric, detected_lat, detected_lon, capture_time_str = gps_check(wide_key, lat, lon)

    # Shadow Analysis
    shadow_result = shadow_analysis_check(wide_key, detected_lat, detected_lon, capture_time_str)

    # Satellite Analysis
    satellite_result = await satellite_verification(lat, lon, panel_count, submission_date)

    # Equipment Check
    equipment_result = await equipment_verification(serial_key)

    # Energy Prediction (Not directly used in score, but stored)
    energy_prediction = await calculate_expected_energy(lat, lon, capacity)

    # --- 3. Calculate Final Confidence Score ---

    # Collect scores based on weights from config
    scores = [
        (gps_metric.score, settings.WEIGHT_GPS_MATCH),
        (shadow_result.score, settings.WEIGHT_SHADOW_ANALYSIS),
        (satellite_result.score, settings.WEIGHT_SATELLITE_ANALYSIS),
        (equipment_result.score, settings.WEIGHT_EQUIPMENT_CHECK),
    ]

    total_score = sum(score * weight for score, weight in scores)
    total_weight = sum(weight for _, weight in scores)

    final_confidence = total_score / total_weight if total_weight > 0 else 0.0

    # --- 4. Decision Engine ---

    decision, final_status, reasoning = "manual_review", "manual_review", "Flagged for manual review."

    if final_confidence >= settings.THRESHOLD_AUTO_APPROVE:
        decision, final_status = "Auto-approve", "approved"
        reasoning = "High confidence score, all major checks passed verification."
    elif final_confidence < settings.THRESHOLD_MANUAL_REVIEW:
        decision, final_status = "Auto-reject", "rejected"
        reasoning = "Low confidence score due to major failures in multiple checks (e.g., GPS mismatch, no panels detected)."

    # --- 5. Assemble Report and Update DB ---

    verification_report = VerificationReport(
        gps_check=gps_metric,
        shadow_analysis=shadow_result,
        satellite_analysis=satellite_result,
        equipment_check=equipment_result,
        confidence_score=round(final_confidence, 4),
        decision=decision,
        reasoning=reasoning
    )

    update_payload = {
        "status": final_status,
        "verification_report": verification_report.dict(),
        "expected_energy": energy_prediction.dict()  # Store prediction data
    }

    await app_collection.update_one(
        {"_id": ObjectId(app_id)},
        {"$set": update_payload}
    )
    print(f"Verification complete for App ID: {app_id}. Status: {final_status}")

    # --- 6. Send Notification ---

    # Fetch user's Expo Token (Requires token to be stored in the User Model)
    # user_doc = await user_collection.find_one({"email": user_email})
    # expo_token = user_doc.get("expo_token")

    # SIMULATING the push notification
    # Replace 'ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]' with a real token in your testing
    await send_expo_push_notification(
        token='ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]',
        title="Surya Saathi Verification Update",
        body=f"Your application (ID: {app_id[-4:]}) status is now: {final_status.upper()}.",
        data={"app_id": app_id, "status": final_status}
    )