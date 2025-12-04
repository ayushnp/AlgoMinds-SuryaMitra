import easyocr
import io
import cv2
import numpy as np
from typing import List, Optional, Tuple

from services.storage import get_file_content
from models.application import MetricScore, EquipmentCheckResult

# Initialize EasyOCR reader (Load once globally for efficiency)
# NOTE: Ensure you have the necessary language models installed.
try:
    READER = easyocr.Reader(['en'], gpu=False)  # Use gpu=True if CUDA is configured
except Exception as e:
    print(f"Warning: Could not initialize EasyOCR reader: {e}")
    READER = None

# Placeholder ALMM Approved List (Indian Ministry of New and Renewable Energy)
ALMM_APPROVED_LIST = {
    "SERIAL-123456": {"model": "PV-IND-A1", "manufacturer": "SolarTech India"},
    "SERIAL-987654": {"model": "IN-PRO-B2", "manufacturer": "PowerGen Corp"},
     # Add more valid serial numbers here
}


def extract_serials_with_ocr(image_content: bytes) -> List[str]:
    """
    Runs EasyOCR on the close-up image to extract potential serial numbers.
    """
    if READER is None:
        return ["OCR_ERROR_READER_UNAVAILABLE"]

    try:
        # Convert image bytes to OpenCV format
        nparr = np.frombuffer(image_content, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            return ["OCR_ERROR_INVALID_IMAGE"]

        # Run OCR
        results = READER.readtext(image, detail=0)  # detail=0 returns only the text

        # Filter and clean results (basic filtering: must contain at least one digit and be reasonably long)
        filtered_serials = [
            text.strip().upper().replace('O', '0').replace('I', '1')  # Basic cleaning
            for text in results if any(char.isdigit() for char in text) and len(text) > 5
        ]

        return list(set(filtered_serials))  # Return unique results

    except Exception as e:
        print(f"Error during OCR extraction: {e}")
        return ["OCR_ERROR_EXCEPTION"]


def check_almm_list(detected_serials: List[str]) -> Tuple[MetricScore, List[str]]:
    """
    Verifies extracted serial numbers against the placeholder ALMM database.
    """
    verified_serials = []

    for serial in detected_serials:
        if serial in ALMM_APPROVED_LIST:
            verified_serials.append(serial)

    if not detected_serials:
        score = 0.1
        details = "No legible text/serial numbers could be extracted from the image."
    elif len(verified_serials) == len(detected_serials) and len(verified_serials) > 0:
        score = 1.0
        details = f"All {len(verified_serials)} detected serial numbers match the ALMM approved list."
    elif len(verified_serials) > 0:
        score = 0.7
        details = f"{len(verified_serials)} out of {len(detected_serials)} serials verified. Non-matching serials detected."
    else:
        score = 0.0
        details = f"No detected serial numbers ({len(detected_serials)}) matched the ALMM approved list."

    return MetricScore(score=score, details=details), verified_serials


async def equipment_verification(serial_photo_key: str) -> EquipmentCheckResult:
    """Orchestrates the equipment verification process."""
    try:
        image_content = get_file_content(serial_photo_key)
    except FileNotFoundError:
        return EquipmentCheckResult(
            score=0.0,
            details="Serial number photo not found.",
            detected_serials=[],
            verified_serials=[]
        )

    detected_serials = extract_serials_with_ocr(image_content)

    check_metric, verified_serials = check_almm_list(detected_serials)

    return EquipmentCheckResult(
        score=check_metric.score,
        details=check_metric.details,
        detected_serials=detected_serials,
        verified_serials=verified_serials
    )