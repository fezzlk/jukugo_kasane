import requests


class LineReplyClient:
    """Send replies to LINE Messaging API."""

    def __init__(self, access_token: str, logger):
        """Initialize reply client with access token."""
        self.access_token = access_token
        self.logger = logger
        self.reply_url = "https://api.line.me/v2/bot/message/reply"

    def reply(self, reply_token: str, messages: list) -> bool:
        """Send a reply with message payloads."""
        if not self.access_token:
            self.logger.error("LINE_CHANNEL_ACCESS_TOKEN is missing")
            return False
        payload = {"replyToken": reply_token, "messages": messages}
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.post(
            self.reply_url, json=payload, headers=headers, timeout=10
        )
        if response.status_code >= 400:
            self.logger.error(
                "LINE reply error: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            return False
        return True
