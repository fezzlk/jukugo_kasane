class LineCommandParser:
    """Parse incoming text into structured LINE bot commands."""

    def __init__(self, keywords: dict):
        """Create a parser with keyword mappings."""
        self.keywords = keywords

    def parse(self, text: str) -> dict:
        """Parse text into a command dictionary."""
        stripped = text.strip()
        has_prefix = False
        if stripped.startswith(("/", "#")):
            stripped = stripped[1:].strip()
            has_prefix = True
        help_keywords = self.keywords.get("help", [])
        if has_prefix and stripped in help_keywords:
            return {"type": "help"}

        setting = self._parse_setting(stripped) if has_prefix else {}
        if setting:
            return {"type": "setting", "setting": setting}

        list_keyword = self.keywords.get("list", "")
        list_candidates = (
            list_keyword if isinstance(list_keyword, (list, tuple)) else [list_keyword]
        )
        list_candidates = [str(item) for item in list_candidates if str(item)]
        if has_prefix and stripped in list_candidates:
            return {"type": "list"}

        menu_generate = str(self.keywords.get("menu_generate", ""))
        if has_prefix and menu_generate and stripped == menu_generate:
            return {"type": "menu_generate"}

        menu_register = str(self.keywords.get("menu_register", ""))
        if has_prefix and menu_register and stripped == menu_register:
            return {"type": "menu_register"}

        menu_list = str(self.keywords.get("menu_list", ""))
        if has_prefix and menu_list and stripped == menu_list:
            return {"type": "menu_list"}

        menu_settings = str(self.keywords.get("menu_settings", ""))
        if has_prefix and menu_settings and stripped == menu_settings:
            return {"type": "menu_settings"}

        menu_usage = str(self.keywords.get("menu_usage", ""))
        if has_prefix and menu_usage and stripped == menu_usage:
            return {"type": "menu_usage"}

        menu_mode = str(self.keywords.get("menu_mode", ""))
        if has_prefix and menu_mode and stripped == menu_mode:
            return {"type": "menu_mode"}

        menu_font = str(self.keywords.get("menu_font", ""))
        if has_prefix and menu_font and stripped == menu_font:
            return {"type": "menu_font"}

        prompt_keyword = str(self.keywords.get("prompt", ""))
        if has_prefix and prompt_keyword and stripped.startswith(prompt_keyword):
            _, _, prompt_value = stripped.partition(" ")
            if not prompt_value.strip():
                return {"type": "menu_prompt"}
            return {"type": "quiz_prompt", "value": prompt_value.strip()}

        mode_common = str(self.keywords.get("mode_common", ""))
        if has_prefix and mode_common and stripped == mode_common:
            return {"type": "mode_common"}

        mode_union = str(self.keywords.get("mode_union", ""))
        if has_prefix and mode_union and stripped == mode_union:
            return {"type": "mode_union"}

        font_keyword = str(self.keywords.get("font", ""))
        if has_prefix and stripped.startswith(font_keyword):
            _, _, font_value = stripped.partition(" ")
            if not font_value.strip():
                return {"type": "menu_font"}
            return {"type": "font", "value": font_value.strip()}

        font_prefix = str(self.keywords.get("font_prefix", ""))
        if font_prefix and stripped.startswith(font_prefix):
            font_value = stripped[len(font_prefix) :].strip()
            if not font_value:
                return {"type": "menu_font"}
            return {"type": "font", "value": font_value}

        if "." in stripped:
            return {"type": "unknown"}

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
