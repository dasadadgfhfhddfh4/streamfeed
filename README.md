# StreamFeed

Desktop app (Python + CustomTkinter) with an infinite fullscreen feed of fresh news about games, AI, and programming.

## Features

- Fullscreen vertical feed interface.
- Focused topics: popular games, programming languages, and AI tools (ChatGPT, Claude, Gemini).
- Auto image extraction and higher-resolution preview upgrades where possible.
- Local cache for viewed items and downloaded images.
- Optional Telegram channel parsing from public `t.me/s/...` pages (no bot token required).

## Requirements

- Python 3.11+ (recommended)
- Windows (primary target), should also work on Linux/macOS with minor UI behavior differences

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build EXE (Windows)

```bat
build.bat
```

Or manually:

```bash
pip install -r requirements-dev.txt
pyinstaller --noconfirm --onefile --windowed --name StreamFeed --add-data "telegram_channels.json;." main.py
```

## Development

- Install dev tools:
  - `pip install -r requirements-dev.txt`
- Optional checks:
  - `python -m py_compile main.py feed_ui.py news_engine.py telegram_feed.py`

## Project Structure

- `main.py` — application entrypoint.
- `feed_ui.py` — UI, navigation, image rendering.
- `news_engine.py` — feed fetching, filtering, image caching.
- `telegram_feed.py` — Telegram public page parsing.
- `app_paths.py` — runtime path helpers (script vs bundled app).

## Data Files

- `telegram_channels.json` — user channel list.
- `seen_urls.json` — viewed item history (generated at runtime).
- `.img_cache/` — downloaded image cache (generated at runtime).

Runtime artifacts are ignored by `.gitignore`.

## Notes

- RSS availability can vary by source and region.
- Some image URLs from feeds provide only low-resolution assets; StreamFeed tries to request larger variants when possible.

## Contributing

See `CONTRIBUTING.md`.

## License

MIT (see `LICENSE`).
