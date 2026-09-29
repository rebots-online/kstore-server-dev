"""Read-only, source-labelled observations for the Habitat UI.

See DOCS/ARCHITECTURE.md, "Habitat observability and no invented UI data".
No raw activity, credentials, provider URL, or review finding body leaves here.
"""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import re
from datetime import datetime, timedelta, timezone

import httpx

from . import config
from .db import pg, qdrant


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _observe(read):
    observed_at = _now()
    try:
        return {"state": "ok", "observed_at": observed_at, "data": read()}
    except Exception as exc:
        return {"state": "unavailable", "observed_at": observed_at,
                "error_class": type(exc).__name__}


def _postgres():
    with pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), max(created_at) FROM activity_events")
        event_count, latest_event_at = cur.fetchone()
        cur.execute("SELECT state, count(*) FROM embedding_jobs GROUP BY state")
        job_counts = {state: count for state, count in cur.fetchall()}
        cur.execute("SELECT EXTRACT(EPOCH FROM now()-min(created_at)) "
                    "FROM embedding_jobs WHERE state <> 'complete'")
        oldest_age = cur.fetchone()[0]
        cur.execute("SELECT split_part(last_error, ':', 1), updated_at "
                    "FROM embedding_jobs WHERE last_error IS NOT NULL "
                    "ORDER BY updated_at DESC LIMIT 1")
        error = cur.fetchone()
        cur.execute("SELECT id, verdict->>'status', created_at FROM audit_reviews "
                    "ORDER BY created_at DESC, id DESC LIMIT 1")
        review = cur.fetchone()
    return {
        "activity": {"event_count": event_count,
                     "latest_event_at": latest_event_at},
        "queue": {"counts": {key: job_counts.get(key, 0)
                             for key in ("pending", "processing", "complete")},
                  "oldest_incomplete_age_seconds": float(oldest_age) if oldest_age is not None else None,
                  "latest_error": ({"class": error[0], "updated_at": error[1]}
                                   if error else None)},
        "latest_review": ({"id": str(review[0]), "status": review[1],
                           "created_at": review[2]} if review else None),
    }


def _qdrant():
    collection = qdrant().get_collection(config.COLLECTION)
    return {"collection": config.COLLECTION, "points": collection.points_count}


def _ollama():
    response = httpx.get(config.OLLAMA_URL.rstrip("/") + "/api/ps", timeout=3)
    response.raise_for_status()
    models = response.json().get("models", [])
    return {"configured_embedding_model": config.EMBED_MODEL,
            "loaded": any(model.get("name") == config.EMBED_MODEL or
                          model.get("model") == config.EMBED_MODEL for model in models)}


def _worker():
    result = subprocess.run(
        ["systemctl", "is-active", "kstore-embedding-worker.service"],
        capture_output=True, text=True, timeout=3, check=False)
    state = result.stdout.strip()
    if not state or state not in {"active", "inactive", "failed", "activating", "deactivating"}:
        raise RuntimeError("worker state probe failed")
    return {"unit": "kstore-embedding-worker.service", "state": state}


def snapshot():
    return {"generated_at": _now(), "host": socket.gethostname(),
            "sources": {"postgres": _observe(_postgres),
                        "qdrant": _observe(_qdrant),
                        "ollama": _observe(_ollama),
                        "worker": _observe(_worker)}}


def _cursor_encode(row):
    data = [row[0].isoformat(), row[1], row[2]]
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")


def _cursor_decode(cursor):
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(data, list) or len(data) != 3 or not isinstance(data[1], str) or not isinstance(data[2], int):
            raise ValueError
        return datetime.fromisoformat(data[0]), data[1], data[2]
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid event cursor") from exc


def events(limit=80, before=None):
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    params = []
    where = ""
    if before:
        params.extend(_cursor_decode(before))
        where = "WHERE (created_at, stream_id, sequence) < (%s, %s, %s)"
    params.append(limit + 1)
    with pg() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT created_at, stream_id, sequence, kind, turn_id, filtered, "
            "octet_length(raw), sha256 FROM activity_events " + where +
            " ORDER BY created_at DESC, stream_id DESC, sequence DESC LIMIT %s", params)
        rows = cur.fetchall()
    page = rows[:limit]
    return {"observed_at": _now(), "items": [
        {"created_at": row[0], "stream_id": row[1], "sequence": row[2],
         "kind": row[3], "turn_id": row[4], "filtered": row[5],
         "bytes": row[6], "sha256": row[7]} for row in page],
        "next_cursor": _cursor_encode(page[-1]) if len(rows) > limit else None}


