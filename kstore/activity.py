"""Exact ordered activity evidence, atomically captured alongside indexing jobs."""
from __future__ import annotations

import hashlib

from .db import pg
from .storage import _lock, _store_document


def store_activity(stream_id, events) -> dict:
    if not isinstance(stream_id, str) or not stream_id.strip() or '\x00' in stream_id:
        raise ValueError('stream_id must be nonempty text without NUL')
    if not isinstance(events, list):
        raise ValueError('events must be a list')
    prepared = []
    previous = -1
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('each event must be an object')
        seq, raw = event.get('sequence'), event.get('raw')
        if isinstance(seq, bool) or not isinstance(seq, int) or not previous < seq <= 9223372036854775807:
            raise ValueError('sequences must be nonnegative, strictly ascending bigint values')
        if not isinstance(raw, str) or '\x00' in raw:
            raise ValueError('raw must be a string without NUL')
        kind, turn_id, filtered = event.get('kind', 'unknown'), event.get('turn_id'), event.get('filtered', False)
        if not isinstance(kind, str) or not kind or '\x00' in kind:
            raise ValueError('kind must be nonempty text without NUL')
        if turn_id is not None and (not isinstance(turn_id, str) or '\x00' in turn_id):
            raise ValueError('turn_id must be text without NUL or null')
        if not isinstance(filtered, bool):
            raise ValueError('filtered must be boolean')
        data = raw.encode('utf-8')
        prepared.append((seq, raw, data, hashlib.sha256(data).hexdigest(), kind, turn_id, filtered))
        previous = seq
    receipts = []
    with pg() as conn, conn.cursor() as cur:
        cur.execute('SET LOCAL synchronous_commit = on')
        _lock(cur, 'activity\0' + stream_id)
        for seq, raw, data, digest, kind, turn_id, filtered in prepared:
            cur.execute('SELECT sha256 FROM activity_events WHERE stream_id=%s AND sequence=%s', (stream_id, seq))
            row = cur.fetchone()
            if row and row[0] != digest:
                raise ValueError(f'activity sequence {seq} conflicts with stored evidence')
            if not row:
                cur.execute('''INSERT INTO activity_events(stream_id,sequence,kind,raw,sha256,turn_id,filtered)
                               VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                            (stream_id, seq, kind, data, digest, turn_id, filtered))
                _store_document(cur, f'activity/{stream_id}/{seq}', raw, 'activity',
                                title=kind, sensitivity='confidential')
            receipts.append(dict(sequence=seq, sha256=digest))
    return dict(stream_id=stream_id, stored=True, events=receipts, indexing='pending')


def activity_rows(stream_id, first_sequence, last_sequence) -> list[dict]:
    if not isinstance(stream_id, str) or not stream_id:
        raise ValueError('stream_id must be nonempty')
    if any(isinstance(n, bool) or not isinstance(n, int) for n in (first_sequence, last_sequence)) or not 0 <= first_sequence <= last_sequence:
        raise ValueError('invalid sequence range')
    with pg() as conn, conn.cursor() as cur:
        cur.execute('''SELECT sequence,kind,raw,sha256,turn_id,filtered FROM activity_events
                       WHERE stream_id=%s AND sequence BETWEEN %s AND %s ORDER BY sequence''',
                    (stream_id, first_sequence, last_sequence))
        rows = cur.fetchall()
    return [dict(sequence=r[0], kind=r[1], raw=bytes(r[2]).decode('utf-8'),
                 sha256=r[3], turn_id=r[4], filtered=r[5]) for r in rows]
