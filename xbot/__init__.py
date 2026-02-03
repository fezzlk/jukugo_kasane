import os
import random
import csv
import io
import json
import time
import requests
from bs4 import BeautifulSoup
import tweepy
from dotenv import load_dotenv
from typing import Optional, Tuple, List, Dict
from config import get_config
from logger import get_logger
import token_store

load_dotenv()

# 設定とログを初期化
config = get_config()
logger = get_logger(__name__)


class SpreadsheetClient:
    """Google Spreadsheet access wrapper (public CSV export)."""

    def __init__(self, spreadsheet_url: Optional[str], spreadsheet_id: Optional[str], gid: Optional[str]):
        self.spreadsheet_url = spreadsheet_url.strip() if spreadsheet_url else None
        self.spreadsheet_id = spreadsheet_id.strip() if spreadsheet_id else None
        self.gid = gid.strip() if gid else None

    def _build_csv_url(self) -> str:
        if self.spreadsheet_url:
            return self.spreadsheet_url
        if not self.spreadsheet_id or not self.gid:
            raise ValueError("Spreadsheet URL or ID+GID is required.")
        return (
            "https://docs.google.com/spreadsheets/d/"
            f"{self.spreadsheet_id}/export?format=csv&gid={self.gid}"
        )

    def fetch_rows(self) -> List[Dict[str, str]]:
        url = self._build_csv_url()
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        response.encoding = "utf-8"

        buffer = io.StringIO(response.text)
        reader = csv.DictReader(buffer)
        rows = []
        for row in reader:
            normalized = {}
            for k, v in row.items():
                if not k:
                    continue
                key = k.strip()
                if key.startswith("\ufeff"):
                    key = key.lstrip("\ufeff")
                normalized[key] = (v or "").strip()
            rows.append(normalized)
        return rows


