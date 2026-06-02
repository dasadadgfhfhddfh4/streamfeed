"""Вертикальная лента новостей в стиле TikTok."""

from __future__ import annotations

import threading
import time
import webbrowser

import customtkinter as ctk
from PIL import Image

from news_engine import NewsEngine, NewsItem

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CARD_BG = "#0f0f12"
ACCENT = "#9146ff"  # Twitch purple
TEXT_DIM = "#a0a0b0"


class FeedApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("StreamFeed — игры, IT, стримы")
        self.geometry("420x780")
        self.minsize(360, 640)
        self.configure(fg_color=CARD_BG)
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.engine = NewsEngine(on_new_items=self._on_background_items)
        self._items: list[NewsItem] = []
        self._index = 0
        self._drag_y = 0
        self._photo_ref = None
        self._image_token = 0
        self._current_image_path: str | None = None
        self._last_image_size: tuple[int, int] = (0, 0)
        self._resize_job: str | None = None
        self._preload_token = 0

        self._build_ui()
        self.engine.start()
        self.after(300, self._bootstrap)

        self.bind("<MouseWheel>", self._on_wheel)
        self.bind("<Button-4>", lambda e: self._go_prev())
        self.bind("<Button-5>", lambda e: self._go_next())
        self.bind("<Up>", lambda e: self._go_prev())
        self.bind("<Down>", lambda e: self._go_next())
        self.bind("<Left>", lambda e: self._go_prev())
        self.bind("<Right>", lambda e: self._go_next())
        self.bind("<space>", lambda e: self._go_next())
        self.bind("<Return>", lambda e: self._open_link())
        self.bind("<Double-Button-1>", lambda e: self._open_link())

        self.card.bind("<ButtonPress-1>", self._drag_start)
        self.card.bind("<ButtonRelease-1>", self._drag_end)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_window_configure)

    def _build_ui(self) -> None:
        self.card = ctk.CTkFrame(self, fg_color="#16161c", corner_radius=0)
        self.card.pack(fill="both", expand=True)

        self.img_label = ctk.CTkLabel(
            self.card,
            text="",
            fg_color=CARD_BG,
            anchor="center",
        )
        self.img_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.bottom_panel = ctk.CTkFrame(
            self.card,
            fg_color="#16161c",
            corner_radius=0,
        )
        self.bottom_panel.place(relx=0, rely=1, anchor="sw", relwidth=1)
        bottom_inner = ctk.CTkFrame(self.bottom_panel, fg_color="transparent")
        bottom_inner.pack(fill="both", expand=True, padx=16, pady=(12, 20))
        bottom = bottom_inner

        self.source_label = ctk.CTkLabel(
            bottom,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=ACCENT,
            anchor="w",
        )
        self.source_label.pack(fill="x")

        self.title_label = ctk.CTkLabel(
            bottom,
            text="Загрузка ленты…",
            font=ctk.CTkFont(size=20, weight="bold"),
            wraplength=360,
            justify="left",
            anchor="w",
        )
        self.title_label.pack(fill="x", pady=(6, 4))

        self.summary_label = ctk.CTkLabel(
            bottom,
            text="",
            font=ctk.CTkFont(size=13),
            text_color=TEXT_DIM,
            wraplength=360,
            justify="left",
            anchor="w",
        )
        self.summary_label.pack(fill="x")

        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.pack(fill="x", pady=(12, 0))

        self.open_btn = ctk.CTkButton(
            btn_row,
            text="Читать полностью",
            fg_color=ACCENT,
            hover_color="#772ce8",
            command=self._open_link,
            width=160,
        )
        self.open_btn.pack(side="left")

        self.refresh_btn = ctk.CTkButton(
            btn_row,
            text="Ещё свежее",
            fg_color="#2a2a35",
            hover_color="#3a3a48",
            command=self._force_refresh,
            width=120,
        )
        self.refresh_btn.pack(side="left", padx=(8, 0))

        self.progress = ctk.CTkLabel(
            self.card,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#888",
        )
        self.progress.place(relx=1.0, rely=0, anchor="ne", x=-12, y=10)
        self.bottom_panel.lift()
        self.progress.lift()

    def _bootstrap(self) -> None:
        self._pull_from_queue()
        if not self._items:
            self.title_label.configure(text="Ищем свежие новости…")
            threading.Thread(target=self._wait_first_batch, daemon=True).start()
        else:
            self._show_current()

    def _wait_first_batch(self) -> None:
        for _ in range(20):
            self.engine.fetch_batch(count=10)
            self.after(0, self._pull_from_queue)
            if self._items:
                self.after(0, self._show_current)
                return
            time.sleep(1.2)
        self.after(
            0,
            lambda: self.title_label.configure(
                text="Нет сети или ленты заблокированы",
                text_color="#f55",
            ),
        )

    def _on_background_items(self, _items: list[NewsItem]) -> None:
        self.after(0, self._pull_from_queue)

    def _pull_from_queue(self) -> None:
        batch = self.engine.pop(8)
        if batch:
            self._items.extend(batch)

    def _force_refresh(self) -> None:
        self.refresh_btn.configure(state="disabled")
        threading.Thread(
            target=lambda: (
                self.engine.fetch_batch(count=15),
                self.after(0, self._after_force_refresh),
            ),
            daemon=True,
        ).start()

    def _after_force_refresh(self) -> None:
        self._pull_from_queue()
        self.refresh_btn.configure(state="normal")
        if self._index >= len(self._items) - 1:
            self._go_next()

    def _current(self) -> NewsItem | None:
        if 0 <= self._index < len(self._items):
            return self._items[self._index]
        return None

    def _show_current(self) -> None:
        item = self._current()
        if not item:
            return
        date_str = ""
        if item.published:
            try:
                date_str = item.published.astimezone().strftime("%d.%m.%Y %H:%M")
            except (ValueError, OSError):
                date_str = ""
        self.source_label.configure(
            text=f"{item.source}" + (f" · {date_str}" if date_str else "")
        )
        self.title_label.configure(text=item.title, text_color=("gray10", "gray98"))
        summary = item.summary
        if len(summary) > 280:
            summary = summary[:280].rstrip() + "…"
        self.summary_label.configure(text=summary)
        self.progress.configure(text=f"{self._index + 1} / {len(self._items)}+")
        self._update_wraplength()
        self._layout_bottom_overlay()
        self._load_image_async(item)
        self._preload_neighbors()

        if self._index >= len(self._items) - 4:
            threading.Thread(
                target=self.engine.fetch_batch, kwargs={"count": 12}, daemon=True
            ).start()
            self._pull_from_queue()

    def _update_wraplength(self) -> None:
        width = max(self.winfo_width() - 48, 280)
        self.title_label.configure(wraplength=width)
        self.summary_label.configure(wraplength=width)

    def _layout_bottom_overlay(self) -> None:
        self.bottom_panel.update_idletasks()
        panel_h = max(self.bottom_panel.winfo_reqheight(), 160)
        self.bottom_panel.place_configure(relx=0, rely=1, anchor="sw", relwidth=1, height=panel_h)

    def _display_scale(self) -> float:
        """Множитель для чёткости на экранах с высоким DPI."""
        try:
            dpi = float(self.winfo_fpixels("1i"))
        except Exception:
            dpi = 96.0
        return max(1.25, min(dpi / 96.0, 2.0))

    def _preload_neighbors(self) -> None:
        self._preload_token += 1
        token = self._preload_token
        index = self._index

        def work() -> None:
            for off in (1, -1):
                if token != self._preload_token:
                    return
                pos = index + off
                if 0 <= pos < len(self._items):
                    self.engine.preload_image(self._items[pos])

        threading.Thread(target=work, daemon=True).start()

    def _image_area_size(self) -> tuple[int, int]:
        """Вся карточка — область картинки (текст поверх внизу)."""
        self.update_idletasks()
        card_w = max(self.card.winfo_width(), 360)
        card_h = max(self.card.winfo_height(), 480)
        return card_w, card_h

    def _on_window_configure(self, event) -> None:
        if event.widget is not self:
            return
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(180, self._on_resize_debounced)

    def _on_resize_debounced(self) -> None:
        self._resize_job = None
        self._update_wraplength()
        self._layout_bottom_overlay()
        new_size = self._image_area_size()
        if self._current_image_path and (
            abs(new_size[0] - self._last_image_size[0]) > 24
            or abs(new_size[1] - self._last_image_size[1]) > 24
        ):
            self._display_image_file(
                self._current_image_path, new_size[0], new_size[1], self._image_token
            )

    def _load_image_async(self, item: NewsItem) -> None:
        self._image_token += 1
        token = self._image_token
        self._current_image_path = None
        self.img_label.configure(image=None, text="Загрузка…")
        def work() -> None:
            path = self.engine.load_image(item)
            if token != self._image_token:
                return
            if path is None:
                self.after(0, lambda: self._set_image(None, 0, 0, token))
                return
            self.after(0, lambda: self._render_and_show(path, token))

        threading.Thread(target=work, daemon=True).start()

    def _render_and_show(self, path: str, token: int) -> None:
        if token != self._image_token:
            return
        area = self._image_area_size()
        try:
            with Image.open(path) as src:
                img = self._cover_image(src.copy(), area[0], area[1])
            self._apply_rendered_image(path, img, token)
        except Exception:
            self._apply_rendered_image(None, None, token)

    @staticmethod
    def _to_rgb(img: Image.Image) -> Image.Image:
        if img.mode in ("P", "PA"):
            img = img.convert("RGBA")
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (30, 30, 40))
            bg.paste(img, mask=img.split()[3])
            return bg
        return img.convert("RGB")

    def _cover_image(self, img: Image.Image, max_w: int, max_h: int) -> Image.Image:
        """Заполнить экран; рендер в повышенном разрешении для чёткости."""
        img = self._to_rgb(img)
        hi = self._display_scale()
        render_w = min(max(1, int(max_w * hi)), 3840)
        render_h = min(max(1, int(max_h * hi)), 2160)
        scale = max(render_w / img.width, render_h / img.height)
        fit_w = max(1, int(img.width * scale))
        fit_h = max(1, int(img.height * scale))
        if (fit_w, fit_h) != img.size:
            img = img.resize((fit_w, fit_h), Image.Resampling.LANCZOS)
        x0 = max(0, (fit_w - render_w) // 2)
        y0 = max(0, (fit_h - render_h) // 2)
        img = img.crop((x0, y0, x0 + render_w, y0 + render_h))
        if hi > 1.05 and (render_w, render_h) != (max_w, max_h):
            img = img.resize((max_w, max_h), Image.Resampling.LANCZOS)
        return img

    def _apply_rendered_image(
        self, path: str | None, img: Image.Image | None, token: int
    ) -> None:
        if token != self._image_token:
            return
        if path is None or img is None:
            self._current_image_path = None
            self.img_label.configure(image=None, text="🎮  📺  💻")
            return
        try:
            disp_w, disp_h = img.size
            if disp_w < 40 or disp_h < 40:
                raise ValueError("image too small")
            ctk_img = ctk.CTkImage(
                light_image=img,
                dark_image=img,
                size=(disp_w, disp_h),
            )
            self.img_label.configure(image=ctk_img, text="")
            self._photo_ref = ctk_img
            self._current_image_path = str(path)
            self._last_image_size = self._image_area_size()
            self.img_label.lift()
            self.bottom_panel.lift()
            self.progress.lift()
        except Exception:
            self._current_image_path = None
            self.img_label.configure(image=None, text="🎮  📺  💻")

    def _display_image_file(self, path: str, _max_w: int, _max_h: int, token: int) -> None:
        if token != self._image_token:
            return
        self._render_and_show(path, token)

    def _set_image(self, path, max_w: int, max_h: int, token: int) -> None:
        if token != self._image_token:
            return
        if path is None:
            self._apply_rendered_image(None, None, token)
            return
        self._display_image_file(str(path), max_w, max_h, token)

    def _go_next(self) -> None:
        if self._index < len(self._items) - 1:
            self._index += 1
            self._show_current()
        else:
            self._pull_from_queue()
            if self._index < len(self._items) - 1:
                self._index += 1
                self._show_current()
            else:
                self.title_label.configure(text="Подгружаем ещё…")
                threading.Thread(
                    target=self.engine.fetch_batch, kwargs={"count": 10}, daemon=True
                ).start()

    def _go_prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._show_current()

    def _on_wheel(self, event) -> None:
        if event.delta > 0:
            self._go_prev()
        else:
            self._go_next()

    def _drag_start(self, event) -> None:
        self._drag_y = event.y

    def _drag_end(self, event) -> None:
        dy = event.y - self._drag_y
        if dy < -60:
            self._go_next()
        elif dy > 60:
            self._go_prev()

    def _open_link(self) -> None:
        item = self._current()
        if item and item.link:
            webbrowser.open(item.link)

    def _on_close(self) -> None:
        self.engine.stop()
        self.destroy()


def run_app() -> None:
    app = FeedApp()
    app.mainloop()
