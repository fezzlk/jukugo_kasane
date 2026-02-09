# Kasane - 四字熟語クイズボット

四字熟語のクイズ画像を生成し、LINE 連携で出題/回答できる Web アプリケーションです。

## 機能

- 問題画像と解答画像の生成
- LINE 連携（出題・回答・設定）
- RESTful API エンドポイント
- Web インターフェース

## プロジェクト構成

```
kasane/
├── image_generator/     # 画像生成モジュール
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
# アプリケーション設定
FLASK_ENV=development
LOG_LEVEL=INFO
SECRET_KEY=your_secret_key_here
```

### 3. 実行

#### Web アプリケーションとして実行

```bash
# Web/API サーバー
python main.py
```

## API エンドポイント

### Web アプリケーション (main.py - Port 8080)

- `GET /` - メインページ
- `GET /<word>` - 指定された文字で画像生成
- `GET /generate?jukugo=<word>&font=<font>` - クエリ指定で画像生成（fontは任意）
- `GET /q/<word>?font=<font>` - 問題画像を取得（fontは任意）
- `GET /a/<word>?font=<font>` - 解答画像を取得（fontは任意）
- `GET /health` - ヘルスチェック

### LINE Webhook

LINE Messaging API の webhook は `POST /line/callback` を利用します。

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

## 主な改善点

1. **モジュール化**: 機能を適切に分離し、再利用性を向上
2. **設定管理**: 統一された設定システム
3. **ログ機能**: 構造化されたログ出力
4. **エラーハンドリング**: 適切な例外処理とエラーメッセージ
5. **API 設計**: RESTful なエンドポイント設計
6. **画像管理**: 専用の images ディレクトリで画像を管理

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
