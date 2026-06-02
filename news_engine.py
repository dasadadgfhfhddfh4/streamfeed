"""Агрегация свежих новостей из русскоязычных RSS."""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable

import feedparser
import requests

from app_paths import app_dir
from telegram_feed import (
    add_telegram_channel,
    fetch_telegram_posts,
    load_telegram_channels,
)

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) StreamFeed/1.1"
)

# Только русскоязычные ленты: популярные игры, геймдев, ИИ и языки программирования
FEED_URLS = [
    # Популярные игры и индустрия
    "https://dtf.ru/rss",
    "https://dtf.ru/rss/games",
    "https://dtf.ru/rss/gamedev",
    "https://stopgame.ru/rss/rss_news.xml",
    "https://www.playground.ru/rss/news.xml",
    "https://www.igromania.ru/rss/news.rss",
    "https://www.goha.ru/rss/news/",
    # IT / программирование / ИИ
    "https://habr.com/ru/rss/hub/games/all/",
    "https://habr.com/ru/rss/hub/gamedev/all/",
    "https://habr.com/ru/rss/hub/programming/all/",
    "https://habr.com/ru/rss/hub/python/all/",
    "https://habr.com/ru/rss/hub/machine_learning/all/",
    "https://habr.com/ru/rss/hub/artificial_intelligence/all/",
    "https://habr.com/ru/rss/hub/neural_networks/all/",
    "https://vc.ru/rss/ai",
    "https://vc.ru/rss/dev",
]

# Простая фильтрация по ключевым словам: популярные игры и ИИ‑инструменты
KEYWORDS = [
    # Игры / платформы
    "gta", "cyberpunk", "witcher", "dota", "dota 2", "cs2", "counter-strike",
    "valorant", "fortnite", "pubg", "apex legends", "league of legends",
    "starfield", "elden ring", "xbox", "playstation", "ps5", "steam",
    "игра", "игры", "шутер", "рогалик", "rpg",
    # Языки и программирование
    "python", "питон", "java", "javascript", "typescript", "c#", "c++", "go",
    "rust", "язык программирования",
    # ИИ и конкретные модели
    "искусственный интеллект", "нейросеть", "нейросети", "машинное обучение",
    "ai", "ml", "llm", "gpt", "chatgpt", "claude", "gemini", "copilot",
]

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept-Language": "ru-RU,ru;q=0.9",
    }
)

IMG_CACHE_DIR = app_dir() / ".img_cache"
SEEN_FILE = app_dir() / "seen_urls.json"
MAX_SEEN = 8000


@dataclass
class NewsItem:
    id: str
    title: str
    summary: str
    link: str
    source: str
    published: datetime | None
    image_url: str | None = None
    local_image: Path | None = None


