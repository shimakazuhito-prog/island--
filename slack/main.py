import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

load_dotenv()

app = FastAPI()

SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")

USER_SCOPES = "channels:history,channels:read,groups:history,groups:read,search:read"
SLACK_API = "https://slack.com/api"


def _auth_header():
    return {"Authorization": f"Bearer {SLACK_USER_TOKEN}"}


@app.get("/")
def root():
    return {"status": "ok", "user_token_configured": bool(SLACK_USER_TOKEN)}


@app.get("/slack/install")
def slack_install():
    url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={SLACK_CLIENT_ID}"
        f"&user_scope={USER_SCOPES}"
        f"&redirect_uri={SLACK_REDIRECT_URI}"
    )
    return HTMLResponse(f'<a href="{url}">Slack を認可して User Token を取得</a>')


@app.get("/slack/callback")
async def slack_callback(code: str = None, error: str = None):
    if error:
        return HTMLResponse(f"<p>Error: {error}</p>", status_code=400)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SLACK_API}/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": SLACK_REDIRECT_URI,
            },
        )
    data = resp.json()
    if not data.get("ok"):
        return HTMLResponse(f"<p>Error: {data.get('error')}</p>", status_code=400)

    user_token = data.get("authed_user", {}).get("access_token", "")
    return HTMLResponse(
        "<h2>User Token を取得しました</h2>"
        "<p>Railway の Variables に SLACK_USER_TOKEN として登録してください。</p>"
        f"<pre>{user_token}</pre>"
    )


@app.get("/search")
async def search_messages(query: str, count: int = 20):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SLACK_API}/search.messages",
            headers=_auth_header(),
            params={"query": query, "count": count},
        )
    data = resp.json()
    if not data.get("ok"):
        return JSONResponse({"error": data.get("error")}, status_code=400)

    matches = data.get("messages", {}).get("matches", [])
    return {
        "query": query,
        "count": len(matches),
        "results": [
            {
                "channel": m.get("channel", {}).get("name"),
                "user": m.get("username"),
                "text": m.get("text", ""),
                "permalink": m.get("permalink"),
            }
            for m in matches
        ],
    }


@app.get("/unreplied")
async def check_unreplied(my_user_id: str, count: int = 50):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SLACK_API}/search.messages",
            headers=_auth_header(),
            params={"query": f"<@{my_user_id}>", "count": count},
        )
        data = resp.json()
        if not data.get("ok"):
            return JSONResponse({"error": data.get("error")}, status_code=400)

        unreplied = []
        for msg in data.get("messages", {}).get("matches", []):
            channel_id = msg.get("channel", {}).get("id")
            ts = msg.get("ts")
            if not channel_id or not ts:
                continue

            replies_resp = await client.get(
                f"{SLACK_API}/conversations.replies",
                headers=_auth_header(),
                params={"channel": channel_id, "ts": ts},
            )
            replies = replies_resp.json().get("messages", [])

            if any(r.get("user") == my_user_id for r in replies[1:]):
                continue

            unreplied.append({
                "channel": msg.get("channel", {}).get("name"),
                "from": msg.get("username"),
                "text": msg.get("text", ""),
                "permalink": msg.get("permalink"),
            })

    return {"unreplied_count": len(unreplied), "messages": unreplied}


MEETING_HOSTS = ("meet.google.com", "zoom.us", "teams.microsoft.com", "webex.com")


@app.get("/meeting-url")
async def find_meeting_url(channel_id: str, limit: int = 50):
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SLACK_API}/conversations.history",
            headers=_auth_header(),
            params={"channel": channel_id, "limit": limit},
        )
    data = resp.json()
    if not data.get("ok"):
        return JSONResponse({"error": data.get("error")}, status_code=400)

    found = [
        {"text": m.get("text", ""), "ts": m.get("ts")}
        for m in data.get("messages", [])
        if any(host in m.get("text", "").lower() for host in MEETING_HOSTS)
    ]
    return {"channel": channel_id, "count": len(found), "meeting_urls": found}
  
