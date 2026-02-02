import os


class Config:
    """アプリケーション設定クラス"""

    # 基本設定
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # ログ設定
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # ディレクトリ設定
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    IMAGES_DIR = os.path.join(BASE_DIR, "images")
    STATIC_DIR = os.path.join(BASE_DIR, "static")
    TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

    # Twitter API設定
    X_API_KEY = os.environ.get("X_API_KEY")
    X_API_KEY_SECRET = os.environ.get("X_API_KEY_SECRET")
    X_ACCESS_TOKEN = os.environ.get("X_ACCESS_TOKEN")
    X_ACCESS_TOKEN_SECRET = os.environ.get("X_ACCESS_TOKEN_SECRET")
    X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN")

    # 外部API設定
    KASANE_API_URL = os.environ.get("KASANE_API_URL")
    JUKUGO_API_URL = os.environ.get("JUKUGO_API_URL")
    SPREADSHEET_URL = os.environ.get("SPREADSHEET_URL")
    SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
    SPREADSHEET_GID = os.environ.get("SPREADSHEET_GID")

    # フォント設定
    FONT_PATHS = [
        "/app/.fonts/Honoka_Shin_Mincho_L.otf",
        "/app/.fonts/GenEiMonoGothic-Regular.ttf",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",  # macOS
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # Linux
    ]

    # 画像設定
    IMAGE_SIZE = (1024, 1024)
    TEXT_SIZE = 1024

    # カラー設定
    COLORS = {
        "BLACK": (0, 0, 0, 255),
        "WHITE": (255, 255, 255, 255),
        "PURPLE": (70, 20, 190, 255),
        "BLUE": (70, 65, 225, 255),
        "RED": (230, 70, 70, 255),
    }

    # フォールバック四字熟語
    FALLBACK_JUKUGO = ["一期一会", "温故知新", "風林火山", "百発百中"]

    # サーバー設定
    API_HOST = "0.0.0.0"
    API_PORT = 8080
    WEB_HOST = "0.0.0.0"
    WEB_PORT = 8081


class DevelopmentConfig(Config):
    """開発環境設定"""

    DEBUG = True
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    """本番環境設定"""

    DEBUG = False
    LOG_LEVEL = "WARNING"


class TestingConfig(Config):
    """テスト環境設定"""

    TESTING = True
    LOG_LEVEL = "DEBUG"


# 設定辞書
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config() -> Config:
    """環境に応じた設定を取得"""
    env = os.environ.get("FLASK_ENV", "default")
    return config.get(env, config["default"])
