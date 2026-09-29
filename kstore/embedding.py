"""Measured embedding over ollama — bounded batches, retries, adaptive split.

The v1 defect sent a whole document's chunk list in one request with a flat
60 s timeout; under concurrent load that request exceeded the timeout and
`/doc/write` failed with HTTP 500 before any SQL ran. This module replaces
it everywhere (concierge, ingest, MCP remember).

Policy (defaults from the 2026-09-27 measurement on .87, idle GPU):
- sequential batches of `KSTORE_EMBED_BATCH` (16) — never parallel, so a
  large write cannot pile onto the single embedder alongside concierge
  queries;
- per-request timeout `KSTORE_EMBED_TIMEOUT` (90 s ≈ 10x the worst
  measured batch);
- `KSTORE_EMBED_RETRIES` (2) retries with exponential backoff on timeouts,
  transport errors and 5xx/429;
- a batch that still times out is split in half and each half retried with
  fresh retries (bounded by `KSTORE_EMBED_DEADLINE`, 600 s total) — one
  slow chunk no longer kills a whole document write;
- transport/HTTP failures that persist after retries are backend-down
  conditions: raised as EmbeddingError (surfaces as HTTP 503), never
  silently truncated or padded.
"""

from __future__ import annotations

import time
import math

import httpx

from . import config


class EmbeddingError(RuntimeError):
    """Embedding failed after retries (backend down / persistent HTTP error)."""


class EmbeddingTimeout(EmbeddingError):
    """Embedding exceeded the total deadline."""


def _post(texts: list[str], timeout: float) -> list[list[float]]:
    r = httpx.post(
        f"{config.OLLAMA_URL}/api/embed",
        json={"model": config.EMBED_MODEL, "input": texts, "keep_alive": 0},
        timeout=timeout,
    )
    r.raise_for_status()
    embeddings = r.json()["embeddings"]
    if len(embeddings) != len(texts):
        raise EmbeddingError(
            f"embedder returned {len(embeddings)} vectors for {len(texts)} inputs"
        )
    for vector in embeddings:
        if len(vector) != config.EMBED_DIMS or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
            raise EmbeddingError("Embedding dimensions or finite numeric values invalid")
    return embeddings


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return False


def _with_retries(batch: list[str], deadline: float) -> list[list[float]]:
    attempt = 0
    last: Exception | None = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise EmbeddingTimeout(
                f"embedding deadline exceeded before a batch completed "
                f"({config.EMBED_DEADLINE:.0f}s)"
            )
        try:
            return _post(batch, min(config.EMBED_TIMEOUT, remaining))
        except EmbeddingError:
            raise
        except Exception as exc:  # httpx errors only reach here
            if not _retryable(exc):
                raise EmbeddingError(f"embedding request rejected: {exc}") from exc
            last = exc
        if attempt >= config.EMBED_RETRIES:
            if isinstance(last, httpx.TimeoutException):
                raise last  # let the splitter halve the batch
            raise EmbeddingError(
                f"embedding unavailable after {attempt + 1} attempts: {last}"
            ) from last
        time.sleep(max(0, min(2.0 * (2 ** attempt), 15.0, deadline - time.monotonic())))
        attempt += 1


def _embed_splitting(batch: list[str], deadline: float) -> list[list[float]]:
    try:
        return _with_retries(batch, deadline)
    except httpx.TimeoutException:
        if len(batch) == 1:
            raise EmbeddingTimeout(
                f"single text exceeded {config.EMBED_TIMEOUT:.0f}s after "
                f"{config.EMBED_RETRIES} retries"
            ) from None
        mid = len(batch) // 2
        return _embed_splitting(batch[:mid], deadline) + _embed_splitting(
            batch[mid:], deadline
        )


def embed(texts: list[str], *, deadline: float | None = None) -> list[list[float]]:
    """Embed texts under the measured batch/timeout/retry policy."""
    if not texts:
        return []
    deadline = min(deadline if deadline is not None else float("inf"), time.monotonic() + config.EMBED_DEADLINE)
    out: list[list[float]] = []
    for i in range(0, len(texts), config.EMBED_BATCH):
        out.extend(_embed_splitting(texts[i : i + config.EMBED_BATCH], deadline))
    return out
