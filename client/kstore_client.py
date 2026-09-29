#!/usr/bin/env python3
"""kstore verified client — one generic, centrally configured implementation.

Canonical owner (reconciled 2026-09-27 from the Admin-Manual draft): this
file in https://github.com/rebots-online/kstore. Postgres owns literal
documents; Qdrant owns asynchronous semantic chunks. Durable writes require
independent PostgreSQL readback; verify_document explicitly checks both stores
after indexing. The HTTP write response alone is not verification.

Receipts never contain secrets. Documents (what to write) are invocation
data — manifests and hook transcripts — never configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kstore_config import load_config  # noqa: E402


class VerificationError(RuntimeError):
    """A store readback disagreed with the write or the sent content."""


def _sql_literal(value: str) -> str:
    """Quote a value for the explicit kstore schema SQL (single-quote doubling)."""
    return "'" + value.replace("'", "''") + "'"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class KStoreClient:
    def __init__(self, config: dict | None = None):
        self.config = config or load_config()
        self.base = self.config["KSTORE_URL"].rstrip("/")
        self.qdrant_base = self.config["KSTORE_QDRANT_URL"].rstrip("/")
        self.collection = self.config["KSTORE_COLLECTION"]
        self.timeout = self.config["timeout"]
        self.receipt_root = self.config["receipt_root"]

    # ------------------------------------------------------------------ HTTP
    def _headers(self, has_body: bool) -> dict:
        headers = {"Content-Type": "application/json"} if has_body else {}
        token = self.config.get("KSTORE_HTTP_BEARER_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
        return headers

    def _request(self, method: str, url: str, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(
            url, data=data, method=method, headers=self._headers(data is not None)
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            return json.load(response)

    # ------------------------------------------------------- concierge API
    def read_document(self, path: str, rev: int | None = None) -> dict:
        query = {"id": path}
        if rev is not None:
            query["rev"] = rev
        return self._request("GET", f"{self.base}/doc?{urllib.parse.urlencode(query)}")

    def write_document(
        self, path: str, content: str, source: str, title: str | None = None,
        mode: str = "append",
    ) -> dict:
        return self._request(
            "POST",
            f"{self.base}/doc/write",
            {
                "id": path,
                "content": content,
                "source_type": source,
                "title": title or path.rsplit("/", 1)[-1],
                "mode": mode,
            },
        )

    def inject(self, prompt: str, max_results: int = 3) -> dict:
        return self._request(
            "POST", f"{self.base}/inject",
            {"prompt": prompt[:4000], "max_results": max_results},
        )

    # --------------------------------------------- independent store channels
    def pg_rows(self, sql: str) -> list[list[str]]:
        """Read-only SQL through the configured argv command (stdin→TSV stdout)."""
        proc = subprocess.run(
            self.config["postgres_command"],
            input=sql.encode(),
            capture_output=True,
            timeout=self.timeout,
        )
        if proc.returncode != 0:
            detail = proc.stderr.decode(errors="replace").strip()[:400]
            raise VerificationError(f"postgres read failed: {detail}")
        out = proc.stdout.decode().rstrip("\n")
        return [] if not out else [line.split("\t") for line in out.splitlines()]

    def qdrant_scroll(self, must: list[dict]) -> list[dict]:
        """Direct Qdrant scroll (never via the concierge), paginated."""
        headers = {"Content-Type": "application/json"}
        api_key = self.config.get("KSTORE_QDRANT_API_KEY")
        if api_key:
            headers["api-key"] = api_key
        url = (
            f"{self.qdrant_base}/collections/"
            f"{urllib.parse.quote(self.collection, safe='')}/points/scroll"
        )
        points: list[dict] = []
        offset = None
        while True:
            body: dict = {
                "filter": {"must": must},
                "limit": 256,
                "with_payload": True,
                "with_vector": False,
            }
            if offset is not None:
                body["offset"] = offset
            req = urllib.request.Request(
                url, data=json.dumps(body).encode(), headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                result = json.load(response)["result"]
            points.extend(result.get("points", []))
            offset = result.get("next_page_offset")
            if offset is None:
                return points

    # ------------------------------------------------------------ verification
    def verify_document(
        self,
        path: str,
        source: str | None = None,
        content: str | None = None,
        expect: dict | None = None,
    ) -> dict:
        """Independently verify identity/revision/content/hash in both stores.

        Raises VerificationError (stage-named) on any disagreement. `content`
        enables byte-exact checks against the verbatim revision store.
        `expect` (the write response) is compared against, never trusted.
        """
        where = f"path = {_sql_literal(path)}"
        if source is not None:
            where += f" AND source_type = {_sql_literal(source)}"
        rows = self.pg_rows(
            "SELECT uuid::text, head_rev, sha256, source_type FROM documents "
            f"WHERE {where}"
        )
        if len(rows) != 1:
            raise VerificationError(
                f"postgres documents rows for {path!r}: {len(rows)} (expected 1)"
            )
        doc_uuid, head_rev_s, doc_sha, src = rows[0]
        head_rev = int(head_rev_s)

        if expect is not None:
            if expect.get("doc_uuid") != doc_uuid:
                raise VerificationError("doc_uuid mismatch: write vs postgres")
            if int(expect.get("revision", head_rev)) != head_rev:
                raise VerificationError("revision mismatch: write vs postgres")

        rev_rows = self.pg_rows(
            "SELECT sha256 FROM document_revisions "
            f"WHERE doc_uuid = {_sql_literal(doc_uuid)} AND revision = {head_rev}"
        )
        if len(rev_rows) != 1:
            raise VerificationError(
                "document_revisions row missing — legacy document has no "
                "verbatim store (exact readback impossible)"
            )
        rev_sha = rev_rows[0][0]
        if rev_sha != doc_sha:
            raise VerificationError("sha256 mismatch: documents vs document_revisions")
        if content is not None and rev_sha != _sha256(content):
            raise VerificationError("document_revisions.sha256 != sha256(sent content)")

        ent_rows = self.pg_rows(
            "SELECT uuid::text, content_sha256 FROM entities "
            f"WHERE parent_uuid = {_sql_literal(doc_uuid)} AND revision = {head_rev} "
            "ORDER BY chunk_ix"
        )
        pg_entities = {uuid: csha for uuid, csha in ent_rows}

        points = self.qdrant_scroll([
            {"key": "parent_uuid", "match": {"value": doc_uuid}},
            {"key": "revision", "match": {"value": head_rev}},
        ])
        qdrant_points = {str(p["id"]): (p.get("payload") or {}) for p in points}

        if set(pg_entities) != set(qdrant_points):
            raise VerificationError(
                f"uuid set mismatch: postgres {len(pg_entities)} vs "
                f"qdrant {len(qdrant_points)} entities at head revision"
            )
        if expect is not None and set(expect.get("entity_uuids", [])) != set(pg_entities):
            raise VerificationError("entity uuid set mismatch: write vs postgres")

        for point_id, payload in qdrant_points.items():
            body = payload.get("content")
            if not body:
                raise VerificationError(f"qdrant point {point_id} has empty content")
            claimed = payload.get("content_sha256")
            if claimed and _sha256(body) != claimed:
                raise VerificationError(f"qdrant point {point_id} content hash mismatch")
            pg_claim = pg_entities.get(point_id)
            if claimed and pg_claim and claimed != pg_claim:
                raise VerificationError(
                    f"entity {point_id} content_sha256 mismatch: postgres vs qdrant"
                )
            if content is not None and body not in content:
                raise VerificationError(
                    f"qdrant point {point_id} content not part of the sent document"
                )

        evidence = {
            "doc_uuid": doc_uuid,
            "revision": head_rev,
            "source_type": src,
            "postgres_entities": len(pg_entities),
            "qdrant_points": len(qdrant_points),
            "revision_sha256": rev_sha,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
        if content is not None:
            served = self.read_document(path)
            if not served.get("exact"):
                raise VerificationError("GET /doc did not serve the exact revision")
            if served.get("content") != content:
                raise VerificationError("GET /doc exact content != sent content")
            if served.get("sha256") != _sha256(content):
                raise VerificationError("GET /doc sha256 != sha256(sent content)")
            evidence["byte_exact_readback"] = True
        return evidence

    def verify_stored(self, path, source, content, expect=None):
        rows = self.pg_rows(
            "SELECT d.uuid::text, d.head_rev, r.sha256, "
            "encode(sha256(convert_to(r.content,'UTF8')),'hex'), "
            "(SELECT count(*) FROM entities e WHERE e.parent_uuid=d.uuid "
            "AND e.revision=d.head_rev) FROM documents d "
            "JOIN document_revisions r ON r.doc_uuid=d.uuid AND r.revision=d.head_rev "
            f"WHERE d.path={_sql_literal(path)} AND d.source_type={_sql_literal(source)}"
        )
        if len(rows) != 1 or len(rows[0]) != 5:
            raise VerificationError("Committed revision readback missing")
        row = rows[0]
        if row[2] != _sha256(content) or row[3] != _sha256(content):
            raise VerificationError("Committed literal content digest mismatch")
        if expect and (row[0] != expect.get("doc_uuid") or int(row[1]) != expect.get("revision")):
            raise VerificationError("Committed revision identity mismatch")
        return {"doc_uuid": row[0], "revision": int(row[1]),
                "revision_sha256": row[3], "byte_exact_readback": True,
                "postgres_entities": int(row[4])}

    def capture(self, stream_id, events):
        receipt = self._request("POST", self.base + "/activity",
                                {"stream_id": stream_id, "events": events})
        expected = {e["sequence"]: _sha256(e["raw"]) for e in events}
        if not receipt.get("stored"):
            raise VerificationError("Activity storage was not acknowledged")
        if events:
            sequence_sql = ",".join(str(int(n)) for n in expected)
            rows = self.pg_rows("SELECT sequence, encode(sha256(raw),'hex') FROM activity_events "
                                f"WHERE stream_id={_sql_literal(stream_id)} AND sequence IN ({sequence_sql}) ORDER BY sequence")
            if {int(n): digest for n, digest in rows} != expected:
                raise VerificationError("Independent activity readback disagrees")
        return receipt

    def review(self, stream_id, first, last, git_evidence):
        old_timeout = self.timeout
        try:
            self.timeout = self.config.get("review_timeout", 1800)
            return self._request("POST", self.base + "/audit", {
                "stream_id": stream_id, "first_sequence": first,
                "last_sequence": last, "git_evidence": git_evidence,
            })
        finally:
            self.timeout = old_timeout

    # -------------------------------------------------------- verified write
    def write_verified(
        self, path: str, content: str, source: str, title: str | None = None
    ) -> dict:
        """Write + independently verify. Pending outbox entry retained on any
        failure and retried on the next invocation; identical content already
        present verifies without appending a duplicate revision."""
        if "\x00" in content:
            raise ValueError(
                "refusing NUL-bearing document (the server strips NULs; "
                "content would not read back identically)"
            )
        digest = _sha256(content)
        outbox = self.receipt_root / "outbox"
        outbox.mkdir(parents=True, exist_ok=True, mode=0o700)
        pending = outbox / (hashlib.sha256(path.encode()).hexdigest() + ".json")
        pending.write_text(
            json.dumps({"path": path, "content": content, "source": source,
                        "title": title})
        )
        pending.chmod(0o600)
        with pending.open("rb") as durable:
            os.fsync(durable.fileno())
        try:
            existing = self.read_document(path)
            if existing.get("exact") and existing.get("sha256") == digest:
                receipt = {
                    "path": path,
                    "source": source,
                    "sha256": digest,
                    "duplicate": True,
                    "indexing": "not-checked",
                    "verified": self.verify_stored(path, source, content),
                }
            else:
                written = self.write_document(path, content, source, title=title)
                receipt = {
                    "path": path,
                    "source": source,
                    "sha256": digest,
                    "duplicate": False,
                    "indexing": written.get("indexing", "pending"),
                    "doc_uuid": written.get("doc_uuid"),
                    "revision": written.get("revision"),
                    "chunks": written.get("chunks"),
                    "entity_uuids": written.get("entity_uuids"),
                    "written_at": datetime.now(timezone.utc).isoformat(),
                    "verified": self.verify_stored(path, source, content, written),
                }
            pending.unlink(missing_ok=True)
            return receipt
        except (VerificationError, ValueError, urllib.error.URLError,
                subprocess.SubprocessError, KeyError) as error:
            # pending retained — the next invocation retries this document
            raise VerificationError(f"verified write failed for {path!r}: {error}") from error

    def retry_outbox(self) -> int:
        """Retry every retained pending document; returns receipts recovered."""
        outbox = self.receipt_root / "outbox"
        if not outbox.exists():
            return 0
        recovered = 0
        for pending in sorted(outbox.glob("*.json")):
            item = json.loads(pending.read_text())
            self.write_verified(item["path"], item["content"], item["source"],
                                item.get("title"))
            recovered += 1
        return recovered


def main() -> int:
    ap = argparse.ArgumentParser(description="verified kstore document intake")
    ap.add_argument("--manifest", required=True,
                    help="JSON {documents:[{file,id,source_type,title?}]} — invocation data")
    ap.add_argument("--receipt", required=True,
                    help="caller-supplied receipt output path")
    args = ap.parse_args()

    manifest = json.loads(Path(args.manifest).read_text())
    client = KStoreClient()
    receipts = []
    failures = []
    for doc in manifest["documents"]:
        content = Path(doc["file"]).read_text()
        try:
            receipt = client.write_verified(
                doc["id"], content, doc["source_type"], doc.get("title")
            )
            receipts.append(receipt)
            mark = "duplicate" if receipt["duplicate"] else "written"
            print(f"  {mark}: {doc['id']} rev={receipt['verified']['revision']} "
                  f"chunks={receipt['verified']['postgres_entities']}")
        except (VerificationError, ValueError) as error:
            failures.append({"id": doc["id"], "error": str(error)})
            print(f"  FAILED: {doc['id']}: {error}", file=sys.stderr)
    receipt_path = Path(args.receipt)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(),
         "receipts": receipts, "failures": failures}, indent=2) + "\n")
    if failures:
        print(f"{len(failures)} document(s) failed; pending entries retained",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
