import os
import json
import anthropic
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import secrets

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

security = HTTPBasic()
ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "")

def verify_password(credentials: HTTPBasicCredentials = Depends(security)):
    if not ACCESS_PASSWORD:
        return
    correct = secrets.compare_digest(credentials.password.encode(), ACCESS_PASSWORD.encode())
    if not correct:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="パスワードが違います",
            headers={"WWW-Authenticate": "Basic"},
        )


class BlogRequest(BaseModel):
    content: str
    title_count: int = 3
    title_max_chars: int = 40
    article_max_chars: int = 1000
    header: str = ""
    footer: str = ""


@app.get("/", response_class=HTMLResponse)
async def root(credentials: HTTPBasicCredentials = Depends(verify_password)):
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/generate")
async def generate(req: BlogRequest, credentials: HTTPBasicCredentials = Depends(verify_password)):
    system_prompt = """あなたはSEO・AIO対策に精通したプロのブログライターです。
ユーザーが提供するブログの大まかな内容をもとに、以下の2つを生成してください。

1. ブログタイトル候補（指定された数だけ）
2. SEO・AIO最適化されたブログ記事本文

【SEO・AIO対策の要件】
- タイトルにはメインキーワードを含める
- 記事冒頭100文字以内に主要キーワードを自然に含める（AIがスニペット抽出しやすい構造）
- 見出しは【】を使ったプレーンテキスト形式（例：【はじめに】【まとめ】）
- #・##・###などのMarkdown記法は絶対に使わない
- ▶・■・◆・●・★などの装飾記号は絶対に使わない
- 通常の日本語文章として自然に読める構成にする
- 読者の疑問に直接答える「結論ファースト」の文章構成
- 自然なキーワード配置（詰め込みすぎない）
- 記事末尾にまとめセクションを入れる
- メタディスクリプション（120文字以内）も生成する

必ず以下のJSON形式のみで出力してください。他のテキストは一切含めないでください：
{
  "titles": ["タイトル1", "タイトル2", ...],
  "meta_description": "メタディスクリプション（120文字以内）",
  "article": "記事本文（Markdown形式）..."
}"""

    header_section = f"\n\n【ヘッダー（記事冒頭に必ず挿入）】\n{req.header}" if req.header else ""
    footer_section = f"\n\n【フッター（記事末尾に必ず挿入）】\n{req.footer}" if req.footer else ""

    user_prompt = f"""以下の内容をもとにSEO・AIO対策済みのブログを作成してください。

【内容】
{req.content}

【要件】
- タイトル候補: {req.title_count}個
- タイトルの最大文字数: {req.title_max_chars}文字
- 記事の目安文字数: {req.article_max_chars}文字
- 言語: 日本語{header_section}{footer_section}"""

    def stream_response():
        with client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield f"data: {json.dumps({'chunk': text}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")
