"""kstore storage: Postgres (literal/canonical) + Qdrant (vector).

The UUID is the identity — Postgres PK and Qdrant point id are the same
value. Nothing extra is generated or embedded for linkage.
"""

from __future__ import annotations

import psycopg
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

from . import config

# Single environment authority: kstore/config.py (process env over the
# repo-root .env). The stale ~/Admin-Manual/INFRA/SERVERS/kstore fallback
# and the POSTGRES_PASSWORD DSN synthesis are gone; KSTORE_PG_DSN is the
# one credential home, documented in the committed .env.example.
PG_DSN = config.PG_DSN
QDRANT_URL = config.QDRANT_URL
OLLAMA_URL = config.OLLAMA_URL
EMBED_MODEL = config.EMBED_MODEL
EMBED_DIMS = config.EMBED_DIMS
COLLECTION = config.COLLECTION

SCHEMA = """
CREATE TABLE IF NOT EXISTS origins (
    uuid        UUID PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS documents (
    uuid        UUID PRIMARY KEY,
    parent_uuid UUID REFERENCES origins(uuid),
    source_type TEXT NOT NULL,
    path        TEXT NOT NULL,
    title       TEXT,
    sensitivity TEXT NOT NULL DEFAULT 'internal',
    sha256      TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_type, path)
);

CREATE TABLE IF NOT EXISTS entities (
    uuid        UUID PRIMARY KEY,
    parent_uuid UUID REFERENCES documents(uuid),
    source_type TEXT NOT NULL,
    path        TEXT NOT NULL,
    breadcrumb  TEXT,
    sensitivity TEXT NOT NULL DEFAULT 'internal',
    chunk_ix    INT  NOT NULL,
    content_sha256 TEXT NOT NULL,
    content     TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS relations (
    from_uuid   UUID NOT NULL,
    to_uuid     UUID NOT NULL,
    rel_type    TEXT NOT NULL,
    properties  JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (from_uuid, to_uuid, rel_type)
);

CREATE TABLE IF NOT EXISTS embeddings_meta (
    entity_uuid  UUID NOT NULL,
    model        TEXT NOT NULL,
    dims         INT  NOT NULL,
    collection   TEXT NOT NULL,
    embedded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (entity_uuid, model)
);

CREATE TABLE IF NOT EXISTS document_revisions (
    doc_uuid    UUID NOT NULL REFERENCES documents(uuid) ON DELETE CASCADE,
    revision    INT  NOT NULL,
    content     TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (doc_uuid, revision)
);

CREATE TABLE IF NOT EXISTS embedding_jobs (
    entity_uuid UUID NOT NULL REFERENCES entities(uuid),
    model TEXT NOT NULL,
    dims INT NOT NULL CHECK (dims > 0),
    collection TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','processing','complete')),
    attempts INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(entity_uuid, model, collection)
);
CREATE INDEX IF NOT EXISTS embedding_jobs_pending_idx
    ON embedding_jobs(next_attempt_at, created_at) WHERE state = 'pending';

CREATE TABLE IF NOT EXISTS activity_events (
    stream_id TEXT NOT NULL,
    sequence BIGINT NOT NULL CHECK (sequence >= 0),
    kind TEXT NOT NULL,
    raw BYTEA NOT NULL,
    sha256 TEXT NOT NULL,
    turn_id TEXT,
    filtered BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(stream_id, sequence)
);
CREATE TABLE IF NOT EXISTS audit_reviews (
    id UUID PRIMARY KEY,
    stream_id TEXT NOT NULL,
    event_sha256 TEXT NOT NULL,
    policy_sha256 TEXT NOT NULL,
    verdict JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS entities_source_type_idx ON entities (source_type);
CREATE INDEX IF NOT EXISTS entities_path_idx        ON entities (path);
CREATE INDEX IF NOT EXISTS entities_parent_idx      ON entities (parent_uuid);
CREATE INDEX IF NOT EXISTS entities_ingested_idx    ON entities (ingested_at);
CREATE INDEX IF NOT EXISTS relations_to_idx         ON relations (to_uuid);
CREATE INDEX IF NOT EXISTS relations_type_idx       ON relations (rel_type);
"""


def pg() -> psycopg.Connection:
    if not PG_DSN:
        raise RuntimeError(
            "KSTORE_PG_DSN is not set — provide it via the service "
            "environment or the repo-root .env (see .env.example)"
        )
    return psycopg.connect(PG_DSN)


def qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def init_schema() -> None:
    with pg() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
        # idempotent upgrade for tables created before the flag existed
        cur.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT 'internal'"
        )
        cur.execute(
            "ALTER TABLE entities ADD COLUMN IF NOT EXISTS sensitivity TEXT NOT NULL DEFAULT 'internal'"
        )
        # revisioned write model: documents.head_rev points at the live revision;
        # entities keep every revision (append-only history, I3 stewardship)
        cur.execute(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS head_rev INT NOT NULL DEFAULT 1"
        )
        cur.execute(
            "ALTER TABLE entities ADD COLUMN IF NOT EXISTS revision INT NOT NULL DEFAULT 1"
        )
        conn.commit()


def init_collection() -> None:
    qc = qdrant()
    if not qc.collection_exists(COLLECTION):
        qc.create_collection(
            COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIMS, distance=Distance.COSINE),
        )
    for field in ("source_type", "path", "parent_uuid"):
        try:
            qc.create_payload_index(
                COLLECTION, field, PayloadSchemaType.KEYWORD
            )
        except Exception:
            pass  # already exists
