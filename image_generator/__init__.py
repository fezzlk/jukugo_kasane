import os
import logging
import re
from itertools import product
from PIL import Image, ImageDraw, ImageFont

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# カラー定義
BLACK = (0, 0, 0, 255)
WHITE = (255, 255, 255, 255)
PURPLE = (70, 20, 190, 255)
BLUE = (70, 65, 225, 255)
RED = (230, 70, 70, 255)

class ImageGenerator:
    """画像生成クラス"""

    def __init__(self, images_dir: str = "images"):
        self.images_dir = images_dir
        self.background_size = (1024, 1024)
        self.background_color = (255, 255, 255, 255)
        self.text_color = BLACK

        # 画像ディレクトリを作成
        os.makedirs(self.images_dir, exist_ok=True)

        # デフォルトフォント候補（Docker環境とローカル環境の両方に対応）
        self.default_font_paths = [
            "/app/.fonts/Honoka_Shin_Mincho_L.otf",
            "/app/.fonts/GenEiMonoGothic-Regular.ttf",
            "/System/Library/Fonts/Hiragino Sans GB.ttc",  # macOS
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
        ]

        self.font_key_map = {
            "mincho": "/app/.fonts/Honoka_Shin_Mincho_L.otf",
            "monogothic": "/app/.fonts/GenEiMonoGothic-Regular.ttf",
            "hiragino": "/System/Library/Fonts/Hiragino Sans GB.ttc",
            "dejavu": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        }
        self.font_key_order = ["mincho", "monogothic", "hiragino", "dejavu"]
        self.font_key_pattern = re.compile(r"^[A-Za-z0-9]{2,10}$")

        self.font = self._get_available_font()

    def _get_available_font(self) -> ImageFont.ImageFont:
        """利用可能なフォントを取得"""
        text_size = 1024

        for font_path in self.default_font_paths:
            try:
                if os.path.exists(font_path):
                    logger.info(f"フォントを使用: {font_path}")
                    return ImageFont.truetype(font_path, text_size)
            except Exception as e:
                logger.warning(f"フォント読み込み失敗: {font_path} - {e}")
                continue

        # フォールバック: デフォルトフォント
        logger.warning("デフォルトフォントを使用")
        return ImageFont.load_default()

    def get_font_keys(self) -> list:
        """利用可能なフォント識別子を取得"""
        return ["default"] + list(self.font_key_order)

    def normalize_font_key(self, font_key: str) -> str:
        """フォント識別子を正規化"""
        if not font_key:
            return "default"
        if not self.font_key_pattern.match(font_key):
            raise ValueError("フォント識別子は2-10文字の英数字で指定してください。")
        if font_key != "default" and font_key not in self.font_key_map:
            raise ValueError("指定されたフォントは利用できません。")
        return font_key

    def _get_font_for_key(self, font_key: str) -> ImageFont.ImageFont:
        """フォント識別子からフォントを取得"""
        if font_key == "default":
            return self.font

        font_path = self.font_key_map.get(font_key)
        if not font_path or not os.path.exists(font_path):
            raise ValueError("指定されたフォントは利用できません。")

        try:
            return ImageFont.truetype(font_path, 1024)
        except Exception as e:
            logger.warning(f"フォント読み込み失敗: {font_path} - {e}")
            raise ValueError("指定されたフォントは利用できません。")

    def _create_kanji_image(self, char: str, font: ImageFont.ImageFont) -> Image.Image:
        """漢字の画像を作成"""
        kanji_image = Image.new("RGBA", self.background_size, self.background_color)
        draw = ImageDraw.Draw(kanji_image)
        draw.text((0, 0), char, font=font, fill=self.text_color)
        return kanji_image

    def _process_pixels(self, kanji1: Image.Image, kanji2: Image.Image) -> tuple:
        """ピクセル処理で問題画像と解答画像を生成"""
        p1 = kanji1.load()
        p2 = kanji2.load()

        # 問題画像
        q_image = Image.new("RGB", (1024, 1024))
        q_pix = q_image.load()

        # 解答画像
        a_image = Image.new("RGB", (1024, 1024))
        a_pix = a_image.load()

        for x, y in product(*map(range, (1024, 1024))):
            if p1[x, y] == BLACK:
                if p2[x, y] == BLACK:
                    a_pix[x, y] = PURPLE  # 共通部分
                    q_pix[x, y] = BLACK
                else:
                    a_pix[x, y] = BLUE  # 1文字目のみ
                    q_pix[x, y] = WHITE
            else:
                q_pix[x, y] = WHITE
                if p2[x, y] == BLACK:
                    a_pix[x, y] = RED  # 2文字目のみ
                else:
                    a_pix[x, y] = WHITE  # 共通部分なし

        return q_image, a_image

    def generate_images(self, word: str, font_key: str = "default") -> tuple:
        """画像を生成して保存"""
        if len(word) != 2:
            raise ValueError("お題は二文字にしてください。")

        normalized_font_key = self.normalize_font_key(font_key)
        logger.info(f"画像生成開始: {word}, font_key: {normalized_font_key}")

        # フォント選択
        font = self._get_font_for_key(normalized_font_key)

        # 漢字画像作成
        kanji1 = self._create_kanji_image(word[0], font)
        kanji2 = self._create_kanji_image(word[1], font)

        # 画像処理
        q_image, a_image = self._process_pixels(kanji1, kanji2)

        # ファイル名生成
        suffix = "" if normalized_font_key == "default" else f"_{normalized_font_key}"
        q_filename = f"Q_{word}{suffix}.png"
        a_filename = f"A_{word}{suffix}.png"

        q_path = os.path.join(self.images_dir, q_filename)
        a_path = os.path.join(self.images_dir, a_filename)

        # 画像保存
        q_image.save(q_path)
        a_image.save(a_path)

        logger.info(f"画像保存完了: {q_filename}, {a_filename}")

        return q_path, a_path


# Flask アプリケーションのルート定義
generator = ImageGenerator()
