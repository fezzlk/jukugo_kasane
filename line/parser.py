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

        if self._is_two_char_word(stripped):
            if not self._is_allowed_word(stripped):
                return {"type": "invalid_word"}
            return {"type": "both", "word": stripped}

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

    def _is_two_char_word(self, text: str) -> bool:
        return len(text) == 2

    def _is_allowed_word(self, text: str) -> bool:
        for char in text:
            if self._is_allowed_char(char):
                continue
            return False
        return True

    def _is_allowed_char(self, char: str) -> bool:
        code = ord(char)
        if 0x3041 <= code <= 0x309F:  # Hiragana
            return True
        if 0x30A0 <= code <= 0x30FF:  # Katakana
            return True
        if 0x4E00 <= code <= 0x9FFF:  # CJK Unified Ideographs (Kanji)
            return True
        if 0x0030 <= code <= 0x0039:  # ASCII digits
            return True
        if 0x0041 <= code <= 0x005A:  # ASCII uppercase
            return True
        if 0x0061 <= code <= 0x007A:  # ASCII lowercase
            return True
        return False