def jobs(limit=50):
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    with pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT entity_uuid, model, collection, state, attempts, "
                    "created_at, updated_at, next_attempt_at, "
                    "split_part(last_error, ':', 1) FROM embedding_jobs "
                    "WHERE state <> 'complete' ORDER BY created_at, entity_uuid LIMIT %s", (limit,))
        rows = cur.fetchall()
    return {"observed_at": _now(), "items": [
        {"entity_uuid": str(row[0]), "model": row[1], "collection": row[2],
         "state": row[3], "attempts": row[4], "created_at": row[5],
         "updated_at": row[6], "next_attempt_at": row[7],
         "error_class": row[8] or None} for row in rows]}


def reviews(limit=30):
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    with pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, stream_id, verdict->>'status', verdict->'coverage', "
                    "created_at FROM audit_reviews ORDER BY created_at DESC, id DESC LIMIT %s", (limit,))
        rows = cur.fetchall()
    return {"observed_at": _now(), "items": [
        {"id": str(row[0]), "stream_id": row[1], "status": row[2],
         "coverage": row[3], "created_at": row[4]} for row in rows]}


_LOG_UNITS = {
    "qdrant": "qdrant.service",
    "concierge": "kstore-concierge.service",
    "worker": "kstore-embedding-worker.service",
    "gpu_recovery": "kstore-gpu-recovery.service",
    "ollama": "ollama.service",
}
_IMPORTANT = re.compile(r"error|fail|timeout|timed out|refus|denied|disconnect|unavailable", re.I)


def logs(source, limit=100, cursor=None, at=None, query=None):
    """Read actual journald entries; cursor means newer, at means a ±5m seek."""
    if source not in _LOG_UNITS:
        raise ValueError("unknown log source")
    if not 1 <= limit <= 200:
        raise ValueError("limit must be between 1 and 200")
    if cursor and at:
        raise ValueError("cursor and at are mutually exclusive")
    command = ["journalctl", "-u", _LOG_UNITS[source], "--no-pager", "-o", "json"]
    if cursor:
        if len(cursor) > 1024 or "\n" in cursor or "\x00" in cursor:
            raise ValueError("invalid journal cursor")
        command.extend(["--after-cursor", cursor])
    elif at:
        try:
            instant = datetime.fromisoformat(at.replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise ValueError("invalid seek time") from exc
        start = (instant - timedelta(minutes=5)).astimezone()
        end = (instant + timedelta(minutes=5)).astimezone()
        command.extend(["--since", start.strftime("%Y-%m-%d %H:%M:%S"),
                        "--until", end.strftime("%Y-%m-%d %H:%M:%S")])
    else:
        command.extend(["--since", "1 hour ago"])
    if not cursor:
        command.extend(["-n", str(limit * 3)])
    result = subprocess.run(command, capture_output=True, timeout=7, check=False)
    if result.returncode != 0:
        raise RuntimeError("journal read failed")
    if len(result.stdout) > 2_000_000:
        raise RuntimeError("journal page exceeded bound")
    entries = []
    for raw_line in result.stdout.splitlines():
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        message = row.get("MESSAGE", "")
        if isinstance(message, list):
            message = "".join(str(item) for item in message)
        message = str(message)
        if query and query.casefold() not in message.casefold():
            continue
        microseconds = int(row.get("__REALTIME_TIMESTAMP", 0))
        stamp = datetime.fromtimestamp(microseconds / 1_000_000, timezone.utc).isoformat()
        priority = int(row.get("PRIORITY", 6))
        entries.append({"id": row.get("__CURSOR", ""), "at": stamp,
                        "message": message[:4000], "truncated": len(message) > 4000,
                        "priority": priority,
                        "highlight": priority <= 4 or bool(_IMPORTANT.search(message))})
    page = entries[-limit:] if not cursor else entries[:limit]
    return {"source": source, "unit": _LOG_UNITS[source], "observed_at": _now(),
            "items": page, "next_cursor": page[-1]["id"] if page else cursor,
            "gap": bool(cursor and len(entries) > limit)}
