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
    all_tags = []

    for line in lines:
        stripped_line = line.strip()

        # タグセクションを探す（日本語と英語の両方に対応）
        if stripped_line.startswith('## タグ') or stripped_line.startswith('## Tags'):
            in_tags_section = True
            continue

        # タグセクション内でタグを抽出
        if in_tags_section:
            # 次のセクション（##で始まる）に到達したら終了
            if stripped_line.startswith('##'):
                break

            # #で始まるタグを抽出（#の後に日本語・英語・数字が続くパターン）
            tags = re.findall(r'#([a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF_\-]+)', stripped_line)
            if tags:
                all_tags.extend(tags)

    return all_tags if all_tags else []


def extract_published_date_from_markdown(markdown: str) -> Optional[str]:
    """
    Markdownから公開日を抽出する
    """
    lines = markdown.split('\n')

    for line in lines:
        stripped_line = line.strip()

        # **公開日**: の形式を探す
        if '**公開日**:' in stripped_line or '**公開日**：' in stripped_line:
            # コロンの後の日付部分を抽出
            date_text = re.sub(r'.*\*\*公開日\*\*[:：]\s*', '', stripped_line)
            date_text = date_text.strip()

            # 日付形式を検出（YYYY-MM-DD, YYYY/MM/DD, YYYY年MM月DD日など）
            # YYYY-MM-DD形式
            match = re.search(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2})', date_text)
            if match:
                date_str = match.group(1)
                # 年月日を-に統一
                date_str = re.sub(r'[年月]', '-', date_str)
                date_str = re.sub(r'日', '', date_str)
                date_str = re.sub(r'/', '-', date_str)
                return date_str

    return None


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
        # Gemini モデルの初期化（Search grounding対応モデル）
        model = genai.GenerativeModel('gemini-2.5-flash')

        # URLから記事を取得して分析
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


def parse_markdown_text(text: str) -> list:
    """
    Markdownテキストをrich_text配列に変換（太字、斜体、リンク対応）
    """
    rich_text = []
    current_text = ""
    i = 0

    while i < len(text):
        # 太字 **text**
        if text[i:i+2] == '**':
            if current_text:
                rich_text.append({"type": "text", "text": {"content": current_text}})
                current_text = ""

            end = text.find('**', i + 2)
            if end != -1:
                bold_text = text[i+2:end]
                rich_text.append({
                    "type": "text",
                    "text": {"content": bold_text},
                    "annotations": {"bold": True}
                })
                i = end + 2
                continue

        # 斜体 *text* または _text_
        elif text[i] in ['*', '_'] and (i == 0 or text[i-1] != '*'):
            if current_text:
                rich_text.append({"type": "text", "text": {"content": current_text}})
                current_text = ""

            end = text.find(text[i], i + 1)
            if end != -1:
                italic_text = text[i+1:end]
                rich_text.append({
                    "type": "text",
                    "text": {"content": italic_text},
                    "annotations": {"italic": True}
                })
                i = end + 1
                continue

        current_text += text[i]
        i += 1

    if current_text:
        rich_text.append({"type": "text", "text": {"content": current_text}})

    return rich_text if rich_text else [{"type": "text", "text": {"content": text}}]


def markdown_to_notion_blocks(markdown: str) -> list:
    """
    MarkdownをNotionブロックに変換する
    """
    blocks = []
    lines = markdown.split('\n')
    skip_section = False

    for line in lines:
        stripped_line = line.strip()

        if not stripped_line:
            continue

        # スキップするセクションの開始を検出
        if (stripped_line.startswith('## タグ') or
            stripped_line.startswith('## Tags') or
            stripped_line.startswith('## メタ情報') or
            stripped_line.startswith('## Meta Information')):
            skip_section = True
            continue

        # スキップセクション内の行をスキップ
        if skip_section:
            # 次の見出しセクションに到達したらスキップ解除
            if stripped_line.startswith('##'):
                skip_section = False
            else:
                # スキップセクション内はスキップ
                continue

        # 見出し1（最初のタイトルは除外）
        if stripped_line.startswith('# '):
            content = stripped_line[2:]
            # 既にブロックがある場合のみ追加（最初のタイトルは除外）
            if blocks:
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": parse_markdown_text(content)
                    }
                })
        # 見出し2
        elif stripped_line.startswith('## '):
            content = stripped_line[3:]
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": parse_markdown_text(content)
                }
            })
        # 見出し3
        elif stripped_line.startswith('### '):
            content = stripped_line[4:]
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": parse_markdown_text(content)
                }
            })
        # 箇条書き
        elif stripped_line.startswith('- '):
            content = stripped_line[2:]
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": parse_markdown_text(content)
                }
            })
        # 区切り線
        elif stripped_line.startswith('---'):
            blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
        # 通常のテキスト
        else:
            # 長すぎるテキストは分割
            if len(stripped_line) > 2000:
                stripped_line = stripped_line[:2000]
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": parse_markdown_text(stripped_line)
                }
            })

    # Notionの制限により最大100ブロック
    return blocks[:100]


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

    # 公開日を抽出
    published_date = extract_published_date_from_markdown(markdown)

    # Markdownを Notionブロックに変換
    notion_blocks = markdown_to_notion_blocks(markdown)

    # Notionプロパティを構築
    properties = {
        "Name": {
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
        "Date": {
            "date": {
                "start": datetime.now().strftime('%Y-%m-%d')
            }
        },
        "Tags": {
            "multi_select": [{"name": tag} for tag in tags]
        }
    }

    # 公開日が抽出できた場合は追加
    if published_date:
        properties["Published"] = {
            "date": {
                "start": published_date
            }
        }

    try:
        # Notionページを作成
        new_page = notion.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties=properties,
            children=notion_blocks
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
