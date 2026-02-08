# 機能仕様書: Kasane

## 概要
Kasane は Flask ベースの Web アプリケーションおよびボット群で、漢字のクイズ画像生成、X（旧 Twitter）への投稿、LINE 連携による対話機能を提供します。主な構成は以下です。
- クイズ画像や和集合/共通部分の生成を行う Web UI
- X への問題・解答投稿用 API
- LINE Messaging API webhook による画像合成・出題管理・グループ出題

## 基本ルール
- 文字数のルール:
  - 2文字: 共通部分の問題画像(Q)と解答画像(A)を生成
  - 2〜8文字: 共通部分(Q)と和集合(U)を生成
  - 3〜8文字: 和集合の動画(V)とプレビュー(P)を生成
- 画像サイズ: 1024x1024
- 2文字の解答画像の色分け:
  - 紫: 共通部分
  - 青: 1文字目のみ
  - 赤: 2文字目のみ

## Web アプリケーション (Flask)

### ルート
- `GET /`
  - メインページを表示（フォント選択を含む）
- `GET /<word>`
  - パス指定の語で画像生成・表示
  - 2文字: Q/A を表示
  - 3文字以上: Q/U を表示し、和集合動画も生成
- `GET /generate?jukugo=<word>&font=<font>`
  - クエリ指定で `/<word>` と同等の生成を実行
- `GET /q/<word>?font=<font>`
  - 問題画像(Q)を返す。未生成の場合は404と生成リンク
- `GET /a/<word>?font=<font>`
  - 解答画像(A)を返す。未生成の場合は404と生成リンク
- `GET /u/<word>?font=<font>`
  - 和集合画像(U)を返す。未生成の場合は生成して返却
- `GET /p/<word>?font=<font>`
  - 動画プレビュー画像(P)を返す。未生成の場合は生成して返却
- `GET /v/<word>?font=<font>`
  - 和集合動画(V)を返す。未生成の場合は生成して返却
- `GET /health`
  - ヘルスチェック JSON を返す

### フォント取り扱い
- 対応キー: `default`, `mincho`, `monogothic`, `hiragino`, `dejavu`
- キーは2〜10文字の英数字、かつ `default` 以外は定義済みである必要があります

## X (Twitter) ボット

### 投稿フロー
- `/question`:
  - ローカル Web から Q/A 画像を取得し、Q 画像で問題投稿
  - テストモード（投稿スキップ）とメディア省略に対応
- `/answer`:
  - images 配下の最新 A 画像を投稿
- `/answer/by-jukugo?jukugo=<word>`:
  - 指定熟語の A 画像を生成して投稿
- `/question/by-date?date=YYYY/MM/DD`:
  - Google スプレッドシート CSV から指定日付の2文字熟語を取得して出題

### 認証
- OAuth 2.0(User Context)でツイート作成
- トークンは `token.json` または GCS 保存（設定時）
- 画像アップロードは OAuth 1.0a を使用

## LINE ボット

### Webhook
- `POST /line/callback`, `POST /callback`, `POST /` で同一ハンドラ
- `LINE_CHANNEL_SECRET` による署名検証が必須

### 1:1 チャット
- 画像合成:
  - 2〜8文字で共通部分/和集合画像を返す
  - 3〜8文字で和集合動画も返す
- 問題登録:
  - `1.<word>` 〜 `10.<word>` で出題用熟語を登録
  - 文字数は2〜8
- 設定:
  - 出題モード（共通部分/和集合）、フォント、問題文を設定可能
  - 設定は `line_settings.json` もしくは `LINE_SETTINGS_FILE_PATH` に保存
- 一括更新:
  - 問題一覧の全文貼り付けで10問分を一括更新

### グループ機能
- ボットへのメンション:
  - `@BotName <number>` で該当問題を出題
  - `@BotName 答え <number>` で解答画像/動画を表示
- 他ユーザーへのメンション:
  - `@User <number>.<answer>` で正誤判定を返す

### ストレージ
- 画像配信:
  - ローカル: `SERVER_FQDN` から HTTPS で配信
  - GCS: Cloud Storage にアップロードし公開 URL を返信
- 問題保存:
  - SQLite（デフォルト）: `LINE_QUIZ_DB_PATH`
  - Datastore: `LINE_QUIZ_STORE=datastore`

## 画像生成
- PIL を用いて 1024x1024 の漢字画像を生成
- 共通部分・和集合はピクセル単位で合成
- 動画は ffmpeg でフレームを連結して生成

## 外部依存
- `ffmpeg`（動画生成）
- `PIL`（Pillow）
- `tweepy`（X メディアアップロード）
- `requests`, `BeautifulSoup`（外部取得と解析）

## 設定（環境変数）
- Web:
  - `SECRET_KEY`, `PORT`, `SERVER_FQDN`
- X (Twitter):
  - `X_CLIENT_ID`, `X_CLIENT_SECRET`
  - `X_BEARER_TOKEN`
  - `X_API_KEY`, `X_API_KEY_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
- 外部データ:
  - `KASANE_API_URL`, `JUKUGO_API_URL`
  - `SPREADSHEET_URL` または `SPREADSHEET_ID` + `SPREADSHEET_GID`
- LINE:
  - `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`
  - `LINE_BOT_USER_ID`, `LINE_BOT_NAME`
  - `LINE_IMAGE_STORAGE`, `LINE_GCS_BUCKET`, `LINE_GCS_PREFIX`
  - `LINE_SETTINGS_FILE_PATH`, `LINE_QUIZ_DB_PATH`, `LINE_QUIZ_STORE`, `LINE_FIRESTORE_PROJECT`

## エラーハンドリング
- API は JSON 形式でエラーを返却
- 404/405 は JSON 形式で返却
- LINE Webhook は署名不一致で 403、不正ペイロードで 400
