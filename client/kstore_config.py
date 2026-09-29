"""kstore client configuration — one user-owned deployment config, strictly read.

Reconciled 2026-09-27 into the kstore repo (canonical: the earlier
Admin-Manual draft specified per-endpoint full URLs; the canonical server
env convention and the repair brief both require base URLs with routes
derived once in client code — this loader follows that).

Rules:
- File: ~/.config/kstore/client.env (override: KSTORE_CONFIG_FILE); mode
  must not be group/world-readable.
- Process environment overrides file values.
- Unknown, duplicate, missing-required or invalid values fail by key name;
  no deployment fallback, no interpolation, no shell execution.
- Base URLs only (KSTORE_URL, KSTORE_QDRANT_URL); endpoints are derived in
  client/kstore_client.py, never configured per-route.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED = (
    "KSTORE_URL",
    "KSTORE_QDRANT_URL",
    "KSTORE_COLLECTION",
    "KSTORE_RECEIPT_ROOT",
    "KSTORE_REQUEST_TIMEOUT_SECONDS",
    "KSTORE_POSTGRES_READ_COMMAND_JSON",
)
OPTIONAL = (
    "KSTORE_HTTP_BEARER_TOKEN",
    "KSTORE_QDRANT_API_KEY",
    "KSTORE_REVIEW_TIMEOUT_SECONDS",
)

KNOWN_KEYS = REQUIRED + OPTIONAL


def _parse_file(path: Path) -> dict:
    if path.stat().st_mode & 0o077:
        raise ValueError(
            "KStore configuration must not be accessible by group/others"
        )
    values: dict = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or key not in KNOWN_KEYS or key in values:
            raise ValueError(f"Invalid or duplicate configuration key on line {number}")
        if value.startswith(('"', "'")) and value[-1:] == value[:1] and len(value) >= 2:
            value = value[1:-1]
        values[key] = value
    return values


def load_config() -> dict:
    path = Path(
        os.environ.get("KSTORE_CONFIG_FILE", "~/.config/kstore/client.env")
    ).expanduser()
    values: dict = {}
    if path.exists():
        values.update(_parse_file(path))
    values.update(
        {key: os.environ[key] for key in KNOWN_KEYS if key in os.environ}
    )
    missing = [key for key in REQUIRED if not values.get(key)]
    if missing:
        raise ValueError("Missing KStore configuration: " + ", ".join(missing))

    for key in ("KSTORE_URL", "KSTORE_QDRANT_URL"):
        parsed = urlsplit(values[key])
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.query
        ):
            raise ValueError("Invalid base URL: " + key)
        try:
            parsed.port
        except ValueError:
            raise ValueError("Invalid port: " + key) from None

    if not values["KSTORE_COLLECTION"].strip():
        raise ValueError("KSTORE_COLLECTION must not be blank")

    receipt_root = Path(values["KSTORE_RECEIPT_ROOT"]).expanduser()
    if not receipt_root.is_absolute():
        raise ValueError("KSTORE_RECEIPT_ROOT must be an absolute path")

    try:
        timeout = float(values["KSTORE_REQUEST_TIMEOUT_SECONDS"])
        command = json.loads(values["KSTORE_POSTGRES_READ_COMMAND_JSON"])
    except (ValueError, TypeError):
        raise ValueError("Invalid timeout or PostgreSQL command configuration") from None
    if not 0 < timeout <= 3600:
        raise ValueError("Timeout must be greater than zero and at most 3600 seconds")
    if (
        not isinstance(command, list)
        or not command
        or any(
            not isinstance(part, str) or not part or "\x00" in part
            for part in command
        )
    ):
        raise ValueError("PostgreSQL read command must be a nonempty JSON argv array")

    values["review_timeout"] = float(values.get("KSTORE_REVIEW_TIMEOUT_SECONDS", "1800"))
    if not 0 < values["review_timeout"] <= 7200:
        raise ValueError("Invalid review timeout")
    values["timeout"] = timeout
    values["postgres_command"] = command
    values["receipt_root"] = receipt_root
    return values
