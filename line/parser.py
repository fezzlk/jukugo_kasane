class LineCommandParser:
    """Parse incoming text into structured LINE bot commands."""

    def __init__(self, keywords: dict):
        """Create a parser with keyword mappings."""
        self.keywords = keywords

    def parse(self, text: str) -> dict:
        """Parse text into a command dictionary."""
        stripped = text.strip()
        help_keywords = self.keywords.get("help", [])
        if stripped in help_keywords:
            return {"type": "help"}

        setting = self._parse_setting(stripped)
        if setting:
            return {"type": "setting", "setting": setting}

        font_keyword = str(self.keywords.get("font", ""))
        if stripped.startswith(font_keyword):
            _, _, font_value = stripped.partition(" ")
            return {"type": "font", "value": font_value.strip()}

        question_keyword = str(self.keywords.get("question", ""))
        if stripped.startswith(question_keyword):
            _, _, word = stripped.partition(" ")
            if not word and len(stripped) > len(question_keyword):
                word = stripped[len(question_keyword) :]
            return {"type": "question", "word": word.strip()}

        answer_keyword = str(self.keywords.get("answer", ""))
        if stripped.startswith(answer_keyword):
            _, _, word = stripped.partition(" ")
            if not word and len(stripped) > len(answer_keyword):
                word = stripped[len(answer_keyword) :]
            return {"type": "answer", "word": word.strip()}

        if len(stripped) == 2:
            return {"type": "question", "word": stripped}

        return {"type": "unknown"}

    def _parse_setting(self, text: str) -> dict:
        """Parse key=value settings command."""
        setting_keyword = str(self.keywords.get("setting", ""))
        if not text.startswith(setting_keyword):
            return {}
        _, _, rest = text.partition(" ")
        if "=" not in rest:
            return {}
        key, value = rest.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        if not key or not value:
            return {}
        return {key: value}
