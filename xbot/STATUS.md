## X投稿機能の現状（保留）

### うまく動かなかった概要
- OAuth2 user context で取得した access_token を使っても `/2/users/me` が常に 403 Forbidden になる。
- 同じ token で `/2/tweets` も 403 になり、投稿できない。

### 試行した対策
- 新規 App 作成、User authentication 有効化、Read and Write 設定、Callback/Website 設定。
- スコープ確認（`tweet.write users.read offline.access`）と再認可。
- Cloud Run で token.json を GCS 保存、`accesstoken.json` も出力。
- `/diagnostics/oauth2` でサーバ内トークンの `/2/users/me` 直接確認（結果は 403）。
- OAuth1.0a も試したが Free プランの制限で v1.1 投稿が不可（453）。

### 現在の状況
- X Developer Support に問い合わせ中。
