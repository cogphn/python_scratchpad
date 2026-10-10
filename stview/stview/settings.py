"""Persistent settings for stview.

Settings live in ``~/.config/stview/config.json`` and can be overridden with
environment variables:

* ``STVIEW_HOST``  – base URL of the SpacetimeDB server (default http://127.0.0.1:3000)
* ``STVIEW_TOKEN`` – Spacetime auth token to use for privileged calls
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_HOST = "http://127.0.0.1:3000"
CONFIG_DIR = Path(os.environ.get("STVIEW_CONFIG_DIR", Path.home() / ".config" / "stview"))
CONFIG_FILE = CONFIG_DIR / "config.json"
SPACETIME_CLI_CONFIG = Path.home() / ".config" / "spacetime" / "cli.toml"

_lock = threading.Lock()


@dataclass
class Settings:
    host: str = DEFAULT_HOST
    token: str | None = None
    identity: str | None = None
    token_source: str | None = None
    # Databases (names or identities) the user explicitly asked to track, in
    # addition to the ones owned by our identity.
    tracked_databases: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ io
    @classmethod
    def load(cls) -> "Settings":
        data: dict = {}
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text())
            except (OSError, ValueError):
                data = {}
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        s = cls(**known)
        if os.environ.get("STVIEW_HOST"):
            s.host = os.environ["STVIEW_HOST"]
        if os.environ.get("STVIEW_TOKEN"):
            s.token = os.environ["STVIEW_TOKEN"]
            s.token_source = "environment (STVIEW_TOKEN)"
        s.host = s.host.rstrip("/")
        return s

    def save(self) -> None:
        with _lock:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2) + "\n")

    # ------------------------------------------------------------ helpers
    def track(self, name_or_identity: str) -> bool:
        name_or_identity = name_or_identity.strip()
        if not name_or_identity or name_or_identity in self.tracked_databases:
            return False
        self.tracked_databases.append(name_or_identity)
        self.save()
        return True

    def untrack(self, name_or_identity: str) -> bool:
        if name_or_identity in self.tracked_databases:
            self.tracked_databases.remove(name_or_identity)
            self.save()
            return True
        return False


def cli_token() -> str | None:
    """Return the token the ``spacetime`` CLI is logged in with, if any."""
    if not SPACETIME_CLI_CONFIG.exists():
        return None
    try:
        text = SPACETIME_CLI_CONFIG.read_text()
    except OSError:
        return None
    m = re.search(r'^\s*spacetimedb_token\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return m.group(1) if m else None
