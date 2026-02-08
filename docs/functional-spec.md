# Functional Specification: Kasane

## Overview
Kasane is a Flask-based web application and bot suite that generates image-based kanji quizzes, posts them to X (Twitter), and provides interactive features via LINE. It includes:
- A web UI for generating quiz images and union/intersection visuals.
- REST-style API endpoints for posting quiz questions/answers to X.
- A LINE Messaging API webhook that supports image synthesis, quiz registration, and group quiz gameplay.

## Core Concepts
- Word length rules:
  - 2 characters: intersection quiz image (Q) and answer image (A).
  - 2 to 8 characters: intersection (Q) and union (U) images.
  - 3 to 8 characters: union video (V) and preview (P).
- Image sizes: 1024x1024 pixels.
- Color mapping for 2-character answers:
  - Purple: shared pixels.
  - Blue: only first character.
  - Red: only second character.

## Web Application (Flask)

### Routes
- `GET /`
  - Renders the main page with font selection options.
- `GET /<word>`
  - Generates and renders images based on the path word.
  - For 2 characters: shows Q and A.
  - For 3+ characters: shows Q and U, and generates a union video.
- `GET /generate?jukugo=<word>&font=<font>`
  - Same as `/<word>` but uses query parameters.
- `GET /q/<word>?font=<font>`
  - Serves question image (Q) if available; otherwise returns a 404 with a generation link.
- `GET /a/<word>?font=<font>`
  - Serves answer image (A) if available; otherwise returns a 404 with a generation link.
- `GET /u/<word>?font=<font>`
  - Serves union image (U); generates on-demand if missing.
- `GET /p/<word>?font=<font>`
  - Serves video preview image (P); generates on-demand if missing.
- `GET /v/<word>?font=<font>`
  - Serves union video (V); generates on-demand if missing.
- `GET /health`
  - Returns JSON health status.

### Font Handling
- Supported font keys: `mincho`, `monogothic`, `hiragino`, `dejavu`.
- Available keys are detected at server startup; only usable fonts are presented.
- A font key must be 2-10 alphanumeric characters, and must exist in the configured font map.

## X (Twitter) Bot

### Posting Flow
- `/question` endpoint:
  - Fetches Q and A images from the local web app and posts the Q image with the status text.
  - Supports test mode (no tweet) and optional media skip.
- `/answer` endpoint:
  - Finds the most recent A image in the images directory and posts it as the answer.
- `/answer/by-jukugo?jukugo=<word>`:
  - Generates and posts the A image for the specified word.
- `/question/by-date?date=YYYY/MM/DD`:
  - Looks up a 2-character word from a Google Spreadsheet CSV and posts the quiz for that date.

### X Authentication
- OAuth 2.0 (User Context) is used for tweet creation.
- Access tokens are stored in `token.json` or in GCS (if configured).
- Media upload uses OAuth 1.0a via `tweepy.API` when an image is included.

## LINE Bot

### Webhook
- `POST /line/callback`, `POST /callback`, and `POST /` all route to the same LINE handler.
- Signature validation is required using `LINE_CHANNEL_SECRET`.

### User Features (1:1 chat)
- Image synthesis:
  - Sending 2-8 characters returns union/intersection images.
  - Sending 3-8 characters additionally returns a union video.
- Quiz registration:
  - Send `1.<word>` through `10.<word>` to register quiz items.
  - Word length must be 2-8 characters.
  - If a custom quiz prompt exists, it is appended to the success message as `問題文:(カスタム問題文)`.
- Settings:
  - Users can set quiz mode (intersection/union), font, and custom quiz prompt text.
  - Settings are persisted in `line_settings.json` or a path defined by `LINE_SETTINGS_FILE_PATH`.
- Bulk update:
  - Users can paste a full quiz list and update all 10 items in one message.
  - When displaying quiz prompts, the `@` line is shown on a new line.

### Group Features
- When the bot is mentioned:
  - `@BotName <number>` posts a quiz image for the specified registered item.
  - `@BotName 答え <number>` reveals the answer image or video.
- When a user mentions another user with `@User <number>.<answer>`:
  - The bot validates and replies with correct/incorrect.

### Storage Options
- Image delivery:
  - Local mode: uses HTTPS `SERVER_FQDN` to serve images.
  - GCS mode: uploads generated images to Cloud Storage and serves public URLs.
- Quiz storage:
  - SQLite (default) in `LINE_QUIZ_DB_PATH`.
  - Google Cloud Datastore if `LINE_QUIZ_STORE=datastore`.

## Image Generation Pipeline
- Uses PIL to rasterize characters to 1024x1024 canvases.
- Intersection and union images are generated via per-pixel operations.
- Union videos are generated with ffmpeg from staged frames.

## External Dependencies
- `ffmpeg` must be available for union video creation.
- `PIL` (Pillow) for image rendering.
- `tweepy` for X media upload.
- `requests` and `BeautifulSoup` for external HTTP calls and parsing.

## Configuration (Environment Variables)
- Web:
  - `SECRET_KEY`, `PORT`, `SERVER_FQDN`
- X (Twitter):
  - `X_CLIENT_ID`, `X_CLIENT_SECRET`
  - `X_BEARER_TOKEN`
  - `X_API_KEY`, `X_API_KEY_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET`
- External data:
  - `KASANE_API_URL`, `JUKUGO_API_URL`
  - `SPREADSHEET_URL` or `SPREADSHEET_ID` + `SPREADSHEET_GID`
- LINE:
  - `LINE_CHANNEL_SECRET`, `LINE_CHANNEL_ACCESS_TOKEN`
  - `LINE_BOT_USER_ID`, `LINE_BOT_NAME`
  - `LINE_IMAGE_STORAGE`, `LINE_GCS_BUCKET`, `LINE_GCS_PREFIX`
  - `LINE_SETTINGS_FILE_PATH`, `LINE_QUIZ_DB_PATH`, `LINE_QUIZ_STORE`, `LINE_FIRESTORE_PROJECT`

## Error Handling and Responses
- JSON error responses for API routes with appropriate HTTP status codes.
- 404 and 405 handlers return JSON error payloads.
- LINE handler returns a 403 on invalid signatures and 400 on bad payloads.
