# Shortcut Article Clipper

Safari記事をiPhoneショートカットから保存し、AIで分析してGitHubに保存するシステム

## 概要

Safariで閲覧中の記事URLをiPhoneショートカットから送信すると、AIが自動的に記事を取得・分析してMarkdownファイルを生成し、プライベートGitHubリポジトリに保存します。

## 技術スタック

- **バックエンド**: FastAPI (Python)
- **AI分析**: Gemini API (gemini-1.5-flash)
- **デプロイ先**: Render.com
- **トリガー**: iPhoneショートカット
- **ストレージ**: GitHub (プライベートリポジトリ)

## 主な機能

- 記事URLから自動的にコンテンツを取得・分析
- AIによる記事要約とMarkdown生成
- GitHubへの自動保存
- iPhoneショートカットとの連携

## セットアップ

### 1. 依存関係のインストール

```bash
# uvを使用した依存関係のインストール
uv sync
```

### 2. 環境変数の設定

`.env.example`を`.env`にコピーして、必要な環境変数を設定してください。

```bash
cp .env.example .env
```

必要な環境変数:

- `SECRET_TOKEN`: iPhoneショートカット認証用トークン（任意の文字列）
- `GEMINI_API_KEY`: Gemini API Key ([取得方法](https://makersuite.google.com/app/apikey))
- `GITHUB_TOKEN`: GitHub Personal Access Token ([取得方法](https://github.com/settings/tokens))
- `GITHUB_OWNER`: GitHubユーザー名
- `GITHUB_REPO`: プライベートリポジトリ名
- `GITHUB_BRANCH`: ブランチ名（デフォルト: main）

### 3. アプリケーションの起動

```bash
# 開発サーバーの起動
uv run python main.py

# または
uv run uvicorn main:app --reload
```

## API エンドポイント

### GET /

ヘルスチェック用のルートエンドポイント。

**レスポンス例:**
```json
{
  "status": "ok",
  "message": "Shortcut Article Clipper API"
}
```

### GET /health

サーバー生存確認用エンドポイント（Renderスリープ対策）。

**レスポンス例:**
```json
{
  "status": "ok",
  "timestamp": "2025-11-03T12:00:00"
}
```

### POST /save-article

記事を保存するメインエンドポイント。

**リクエスト例:**
```json
{
  "url": "https://example.com/article",
  "token": "your-secret-token"
}
```

**レスポンス例（成功時）:**
```json
{
  "success": true,
  "message": "記事を保存しました！",
  "title": "記事のタイトル",
  "github_url": "https://github.com/username/repo/blob/main/articles/2025-11-03-article-title.md"
}
```

## iPhoneショートカット設定

### ショートカットの作成手順

1. iPhoneの「ショートカット」アプリを開く
2. 新規ショートカットを作成
3. 以下のアクションを追加:

#### アクション1: 共有シートから入力を取得
- タイプ: URL

#### アクション2: URLの内容を取得
- URL: `https://your-app.onrender.com/save-article`
- メソッド: POST
- ヘッダー: `Content-Type: application/json`
- 本文: JSON
```json
{
  "url": "ショートカット入力",
  "token": "your-secret-token"
}
```

#### アクション3: 辞書の値を取得
- キー: `message`
- 辞書: `URLの内容`

#### アクション4: 通知を表示
- タイトル: `記事保存`
- 本文: `辞書の値`

### 設定
- 「共有シートに表示」: ON
- アイコン: 任意（ブックマークやドキュメントアイコン推奨）

## デプロイ (Render.com)

### Build Command
```bash
pip install -r requirements.txt
```

### Start Command
```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Environment
- Python 3.11 or later

### 環境変数の設定
Renderのダッシュボードで上記の環境変数を設定してください。

## テスト

### ローカルテスト

```bash
# アプリ起動
uv run python main.py

# 別ターミナルでテスト
curl -X POST http://localhost:8000/save-article \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/article",
    "token": "test-token"
  }'
```

## 生成されるMarkdownファイルの構造

```markdown
# [記事のタイトル]

## メタ情報
- **URL**: https://example.com/article
- **保存日**: 2025-11-03
- **サイト名**: Example Site
- **公開日**: 2025-11-01

## 概要
記事の要点を2-4行で簡潔に記載

## 主要なポイント
- 重要な主張や発見を箇条書きで記載
- 具体的な数字やデータがあれば含める

## 詳細メモ
特に興味深い点、技術的な詳細、引用など

## タグ
#AI #プログラミング #ビジネス

## 個人的メモ
[後で追記するための空欄]
```

## トラブルシューティング

### 問題1: Gemini APIがタイムアウト
- **原因**: 記事が長すぎる、または複雑
- **対策**: タイムアウト時間を延長、max_output_tokensを調整

### 問題2: 記事が取得できない
- **原因**: Grounding機能が記事を読み取れない
- **対策**: エラーメッセージを確認し、URLを確認

### 問題3: GitHub pushが失敗
- **原因**: トークン権限不足、ファイル名重複
- **対策**: repoスコープ確認、ファイル名にタイムスタンプが含まれているか確認

### 問題4: Renderがスリープ
- **原因**: 15分無アクセス
- **対策**: cron-job.orgで定期ping、または有料プラン

## 注意事項

1. Gemini APIは無料だがレート制限あり（1500 requests/日）
2. Renderの無料版は月750時間まで（1プロジェクトなら十分）
3. プライベートリポジトリのGitHub Tokenは厳重に管理
4. Gemini APIのGrounding機能は100%確実ではない
5. 個人利用の範囲で使用すること

## ライセンス

MIT License

## 参考リンク

- [Gemini API](https://ai.google.dev/)
- [Google AI Studio](https://makersuite.google.com/)
- [Render.com](https://render.com)
- [FastAPI](https://fastapi.tiangolo.com)
- [GitHub API](https://docs.github.com/en/rest)
