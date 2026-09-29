"""kstore MCP server — stdio transport, runs on each workstation.

All state lives on .87; this is a thin proxy so every agent CLI gets the
same tools:

    kstore_search   — semantic search over the knowledge store
    kstore_remember — write a decision/finding back (conversations dataset)
    kstore_stats    — collection size/health

Register per-CLI:
    claude:  claude mcp add kstore -- <venv>/python -m kstore.mcp_server
    codex:   ~/.codex/config.toml [mcp_servers.kstore] command=...
    devin:   ~/.config/devin/... (mcp server entry)
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP
from qdrant_client.models import PointStruct

from . import config
from .db import COLLECTION, pg, qdrant
from .embedding import embed
from .ids import uuidv8

CONCIERGE_URL = config.CONCIERGE_URL

mcp = FastMCP("kstore")


@mcp.tool()
def kstore_search(query: str, limit: int = 8, source_type: str | None = None) -> str:
    """Search the shared knowledge store (Admin-Manual, research, codebases,
    decisions, past conversations). ALWAYS search before re-deriving prior
    work — this is the single source of truth."""
    r = httpx.get(
        f"{CONCIERGE_URL}/search", params={"q": query, "limit": limit}, timeout=30
    )
    r.raise_for_status()
    hits = r.json()["hits"]
    if source_type:
        hits = [h for h in hits if h["source_type"] == source_type]
    if not hits:
        return "No results."
    return "\n\n---\n\n".join(
        f"[{h['source_type']}] {h['path']} — {h['breadcrumb']} "
        f"(score {h['score']}, uuid {h['uuid']})\n\n{h['content'][:2000]}"
        for h in hits
    )


@mcp.tool()
def kstore_remember(content: str, kind: str = "decision", title: str = "") -> str:
    """Write a decision, finding, or outcome back to the knowledge store so
    future sessions never re-derive it. kind: decision|finding|conversation|note"""
    headers = {}
    if config.HTTP_BEARER_TOKEN:
        headers["Authorization"] = "Bearer " + config.HTTP_BEARER_TOKEN
    response = httpx.post(CONCIERGE_URL + "/remember", json={
        "content": content, "kind": kind, "title": title,
    }, headers=headers, timeout=30)
    response.raise_for_status()
    receipt = response.json()
    return f"Stored as {receipt['uuid']}; indexing={receipt['indexing']}"


@mcp.tool()
def kstore_stats() -> str:
    """Health + size of the knowledge store."""
    qc = qdrant()
    info = qc.get_collection(COLLECTION)
    return f"collection={COLLECTION} points={info.points_count} status={info.status}"


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
