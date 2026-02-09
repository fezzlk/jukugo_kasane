# -*- coding:utf8 -*-
import os
import logging
import json
from urllib.parse import urlencode
from flask import (
    Flask,
    render_template,
    send_from_directory,
    jsonify,
    request,
)
from image_generator import ImageGenerator
from line import store as line_store
from line.handler import LineHandler
from line.image_store import GcsImageStore, LocalImageStore
from line.profile import LineProfileClient
from line.quiz_store import DatastoreQuizStore, SqliteQuizStore

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "")

# 画像生成器を初期化
generator = ImageGenerator()
# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
server_fqdn = os.getenv("SERVER_FQDN", "").rstrip("/")
line_channel_secret = os.getenv("LINE_CHANNEL_SECRET", "")
line_channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
line_default_font_key = "default"
line_image_storage = os.getenv("LINE_IMAGE_STORAGE", "local").strip().lower()
line_gcs_bucket = os.getenv("LINE_GCS_BUCKET", "")
line_gcs_prefix = os.getenv("LINE_GCS_PREFIX", "line-images")
line_bot_user_id = os.getenv("LINE_BOT_USER_ID", "").strip()
line_bot_name = os.getenv("LINE_BOT_NAME", "").strip() or "文字合成ボット"
line_quiz_db_path = os.getenv("LINE_QUIZ_DB_PATH", "line/quiz.db").strip()
line_quiz_store_mode = os.getenv("LINE_QUIZ_STORE", "sqlite").strip().lower()
line_firestore_project = os.getenv("LINE_FIRESTORE_PROJECT", "").strip()

def _mask_presence(value: str) -> str:
    return "set" if value else "missing"

logger.info(
    "Secret/env presence: LINE_CHANNEL_SECRET=%s, LINE_CHANNEL_ACCESS_TOKEN=%s, "
    "LINE_BOT_USER_ID=%s, SERVER_FQDN=%s",
    _mask_presence(line_channel_secret),
    _mask_presence(line_channel_access_token),
    _mask_presence(line_bot_user_id),
    _mask_presence(server_fqdn),
)
print(
    "Secret/env presence: LINE_CHANNEL_SECRET=%s, LINE_CHANNEL_ACCESS_TOKEN=%s, "
    "LINE_BOT_USER_ID=%s, SERVER_FQDN=%s"
    % (
        _mask_presence(line_channel_secret),
        _mask_presence(line_channel_access_token),
        _mask_presence(line_bot_user_id),
        _mask_presence(server_fqdn),
    ),
    flush=True,
)


def build_generate_url(word, font_key):
    query = {"jukugo": word}
    if font_key and font_key != "default":
        query["font"] = font_key
    query_string = urlencode(query)
    return (
        f"{server_fqdn}/generate?{query_string}"
        if server_fqdn
        else f"/generate?{query_string}"
    )


def build_line_usage_text(bot_name: str) -> str:
    return (
        "【合成機能】\n"
        "送信された文字（2〜8文字）を合成し、共通部分/和集合画像を生成します。\n"
        "\n"
        "【出題機能】\n"
        "問題登録/一覧/出題/正誤判定を行います。\n"
        "・問題登録: 「1.熟語」のように送信（10問まで）\n"
        "・問題一覧: 「#問題一覧」\n"
        f"・出題: グループで「@{bot_name} + (問題番号)」\n"
        f"・正解発表: グループで「@{bot_name} 答え (問題番号)」\n"
        "・正誤判定: グループで「@(出題者) + (問題番号).(解答)」\n"
        "\n"
        "【設定機能】\n"
        "フォントを変更できます。\n"
        "設定: 「#設定」と送信。\n"
        "\n"
        "※ 画像生成には時間がかかる場合があります。"
    )


def build_line_quick_reply() -> dict:
    items = [
        {
            "type": "action",
            "action": {"type": "message", "label": "合成", "text": "#合成"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "問題登録", "text": "#問題登録"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "問題一覧", "text": "#問題一覧"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "設定", "text": "#設定"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "使い方", "text": "#使い方"},
        },
    ]
    return {"items": items}


def build_line_settings_quick_reply() -> dict:
    items = [
        {
            "type": "action",
            "action": {"type": "message", "label": "フォント", "text": "#フォント"},
        },
    ]
    return {"items": items}


def build_line_mode_quick_reply() -> dict:
    items = [
        {
            "type": "action",
            "action": {"type": "message", "label": "共通部分", "text": "#共通部分"},
        },
        {
            "type": "action",
            "action": {"type": "message", "label": "和集合", "text": "#和集合"},
        },
    ]
    return {"items": items}


