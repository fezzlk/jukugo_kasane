import json
import logging
import os
from typing import Optional, Dict, Any
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)


def load_token_data() -> Optional[Dict[str, Any]]:
    """Load OAuth2 token data from file or GCS."""
    if _use_gcs():
        return _load_from_gcs()
    return _load_from_file()


def save_token_data(token_data: Dict[str, Any]) -> bool:
    """Save OAuth2 token data to file or GCS."""
    if _use_gcs():
        return _save_to_gcs(token_data)
    return _save_to_file(token_data)


def _use_gcs() -> bool:
    return bool(os.getenv("TOKEN_GCS_BUCKET"))


def _get_token_file_path() -> str:
    env_path = os.getenv("TOKEN_FILE_PATH")
    if env_path:
        return env_path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")


def _load_from_file() -> Optional[Dict[str, Any]]:
    token_file_path = _get_token_file_path()
    if not os.path.exists(token_file_path):
        return None
    try:
        with open(token_file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.error(f"token file read error: {exc}")
        return None


def _save_to_file(token_data: Dict[str, Any]) -> bool:
    token_file_path = _get_token_file_path()
    try:
        parent_dir = os.path.dirname(token_file_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(token_file_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as exc:
        logger.error(f"token file write error: {exc}")
        return False


def _get_gcs_access_token() -> Optional[str]:
    url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
    headers = {"Metadata-Flavor": "Google"}
    try:
        response = requests.get(url, headers=headers, timeout=3)
        response.raise_for_status()
        data = response.json()
        return data.get("access_token")
    except Exception as exc:
        logger.error(f"metadata token error: {exc}")
        return None


def _get_gcs_bucket() -> Optional[str]:
    bucket = os.getenv("TOKEN_GCS_BUCKET")
    if bucket:
        logger.info(f"token gcs bucket: {bucket!r}")
    else:
        logger.error("TOKEN_GCS_BUCKET is not set")
    return bucket


def _get_gcs_object_name() -> str:
    object_name = os.getenv("TOKEN_GCS_OBJECT", "token.json")
    logger.info(f"token gcs object: {object_name!r}")
    return object_name


def _load_from_gcs() -> Optional[Dict[str, Any]]:
    bucket = _get_gcs_bucket()
    if not bucket:
        return None
    access_token = _get_gcs_access_token()
    if not access_token:
        return None
    object_name = quote(_get_gcs_object_name(), safe="")
    url = f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{object_name}?alt=media"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.error(f"gcs token read error: {exc}")
        return None


def _save_to_gcs(token_data: Dict[str, Any]) -> bool:
    bucket = _get_gcs_bucket()
    if not bucket:
        return False
    access_token = _get_gcs_access_token()
    if not access_token:
        return False
    object_name = quote(_get_gcs_object_name(), safe="")
    url = (
        "https://storage.googleapis.com/upload/storage/v1/b/"
        f"{bucket}/o?uploadType=media&name={object_name}"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(token_data, ensure_ascii=False).encode("utf-8"),
            timeout=5,
        )
        if response.status_code >= 400:
            logger.error(
                "gcs token write response: "
                f"status={response.status_code}, body={response.text[:200]!r}"
            )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.error(f"gcs token write error: {exc}")
        return False
