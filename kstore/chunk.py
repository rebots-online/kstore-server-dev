"""Markdown/text chunker — header-anchored, breadcrumb-carrying.

Each chunk carries its header breadcrumb ("Manual > Conventions > CC-3") so
a retrieved fragment is self-describing without its document context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_CHARS = 3600   # ~900 tokens — fits embedder ctx with room
MIN_CHARS = 200    # merge sections smaller than this into the next
OVERLAP = 0        # header anchoring already carries context


@dataclass
class Chunk:
    text: str
    breadcrumb: str
    chunk_ix: int


_HEADER = re.compile(r"^(#{1,6})\s+(.*)$")


def chunk_markdown(text: str, title: str = "") -> list[Chunk]:
    """Split markdown on headers; merge undersized sections forward."""
    sections: list[tuple[str, str]] = []  # (breadcrumb, body)
    crumbs: list[tuple[int, str]] = []    # header stack [(level, name)]
    buf: list[str] = []

    def flush():
        body = "\n".join(buf).strip()
        if body or sections == []:
            bc = " > ".join(n for _, n in crumbs) or title or "(preamble)"
            sections.append((bc, body))
        buf.clear()

    for line in text.splitlines():
        m = _HEADER.match(line)
        if m:
            flush()
            level, name = len(m.group(1)), m.group(2).strip()
            crumbs = [(l, n) for l, n in crumbs if l < level]
            crumbs.append((level, name))
            buf.append(line)
        else:
            buf.append(line)
    flush()

    # Merge tiny sections into their successor; split oversized ones.
    merged: list[tuple[str, str]] = []
    carry = ""
    carry_bc = ""
    for bc, body in sections:
        body = (carry + "\n\n" + body).strip() if carry else body
        bc = carry_bc or bc
        if len(body) < MIN_CHARS:
            carry, carry_bc = body, bc
            continue
        carry, carry_bc = "", ""
        merged.append((bc, body))
    if carry:
        if merged:
            bc, body = merged[-1]
            merged[-1] = (bc, (body + "\n\n" + carry).strip())
        else:
            merged.append((carry_bc or title, carry))

    chunks: list[Chunk] = []
    ix = 0
    for bc, body in merged:
        if len(body) <= MAX_CHARS:
            chunks.append(Chunk(body, bc, ix)); ix += 1
            continue
        # hard-split oversized section on paragraph boundaries
        part = ""
        for para in re.split(r"\n\s*\n", body):
            if part and len(part) + len(para) + 2 > MAX_CHARS:
                chunks.append(Chunk(part.strip(), bc, ix)); ix += 1
                part = para
            else:
                part = f"{part}\n\n{para}" if part else para
        if part.strip():
            chunks.append(Chunk(part.strip(), bc, ix)); ix += 1
    return chunks


def chunk_text(text: str, title: str = "") -> list[Chunk]:
    """Plain-text fallback — fixed-size paragraph-aware windows."""
    chunks: list[Chunk] = []
    part = ""
    ix = 0
    for para in re.split(r"\n\s*\n", text):
        if part and len(part) + len(para) + 2 > MAX_CHARS:
            chunks.append(Chunk(part.strip(), title, ix)); ix += 1
            part = para
        else:
            part = f"{part}\n\n{para}" if part else para
    if part.strip():
        chunks.append(Chunk(part.strip(), title, ix))
    return chunks


def chunk_document(text: str, path: str, title: str = "") -> list[Chunk]:
    if path.lower().endswith((".md", ".markdown")):
        return chunk_markdown(text, title)
    return chunk_text(text, title)
