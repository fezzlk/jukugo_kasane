# Kasane - 四字熟語クイズボット

四字熟語のクイズ問題を X（旧 Twitter）に投稿するボットと、画像生成 Web アプリケーションです。

## 機能

- ランダムな四字熟語の取得
- 問題画像と解答画像の自動生成
- X（Twitter）への自動投稿
- RESTful API エンドポイント
- Web インターフェース

## プロジェクト構成

```
kasane/
├── image_generator/     # 画像生成モジュール
├── xbot/                # X（Twitter）投稿用ボット
├── main.py              # Web/API サーバー
├── config.py            # 設定管理
├── logger.py            # ログ設定
├── requirements.txt     # 依存関係
├── Dockerfile           # Docker設定
├── images/              # 生成された画像保存先
├── static/              # 静的ファイル
├── templates/           # HTMLテンプレート
└── README.md            # このファイル
```

## セットアップ

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env`ファイルを作成し、以下の変数を設定してください：

```env
# Twitter API v2（推奨）
X_BEARER_TOKEN=your_bearer_token_here

# Twitter API v1.1（フォールバック用）
X_API_KEY=your_api_key_here
X_API_KEY_SECRET=your_api_key_secret_here
X_ACCESS_TOKEN=your_access_token_here
X_ACCESS_TOKEN_SECRET=your_access_token_secret_here

# アプリケーション設定
FLASK_ENV=development
LOG_LEVEL=INFO
SECRET_KEY=your_secret_key_here
```

**注意**: Twitter API v2 の Bearer Token があれば、v1.1 の認証情報は不要です。

### 3. 実行

#### Web アプリケーションとして実行

```bash
# Web/API サーバー
python main.py
```

#### ボットとして実行

API 経由で `POST /question` と `POST /answer` を使用してください。

## API エンドポイント

### Web アプリケーション (main.py - Port 8080)

- `GET /` - メインページ
- `GET /<word>` - 指定された文字で画像生成
- `GET /generate?jukugo=<word>&font=<font>` - クエリ指定で画像生成（fontは任意）
- `GET /q/<word>?font=<font>` - 問題画像を取得（fontは任意）
- `GET /a/<word>?font=<font>` - 解答画像を取得（fontは任意）
- `GET /health` - ヘルスチェック

### API サーバー (main.py - Port 8080)

#### GET/POST /question

問題画像を投稿します。

```bash
# GETリクエスト
curl http://localhost:8080/question
curl http://localhost:8080/question?jukugo=例題

# POSTリクエスト
curl -X POST http://localhost:8080/question
curl -X POST -H "Content-Type: application/json" -d '{"jukugo":"例題"}' http://localhost:8080/question

# テストモード（ツイート投稿なし）
curl http://localhost:8080/question?test=true
curl -X POST -H "Content-Type: application/json" -d '{"jukugo":"例題","test":true}' http://localhost:8080/question
```

#### GET/POST /answer

解答画像を投稿します。

```bash
# GETリクエスト
curl http://localhost:8080/answer

# POSTリクエスト
curl -X POST http://localhost:8080/answer
```

#### GET /jukugo/random

ランダムな四字熟語を取得します。

```bash
curl http://localhost:8080/jukugo/random
```

#### GET /health

ヘルスチェックを行います。

```bash
curl http://localhost:8080/health
```

## Docker での実行

```bash
# イメージをビルド
docker build -t kasane-bot .

# コンテナを実行
docker run -p 8080:8080 --env-file .env kasane-bot
```

## トラブルシューティング

### 「問題投稿に失敗しました」エラーが発生する場合

1. **環境変数の確認**

   ```bash
   # .envファイルが存在するか確認
   ls -la .env

   # 環境変数が設定されているか確認
   python -c "from dotenv import load_dotenv; import os; load_dotenv(); print('X_BEARER_TOKEN:', 'OK' if os.getenv('X_BEARER_TOKEN') else 'NG')"
   ```

2. **Twitter API アクセスレベルの確認**

   - 403 Forbidden エラーが発生する場合、Twitter API のアクセスレベルが不足している可能性があります
   - Twitter Developer Portal でより高いアクセスレベルを申請してください
   - または、Twitter API v2 の Bearer Token を取得してください

3. **テストモードでの実行**

   ```bash
   # ツイート投稿をスキップして画像取得のみテスト
   curl http://localhost:8080/question?test=true
   ```

4. **ログの確認**

   - アプリケーションログで詳細なエラー情報を確認
   - Twitter API 認証エラー、画像取得エラーなどを特定

5. **手動テスト**
   ```bash
   # API 経由でデバッグ
   curl http://localhost:8080/question?test=true
   ```

## 主な改善点

1. **モジュール化**: 機能を適切に分離し、再利用性を向上
2. **設定管理**: 統一された設定システム
3. **ログ機能**: 構造化されたログ出力
4. **エラーハンドリング**: 適切な例外処理とエラーメッセージ
5. **API 設計**: RESTful なエンドポイント設計
6. **画像管理**: 専用の images ディレクトリで画像を管理
7. **Twitter API v2 対応**: 最新の API に対応
8. **テストモード**: 開発・テスト用の機能

## 開発

### 環境設定

```bash
# 開発環境
export FLASK_ENV=development
export LOG_LEVEL=DEBUG

# 本番環境
export FLASK_ENV=production
export LOG_LEVEL=WARNING
```

### テスト

```bash
# API のテスト
curl http://localhost:8080/health

# 画像生成のテスト
curl http://localhost:8080/例題
```

## ライセンス

このプロジェクトは MIT ライセンスの下で公開されています。