def build_line_font_quick_reply() -> dict:
    default_key = generator.get_default_font_key()
    default_label = "デフォルト"
    if default_key == "mincho":
        default_label = "明朝(デフォルト)"
    font_labels = {
        "default": default_label,
        "mincho": "明朝",
        "monogothic": "源暎ゴシック",
        "hiragino": "ヒラギノ",
        "dejavu": "DejaVuSans",
    }
    items = []
    for font_key in generator.get_font_keys():
        label = font_labels.get(font_key, font_key)
        items.append(
            {
                "type": "action",
                "action": {
                    "type": "message",
                    "label": label,
                    "text": f"#フォント {font_key}",
                },
            }
        )
    return {"items": items}


line_texts = {
    "welcome_prefix": f"{line_bot_name}です。\n文字の共通部分と和集合を画像生成します\n\n",
    "usage": build_line_usage_text(line_bot_name),
    "generate_prompt": "合成する文字を送信してください。",
    "register_help": "「1.出題文字」のように送信すると出題用に文字を登録します。",
    "settings_prompt": "設定項目を選択してください。",
    "mode_prompt": "出題モードを選択してください。",
    "mode_set_common": "出題モードを共通部分に設定しました。\n設定した値は今後追加された問題に適用されます。",
    "mode_set_union": "出題モードを和集合に設定しました。\n設定した値は今後追加された問題に適用されます。",
    "font_prompt": "フォントを選択してください。",
    "settings_updated": "設定を更新しました: {settings}",
    "font_set": "フォントを {font} に設定しました。",
    "save_failed": "設定の保存に失敗しました。",
    "need_word": "熟語を指定してください。",
    "not_two_chars": "2〜8文字で送ってください。",
    "invalid_word": "使用できない文字が含まれています。",
    "invalid_number": "問題番号は1〜10にしてください。",
    "answer_format": "解答は以下のフォーマットで送信してください。\n@出題者へのメンション (問題番号).(解答)",
    "unregistered_template": "{number}問目は未登録です。",
    "mention_fallback": "ユーザー",
    "quiz_prompt_common": "何の共通部分？",
    "quiz_prompt_union": "何の和集合？",
    "quiz_answer_template": "【解答フォーマット】\n@{name} {number}.(解答)",
    "bot_name": line_bot_name,
    "quiz_format": f"@{line_bot_name} (問題番号)",
    "quiz_dispatch_template": f"グループで「@{line_bot_name} {{number}}」と送ると出題されます。",
    "quiz_dispatch_list": f"グループで「@{line_bot_name} (問題番号)」と送ると出題されます。",
    "quiz_mode_note": "共通部分/和集合どちらで出題するかは「#設定」から変更できます。",
    "quiz_prompt_invalid_char": "問題文に@は使用できません。",
    "quiz_prompt_too_long": "問題文は20文字以内で指定してください。",
    "quiz_answer_invalid_char": "解答に@は使用できません。",
    "quiz_answer_too_long": "解答は20文字以内で指定してください。",
    "quiz_mode_invalid": "出題モードは共通部分/和集合で指定してください。",
    "quiz_format_help": "出題モードや問題文を変更するには以下のフォーマットで送信してください。",
    "quiz_format_details": "(問題番号).(文字)\n【問題文】ここに問題文を入力\n【解答】合成文字とは別の解答があればここに入力\n【出題モード】共通部分/和集合（デフォルトは共通部分",
    "quiz_format_invalid": "問題登録の形式が正しくありません。",
    "answer_release_format": f"解答発表は「@{line_bot_name} 答え (問題番号)」と送ってください。",
    "bulk_update_success": "問題一覧を更新しました。",
    "bulk_update_failed": "問題一覧の形式が正しくありません。",
    "answer_template": "{name}さん、{result}です。",
    "quiz_list_title": "【問題一覧】",
    "quiz_list_footer": f"グループで「@{line_bot_name} (問題番号)」と送ると出題されます。",
    "synth_result": "「{word}」の合成結果です。",
    "quiz_unset": "未設定",
    "generate_failed": "画像の生成に失敗しました。",
    "answer_correct": "正解",
    "answer_incorrect": "不正解",
    "error_prefix": "エラー: ",
    "invalid_signature": "Invalid signature",
    "bad_request": "Bad Request",
}

line_keywords = {
    "help": ["使い方", "ヘルプ", "help"],
    "setting": "設定",
    "font": "フォント",
    "list": "問題一覧",
    "menu_generate": "合成",
    "menu_register": "問題登録",
    "menu_list": "問題一覧",
    "menu_settings": "設定",
    "menu_usage": "使い方",
    "menu_font": "フォント",
    "font_prefix": "font_",
}

