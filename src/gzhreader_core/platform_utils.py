from __future__ import annotations

import os
import webbrowser
from pathlib import Path


def open_local_path(path: str | Path) -> None:
    resolved = Path(path).expanduser().resolve()
    if hasattr(os, "startfile"):
        os.startfile(str(resolved))  # type: ignore[attr-defined]
    else:
        webbrowser.open(resolved.as_uri())


def open_web_url(url: str) -> None:
    if not url.startswith(("https://", "http://")):
        raise ValueError("只能打开网页链接")
    webbrowser.open(url)
