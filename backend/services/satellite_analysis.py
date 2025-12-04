import httpx
import numpy as np
import cv2
from typing import Tuple, Optional

from pathlib import Path

from ultralytics import YOLO

from core.config import settings
from models.application import MetricScore, SatelliteAnalysisResult

# Initialize YOLO model (Load once globally for efficiency)
# NOTE: Replace 'yolov8n.pt' with your trained solar panel detection model.
try:
    YOLO_MODEL = YOLO('yolov8n.pt')
except Exception as e:
    print(f"Warning: Could not load YOLO model: {e}")
    YOLO_MODEL = None

SENTINEL_HUB_API_URL = "https://services.sentinel-hub.com/api/v1/"  # Placeholder base URL


async def get_sentinel_image(lat: float, lon: float, date: str) -> Optional[bytes]:
    """
    Fetches satellite imagery (simplified placeholder for Sentinel Hub API).
    A full implementation requires OAuth, defining AOI, layer ID, and processing request.
    """
    # 1. Get Auth Token (Using configured secrets)
    # auth_url = "https://services.sentinel-hub.com/auth/realms/main/protocol/openid-connect/token"
    # token_response = await httpx.post(auth_url, data={...})

    # 2. Construct WCS or Process API request

    # --- SIMULATED RESPONSE ---
    # Since Sentinel Hub setup is complex, we simulate a downloaded image
    # to allow the YOLO part to be functional.
    print(f"Simulating fetch for {lat}, {lon} on {date}...")

    # Load a dummy image that we can detect panels on
    # In a real setup, this would be an async network request that returns image bytes.
    try:
        # Assuming you have a dummy image named 'dummy_satellite_panel.jpg' in a known path
        dummy_path = Path(__file__).parent.parent.parent / "data" / "dummy_satellite_panel.jpg"
        if not dummy_path.exists():
            # Create a simple dummy image if it doesn't exist for test
            dummy_image = np.zeros((512, 512, 3), dtype=np.uint8)
            cv2.putText(dummy_image, "Simulated Satellite Image", (50, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (255, 255, 255), 2)
            is_success, buffer = cv2.imencode(".jpg", dummy_image)
            return buffer.tobytes()

        with open(dummy_path, 'rb') as f:
            return f.read()

    except Exception as e:
        print(f"Error loading dummy image: {e}")
        return None
    # --- END SIMULATED RESPONSE ---


def run_yolo_detection(image_content: bytes) -> Tuple[int, float]:
    """
    Runs YOLOv8 model to detect and count solar panels in an image.
    Returns: (panel_count, avg_confidence)
    """
    if YOLO_MODEL is None:
        return 0, 0.0

    # Convert image bytes to OpenCV format
    nparr = np.frombuffer(image_content, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        print("YOLO failed: Invalid image content.")
        return 0, 0.0

    # Run inference
    results = YOLO_MODEL(image, verbose=False)

    panel_count = 0
    total_conf = 0.0

    # Assuming the YOLO model is trained with a single class 'solar_panel' (class_id=0)
    for r in results:
        # Filter for solar panel class and count
        panel_boxes = r.boxes
        panel_count = len(panel_boxes)

        # Calculate average confidence
        if panel_count > 0:
            total_conf = sum(panel_boxes.conf.tolist())
            avg_confidence = total_conf / panel_count
        else:
            avg_confidence = 0.0

    return panel_count, avg_confidence


async def satellite_verification(
        lat: float,
        lon: float,
        declared_panel_count: int,
        submission_date: str
) -> SatelliteAnalysisResult:
    """Orchestrates the satellite verification process."""

    # Define comparison dates
    # Pre-install: 6 months ago
    six_months_ago = (datetime.now() - timedelta(days=180)).isoformat()

    # Fetch pre-install image
    pre_image_content = await get_sentinel_image(lat, lon, six_months_ago)
    if not pre_image_content:
        return SatelliteAnalysisResult(
            score=0.0,
            details="Failed to fetch pre-installation satellite image.",
            gps_check=MetricScore(score=0.0, details="")
        )

    pre_count, pre_conf = run_yolo_detection(pre_image_content)

    # Fetch post-install image (using a recent date)
    post_image_content = await get_sentinel_image(lat, lon, submission_date)
    if not post_image_content:
        return SatelliteAnalysisResult(
            score=0.0,
            details="Failed to fetch post-installation satellite image.",
            gps_check=MetricScore(score=0.0, details="")
        )

    post_count, post_conf = run_yolo_detection(post_image_content)

    # Comparison and Scoring Logic
    if post_count == 0:
        score = 0.0
        details = "YOLO did not detect any panels in the post-installation image."
    elif pre_count > 0 and (post_count - pre_count) < 0:
        score = 0.1  # Very low score if count went down (highly suspicious)
        details = f"Suspicious activity: Panel count decreased from {pre_count} to {post_count}."
    else:
        # Check against declared count
        count_diff = abs(post_count - declared_panel_count)

        if count_diff <= 2:  # Allow small margin of error
            score = 1.0
            details = f"Panel count verified. Detected: {post_count}, Declared: {declared_panel_count}."
        elif count_diff <= 10:
            score = 0.8
            details = f"Panel count is close. Detected: {post_count}, Declared: {declared_panel_count}."
        else:
            score = 0.5
            details = f"Significant panel count mismatch. Detected: {post_count}, Declared: {declared_panel_count}."

    return SatelliteAnalysisResult(
        score=score,
        details=details,
        pre_install_panel_count=pre_count,
        post_install_panel_count=post_count,
        yolo_confidence=post_conf
    )


from datetime import timedelta, datetime
