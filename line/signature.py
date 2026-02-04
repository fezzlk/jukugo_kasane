import base64
import hashlib
import hmac


def verify_signature(secret: str, body: bytes, signature: str) -> bool:
    """Validate LINE webhook signature using channel secret."""
    if not secret:
        return False
    mac = hmac.new(secret.encode("utf-8"), body, digestmod=hashlib.sha256).digest()
    expected = base64.b64encode(mac).decode("utf-8")
    return hmac.compare_digest(expected, signature or "")