if line_image_storage == "gcs":
    line_image_store = GcsImageStore(line_gcs_bucket, line_gcs_prefix, logger)
else:
    line_image_store = LocalImageStore(server_fqdn)

if line_quiz_store_mode == "datastore":
    line_quiz_store = DatastoreQuizStore(line_firestore_project, logger)
else:
    line_quiz_store = SqliteQuizStore(line_quiz_db_path, logger)
if not line_bot_user_id:
    logger.warning("LINE_BOT_USER_ID is missing; group quiz is disabled.")

line_handler = LineHandler(
    channel_secret=line_channel_secret,
    channel_access_token=line_channel_access_token,
    server_fqdn=server_fqdn,
    generator=generator,
    settings_store=line_store,
    logger=logger,
    texts=line_texts,
    keywords=line_keywords,
    quick_reply_builder=build_line_quick_reply,
    default_font_key=line_default_font_key,
    image_store=line_image_store,
    quiz_store=line_quiz_store,
    bot_user_id=line_bot_user_id,
    settings_quick_reply_builder=build_line_settings_quick_reply,
    mode_quick_reply_builder=build_line_mode_quick_reply,
    font_quick_reply_builder=build_line_font_quick_reply,
    profile_client=LineProfileClient(line_channel_access_token, logger),
)


@app.route("/")
def index():
    """メインページ"""
    return render_template("index.html", font_options=generator.get_font_keys())


@app.route("/<word>")
def generate(word):
    """メインフォーム"""
    try:
        font_key = request.args.get("font")
        normalized_font_key = generator.normalize_font_key(font_key)
        if len(word) == 2:
            q_path, a_path = generator.generate_images(word, font_key)
            return render_template(
                "generate.html",
                word=word,
                font=normalized_font_key,
                show_answer=True,
                show_union=False,
                show_video=False,
            )
        q_path, a_path, u_path = generator.generate_images_with_union(word, font_key)
        show_video = len(word) >= 3
        if show_video:
            generator.generate_union_video(word, font_key, fps=1)
        return render_template(
            "generate.html",
            word=word,
            font=normalized_font_key,
            show_answer=False,
            show_union=True,
            show_video=show_video,
        )
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        logger.error(f"画像生成エラー: {e}")
        return f"エラーが発生しました: {e}", 500


@app.route("/generate")
def form_query():
    """クエリパラメータjukugoで画像生成"""
    jukugo = request.args.get("jukugo")
    if not jukugo:
        return "jukugo is required", 400
    try:
        font_key = request.args.get("font")
        normalized_font_key = generator.normalize_font_key(font_key)
        if len(jukugo) == 2:
            q_path, a_path = generator.generate_images(jukugo, font_key)
            return render_template(
                "generate.html",
                word=jukugo,
                font=normalized_font_key,
                show_answer=True,
                show_union=False,
                show_video=False,
            )
        q_path, a_path, u_path = generator.generate_images_with_union(jukugo, font_key)
        show_video = len(jukugo) >= 3
        if show_video:
            generator.generate_union_video(jukugo, font_key, fps=1)
        return render_template(
            "generate.html",
            word=jukugo,
            font=normalized_font_key,
            show_answer=False,
            show_union=True,
            show_video=show_video,
        )
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        logger.error(f"画像生成エラー: {e}")
        return f"エラーが発生しました: {e}", 500


@app.route("/q/<word>")
def get_q(word):
    """問題画像を返す"""
    try:
        font_key = generator.normalize_font_key(request.args.get("font"))
        suffix = "" if font_key == "default" else f"_{font_key}"
        filename = f"Q_{word}{suffix}.png"
        file_path = os.path.join(generator.images_dir, filename)
        if not os.path.exists(file_path):
            generate_url = build_generate_url(word, font_key)
            return (
                f'画像生成が未実行です。<a href="{generate_url}">生成する</a>',
                404,
            )
        return send_from_directory(generator.images_dir, filename)
    except ValueError as e:
        return str(e), 400


@app.route("/a/<word>")
def get_a(word):
    """解答画像を返す"""
    try:
        font_key = generator.normalize_font_key(request.args.get("font"))
        suffix = "" if font_key == "default" else f"_{font_key}"
        filename = f"A_{word}{suffix}.png"
        file_path = os.path.join(generator.images_dir, filename)
        if not os.path.exists(file_path):
            generate_url = build_generate_url(word, font_key)
            return (
                f'画像生成が未実行です。<a href="{generate_url}">生成する</a>',
                404,
            )
        return send_from_directory(generator.images_dir, filename)
    except ValueError as e:
        return str(e), 400


