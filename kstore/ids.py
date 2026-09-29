"""UUIDv8 generation — ihkg scheme.

Layout (128 bits, RFC-4122 variant):

    tttttttt-tttt-8nnn-ysss-rrrrrrrrrrrr
    ├─ bits 127..80 : timestamp, ms since epoch, big-endian (sortable)
    ├─ bits  79..76 : version = 8
    ├─ bits  75..64 : node_id (12 bits) — the "ancestry": which origin
    │                  node minted it (default: last IP octet)
    ├─ bits  63..62 : variant = 0b10 (RFC 4122)  ─┐ g4
    ├─ bits  61..48 : sequence (14 bits)        ─┘
    └─ bits  47..0  : random entropy (48 bits)  (g5)

Origin root for the kstore system, same role as hKG's
01928c5d-2000-8000-8000-000000000001:

    KSTORE_ORIGIN_UUID — minted once, immutable, every entity's ancestry
    chain terminates here via parent_uuid links.
"""

from __future__ import annotations

import os
import random
import socket
import time
import uuid as _uuid

# Minted 2026-09-22 for the kstore system (kstore.db init writes it as the
# root row; all top-level ingests carry parent_uuid=KSTORE_ORIGIN_UUID).
KSTORE_ORIGIN_UUID = "01928c5d-2000-8000-8000-0000000000a1"

_rng = random.SystemRandom()


def default_node_id() -> int:
    """12-bit node id — last octet of the host IP, as in ihkg."""
    try:
        ip = socket.gethostbyname(socket.gethostname())
        return int(ip.split(".")[-1]) & 0xFFF
    except Exception:
        return _rng.randint(0, 0xFFF)


_seq = _rng.randint(0, 0x3FFF)
_seq_lock_ts = 0


def _next_seq() -> int:
    global _seq
    _seq = (_seq + 1) & 0x3FFF
    return _seq


def uuidv8(node_id: int | None = None) -> str:
    """Generate a time-ordered, node-attributed UUIDv8 string."""
    if node_id is None:
        node_id = default_node_id()
    ts = int(time.time() * 1000) & 0xFFFFFFFFFFFF  # 48 bits
    seq = _next_seq()
    rand = int.from_bytes(os.urandom(6), "big")  # 48 bits

    uuid_int = ts << 80
    uuid_int |= 0x8 << 76                    # version 8
    uuid_int |= (node_id & 0xFFF) << 64      # ancestry/origin node
    uuid_int |= 0b10 << 62                   # RFC 4122 variant
    uuid_int |= seq << 48
    uuid_int |= rand
    return str(_uuid.UUID(int=uuid_int))


def parse(uuid_str: str) -> dict:
    """Decode a kstore UUIDv8 back into its components."""
    i = _uuid.UUID(uuid_str).int
    return {
        "timestamp_ms": i >> 80,
        "version": (i >> 76) & 0xF,
        "node_id": (i >> 64) & 0xFFF,
        "variant": (i >> 62) & 0x3,
        "sequence": (i >> 48) & 0x3FFF,
    }
