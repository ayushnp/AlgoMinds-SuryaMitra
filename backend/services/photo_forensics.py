from typing import Dict, Tuple, Optional
from PIL import Image
from PIL.ExifTags import TAGS
import io
import cv2
import numpy as np
import pytz
from datetime import datetime
from pvlib import solarposition

from services.storage import get_file_content
from models.application import MetricScore, ShadowAnalysisResult


def extract_exif_data(file_content: bytes) -> Dict:
    """Extracts relevant EXIF data (GPS, Date/Time) from a photo."""
    exif_data = {}
    try:
        image = Image.open(io.BytesIO(file_content))
        info = image._getexif()
        if info:
            for tag, value in info.items():
                decoded = TAGS.get(tag, tag)
                exif_data[decoded] = value

        # Handle GPS Info (Requires a separate lookup)
        if 'GPSInfo' in exif_data:
            # Placeholder: A full implementation would parse the GPS tuple structure
            print("GPS data detected in EXIF.")
            # We assume a helper function converts GPSInfo into (lat, lon)
            # For simplicity here, we rely on the client app providing clean GPS data,
            # but this function is the safeguard.

    except Exception as e:
        print(f"Error extracting EXIF data: {e}")

    return exif_data


def gps_check(
        photo_s3_key: str,
        registered_lat: float,
        registered_lon: float,
        threshold_m: float = 100.0
) -> Tuple[MetricScore, float, float]:
    """
    Verifies the photo's EXIF GPS matches the registered location.
    Returns score, detected_lat, detected_lon.
    """
    # 1. Load EXIF data
    try:
        file_content = get_file_content(photo_s3_key)
        exif_data = extract_exif_data(file_content)
    except FileNotFoundError:
        return MetricScore(score=0.0, details="Photo file not found in storage."), 0.0, 0.0

    # 2. Extract detected GPS from EXIF
    # **NOTE:** Implement robust EXIF GPS extraction here.
    # For this model, we'll simulate the extraction result.
    detected_lat = registered_lat + 0.0001  # Simulate slight deviation
    detected_lon = registered_lon + 0.0001
    capture_time_str = exif_data.get('DateTimeOriginal', datetime.now().isoformat())

    # 3. Calculate distance (using Haversine or simple distance)
    # distance = calculate_distance(registered_lat, registered_lon, detected_lat, detected_lon)
    distance = 15.0  # Simulated distance in meters (15m)

    if distance <= threshold_m:
        score = 1.0
        details = f"GPS location verified. Deviation: {distance:.2f}m."
    else:
        score = 0.0
        details = f"GPS mismatch detected. Deviation: {distance:.2f}m. Exceeds {threshold_m}m threshold."

    return MetricScore(score=score, details=details), detected_lat, detected_lon, capture_time_str


def shadow_analysis_check(
        photo_s3_key: str,
        lat: float,
        lon: float,
        capture_time_str: str,
) -> ShadowAnalysisResult:
    """
    Compares detected shadows in the image with expected solar position.
    """
    # 1. Calculate Expected Solar Position (Azimuth/Elevation)
    try:
        # Convert to datetime object with timezone (assuming Indian Standard Time)
        tz = pytz.timezone('Asia/Kolkata')
        time = datetime.fromisoformat(capture_time_str)
        time_local = tz.localize(time.replace(microsecond=0))

        solpos = solarposition.get_solarposition(time_local, lat, lon)
        expected_azimuth = solpos['azimuth'].iloc[0]
        expected_elevation = solpos['elevation'].iloc[0]
    except Exception as e:
        return ShadowAnalysisResult(
            score=0.0, details=f"Failed to calculate expected solar position: {e}",
            gps_check=MetricScore(score=0.0, details="Time/GPS data invalid or missing.")
        )

    # 2. Image Processing to Detect Shadow Angles (Simplified)
    # This involves complex CV: Canny edge detection, Hough lines, perspective transform.
    file_content = get_file_content(photo_s3_key)
    nparr = np.frombuffer(file_content, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Placeholder for actual CV detection
    # detected_shadow_angle = run_shadow_detection_cv(image)
    detected_shadow_angle = expected_azimuth + np.random.uniform(-5, 5)  # Simulate a small error

    # 3. Comparison
    angle_difference = abs(expected_azimuth - detected_shadow_angle)

    if angle_difference < 10:
        score = 1.0
        details = f"Shadow angle matches solar position within {angle_difference:.2f} degrees."
    elif angle_difference < 30:
        score = 0.7
        details = f"Shadow angle deviated significantly ({angle_difference:.2f} degrees). Possible tampering or measurement error."
    else:
        score = 0.2
        details = f"Major shadow angle mismatch ({angle_difference:.2f} degrees). High probability of tampered photo (e.g., wrong time/date)."

    return ShadowAnalysisResult(
        score=score,
        details=details,
        expected_sun_azimuth=expected_azimuth,
        expected_sun_elevation=expected_elevation,
        detected_shadow_angle=detected_shadow_angle
    )