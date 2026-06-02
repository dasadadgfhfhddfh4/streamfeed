# Contributing

Thanks for contributing to StreamFeed.

## Setup

1. Create and activate virtual environment.
2. Install dependencies:
   - `pip install -r requirements-dev.txt`
3. Run app:
   - `python main.py`

## Style

- Python 3.11+
- Follow `pyproject.toml` settings (`black`/`ruff` compatible formatting).
- Keep changes small and focused.

## Pull Requests

- Explain **why** change is needed.
- Add manual test steps in PR description.
- Do not commit local runtime artifacts (`.img_cache`, `seen_urls.json`, `build`, `dist`).
