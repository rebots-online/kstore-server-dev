"""Durable embedding scheduling and queue priority."""
from .db import pg


def pending_embedding_work():
    """All waiting work vetoes mining, including delayed and other-model jobs."""
    with pg() as conn:
        row = conn.execute(
            "SELECT count(*) FILTER (WHERE state='pending'), "
            "count(*) FILTER (WHERE state='processing') FROM embedding_jobs"
        ).fetchone()
    return {'pending': row[0], 'processing': row[1]}
