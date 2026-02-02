import logging
import sys
from typing import Optional
from config import get_config


def setup_logger(
    name: Optional[str] = None, level: Optional[str] = None
) -> logging.Logger:
    """ログ設定を初期化"""
    config = get_config()

    # ログレベルを設定
    log_level = level or config.LOG_LEVEL

    # ログフォーマットを設定
    formatter = logging.Formatter(config.LOG_FORMAT)

    # ロガーを作成
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # 既存のハンドラーをクリア
    logger.handlers.clear()

    # コンソールハンドラーを追加
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # ファイルハンドラーを追加（本番環境）
    if config.LOG_LEVEL.upper() in ["WARNING", "ERROR"]:
        file_handler = logging.FileHandler("app.log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """設定済みロガーを取得"""
    return setup_logger(name)
