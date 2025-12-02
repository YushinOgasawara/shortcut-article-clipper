import os
import re
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv
from notion_client import Client

# 環境変数の読み込み
load_dotenv()

# FastAPIアプリの初期化
app = FastAPI(
    title="Shortcut Article Clipper API",
    description="Safari記事をiPhoneショートカットから保存し、AIで分析してNotionに保存するシステム",
    version="0.1.0"
)

# 環境変数の取得
SECRET_TOKEN = os.environ.get("SECRET_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID")

# Gemini APIの初期化
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Notion クライアントの初期化
if NOTION_API_KEY:
    notion = Client(auth=NOTION_API_KEY)


# リクエストモデル
class SaveArticleRequest(BaseModel):
    url: HttpUrl
    token: str


# レスポンスモデル
class SaveArticleResponse(BaseModel):
    success: bool
    message: str
    title: Optional[str] = None
    notion_url: Optional[str] = None


# ヘルスチェック用のルートエンドポイント
@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "Shortcut Article Clipper API"
    }


# サーバー生存確認用エンドポイント（Renderスリープ対策）
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }


def extract_title_from_markdown(markdown: str) -> str:
    """
    Markdownから最初の見出しをタイトルとして抽出する
    """
    lines = markdown.split('\n')
    for line in lines:
        if line.startswith('#'):
            title = line.lstrip('#').strip()
            return title

    # タイトルが見つからない場合はデフォルト
    return "記事"


def extract_tags_from_markdown(markdown: str) -> list[str]:
    """
    Markdownからタグを抽出する（## タグ セクションから）
    """
    lines = markdown.split('\n')
    in_tags_section = False

    for line in lines:
        # タグセクションを探す
        if line.strip().startswith('## タグ'):
            in_tags_section = True
            continue

        # タグセクション内でタグを抽出
        if in_tags_section:
            # 次のセクションに到達したら終了
            if line.strip().startswith('#'):
                break

            # #で始まるタグを抽出
            tags = re.findall(r'#(\w+)', line)
            if tags:
                return tags

    return []


def generate_article_markdown(url: str) -> str:
    """
    Gemini APIを使用して記事を取得・分析し、Markdownを生成する
    """
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY が設定されていません"
        )

    # プロンプトの作成
    prompt = f"""以下のURLの記事を読んで、後で見返しやすいMarkdownファイルを作成してください。

URL: {url}

# 出力形式

以下の構造でMarkdownを作成してください：

# [記事のタイトル]

## メタ情報
- **URL**: {url}
- **保存日**: {datetime.now().strftime('%Y-%m-%d')}
- **サイト名**: [記事のサイト名]
- **公開日**: [わかれば記載]

## 概要
[記事の要点を2-4行で簡潔に]

## 主要なポイント
- [重要な主張や発見を箇条書きで3-7個]
- [具体的な数字やデータがあれば含める]

## 詳細メモ
[特に興味深い点、技術的な詳細、引用など]

## タグ
[内容に応じた適切なタグを3-5個、例: #AI #プログラミング #ビジネス]

## 個人的メモ
[後で追記するための空欄]

---

注意事項：
- 記事の内容を正確に反映してください
- 読みやすく構造化してください
- 検索しやすいキーワードを含めてください
- 日本語で出力してください
"""

    try:
        # Gemini モデルの初期化
        model = genai.GenerativeModel('gemini-1.5-flash-latest')

        # 記事URLを含めたプロンプトでコンテンツを生成
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=4096,
            )
        )

        markdown = response.text

        # 記事が正しく取得できたかチェック
        if not markdown or len(markdown) < 100 or "取得できません" in markdown:
            raise HTTPException(
                status_code=500,
                detail="記事の取得に失敗しました。URLを確認してください。"
            )

        return markdown

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini API error: {str(e)}"
        )


def save_to_notion(markdown: str, url: str) -> str:
    """
    生成されたMarkdownをNotionデータベースに保存する
    """
    if not all([NOTION_API_KEY, NOTION_DATABASE_ID]):
        raise HTTPException(
            status_code=500,
            detail="Notion設定が不足しています（API_KEY/DATABASE_ID）"
        )

    # タイトルを抽出
    title = extract_title_from_markdown(markdown)

    # タグを抽出
    tags = extract_tags_from_markdown(markdown)

    try:
        # Notionページを作成
        new_page = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties={
                "タイトル": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                },
                "URL": {
                    "url": url
                },
                "保存日": {
                    "date": {
                        "start": datetime.now().strftime('%Y-%m-%d')
                    }
                },
                "タグ": {
                    "multi_select": [{"name": tag} for tag in tags]
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "code",
                    "code": {
                        "language": "markdown",
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": markdown[:2000]  # Notionの制限により最初の2000文字
                                }
                            }
                        ]
                    }
                }
            ]
        )

        # NotionページのURLを返す
        notion_url = new_page.get('url', '')
        return notion_url

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Notion save failed: {str(e)}"
        )


# 記事を保存するメインエンドポイント
@app.post("/save-article", response_model=SaveArticleResponse)
async def save_article(request: SaveArticleRequest):
    """
    iPhoneショートカットから記事URLを受け取り、
    Gemini APIで分析してNotionに保存する
    """
    # 認証トークンの確認
    if request.token != SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # 1. Gemini APIで記事を取得・分析
        markdown = generate_article_markdown(str(request.url))

        # 2. タイトルを抽出
        title = extract_title_from_markdown(markdown)

        # 3. Notionに保存
        notion_url = save_to_notion(markdown, str(request.url))

        # 4. 成功レスポンスを返す
        return SaveArticleResponse(
            success=True,
            message="記事を保存しました！",
            title=title,
            notion_url=notion_url
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"記事の保存に失敗しました: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
