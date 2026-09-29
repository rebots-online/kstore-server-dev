"""Read-only PostgreSQL/Qdrant parity report. NEVER mutates either store.

Reports the known v1 gap (Qdrant points > PG entities from superseded
revisions and orphans of the crashed first ingest pass) as evidence for
the pending reconcile decision. Per-document verification of new writes
(kstore_client) does not certify whole-corpus parity — this report is the
honest scope boundary.

Usage: python -m kstore.parity [--json]
"""

from __future__ import annotations

import argparse
import json
import sys

from .db import COLLECTION, pg, qdrant


def collect() -> dict:
    out: dict = {"collection": COLLECTION}

    with pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM documents")
        out["pg_documents"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM entities")
        out["pg_entities"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM document_revisions")
        out["pg_document_revisions"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM documents WHERE head_rev > 1")
        out["pg_documents_multirev"] = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM entities WHERE revision > 1")
        out["pg_entities_superseded_revisions"] = cur.fetchone()[0]
        cur.execute("SELECT uuid::text FROM entities")
        pg_ids = {r[0] for r in cur.fetchall()}

    qc = qdrant()
    info = qc.get_collection(COLLECTION)
    out["qdrant_points"] = info.points_count

    qdrant_ids: set[str] = set()
    offset = None
    while True:
        pts, offset = qc.scroll(
            COLLECTION,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        if not pts:
            break
        qdrant_ids.update(str(p.id) for p in pts)
        if offset is None:
            break

    out["qdrant_ids"] = len(qdrant_ids)
    out["qdrant_orphans_not_in_pg"] = len(qdrant_ids - pg_ids)
    out["pg_entities_missing_vectors"] = len(pg_ids - qdrant_ids)
    out["parity_gap_points_minus_entities"] = out["qdrant_points"] - out["pg_entities"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="raw JSON instead of table")
    args = ap.parse_args()
    data = collect()
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    for key in sorted(data):
        print(f"{key:38} {data[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
