"""Versand der fertigen Videos: per Telegram aufs Handy und/oder in den TikTok-Posteingang."""
from __future__ import annotations

import os
import secrets
import urllib.parse
from pathlib import Path

import requests

TIKTOK_API = "https://open.tiktokapis.com/v2"


# ---------------------------------------------------------------- Telegram

def _tg(method: str, **kwargs) -> dict:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    r = requests.post(f"https://api.telegram.org/bot{token}/{method}", timeout=120, **kwargs)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data.get('description')}")
    return data


def telegram_send_video(video: Path, short_caption: str) -> None:
    with open(video, "rb") as f:
        _tg("sendVideo",
            data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": short_caption[:1000],
                  "supports_streaming": "true", "width": "1080", "height": "1920"},
            files={"video": (video.name, f, "video/mp4")})


def telegram_send_text(text: str) -> None:
    _tg("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text[:4000],
                             "disable_web_page_preview": "true"})


def telegram_find_chat_id() -> list[tuple[int, str]]:
    """Liest die letzten Nachrichten an den Bot, um deine Chat-ID herauszufinden."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    data = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
    found = {}
    for upd in data.get("result", []):
        chat = (upd.get("message") or {}).get("chat")
        if chat:
            found[chat["id"]] = chat.get("first_name") or chat.get("title") or ""
    return list(found.items())


# ---------------------------------------------------------------- TikTok

def tiktok_auth_url(client_key: str, redirect_uri: str) -> tuple[str, str]:
    state = secrets.token_urlsafe(12)
    params = {
        "client_key": client_key,
        "scope": "user.info.basic,video.upload",
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return "https://www.tiktok.com/v2/auth/authorize/?" + urllib.parse.urlencode(params), state


def _token_request(data: dict) -> dict:
    r = requests.post(
        f"{TIKTOK_API}/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=data, timeout=30,
    )
    body = r.json()
    if "access_token" not in body:
        raise RuntimeError(f"TikTok-Token-Fehler: {body}")
    return body


def tiktok_exchange_code(client_key: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    return _token_request({
        "client_key": client_key, "client_secret": client_secret, "code": code,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri,
    })


def tiktok_access_token() -> str:
    """Holt mit dem gespeicherten Refresh-Token ein frisches Access-Token."""
    body = _token_request({
        "client_key": os.environ["TIKTOK_CLIENT_KEY"],
        "client_secret": os.environ["TIKTOK_CLIENT_SECRET"],
        "grant_type": "refresh_token",
        "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"],
    })
    if body.get("refresh_token") and body["refresh_token"] != os.environ["TIKTOK_REFRESH_TOKEN"]:
        print("  ℹ TikTok hat ein neues Refresh-Token ausgegeben – bei Fehlern `python run.py tiktok-login` neu ausführen.")
    return body["access_token"]


def tiktok_upload_to_inbox(video: Path, access_token: str) -> str:
    """Lädt das Video in den TikTok-Posteingang (Entwürfe). Du postest es dann in der App."""
    size = video.stat().st_size
    if size > 64 * 1024 * 1024:
        raise RuntimeError("Video größer als 64 MB – bitte kürzer/kleiner rendern.")
    r = requests.post(
        f"{TIKTOK_API}/post/publish/inbox/video/init/",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json; charset=UTF-8"},
        json={"source_info": {"source": "FILE_UPLOAD", "video_size": size,
                              "chunk_size": size, "total_chunk_count": 1}},
        timeout=30,
    )
    body = r.json()
    err = body.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init: {err.get('code')} – {err.get('message')}")
    upload_url, publish_id = body["data"]["upload_url"], body["data"]["publish_id"]

    with open(video, "rb") as f:
        put = requests.put(
            upload_url, data=f,
            headers={"Content-Type": "video/mp4", "Content-Length": str(size),
                     "Content-Range": f"bytes 0-{size - 1}/{size}"},
            timeout=300,
        )
    if put.status_code not in (200, 201):
        raise RuntimeError(f"TikTok Upload: HTTP {put.status_code} {put.text[:200]}")
    return publish_id