class XBot:
    """X（旧Twitter）投稿用ボットクラス"""

    def __init__(self):
        self.base_url = config.KASANE_API_URL
        self.jukugo_url = config.JUKUGO_API_URL
        self.fallback_jukugo = config.FALLBACK_JUKUGO
        self.images_dir = config.IMAGES_DIR
        self.spreadsheet_client = SpreadsheetClient(
            config.SPREADSHEET_URL, config.SPREADSHEET_ID, config.SPREADSHEET_GID
        )
        self.oauth_client_id = os.getenv("X_CLIENT_ID", "")
        self.oauth_client_secret = os.getenv("X_CLIENT_SECRET", "")

    def _alert_missing_jukugo_date(self, date_str: str) -> None:
        """Placeholder for alerting when no date row is found."""
        logger.warning(f"No spreadsheet row found for date: {date_str}")

    def get_jukugo_by_date(self, date_str: str) -> Optional[str]:
        """date列に一致する行から二字熟語を取得"""
        rows = self.spreadsheet_client.fetch_rows()
        matched = [row for row in rows if row.get("date") == date_str]

        if not matched:
            self._alert_missing_jukugo_date(date_str)
            return None

        jukugo = (matched[0].get("jukugo") or "").strip()
        if not jukugo or len(jukugo) != 2:
            raise ValueError("jukugo value is invalid.")

        return jukugo

    def post_question_by_date(self, date_str: str, test_mode: bool = False) -> bool:
        """スプレッドシートのdateから取得した熟語で問題投稿"""
        jukugo = self.get_jukugo_by_date(date_str)
        if not jukugo:
            return False
        return self.post_question(jukugo, test_mode)

    def _cleanup_old_files(self) -> None:
        """生成済み画像ファイルを削除"""
        if not os.path.exists(self.images_dir):
            os.makedirs(self.images_dir, exist_ok=True)
            logger.info(f"imagesディレクトリを作成しました: {self.images_dir}")

        deleted_count = 0

        # imagesディレクトリ内のファイルを削除
        try:
            for filename in os.listdir(self.images_dir):
                file_path = os.path.join(self.images_dir, filename)
                try:
                    os.remove(file_path)
                    logger.info(f"削除完了: {filename}")
                    deleted_count += 1
                except OSError as e:
                    logger.error(f"削除失敗: {filename} - {e}")
        except OSError as e:
            logger.error(f"imagesディレクトリの読み込みエラー: {e}")

        logger.info(f"合計{deleted_count}個のファイルを削除しました")

    def get_random_jukugo(self) -> str:
        """ランダムな四字熟語を取得"""
        try:
            response = requests.get(self.jukugo_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            word = soup.select_one("h2").text.strip()

            if word:
                logger.info(f"四字熟語を取得: {word}")
                return word
            else:
                raise ValueError("四字熟語が見つかりませんでした")

        except Exception as e:
            fallback_word = random.choice(self.fallback_jukugo)
            logger.warning(
                f"四字熟語取得エラー: {e}, フォールバック使用: {fallback_word}"
            )
            return fallback_word

    def _extract_image_urls(
        self, html_content: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """HTMLから画像URLを抽出"""
        soup = BeautifulSoup(html_content, "html.parser")
        img_tags = soup.find_all("img")

        q_image_url = None
        a_image_url = None

        for img in img_tags:
            src = img.get("src", "")
            if src.startswith("/q/") and not q_image_url:
                q_image_url = src
            elif src.startswith("/a/") and not a_image_url:
                a_image_url = src

        return q_image_url, a_image_url

    def _download_image(self, image_url: str, file_path: str) -> bool:
        """画像をダウンロード"""
        try:
            # 相対URLを絶対URLに変換
            if image_url.startswith("/"):
                image_url = self.base_url + image_url

            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            with open(file_path, "wb") as f:
                f.write(response.content)

            logger.info(f"画像ダウンロード完了: {file_path}")
            return True

        except Exception as e:
            logger.error(f"画像ダウンロード失敗: {file_path} - {e}")
            return False

    def fetch_images(self, jukugo: str = "例題") -> Tuple[Optional[str], Optional[str]]:
        """出題画像と解答画像を取得"""
        os.makedirs(self.images_dir, exist_ok=True)

        q_path = os.path.join(self.images_dir, f"Q_{jukugo}.jpg")
        a_path = os.path.join(self.images_dir, f"A_{jukugo}.jpg")

        try:
            url = f"{self.base_url}/{jukugo}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            q_image_url, a_image_url = self._extract_image_urls(response.text)

            q_success = False
            a_success = False

            if q_image_url:
                q_success = self._download_image(q_image_url, q_path)
            else:
                logger.warning("問題画像URLが見つかりませんでした")

            if a_image_url:
                a_success = self._download_image(a_image_url, a_path)
            else:
                logger.warning("解答画像URLが見つかりませんでした")

            return q_path if q_success else None, a_path if a_success else None

        except Exception as e:
            logger.error(f"画像取得エラー: {e}")
            return None, None

    def _get_twitter_api(self) -> Optional[tweepy.API]:
        """Twitter API認証"""
        try:
            # 設定から認証情報を取得
            api_key = config.X_API_KEY
            api_key_secret = config.X_API_KEY_SECRET
            access_token = config.X_ACCESS_TOKEN
            access_token_secret = config.X_ACCESS_TOKEN_SECRET

            logger.info("環境変数チェック:")
            logger.info(f"  X_API_KEY: {'設定済み' if api_key else '未設定'}")
            logger.info(
                f"  X_API_KEY_SECRET: {'設定済み' if api_key_secret else '未設定'}"
            )
            logger.info(f"  X_ACCESS_TOKEN: {'設定済み' if access_token else '未設定'}")
            logger.info(
                f"  X_ACCESS_TOKEN_SECRET: {'設定済み' if access_token_secret else '未設定'}"
            )

            if not all([api_key, api_key_secret, access_token, access_token_secret]):
                logger.error(
                    "Twitter API認証情報が不完全です。.envファイルを確認してください。"
                )
                return None

            auth = tweepy.OAuth1UserHandler(
                api_key,
                api_key_secret,
                access_token,
                access_token_secret,
            )
            return tweepy.API(auth)
        except Exception as e:
            logger.error(f"Twitter API認証エラー: {e}")
            return None

    def _get_twitter_client(self):
        """Twitter API v2 クライアント認証"""
        try:
            # 設定から認証情報を取得
            bearer_token = config.X_BEARER_TOKEN
            api_key = config.X_API_KEY
            api_key_secret = config.X_API_KEY_SECRET
            access_token = config.X_ACCESS_TOKEN
            access_token_secret = config.X_ACCESS_TOKEN_SECRET

            logger.info("Twitter API v2認証情報チェック:")
            logger.info(f"  X_BEARER_TOKEN: {'設定済み' if bearer_token else '未設定'}")

            if bearer_token:
                # Bearer Token認証（推奨）
                logger.info("Bearer Token認証を使用")
                return tweepy.Client(bearer_token=bearer_token)
            elif all([api_key, api_key_secret, access_token, access_token_secret]):
                # OAuth 1.0a認証
                logger.info("OAuth 1.0a認証を使用")
                return tweepy.Client(
                    consumer_key=api_key,
                    consumer_secret=api_key_secret,
                    access_token=access_token,
                    access_token_secret=access_token_secret,
                )
            else:
                logger.error("Twitter API認証情報が不完全です。")
                return None
        except Exception as e:
            logger.error(f"Twitter API v2認証エラー: {e}")
            return None

    def post_tweet(
        self, image_path: Optional[str] = None, status: str = "何の二字熟語の共通部分？"
    ) -> bool:
        """ツイートを投稿"""
        logger.info(f"ツイート投稿開始: image_path={image_path}, status={status}")

        try:
            api = self._get_twitter_api()
            if not api:
                logger.error("Twitter API認証に失敗しました")
                return False

            media_ids = []
            if image_path and os.path.exists(image_path):
                logger.info(f"画像ファイル存在確認: {image_path}")
                logger.info("メディアアップロード開始")
                media = api.media_upload(image_path)
                logger.info(f"メディアアップロード完了: media_id={media.media_id}")
                media_ids = [str(media.media_id)]

            if media_ids:
                api.update_status(status=status, media_ids=media_ids)
            else:
                api.update_status(status=status)
            logger.info("Twitter API v1.1でツイート投稿完了")
            return True
        except Exception as e:
            logger.error(f"ツイート投稿エラー: {e}", exc_info=True)
            return False

    def _load_oauth2_access_token(self) -> Optional[str]:
        """token.jsonからOAuth2 access tokenを取得"""
        try:
            data = token_store.load_token_data()
            if not data:
                return None
            access_token = data.get("access_token")
            refresh_token = data.get("refresh_token")
            expires_in = data.get("expires_in")
            obtained_at = data.get("obtained_at")

            if not access_token:
                return None

            if self._is_token_expired(expires_in, obtained_at):
                if refresh_token:
                    return self._refresh_oauth2_token(refresh_token)
                return None

            return access_token
        except Exception as e:
            logger.error(f"token.json読み込みエラー: {e}")
            return None

    def _is_token_expired(self, expires_in, obtained_at) -> bool:
        """トークン有効期限の簡易判定"""
        try:
            if not expires_in or not obtained_at:
                return False
            now = int(time.time())
            return now >= int(obtained_at) + int(expires_in) - 60
        except Exception:
            return False

    def _refresh_oauth2_token(self, refresh_token: str) -> Optional[str]:
        """refresh_tokenでアクセストークンを更新"""
        if not self.oauth_client_id or not self.oauth_client_secret:
            logger.error("OAuth client credentials are required.")
            return None

        try:
            response = requests.post(
                "https://api.twitter.com/2/oauth2/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": self.oauth_client_id,
                },
                auth=(self.oauth_client_id, self.oauth_client_secret),
                timeout=10,
            )
            response.raise_for_status()
            token_data = response.json()
            token_data["obtained_at"] = int(time.time())

            if not token_store.save_token_data(token_data):
                logger.error("token store write failed")
                return None

            return token_data.get("access_token")
        except Exception as e:
            logger.error(f"token refresh error: {e}", exc_info=True)
            return None

    def find_answer_image(self) -> Optional[str]:
        """A_から始まるファイルを検索"""
        if not os.path.exists(self.images_dir):
            logger.warning("imagesディレクトリが存在しません")
            return None

        try:
            for filename in os.listdir(self.images_dir):
                if filename.startswith("A_") and os.path.isfile(
                    os.path.join(self.images_dir, filename)
                ):
                    file_path = os.path.join(self.images_dir, filename)
                    logger.info(f"解答画像が見つかりました: {filename}")
                    return file_path
        except OSError as e:
            logger.error(f"imagesディレクトリの読み込みエラー: {e}")

        logger.warning("A_から始まるファイルが見つかりませんでした")
        return None

    def post_question(self, jukugo: str = "例題", test_mode: bool = False) -> bool:
        """問題投稿の一連の処理"""
        try:
            logger.info(f"問題投稿開始: jukugo={jukugo}, test_mode={test_mode}")

            # 既存ファイルのクリーンアップ
            self._cleanup_old_files()

            # 画像取得
            logger.info("画像取得開始")
            q_path, a_path = self.fetch_images(jukugo)
            logger.info(f"画像取得結果: q_path={q_path}, a_path={a_path}")

            # 問題画像でツイート投稿
            if q_path:
                if test_mode:
                    logger.info(f"テストモード: ツイート投稿をスキップ - {q_path}")
                    return True
                else:
                    logger.info(f"問題画像でツイート投稿開始: {q_path}")
                    result = self.post_tweet(q_path, "何の二字熟語の共通部分？")
                    logger.info(f"ツイート投稿結果: {result}")
                    return result
            else:
                logger.error("問題画像の取得に失敗しました")
                return False

        except Exception as e:
            logger.error(f"問題投稿エラー: {e}", exc_info=True)
            return False

    def post_answer(self) -> bool:
        """解答投稿の一連の処理"""
        try:
            # 解答画像を検索
            answer_image = self.find_answer_image()

            if answer_image:
                return self.post_tweet(answer_image, f"答え: {answer_image[2:-4]}")
            else:
                logger.error("解答画像が見つかりませんでした")
                return False

        except Exception as e:
            logger.error(f"解答投稿エラー: {e}")
            return False

    def post_answer_for_jukugo(
        self, jukugo: str, test_mode: bool = False
    ) -> bool:
        """指定熟語の解答画像を生成して投稿"""
        try:
            logger.info(f"解答投稿開始: jukugo={jukugo}, test_mode={test_mode}")

            # 既存ファイルのクリーンアップ
            self._cleanup_old_files()

            # 画像取得
            logger.info("画像取得開始")
            q_path, a_path = self.fetch_images(jukugo)
            logger.info(f"画像取得結果: q_path={q_path}, a_path={a_path}")

            if a_path:
                if test_mode:
                    logger.info(f"テストモード: ツイート投稿をスキップ - {a_path}")
                    return True
                result = self.post_tweet(a_path, "昨日の答え")
                logger.info(f"ツイート投稿結果: {result}")
                return result

            logger.error("解答画像の取得に失敗しました")
            return False
        except Exception as e:
            logger.error(f"解答投稿エラー: {e}", exc_info=True)
            return False


# 後方互換性のための関数
def question(jukugo: str = "例題"):
    """問題投稿（後方互換性）"""
    bot = XBot()
    return bot.post_question(jukugo)


def answer():
    """解答投稿（後方互換性）"""
    bot = XBot()
    return bot.post_answer()


def random_jukugo():
    """ランダム四字熟語取得（後方互換性）"""
    bot = XBot()
    return bot.get_random_jukugo()


def fetch_random_image(jukugo: str = "例題"):
    """画像取得（後方互換性）"""
    bot = XBot()
    bot._cleanup_old_files()
    return bot.fetch_images(jukugo)


def get_api():
    """Twitter API取得（後方互換性）"""
    bot = XBot()
    return bot._get_twitter_api()


def post_tweet(image_path=None):
    """ツイート投稿（後方互換性）"""
    bot = XBot()
    return bot.post_tweet(image_path)

    # bot = XBot()
    # success = bot.post_question("例題")
    # if success:
    #     print("✅ 問題投稿完了")
    # else:
    #     print("❌ 問題投稿失敗")
