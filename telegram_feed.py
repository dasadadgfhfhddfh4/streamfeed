"""Публичные Telegram-каналы через превью t.me/s (без API-ключа)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests

from app_paths import app_dir, ensure_file_beside_app


def _channels_file() -> Path:
    return ensure_file_beside_app("telegram_channels.json")

_MESSAGE_SPLIT = re.compile(
    r'<div class="tgme_widget_message_wrap[^>]*>',
    re.IGNORECASE,
)
_BG_IMAGE = re.compile(
    r"background-image:\s*url\(['\"]?(https?://[^'\" )]+)['\"]?\)",
    re.IGNORECASE,
)
_IMG_SRC = re.compile(
    r'<img[^>]+src=["\'](https?://[^"\']+)["\']',
    re.IGNORECASE,
)
_TEXT_BLOCK = re.compile(
    r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)
_MSG_LINK = re.compile(
    r'class="tgme_widget_message_date[^"]*"[^>]*href="([^"]+)"',
    re.IGNORECASE,
)
_MSG_TIME = re.compile(
    r'<time[^>]+datetime="([^"]+)"',
    re.IGNORECASE,
)


def normalize_telegram_channel(raw: str) -> str | None:
    """@channel, t.me/channel, https://t.me/s/channel → channel."""
    s = (raw or "").strip()
    if not s:
        return None

    s = s.split("?")[0].rstrip("/")

    patterns = [
        r"(?:https?://)?t\.me/s/([A-Za-z0-9_]+)",
        r"(?:https?://)?t\.me/\+?([A-Za-z0-9_]+)",
        r"^@([A-Za-z0-9_]+)$",
        r"^([A-Za-z0-9_]+)$",
    ]
    for pat in patterns:
        m = re.search(pat, s, re.IGNORECASE)
        if m:
            name = m.group(1)
            if name.lower() not in ("s", "joinchat", "addstickers", "share"):
                return name
    return None


def load_telegram_channels() -> list[str]:
    path = _channels_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x).strip().lstrip("@") for x in data if str(x).strip()]
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_telegram_channels(channels: list[str]) -> None:
    unique: list[str] = []
    seen: set[str] = set()
    for ch in channels:
        key = ch.lower()
        if key not in seen:
            seen.add(key)
            unique.append(ch)
    _channels_file().write_text(
        json.dumps(unique, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_telegram_channel(raw: str) -> tuple[bool, str]:
    username = normalize_telegram_channel(raw)
    if not username:
        return False, "Укажи @канал или ссылку вида t.me/имя_канала"

    channels = load_telegram_channels()
    if username.lower() in {c.lower() for c in channels}:
        return False, f"@{username} уже в списке"

    channels.append(username)
    save_telegram_channels(channels)
    return True, f"@{username} добавлен — подгружаем посты…"


def fetch_telegram_posts(channel: str, session: requests.Session) -> list[dict]:
    """Возвращает словари для NewsItem (публичный канал)."""
    username = normalize_telegram_channel(channel)
    if not username:
        return []

    url = f"https://t.me/s/{username}"
    resp = session.get(url, timeout=20)
    resp.raise_for_status()
    html = resp.text

    chunks = _MESSAGE_SPLIT.split(html)
    posts: list[dict] = []
    source = f"Telegram @{username}"

    for chunk in chunks[1:]:
        link_m = _MSG_LINK.search(chunk)
        if not link_m:
            continue
        link = unescape(link_m.group(1))

        text_html = ""
        text_m = _TEXT_BLOCK.search(chunk)
        if text_m:
            text_html = text_m.group(1)
        text = _strip_html(text_html)
        if not text:
            text = "Пост в Telegram"

        title = text.split("\n")[0].strip()
        if len(title) > 120:
            title = title[:117] + "…"
        summary = text
        if len(summary) > 420:
            summary = summary[:420] + "…"

        published = None
        time_m = _MSG_TIME.search(chunk)
        if time_m:
            published = _parse_iso(time_m.group(1))

        image_url = None
        bg_m = _BG_IMAGE.search(chunk)
        if bg_m:
            image_url = unescape(bg_m.group(1))
        if not image_url:
            img_m = _IMG_SRC.search(chunk)
            if img_m:
                image_url = unescape(img_m.group(1))

        posts.append(
            {
                "id": link,
                "title": title,
                "summary": summary,
                "link": link,
                "source": source,
                "published": published,
                "image_url": image_url,
            }
        )

    posts.sort(
        key=lambda p: p["published"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return posts[:25]


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def _parse_iso(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