@app.route("/u/<word>")
def get_u(word):
    """和集合画像を返す"""
    try:
        font_key = generator.normalize_font_key(request.args.get("font"))
        suffix = "" if font_key == "default" else f"_{font_key}"
        filename = f"U_{word}{suffix}.png"
        file_path = os.path.join(generator.images_dir, filename)
        if not os.path.exists(file_path):
            generator.generate_images_with_union(word, font_key)
        return send_from_directory(generator.images_dir, filename)
    except ValueError as e:
        return str(e), 400


@app.route("/p/<word>")
def get_p(word):
    """動画プレビュー画像を返す"""
    try:
        font_key = generator.normalize_font_key(request.args.get("font"))
        suffix = "" if font_key == "default" else f"_{font_key}"
        filename = f"P_{word}{suffix}.png"
        file_path = os.path.join(generator.images_dir, filename)
        if not os.path.exists(file_path):
            generator.generate_union_video(word, font_key, fps=1)
        return send_from_directory(generator.images_dir, filename)
    except ValueError as e:
        return str(e), 400


@app.route("/v/<word>")
def get_v(word):
    """動画を返す"""
    try:
        font_key = generator.normalize_font_key(request.args.get("font"))
        suffix = "" if font_key == "default" else f"_{font_key}"
        filename = f"V_{word}{suffix}.mp4"
        file_path = os.path.join(generator.images_dir, filename)
        if not os.path.exists(file_path):
            generator.generate_union_video(word, font_key, fps=1)
        return send_from_directory(generator.images_dir, filename)
    except ValueError as e:
        return str(e), 400


@app.route("/health", methods=["GET"])
def health_check():
    """ヘルスチェック"""
    return {"status": "healthy", "service": "kasane-web", "version": "2.0.0"}


def _handle_line_callback():
    """LINE Messaging API webhook"""
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    response_text, status_code = line_handler.handle_callback(body, signature)
    return response_text, status_code


@app.route("/line/callback", methods=["POST"])
def line_callback():
    return _handle_line_callback()


@app.route("/callback", methods=["POST"])
def line_callback_alias():
    return _handle_line_callback()


@app.route("/", methods=["POST"])
def line_callback_root():
    return _handle_line_callback()
@app.errorhandler(404)
def not_found(error):
    """404エラーハンドラー"""
    return jsonify(
        {"status": "error", "message": "エンドポイントが見つかりません"}
    ), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """405エラーハンドラー"""
    allowed_methods = getattr(error, "valid_methods", [])
    return jsonify(
        {
            "status": "error",
            "message": "メソッドが許可されていません",
            "allowed_methods": allowed_methods,
        }
    ), 405


@app.errorhandler(500)
def internal_error(error):
    """500エラーハンドラー"""
    logger.error(f"内部サーバーエラー: {error}")
    return jsonify(
        {"status": "error", "message": "内部サーバーエラーが発生しました"}
    ), 500

    # background_size = (1024, 1024)
    # background_color = (255, 255, 255, 255)
    # # font_path = '/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc'
    # font_path = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
    # text_size = 1024
    # font = ImageFont.truetype(font_path, text_size)
    # text_color = BLACK

    # kanji1 = Image.new("RGBA", background_size, background_color)
    # d1 = ImageDraw.Draw(kanji1)
    # d1.text((0, 0), word[0], font=font, fill=text_color)
    # p1 = kanji1.load()

    # kanji2 = Image.new("RGBA", background_size, background_color)
    # d2 = ImageDraw.Draw(kanji2)
    # d2.text((0, 0), word[1], font=font, fill=text_color)
    # p2 = kanji2.load()

    # # Question
    # q_image = Image.new("RGB", (1024, 1024))
    # q_pix = q_image.load()
    # # Answer
    # a_image = Image.new("RGB", (1024, 1024))
    # a_pix = a_image.load()

    # for x, y in product(*map(range, (1024, 1024))):
    #     if p1[x, y] == BLACK:
    #         if p2[x, y] == BLACK:
    #             a_pix[x, y] = PURPLE
    #             q_pix[x, y] = BLACK
    #         else:
    #             a_pix[x, y] = BLUE
    #             q_pix[x, y] = WHITE
    #     else:
    #         q_pix[x, y] = WHITE
    #         if p2[x, y] == BLACK:
    #             a_pix[x, y] = RED
    #         else:
    #             a_pix[x, y] = WHITE

    # q_image.show()
    # q_image.save(f"Q_{word}.png")
    # a_image.save(f"A_{word}.png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
