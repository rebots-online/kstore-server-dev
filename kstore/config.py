"""kstore configuration — the single environment authority for server-side code.

Resolution order: process environment (the systemd unit sets the KSTORE_*
keys for the deployed concierge) wins over the repo-root `.env`
(gitignored; schema documented in the committed `.env.example`). No other
module in the package reads os.environ for topology — the reference
deployment defaults live here, exactly once, so workstation checkouts
without a `.env` still point at the live service.

Clients (workstation side) are configured separately and strictly through
`client/kstore_config.py` + `~/.config/kstore/client.env`.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ENV = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv() -> None:
    """Repo-root .env provides defaults for keys not already in the environment."""
    if not _REPO_ENV.exists():
        return
    for line in _REPO_ENV.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw.strip() else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    return float(raw) if raw.strip() else default


# --- required for any Postgres-touching entry point (no synthesis, no fallback)
PG_DSN = os.environ.get("KSTORE_PG_DSN", "")

# --- reference deployment topology (.87 LAN); override via env or repo .env
QDRANT_URL = os.environ.get("KSTORE_QDRANT_URL", "http://192.168.0.87:6333")
OLLAMA_URL = os.environ.get("KSTORE_OLLAMA_URL", "http://192.168.0.87:11434")
CONCIERGE_URL = os.environ.get("KSTORE_CONCIERGE_URL", "http://192.168.0.87:8788")

# --- models / collection
CONCIERGE_MODEL = os.environ.get("KSTORE_CONCIERGE_MODEL", "glm-5.3-flash")
EMBED_MODEL = os.environ.get("KSTORE_EMBED_MODEL", "qwen3-embedding:8b")
EMBED_DIMS = _int("KSTORE_EMBED_DIMS", 4096)
COLLECTION = os.environ.get("KSTORE_COLLECTION", "knowledge")

# --- retrieval knobs
TOP_K_PER_QUERY = _int("KSTORE_TOP_K", 10)
MAX_RESULTS = _int("KSTORE_MAX_RESULTS", 5)
SCORE_FLOOR = _float("KSTORE_SCORE_FLOOR", 0.35)

# --- embedding policy (measured 2026-09-27 on .87, idle GPU:
#     ~0.33-0.44 s per 1k-char text; 16x3600-char batch ~7 s. Timeout is
#     ~10x the worst measured batch to absorb concurrent concierge load.)
EMBED_BATCH = _int("KSTORE_EMBED_BATCH", 4)
EMBED_TIMEOUT = _float("KSTORE_EMBED_TIMEOUT", 90.0)
EMBED_RETRIES = _int("KSTORE_EMBED_RETRIES", 2)
EMBED_DEADLINE = _float("KSTORE_EMBED_DEADLINE", 600.0)

# --- optional HTTP bearer for the concierge; unset (default) keeps the
#     LAN-trusted no-auth behavior. Clients send it only when configured.
HTTP_BEARER_TOKEN = os.environ.get("KSTORE_HTTP_BEARER_TOKEN", "")


# Hosted review and retrieval reasoner; independent of local embedding capacity.
CONCIERGE_BASE_URL = os.environ.get("KSTORE_CONCIERGE_BASE_URL", "https://api.z.ai/api/paas/v4").rstrip("/")
CONCIERGE_API_KEY = os.environ.get("KSTORE_CONCIERGE_API_KEY", os.environ.get("ZAI_API_KEY", ""))
REVIEW_TIMEOUT = _float("KSTORE_REVIEW_TIMEOUT", 360)
REVIEW_IDLE_TIMEOUT = _float("KSTORE_REVIEW_IDLE_TIMEOUT", 30)
REVIEW_CONNECT_TIMEOUT = _float("KSTORE_REVIEW_CONNECT_TIMEOUT", 10)
REVIEW_MAX_TOKENS = _int("KSTORE_REVIEW_MAX_TOKENS", 16384)
REVIEW_WINDOW_CHARS = _int("KSTORE_REVIEW_WINDOW_CHARS", 120000)
AUTHORITY_ROOT = Path(os.environ.get("KSTORE_AUTHORITY_ROOT", "/home/robin/Admin-Manual")).expanduser()
WORKER_POLL = _float("KSTORE_WORKER_POLL", 10)
GPU_WINDOW = _float("KSTORE_GPU_WINDOW", 60)
GPU_COOLDOWN = _float("KSTORE_GPU_COOLDOWN", 300)
GPU_MIN_FREE_MB = _int("KSTORE_GPU_MIN_FREE_MB", 6500)
GPU_INDEX = _int("KSTORE_GPU_INDEX", 0)
GPU_RELEASE_TIMEOUT = _float("KSTORE_GPU_RELEASE_TIMEOUT", 30)
GPU_STATE_PATH = Path(os.environ.get("KSTORE_GPU_STATE_PATH", "~/.local/state/kstore/gpu.json")).expanduser()
MINER_EXE = str(Path(os.environ.get("KSTORE_MINER_EXE", "~/.local/bin/krig-miner")).expanduser())
MINER_LAUNCHER = str(Path(os.environ.get("KSTORE_MINER_LAUNCHER", "~/.local/bin/minekrig-prl.sh")).expanduser())
MINER_SERVICE = os.environ.get("KSTORE_MINER_SERVICE", "kstore-prl-miner.service")

for _name in ("EMBED_DIMS", "EMBED_BATCH", "EMBED_TIMEOUT", "EMBED_DEADLINE",
              "REVIEW_TIMEOUT", "REVIEW_IDLE_TIMEOUT", "REVIEW_CONNECT_TIMEOUT",
              "REVIEW_MAX_TOKENS", "REVIEW_WINDOW_CHARS",
              "WORKER_POLL", "GPU_WINDOW", "GPU_MIN_FREE_MB", "GPU_RELEASE_TIMEOUT"):
    if globals()[_name] <= 0:
        raise ValueError("KSTORE_" + _name + " must be positive")
if GPU_INDEX < 0 or GPU_COOLDOWN < 0 or EMBED_RETRIES < 0:
    raise ValueError("GPU index, cooldown and retry count must be nonnegative")
from urllib.parse import urlsplit
for _name in ("CONCIERGE_BASE_URL", "OLLAMA_URL", "QDRANT_URL"):
    _url = urlsplit(globals()[_name])
    if _url.scheme not in ("http", "https") or not _url.hostname or _url.username or _url.password:
        raise ValueError("Invalid KSTORE_" + _name)

GPU_DISPLAY_ALLOWLIST = tuple(os.environ.get("KSTORE_GPU_DISPLAY_ALLOWLIST", "gnome-remote-desktop-daemon,Xorg,Xwayland").split(","))

# Operator-owned manifest selects mandatory reminders, independent of lexical search.
_REMINDER_MANIFEST = os.environ.get("KSTORE_REMINDER_MANIFEST", "").strip()
REMINDER_MANIFEST = Path(_REMINDER_MANIFEST).expanduser() if _REMINDER_MANIFEST else None
