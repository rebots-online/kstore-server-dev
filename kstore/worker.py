"""Durable PostgreSQL jobs with one GPU worker and verified vector delivery."""
from __future__ import annotations
import hashlib
import math
import signal
import time
from psycopg.rows import dict_row
from qdrant_client.models import PointStruct
from . import config
from .db import pg, qdrant
from .embedding import embed
from .gpu import GpuLease, GpuBusy

LOCK_ID = 1263752274

class EmbeddingWorker:
    def __init__(self):
        self.conn = None
        self.qc = None
        self.stopping = False

    def _connect(self):
        if self.conn is not None:
            return
        conn = pg()
        conn.autocommit = True
        if not conn.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,)).fetchone()[0]:
            conn.close()
            raise GpuBusy('Another embedding worker owns the database lock')
        self.conn = conn
        # The session lock guarantees no live peer still owns these jobs.
        conn.execute("UPDATE embedding_jobs SET state='pending',last_error='Recovered interrupted worker',updated_at=now() WHERE state='processing'")
        self.qc = qdrant()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None
        if self.qc:
            self.qc.close()
            self.qc = None

    def run_once(self) -> int:
        self._connect()
        jobs = []
        with self.conn.transaction(), self.conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""SELECT j.*,e.content,e.content_sha256,e.path,e.source_type,e.breadcrumb,e.parent_uuid,e.revision,e.chunk_ix
                 FROM embedding_jobs j LEFT JOIN entities e ON e.uuid=j.entity_uuid
                 WHERE j.state='pending' AND j.next_attempt_at<=now()
                   AND j.model=%s AND j.collection=%s ORDER BY j.created_at,j.entity_uuid
                 LIMIT %s FOR UPDATE OF j SKIP LOCKED""", (config.EMBED_MODEL, config.COLLECTION, config.EMBED_BATCH))
            jobs = cur.fetchall()
            for job in jobs:
                cur.execute("UPDATE embedding_jobs SET state='processing',updated_at=now() WHERE entity_uuid=%s AND model=%s AND collection=%s", self._key(job))
        if not jobs:
            return 0
        try:
            vectors_config = self.qc.get_collection(config.COLLECTION).config.params.vectors
            if getattr(vectors_config, 'size', None) != config.EMBED_DIMS:
                raise ValueError('Collection vector dimensions mismatch')
            for job in jobs:
                if job['content'] is None or job['dims'] != config.EMBED_DIMS:
                    raise ValueError('Missing entity or incompatible queued dimensions')
                if hashlib.sha256(job['content'].encode()).hexdigest() != job['content_sha256']:
                    raise ValueError('Entity content checksum mismatch')
            with GpuLease() as lease:
                vectors = embed([j['content'] for j in jobs], deadline=lease.deadline)
                points = [PointStruct(id=str(j['entity_uuid']), vector=v, payload={
                    'content_sha256': j['content_sha256'], 'content': j['content'],
                    'path': j['path'], 'source_type': j['source_type'], 'breadcrumb': j['breadcrumb'],
                    'parent_uuid': str(j['parent_uuid']), 'revision': j['revision'], 'chunk_ix': j['chunk_ix'],
                    'model': config.EMBED_MODEL,
                }) for j,v in zip(jobs,vectors)]
                if len(points) != len(jobs):
                    raise ValueError('Incomplete embedding batch')
                self.qc.upsert(collection_name=config.COLLECTION, points=points, wait=True)
                found = {str(p.id):p for p in self.qc.retrieve(config.COLLECTION, ids=[p.id for p in points], with_vectors=True, with_payload=True)}
                for j in jobs:
                    point = found.get(str(j['entity_uuid']))
                    if point is None or point.payload.get('content_sha256') != j['content_sha256'] or point.payload.get('content') != j['content']:
                        raise ValueError('Vector readback content mismatch')
                    if not isinstance(point.vector,list) or len(point.vector) != config.EMBED_DIMS or any(not isinstance(v,(float,int)) or isinstance(v,bool) or not math.isfinite(v) for v in point.vector):
                        raise ValueError('Vector readback dimensions/values mismatch')
            with self.conn.transaction():
                for j in jobs:
                    self.conn.execute("UPDATE embedding_jobs SET state='complete',last_error=NULL,updated_at=now() WHERE entity_uuid=%s AND model=%s AND collection=%s", self._key(j))
                    self.conn.execute("""INSERT INTO embeddings_meta(entity_uuid,model,dims,collection) VALUES(%s,%s,%s,%s)
                        ON CONFLICT(entity_uuid,model) DO UPDATE SET dims=excluded.dims,collection=excluded.collection,embedded_at=now()""", (j['entity_uuid'],j['model'],j['dims'],j['collection']))
            return len(jobs)
        except BaseException as exc:
            with self.conn.transaction():
                for j in jobs:
                    # Do not store exception bodies: provider errors can contain input data.
                    self.conn.execute("""UPDATE embedding_jobs SET state='pending',attempts=attempts+1,
                      next_attempt_at=now()+(%s * interval '1 second'),last_error=%s,updated_at=now()
                      WHERE entity_uuid=%s AND model=%s AND collection=%s""", (min(3600, 10 * 2**min(j['attempts'],8)), (type(exc).__name__ + ': ' + str(exc)[:240]) if isinstance(exc, GpuBusy) else type(exc).__name__, *self._key(j)))
            if not isinstance(exc, Exception):
                raise
            return 0

    @staticmethod
    def _key(job):
        return job['entity_uuid'], job['model'], job['collection']

    def run_forever(self) -> None:
        def stop(*_):
            self.stopping = True
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            while not self.stopping:
                self.run_once()
                time.sleep(config.WORKER_POLL)
        finally:
            self.close()

if __name__ == '__main__':
    EmbeddingWorker().run_forever()
