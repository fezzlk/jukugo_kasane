import os
import secrets
from datetime import datetime
from urllib.parse import quote

import requests


class BaseImageStore:
    def get_image_url(self, kind: str, word: str, font_key: str, local_path: str) -> str:
        raise NotImplementedError

    def cleanup(self, paths: list) -> None:
        return None


class LocalImageStore(BaseImageStore):
    def __init__(self, server_fqdn: str):
        normalized_fqdn = server_fqdn.rstrip("/")
        if normalized_fqdn.startswith("http://"):
            normalized_fqdn = "https://" + normalized_fqdn[len("http://") :]
        self.server_fqdn = normalized_fqdn

    def get_image_url(self, kind: str, word: str, font_key: str, local_path: str) -> str:
        if not self.server_fqdn:
            raise ValueError("SERVER_FQDN is required for LINE image replies.")
        if not self.server_fqdn.startswith("https://"):
            raise ValueError("SERVER_FQDN must start with https:// for LINE images.")
        safe_word = quote(word)
        font_param = ""
        if font_key and font_key != "default":
            font_param = f"?font={font_key}"
        return f"{self.server_fqdn}/{kind}/{safe_word}{font_param}"


class GcsImageStore(BaseImageStore):
    def __init__(self, bucket: str, prefix: str, logger):
        self.bucket = bucket
        self.prefix = (prefix or "").strip("/").strip()
        self.logger = logger

    def get_image_url(self, kind: str, word: str, font_key: str, local_path: str) -> str:
        if not self.bucket:
            raise ValueError("LINE_GCS_BUCKET is required for GCS image storage.")
        if not local_path or not os.path.exists(local_path):
            raise ValueError("Local image file is missing.")

        object_name = self._build_object_name(kind, word, font_key, local_path)
        self._upload_file(object_name, local_path)
        quoted_name = quote(object_name, safe="/")
        return f"https://storage.googleapis.com/{self.bucket}/{quoted_name}"

    def cleanup(self, paths: list) -> None:
        for path in paths:
            if not path:
                continue
            try:
                os.remove(path)
            except OSError as exc:
                self.logger.error("local image cleanup failed: %s", exc)

    def _build_object_name(
        self, kind: str, word: str, font_key: str, local_path: str
    ) -> str:
        date_prefix = datetime.utcnow().strftime("%Y/%m/%d")
        token = secrets.token_hex(8)
        suffix = ""
        if font_key and font_key != "default":
            suffix = f"_{font_key}"
        filename = f"{kind.upper()}_{word}{suffix}.png"
        base = f"{date_prefix}/{token}_{filename}"
        if self.prefix:
            return f"{self.prefix}/{base}"
        return base

    def _upload_file(self, object_name: str, local_path: str) -> None:
        access_token = self._get_gcs_access_token()
        if not access_token:
            raise ValueError("GCS access token is missing.")
        url = (
            "https://storage.googleapis.com/upload/storage/v1/b/"
            f"{self.bucket}/o?uploadType=media&name={quote(object_name, safe='')}"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "image/png",
        }
        with open(local_path, "rb") as f:
            response = requests.post(url, headers=headers, data=f.read(), timeout=10)
        if response.status_code >= 400:
            raise ValueError(
                f"GCS upload failed: status={response.status_code} body={response.text[:500]}"
            )

    def _get_gcs_access_token(self) -> str:
        url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
        headers = {"Metadata-Flavor": "Google"}
        response = requests.get(url, headers=headers, timeout=3)
        if response.status_code >= 400:
            raise ValueError(
                f"metadata token error: status={response.status_code} body={response.text[:200]}"
            )
        data = response.json()
        return data.get("access_token", "")
