import os
import logging
import re
from itertools import product
import shutil
import subprocess
import tempfile
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
# RGB画像で使うため、透明度ではなく白寄りの赤で表現する
RED_SOFT = (255, 170, 170)


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
        self.available_font_keys = self._detect_available_font_keys()

    def _detect_available_font_keys(self) -> list:
        available = []
        for key in self.font_key_order:
            font_path = self.font_key_map.get(key)
            if not font_path:
                continue
            if self._is_font_usable(font_path):
                available.append(key)
        return available

    def _is_font_usable(self, font_path: str) -> bool:
        if not os.path.exists(font_path):
            return False
        try:
            ImageFont.truetype(font_path, 10)
            return True
        except Exception as e:
            logger.warning(f"フォント読み込み失敗: {font_path} - {e}")
            return False

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
        return list(self.available_font_keys)

    def get_default_font_key(self) -> str:
        """デフォルトで選ばれるフォント識別子を取得"""
        for font_path in self.default_font_paths:
            if not os.path.exists(font_path):
                continue
            for key, value in self.font_key_map.items():
                if value == font_path:
                    return key
            return "default"
        return "default"

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

    def _process_union_pixels(
        self, kanji1: Image.Image, kanji2: Image.Image
    ) -> Image.Image:
        """ピクセル処理で和集合画像を生成"""
        p1 = kanji1.load()
        p2 = kanji2.load()

        u_image = Image.new("RGB", (1024, 1024))
        u_pix = u_image.load()

        for x, y in product(*map(range, (1024, 1024))):
            if p1[x, y] == BLACK or p2[x, y] == BLACK:
                u_pix[x, y] = BLACK
            else:
                u_pix[x, y] = WHITE

        return u_image

    def _process_intersection_pixels(self, kanji_images: list) -> Image.Image:
        """ピクセル処理で共通部分画像を生成"""
        pixels = [img.load() for img in kanji_images]
        q_image = Image.new("RGB", (1024, 1024))
        q_pix = q_image.load()

        for x, y in product(*map(range, (1024, 1024))):
            all_black = True
            for p in pixels:
                if p[x, y] != BLACK:
                    all_black = False
                    break
            q_pix[x, y] = BLACK if all_black else WHITE

        return q_image

    def _process_union_pixels_multi(self, kanji_images: list) -> Image.Image:
        """ピクセル処理で和集合画像を生成（多文字対応）"""
        pixels = [img.load() for img in kanji_images]
        u_image = Image.new("RGB", (1024, 1024))
        u_pix = u_image.load()

        for x, y in product(*map(range, (1024, 1024))):
            any_black = False
            for p in pixels:
                if p[x, y] == BLACK:
                    any_black = True
                    break
            u_pix[x, y] = BLACK if any_black else WHITE

        return u_image

    def _process_step_pixels(self, kanji_images: list, step_index: int) -> Image.Image:
        """ピクセル処理で段階画像を生成"""
        frame = Image.new("RGB", (1024, 1024))
        frame_pix = frame.load()
        pixels = [img.load() for img in kanji_images]

        if step_index == 1:
            p1 = pixels[0]
            p2 = pixels[1]
            for x, y in product(*map(range, (1024, 1024))):
                p1_black = p1[x, y] == BLACK
                p2_black = p2[x, y] == BLACK
                if p1_black and p2_black:
                    frame_pix[x, y] = PURPLE
                elif p1_black and not p2_black:
                    frame_pix[x, y] = RED
                elif not p1_black and p2_black:
                    frame_pix[x, y] = BLUE
                else:
                    frame_pix[x, y] = WHITE
            return frame

        prefix_end = step_index
        next_index = step_index
        for x, y in product(*map(range, (1024, 1024))):
            prefix_all_black = True
            prefix_any_black = False
            for idx in range(prefix_end):
                if pixels[idx][x, y] == BLACK:
                    prefix_any_black = True
                else:
                    prefix_all_black = False
            next_black = pixels[next_index][x, y] == BLACK

            if prefix_all_black and not next_black:
                frame_pix[x, y] = RED
            elif prefix_all_black and next_black:
                frame_pix[x, y] = PURPLE
            elif prefix_any_black and not next_black:
                frame_pix[x, y] = RED_SOFT
            elif next_black:
                frame_pix[x, y] = BLUE
            else:
                frame_pix[x, y] = WHITE

        return frame

    def generate_images(self, word: str, font_key: str = "default") -> tuple:
        """画像を生成して保存"""
        if len(word) != 2:
            raise ValueError("お題は2文字のときのみ対応しています。")

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

    def generate_images_with_union(self, word: str, font_key: str = "default") -> tuple:
        """問題画像・解答画像・和集合画像を生成して保存"""
        if len(word) < 2 or len(word) > 8:
            raise ValueError("お題は二〜八文字にしてください。")

        normalized_font_key = self.normalize_font_key(font_key)
        logger.info(f"画像生成開始(和集合): {word}, font_key: {normalized_font_key}")

        font = self._get_font_for_key(normalized_font_key)
        kanji_images = [self._create_kanji_image(char, font) for char in word]

        a_image = None
        if len(word) == 2:
            q_image, a_image = self._process_pixels(kanji_images[0], kanji_images[1])
            u_image = self._process_union_pixels(kanji_images[0], kanji_images[1])
        else:
            q_image = self._process_intersection_pixels(kanji_images)
            u_image = self._process_union_pixels_multi(kanji_images)

        suffix = "" if normalized_font_key == "default" else f"_{normalized_font_key}"
        q_filename = f"Q_{word}{suffix}.png"
        a_filename = f"A_{word}{suffix}.png"
        u_filename = f"U_{word}{suffix}.png"

        q_path = os.path.join(self.images_dir, q_filename)
        a_path = os.path.join(self.images_dir, a_filename)
        u_path = os.path.join(self.images_dir, u_filename)

        q_image.save(q_path)
        if a_image is not None:
            a_image.save(a_path)
        u_image.save(u_path)

        if a_image is not None:
            logger.info(f"画像保存完了: {q_filename}, {a_filename}, {u_filename}")
        else:
            logger.info(f"画像保存完了: {q_filename}, {u_filename}")

        return q_path, a_path if a_image is not None else None, u_path

    def generate_union_video(
        self, word: str, font_key: str = "default", fps: int = 1
    ) -> tuple:
        """段階画像を生成して動画に変換"""
        if len(word) < 3 or len(word) > 8:
            raise ValueError("お題は三〜八文字にしてください。")

        normalized_font_key = self.normalize_font_key(font_key)
        logger.info(f"動画生成開始: {word}, font_key: {normalized_font_key}")

        font = self._get_font_for_key(normalized_font_key)
        kanji_images = [self._create_kanji_image(char, font) for char in word]

        temp_dir = tempfile.mkdtemp(prefix="frames_", dir=self.images_dir)
        frame_paths = []
        try:
            for idx in range(1, len(word)):
                frame = self._process_step_pixels(kanji_images, idx)
                frame_name = f"frame_{idx:03d}.png"
                frame_path = os.path.join(temp_dir, frame_name)
                frame.save(frame_path)
                frame_paths.append(frame_path)

            intersection_frame = self._process_intersection_pixels(kanji_images)
            intersection_index = len(word)
            intersection_name = f"frame_{intersection_index:03d}.png"
            intersection_path = os.path.join(temp_dir, intersection_name)
            intersection_frame.save(intersection_path)
            frame_paths.append(intersection_path)

            suffix = (
                "" if normalized_font_key == "default" else f"_{normalized_font_key}"
            )
            video_filename = f"V_{word}{suffix}.mp4"
            preview_filename = f"P_{word}{suffix}.png"
            video_path = os.path.join(self.images_dir, video_filename)
            preview_path = os.path.join(self.images_dir, preview_filename)

            if frame_paths:
                shutil.copyfile(frame_paths[0], preview_path)

            self._build_video_from_frames(temp_dir, fps, video_path)
            logger.info(f"動画保存完了: {video_filename}")
            return video_path, preview_path
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _build_video_from_frames(
        self, frame_dir: str, fps: int, output_path: str
    ) -> None:
        """ffmpegでフレーム画像を動画に変換"""
        pattern = os.path.join(frame_dir, "frame_%03d.png")
        cmd = [
            "ffmpeg",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            pattern,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            output_path,
        ]
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.error("ffmpeg error: %s", exc.stderr)
            raise


# Flask アプリケーションのルート定義
generator = ImageGenerator()
