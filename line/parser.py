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

        list_keyword = str(self.keywords.get("list", ""))
        if list_keyword and stripped == list_keyword:
            return {"type": "list"}

        menu_generate = str(self.keywords.get("menu_generate", ""))
        if menu_generate and stripped == menu_generate:
            return {"type": "menu_generate"}

        menu_register = str(self.keywords.get("menu_register", ""))
        if menu_register and stripped == menu_register:
            return {"type": "menu_register"}

        menu_list = str(self.keywords.get("menu_list", ""))
        if menu_list and stripped == menu_list:
            return {"type": "menu_list"}

        menu_settings = str(self.keywords.get("menu_settings", ""))
        if menu_settings and stripped == menu_settings:
            return {"type": "menu_settings"}

        menu_usage = str(self.keywords.get("menu_usage", ""))
        if menu_usage and stripped == menu_usage:
            return {"type": "menu_usage"}

        menu_mode = str(self.keywords.get("menu_mode", ""))
        if menu_mode and stripped == menu_mode:
            return {"type": "menu_mode"}

        menu_font = str(self.keywords.get("menu_font", ""))
        if menu_font and stripped == menu_font:
            return {"type": "menu_font"}

        mode_common = str(self.keywords.get("mode_common", ""))
        if mode_common and stripped == mode_common:
            return {"type": "mode_common"}

        mode_union = str(self.keywords.get("mode_union", ""))
        if mode_union and stripped == mode_union:
            return {"type": "mode_union"}

        font_keyword = str(self.keywords.get("font", ""))
        if stripped.startswith(font_keyword):
            _, _, font_value = stripped.partition(" ")
            if not font_value.strip():
                return {"type": "menu_font"}
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
        return 2 <= len(text) <= 8

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
