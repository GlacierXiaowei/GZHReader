from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    db: Path
    logs: Path
    briefings: Path
    browser_profile: Path
    link_browser_profile: Path
    secrets: Path
    backups: Path


def get_paths() -> AppPaths:
    local = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    root = local / "GZHReader" / "workspace-v3"
    documents = Path(os.getenv("USERPROFILE") or Path.home()) / "Documents"
    value = AppPaths(
        root=root,
        db=root / "gzhreader.db",
        logs=root / "logs",
        briefings=documents / "GZHReader" / "Briefings",
        browser_profile=root / "browser",
        link_browser_profile=root / "link-browser",
        secrets=root / "secrets",
        backups=root / "backups",
    )
    for path in (
        value.root,
        value.logs,
        value.briefings,
        value.browser_profile,
        value.link_browser_profile,
        value.secrets,
        value.backups,
    ):
        path.mkdir(parents=True, exist_ok=True)
    return value