@dataclass
class NewsEngine:
    on_new_items: Callable[[list[NewsItem]], None] | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _queue: list[NewsItem] = field(default_factory=list, repr=False)
    _seen_order: deque[str] = field(default_factory=deque, repr=False)
    _seen_set: set[str] = field(default_factory=set, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _worker: threading.Thread | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        IMG_CACHE_DIR.mkdir(exist_ok=True)
        self._load_seen()

    def _load_seen(self) -> None:
        if not SEEN_FILE.exists():
            return
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return
            for item_id in data[-MAX_SEEN:]:
                if item_id not in self._seen_set:
                    self._seen_set.add(item_id)
                    self._seen_order.append(item_id)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    def _remember_seen(self, item_id: str) -> bool:
        """True, если запись новая и её нужно показать."""
        if item_id in self._seen_set:
            return False
        self._seen_set.add(item_id)
        self._seen_order.append(item_id)
        while len(self._seen_order) > MAX_SEEN:
            old = self._seen_order.popleft()
            self._seen_set.discard(old)
        return True

    def _save_seen(self) -> None:
        try:
            SEEN_FILE.write_text(
                json.dumps(list(self._seen_order), ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._refresh_loop, daemon=True)
        self._worker.start()
        threading.Thread(
            target=self.fetch_batch, kwargs={"count": 12}, daemon=True
        ).start()

    def stop(self) -> None:
        self._stop.set()

    def _refresh_loop(self) -> None:
        while not self._stop.wait(45):
            self.fetch_batch(count=8)

    def pop(self, n: int = 1) -> list[NewsItem]:
        with self._lock:
            items = self._queue[:n]
            self._queue = self._queue[n:]
        return items

    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    def fetch_batch(self, count: int = 10) -> None:
        urls = FEED_URLS.copy()
        random.shuffle(urls)
        collected: list[NewsItem] = []
        seen_in_batch: set[str] = set()

        for url in urls:
            if len(collected) >= count * 4:
                break
            try:
                for item in self._parse_feed(url):
                    if item.id in seen_in_batch:
                        continue
                    seen_in_batch.add(item.id)
                    collected.append(item)
            except Exception as exc:
                log.debug("Лента недоступна %s: %s", url, exc)

        for channel in load_telegram_channels():
            if len(collected) >= count * 4:
                break
            try:
                for raw in fetch_telegram_posts(channel, SESSION):
                    item = self._post_dict_to_item(raw)
                    if item.id in seen_in_batch:
                        continue
                    seen_in_batch.add(item.id)
                    collected.append(item)
            except Exception as exc:
                log.debug("Telegram @%s: %s", channel, exc)

        collected.sort(
            key=lambda x: x.published or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )

        fresh: list[NewsItem] = []
        with self._lock:
            for item in collected:
                if not self._remember_seen(item.id):
                    continue
                fresh.append(item)
                self._queue.append(item)
                if len(fresh) >= count:
                    break

        if fresh:
            self._save_seen()
            if self.on_new_items:
                self.on_new_items(fresh)

    def _parse_feed(self, url: str) -> list[NewsItem]:
        resp = SESSION.get(url, timeout=14)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        if parsed.bozo and not parsed.entries:
            return []

        source = parsed.feed.get("title", _host(url))
        items: list[NewsItem] = []

        for entry in parsed.entries[:30]:
            link = entry.get("link") or ""
            title = _clean_html(entry.get("title", "Без названия"))
            if not link or len(title) < 3:
                continue

            item_id = entry.get("id") or link
            raw_summary = entry.get("summary") or entry.get("description") or ""
            summary = _clean_html(raw_summary)
            if len(summary) > 420:
                summary = summary[:420] + "…"

            # Фильтр по тематике: популярные игры, языки и ИИ
            text_for_match = f"{title} {summary}".lower()
            if KEYWORDS and not any(k in text_for_match for k in KEYWORDS):
                continue

            published = _entry_date(entry)
            image_url = _extract_image(entry, raw_summary)

            items.append(
                NewsItem(
                    id=item_id,
                    title=title,
                    summary=summary or "Открой ссылку, чтобы прочитать полностью.",
                    link=link,
                    source=source,
                    published=published,
                    image_url=image_url,
                )
            )
        return items

    def add_telegram(self, raw: str) -> tuple[bool, str]:
        """Добавить публичный TG-канал и сразу подгрузить посты."""
        ok, message = add_telegram_channel(raw)
        if ok:
            threading.Thread(
                target=self.fetch_batch, kwargs={"count": 15}, daemon=True
            ).start()
        return ok, message

    def _post_dict_to_item(self, raw: dict) -> NewsItem:
        return NewsItem(
            id=raw["id"],
            title=raw["title"],
            summary=raw["summary"],
            link=raw["link"],
            source=raw["source"],
            published=raw.get("published"),
            image_url=raw.get("image_url"),
        )

    def load_image(self, item: NewsItem) -> Path | None:
        if item.local_image and item.local_image.exists():
            return item.local_image

        original = item.image_url
        if not original:
            return None

        candidates: list[str] = []
        upgraded = _upgrade_image_url(original)
        if upgraded:
            candidates.append(upgraded)
        if original not in candidates:
            candidates.append(original)

        safe_id = re.sub(r"[^\w.-]", "_", item.id)[-120:] or "img"

        for url in candidates:
            ext = _image_ext(url)
            path = IMG_CACHE_DIR / f"{safe_id}{ext}"
            if path.exists():
                item.local_image = path
                return path

            try:
                r = SESSION.get(url, timeout=20)
                r.raise_for_status()
                data = r.content
                if len(data) < 400:
                    continue
                path.write_bytes(data)
                item.local_image = path
                return path
            except Exception:
                continue

        return None

    def preload_image(self, item: NewsItem) -> None:
        """Фоновая подгрузка картинки для соседних карточек."""
        if not item.image_url:
            return
        if item.local_image and item.local_image.exists():
            return
        threading.Thread(target=self.load_image, args=(item,), daemon=True).start()


def _upgrade_image_url(url: str | None) -> str | None:
    """По возможности запрашивает более крупную версию превью."""
    if not url:
        return None
    u = url
    # Google‑style превью (DTF / VC и др.)
    u = re.sub(r"=s\d+(?:-c)?(?:-rw)?$", "=s1600", u)
    u = re.sub(r"=w\d+-h\d+", "=w1600-h1000", u)
    # Параметры размеров
    u = re.sub(r"\?size=(?:small|medium)", "?size=large", u, flags=re.IGNORECASE)
    u = re.sub(r"[?&]mw=\d+", "?mw=1600", u)
    # Основа (DTF / VC CDN)
    if "leonardo.osnova.io" in u and "mw=" not in u:
        sep = "&" if "?" in u else "?"
        u = f"{u}{sep}mw=1600"
    return u


def _image_ext(url: str) -> str:
    lower = url.lower().split("?")[0]
    for ext in (".png", ".webp", ".gif", ".jpeg", ".jpg"):
        if lower.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return ".jpg"


def _host(url: str) -> str:
    m = re.search(r"https?://([^/]+)", url)
    return m.group(1) if m else "Новости"


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _entry_date(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                pass
    return None


def _extract_image(entry, summary_html: str) -> str | None:
    best_url: str | None = None
    best_score = 0
    for key in ("media_content", "media_thumbnail"):
        for m in entry.get(key) or []:
            u = m.get("url")
            if not u or not _looks_like_image(u):
                continue
            try:
                w = int(m.get("width") or 0)
                h = int(m.get("height") or 0)
            except (TypeError, ValueError):
                w, h = 0, 0
            score = w * h if w and h else 1
            if score >= best_score:
                best_score = score
                best_url = u
    if best_url:
        return best_url

    for enc in entry.get("enclosures") or []:
        if enc.get("type", "").startswith("image"):
            href = enc.get("href")
            if href:
                return href

    for m in re.finditer(r'src=["\']([^"\']+)["\']', summary_html or ""):
        u = m.group(1)
        if _looks_like_image(u):
            return u

    for m in re.finditer(
        r"(https://[^\s\"'<>]+?\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s\"'<>]*)?)",
        summary_html or "",
        re.IGNORECASE,
    ):
        return m.group(1)

    return None


def _looks_like_image(url: str) -> bool:
    lower = url.lower()
    if any(x in lower for x in (".svg", "pixel", "1x1", "spacer")):
        return False
    return any(
        x in lower
        for x in (
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            "leonardo.osnova.io",
            "images.habr.com",
            "static.playground",
            "igromania.ru",
            "stopgame.ru",
            "ixbt.com",
            "telesco.pe",
            "telegra.ph",
            "cdn4.telegram",
        )
    )
