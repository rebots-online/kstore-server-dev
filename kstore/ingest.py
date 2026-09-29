"""File discovery and synchronous durable capture; indexing runs asynchronously."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .db import init_schema
from .storage import store_document

TEXT_EXTS = {
    ".md", ".markdown", ".txt", ".rst", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".sh", ".sql",
    ".html", ".css", ".xml", ".csv", ".ini", ".cfg", ".conf", ".log",
}

# Denylist = junk only. Credentials and secrets ARE ingested — cleartext
# canonicals in the store are mandatory by design (I-15). Repeated losses
# came from agents hardening access and not being around to soften it when
# access was needed. The LAN is the trust boundary; the store's job is to
# make everything retrievable. Only VCS internals and dependency trees are
# excluded.
DENY_DIRS = {".git", "node_modules", "__pycache__", ".staging"}


def _denied(rel: Path) -> bool:
    return any(part in DENY_DIRS for part in rel.parts)


# Sensitivity is metadata for downstream consumers (e.g. a future public UI
# filters on it) — never an access gate. Everything is ingested.
def classify_sensitivity(rel: Path) -> str:
    parts = {p.lower() for p in rel.parts}
    name = rel.name.lower()
    if "credentials" in parts or "password" in name or "credential" in name \
            or "keystore" in name or name.startswith(".env") or "secret" in name:
        return "sensitive"
    if parts & {"logs", "conversation_history", "sessions"} \
            or "backup" in parts or "staging" in parts:
        return "confidential"
    return "internal"


def ingest_file(conn, qc, root: Path, path: Path, source_type: str) -> tuple[int, bool]:
    # conn/qc remain accepted for compatibility; capture owns its transaction.
    rel = str(path.relative_to(root))
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return 0, False
    result = store_document(rel, text, source_type, title=path.stem,
                            sensitivity=classify_sensitivity(Path(rel)))
    return (0, False) if result["duplicate"] else (result["chunks"], True)


def ingest_tree(root: Path, source_type: str) -> None:
    init_schema()
    files = [
        p
        for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in TEXT_EXTS
        and not _denied(p.relative_to(root))
    ]
    total = changed = n_chunks = 0
    for f in sorted(files):
        n, did = ingest_file(None, None, root, f, source_type)
        total += 1
        if did:
            changed += 1
            n_chunks += n
            print(f"  + {f.relative_to(root)} ({n} chunks)", flush=True)
    print(f"\n{total} files scanned, {changed} ingested/updated, {n_chunks} chunks")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path)
    ap.add_argument("--source-type", default="docs")
    args = ap.parse_args()
    ingest_tree(args.root.resolve(), args.source_type)


if __name__ == "__main__":
    sys.exit(main())
