"""Synchronous canonical storage with a transactional asynchronous indexing queue."""
from __future__ import annotations

import hashlib

from . import config
from .chunk import chunk_document
from .db import pg
from .ids import KSTORE_ORIGIN_UUID, uuidv8


def _lock(cur, key: str) -> None:
    number = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
    cur.execute('SELECT pg_advisory_xact_lock(%s)', (number,))


def enqueue_entities(cur, entity_uuids) -> None:
    """Queue in the caller's transaction; replay never resets completed work."""
    for entity_uuid in entity_uuids:
        cur.execute('''INSERT INTO embedding_jobs(entity_uuid,model,dims,collection)
                       VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                    (entity_uuid, config.EMBED_MODEL, config.EMBED_DIMS, config.COLLECTION))


def _store_document(cur, path, content, source_type, title='', sensitivity='internal') -> dict:
    if not isinstance(content, str) or '\x00' in content:
        raise ValueError('content must be a string without NUL bytes')
    if not isinstance(path, str) or not path or not isinstance(source_type, str) or not source_type:
        raise ValueError('path and source_type must be nonempty strings')
    digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
    _lock(cur, 'document\0' + source_type + '\0' + path)
    cur.execute('SELECT uuid,sha256,head_rev FROM documents WHERE source_type=%s AND path=%s',
                (source_type, path))
    row = cur.fetchone()
    duplicate = bool(row and row[1] == digest)
    doc_uuid = str(row[0]) if row else uuidv8()
    revision = row[2] if duplicate else (row[2] + 1 if row else 1)
    if duplicate:
        cur.execute('SELECT uuid FROM entities WHERE parent_uuid=%s AND revision=%s ORDER BY chunk_ix',
                    (doc_uuid, revision))
        entities = [str(item[0]) for item in cur.fetchall()]
    else:
        cur.execute('INSERT INTO origins(uuid,name) VALUES (%s,%s) ON CONFLICT DO NOTHING',
                    (KSTORE_ORIGIN_UUID, 'kstore system root'))
        if row:
            cur.execute('''UPDATE documents SET sha256=%s,head_rev=%s,title=%s,sensitivity=%s,
                           ingested_at=now() WHERE uuid=%s''',
                        (digest, revision, title, sensitivity, doc_uuid))
        else:
            cur.execute('''INSERT INTO documents(uuid,parent_uuid,source_type,path,title,sensitivity,sha256,head_rev)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (doc_uuid, KSTORE_ORIGIN_UUID, source_type, path, title, sensitivity, digest, revision))
        cur.execute('INSERT INTO document_revisions(doc_uuid,revision,content,sha256) VALUES (%s,%s,%s,%s)',
                    (doc_uuid, revision, content, digest))
        entities = []
        for chunk in chunk_document(content, path, title=title):
            # Paragraph-based chunking can emit an arbitrarily large JSON line.
            # Bound derived inputs without altering the canonical revision.
            for offset in range(0, len(chunk.text), 3000):
                text = chunk.text[offset:offset + 3000]
                entity_uuid = uuidv8()
                cur.execute('''INSERT INTO entities(uuid,parent_uuid,source_type,path,breadcrumb,sensitivity,
                               chunk_ix,content_sha256,content,revision) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                            (entity_uuid, doc_uuid, source_type, path, chunk.breadcrumb, sensitivity,
                             len(entities), hashlib.sha256(text.encode()).hexdigest(), text, revision))
                entities.append(entity_uuid)
    enqueue_entities(cur, entities)
    cur.execute('''SELECT count(*) FROM embedding_jobs WHERE entity_uuid = ANY(%s::uuid[])
                   AND model=%s AND collection=%s AND state <> 'complete' ''',
                (entities, config.EMBED_MODEL, config.COLLECTION))
    pending = cur.fetchone()[0]
    return dict(path=path, doc_uuid=doc_uuid, revision=revision, entity_uuids=entities,
                chunks=len(entities), sha256=digest, stored=True,
                indexing='pending' if pending else 'complete', duplicate=duplicate)


def store_document(path, content, source_type, title='', sensitivity='internal') -> dict:
    with pg() as conn, conn.cursor() as cur:
        cur.execute('SET LOCAL synchronous_commit = on')
        result = _store_document(cur, path, content, source_type, title, sensitivity)
    # Connection context has committed successfully before acknowledgment.
    return result


def queue_status() -> dict:
    with pg() as conn, conn.cursor() as cur:
        cur.execute('SELECT state,count(*) FROM embedding_jobs GROUP BY state')
        counts = dict.fromkeys(('pending', 'processing', 'complete'), 0)
        counts.update(dict(cur.fetchall()))
        cur.execute("SELECT EXTRACT(EPOCH FROM now()-min(created_at)) FROM embedding_jobs WHERE state <> 'complete'")
        age = cur.fetchone()[0]
        cur.execute('SELECT last_error FROM embedding_jobs WHERE last_error IS NOT NULL ORDER BY updated_at DESC LIMIT 1')
        error = cur.fetchone()
    return dict(counts=counts, oldest_pending_age_seconds=float(age) if age is not None else None,
                latest_error=error[0] if error else None)


def lexical_search(query, limit=10) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        return []
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('limit must be between 1 and 1000')
    with pg() as conn, conn.cursor() as cur:
        cur.execute('''SELECT e.uuid,ts_rank(to_tsvector('simple',e.content),plainto_tsquery('simple',%s)),
                       e.path,e.source_type,e.breadcrumb,e.content
                       FROM entities e JOIN documents d ON d.uuid=e.parent_uuid AND d.head_rev=e.revision
                       WHERE to_tsvector('simple',e.content) @@ plainto_tsquery('simple',%s)
                          OR strpos(lower(e.path),lower(%s))>0
                       ORDER BY 2 DESC,e.path,e.chunk_ix LIMIT %s''', (query, query, query, limit))
        rows = cur.fetchall()
    return [dict(uuid=str(r[0]), score=float(r[1]), path=r[2], source_type=r[3],
                 breadcrumb=r[4], content=r[5]) for r in rows]
