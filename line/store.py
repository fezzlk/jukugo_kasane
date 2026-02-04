import json
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _get_settings_file_path() -> str:
    env_path = os.getenv("LINE_SETTINGS_FILE_PATH")
    if env_path:
        return env_path
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "line_settings.json")


def load_settings() -> Dict[str, Any]:
    path = _get_settings_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception as exc:
        logger.error("line settings read error: %s", exc)
        return {}


def save_settings(settings: Dict[str, Any]) -> bool:
    path = _get_settings_file_path()
    try:
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=True, indent=2, sort_keys=True)
        return True
    except Exception as exc:
        logger.error("line settings write error: %s", exc)
        return False
