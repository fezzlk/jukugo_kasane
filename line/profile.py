import requests


class LineProfileClient:
    def __init__(self, access_token: str, logger):
        self.access_token = access_token
        self.logger = logger
        self.base_url = "https://api.line.me"

    def get_display_name(self, source: dict, user_id: str) -> str:
        if not self.access_token or not user_id:
            return ""
        source_type = source.get("type")
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            if source_type == "group":
                group_id = source.get("groupId", "")
                if not group_id:
                    return ""
                url = f"{self.base_url}/v2/bot/group/{group_id}/member/{user_id}"
            elif source_type == "room":
                room_id = source.get("roomId", "")
                if not room_id:
                    return ""
                url = f"{self.base_url}/v2/bot/room/{room_id}/member/{user_id}"
            else:
                url = f"{self.base_url}/v2/bot/profile/{user_id}"

            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code >= 400:
                return ""
            data = response.json()
            return data.get("displayName", "")
        except Exception as exc:
            self.logger.error("LINE profile fetch error: %s", exc)
            return ""
