import os
import shutil
from typing import Dict
from pathlib import Path
from fastapi import UploadFile
from core.config import settings

# Base storage directory defined in core/config.py
BASE_STORAGE_PATH = Path(settings.STORAGE_DIR)


def get_storage_path(user_id_str: str, file_key: str) -> Path:
    """Generates the full, secure path for a file."""
    # Structure: storage_dir/user_id/file_key
    user_dir = BASE_STORAGE_PATH / user_id_str
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir / file_key


async def save_uploaded_files(user_id_str: str, files: Dict[str, UploadFile]) -> Dict[str, str]:
    """
    Saves multiple UploadFile objects to local storage (or S3 in production).
    Returns a dictionary of keys (the file name/path identifier).
    """
    saved_file_keys = {}

    for file_type, file in files.items():
        # Create a unique, descriptive file key
        # Format: user_id-app_id-file_type.ext
        # We will use the original filename + file_type for uniqueness for now.
        # In a real system, you'd use a UUID or the application ID for robustness.
        file_extension = Path(file.filename).suffix if file.filename else ".jpg"
        file_key = f"{user_id_str}-{file_type}{file_extension}"

        # Get the full path
        file_path = get_storage_path(user_id_str, file_key)

        # Write the file content asynchronously
        try:
            # Use shutil.copyfileobj for efficient, buffered writing
            with open(file_path, "wb") as buffer:
                # Read chunks from the UploadFile
                shutil.copyfileobj(file.file, buffer)

            saved_file_keys[file_type] = str(file_path)  # Store local path as the key
        except Exception as e:
            print(f"Error saving file {file_type}: {e}")
            # Reraise or handle cleanup if needed
            raise e

    return saved_file_keys


def get_file_content(file_path: str) -> bytes:
    """
    Retrieves the raw bytes content of a file given its storage path/key.
    (This function is crucial for ML/CV services to load the image data.)
    """
    try:
        with open(file_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        raise FileNotFoundError(f"File not found: {file_path}")