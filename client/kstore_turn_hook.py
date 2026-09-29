#!/usr/bin/env python3
"""Synchronous activity capture; hosted Stop review; GPU indexing is asynchronous."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kstore_client import KStoreClient, _sql_literal


def digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def durable_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending = path.with_suffix('.pending')
    with pending.open('w') as target:
        os.chmod(pending, 0o600)
        json.dump(value, target, ensure_ascii=False)
        target.flush()
        os.fsync(target.fileno())
    pending.replace(path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def scrub_private(value):
    """Remove typed private reasoning, preserving tool arguments and visible text."""
    if isinstance(value, list):
        return [clean for item in value if (clean := scrub_private(item)) is not None]
    if isinstance(value, dict):
        if value.get('type') in ('thinking', 'redacted_thinking', 'reasoning', 'analysis', 'reasoning_summary'):
            return None
        return {key: scrub_private(item) for key, item in value.items()
                if key not in ('reasoning_content', 'encrypted_content')}
    return value


def eligible(entry, raw):
    kind = entry.get('type', '')
    message = entry.get('payload', {}) if kind == 'response_item' else entry.get('message', entry)
    if kind == 'response_item':
        if message.get('type') in ('reasoning', 'analysis'):
            return None
        if message.get('type') == 'message' and message.get('channel') not in (None, 'commentary', 'final'):
            return None
    if kind == 'event_msg' and str(entry.get('payload', {}).get('type', '')).startswith(('agent_reasoning', 'reasoning')):
        return None
    clean = scrub_private(entry)
    if clean is None:
        return None
    filtered = clean != entry
    if filtered:
        msg = clean.get('payload', {}) if kind == 'response_item' else clean.get('message', clean)
        if isinstance(msg, dict) and msg.get('content') == []:
            return None
        raw = json.dumps(clean, ensure_ascii=False)
    return {'kind': kind or 'activity', 'raw': raw, 'filtered': filtered}


def state_dir(client, runtime):
    path = client.receipt_root / runtime
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def collect(state, payload, runtime):
    transcript = payload.get('transcript_path')
    if not transcript:
        raise ValueError('Capture requires transcript_path; no success claimed')
    file = Path(transcript).resolve()
    try:
        data = file.read_bytes()
    except FileNotFoundError:
        # Either runtime can submit its first prompt before creating the native JSONL.
        # Capture the hook payload now; the prefix check below rejects later loss.
        if runtime not in ('claude', 'codex') or payload.get('hook_event_name') not in (
            'SessionStart', 'UserPromptSubmit', 'SessionEnd'
        ):
            raise
        data = b''
    lines = data.splitlines(keepends=True)
    entries = []
    for ordinal, line in enumerate(lines):
        # A growing final partial record is neither acknowledged nor discarded.
        if not line.endswith(b'\n'):
            break
        raw = line.decode('utf-8').rstrip('\r\n')
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f'Malformed complete transcript line {ordinal + 1}') from exc
        if not isinstance(value, dict):
            raise ValueError('Transcript record must be an object')
        entries.append((value, raw))
    meta = next((e.get('payload', {}) for e, _ in entries if e.get('type') == 'session_meta'), {})
    session = payload.get('session_id') or payload.get('sessionId') or meta.get('id')
    if not session:
        raise ValueError('Stable session identity missing')
    identity = runtime + ':' + socket.gethostname() + ':' + str(session) + ':' + str(file)
    stream = digest(identity)
    receipt_path = state / (stream + '.json')
    if receipt_path.exists():
        saved = json.loads(receipt_path.read_text())
    else:
        saved = {'lines': 0, 'prefix_sha256': digest(''), 'next_sequence': 0,
                 'first_sequence': None, 'last_sequence': None, 'payload_keys': [],
                 'turn_first': 0, 'review_from': None}
    previous = saved['lines']
    if previous > len(entries):
        raise ValueError('Transcript shrank; refusing cursor reuse')
    prefix = '\n'.join(raw for _, raw in entries[:previous])
    if digest(prefix) != saved['prefix_sha256']:
        raise ValueError('Transcript prefix changed; refusing cursor reuse')
    pending = []
    turn = payload.get('turn_id', '')
    for entry, raw in entries[previous:]:
        is_user_text = entry.get('type') == 'user' and any(
            isinstance(b, dict) and b.get('type') == 'text'
            for b in (entry.get('message', {}).get('content', []) if isinstance(entry.get('message', {}).get('content'), list) else []))
        if entry.get('type') == 'turn_context' or is_user_text:
            saved['turn_first'] = saved['next_sequence']
        item = eligible(entry, raw)
        if item:
            item.update(sequence=saved['next_sequence'], turn_id=str(turn))
            saved['next_sequence'] += 1
            pending.append(item)
    # Hook input captures tool output before it necessarily appears in JSONL.
    exposed = {key: payload[key] for key in (
        'hook_event_name', 'tool_name', 'tool_input', 'tool_response', 'tool_result',
        'tool_use_id', 'error', 'prompt', 'last_assistant_message', 'cwd', 'turn_id',
    ) if key in payload}
    if exposed:
        exposed = scrub_private(exposed)
        raw = json.dumps({'type': 'hook_activity', 'runtime': runtime, 'session_id': session,
                          'payload': exposed}, ensure_ascii=False, sort_keys=True)
        key = digest(raw)
        if key not in saved['payload_keys']:
            pending.append({'sequence': saved['next_sequence'], 'kind': 'hook_activity',
                            'raw': raw, 'filtered': False, 'turn_id': str(turn)})
            if exposed.get('hook_event_name') == 'UserPromptSubmit':
                saved['turn_first'] = saved['next_sequence']
            saved['next_sequence'] += 1
            saved['payload_keys'].append(key)
    saved['lines'] = len(entries)
    saved['prefix_sha256'] = digest('\n'.join(raw for _, raw in entries))
    if pending:
        if saved['first_sequence'] is None:
            saved['first_sequence'] = pending[0]['sequence']
        saved['last_sequence'] = pending[-1]['sequence']
    return stream, receipt_path, saved, pending


def archive(client, state, payload, runtime):
    # A per-transcript lock avoids unrelated sessions waiting for one backlog.
    key = digest(str(payload.get('transcript_path', '')))
    with (state / (key + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        outbox = state / (key + '.outbox.json')
        if outbox.exists():
            old = json.loads(outbox.read_text())
            for start in range(0, len(old['events']), 50):
                client.capture(old['stream'], old['events'][start:start + 50])
            durable_json(Path(old['receipt_path']), old['saved'])
            outbox.unlink()
        stream, receipt_path, saved, events = collect(state, payload, runtime)
        # Bounded request batches, with a durable cursor only after DB verification.
        if events:
            durable_json(outbox, {'stream': stream, 'events': events,
                                 'receipt_path': str(receipt_path), 'saved': saved})
            for start in range(0, len(events), 50):
                client.capture(stream, events[start:start + 50])
        durable_json(receipt_path, saved)
        outbox.unlink(missing_ok=True)
        return {'stream_id': stream, **saved, 'new_events': len(events)}


def git_evidence(cwd):
    def run(*args):
        try:
            process = subprocess.run(['git', '-C', cwd, *args], capture_output=True,
                                     text=True, timeout=15)
            return {'exit_code': process.returncode, 'stdout': process.stdout,
                    'stderr': process.stderr}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'error': type(exc).__name__}
    result = {'cwd': cwd, 'head': run('rev-parse', 'HEAD'),
              'branch': run('branch', '--show-current'),
              'status': run('status', '--short'),
              'upstream': run('rev-list', '--left-right', '--count', 'HEAD...@{upstream}')}
    remotes = run('remote')
    result['remotes'] = remotes
    if remotes.get('exit_code') == 0:
        result['publication'] = {remote: run('ls-remote', remote, 'refs/heads/' + result['branch'].get('stdout', '').strip())
                                 for remote in remotes['stdout'].splitlines()}
    return result


def stop_output(verdict):
    if verdict.get('status') == 'PASS':
        return {}
    return {'decision': 'block', 'reason': 'KStore review requires correction before completion. '
            + json.dumps(verdict, ensure_ascii=False)}


def activity_catalog(client, stream, first, last):
    rows = client.pg_rows(
        "SELECT sequence, convert_from(raw,'UTF8') FROM activity_events "
        f"WHERE stream_id={_sql_literal(stream)} AND sequence BETWEEN {int(first)} AND {int(last)} "
        "ORDER BY sequence"
    )
    catalog = []
    for sequence, raw in rows:
        entry = json.loads(raw)
        item = {'source': 'activity:' + str(sequence), 'type': entry.get('type')}
        message = entry.get('payload', {}) if entry.get('type') in ('response_item', 'hook_activity') else entry.get('message', {})
        if isinstance(message, dict):
            item.update({k: message[k] for k in ('type', 'role', 'name', 'call_id',
                         'tool_name', 'tool_use_id', 'hook_event_name') if k in message})
            content = message.get('content', [])
            if isinstance(content, list):
                item['blocks'] = [{k: block[k] for k in ('type', 'name', 'id', 'tool_use_id', 'is_error')
                                   if k in block} for block in content if isinstance(block, dict)]
                item['text_characters'] = sum(len(block['text']) for block in content
                                               if isinstance(block, dict) and isinstance(block.get('text'), str))
            elif isinstance(content, str):
                item['text_characters'] = len(content)
        catalog.append(item)
    return catalog


def review_until_stable(client, state, payload, runtime, receipt, first):
    for _ in range(3):
        verdict = client.review(receipt['stream_id'], first,
                                receipt['last_sequence'], {
                                    **git_evidence(payload.get('cwd', os.getcwd())),
                                    'capture_event_count': receipt['last_sequence'] - first + 1,
                                    'capture_catalog': activity_catalog(client, receipt['stream_id'],
                                                                        first, receipt['last_sequence']),
                                })
        latest = archive(client, state, payload, runtime)
        if latest['last_sequence'] == receipt['last_sequence']:
            return latest, verdict
        # Claude can flush the final response after Stop starts. Review it too,
        # without forcing a new assistant response and another moving boundary.
        receipt = latest
    return receipt, {'status': 'ERROR', 'detail': 'Activity kept changing during review; retry.'}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    runtime = sys.argv[2] if len(sys.argv) > 2 else 'codex'
    try:
        if mode not in ('pre', 'capture', 'post', 'end'):
            raise ValueError('Expected pre, capture, post or end')
        payload = json.load(sys.stdin)
        client = KStoreClient()
        state = state_dir(client, runtime)
        receipt = archive(client, state, payload, runtime)
        if mode == 'post':
            if receipt['first_sequence'] is None:
                raise ValueError('No captured activity to review')
            first = receipt.get('review_from')
            if first is None:
                first = receipt.get('turn_first', receipt['first_sequence'])
            receipt, verdict = review_until_stable(client, state, payload, runtime, receipt, first)
            # Persist the range needing correction; a successful review releases it.
            key = digest(str(payload.get('transcript_path', '')))
            with (state / (key + '.lock')).open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                cursor_path = state / (receipt['stream_id'] + '.json')
                cursor = json.loads(cursor_path.read_text())
                if cursor['last_sequence'] != receipt['last_sequence']:
                    verdict = {'status': 'ERROR', 'detail': 'Activity changed during review; retry.'}
                cursor['review_from'] = None if verdict.get('status') == 'PASS' else first
                durable_json(cursor_path, cursor)
            durable_json(state / (receipt['stream_id'] + '.review.json'), verdict)
            print(json.dumps(stop_output(verdict)))
        elif mode == 'pre':
            context = client.inject(str(payload.get('prompt', ''))).get('context', '')
            print(json.dumps({'hookSpecificOutput': {'hookEventName': 'UserPromptSubmit',
                'additionalContext': context + '\nKStore durably captures exposed activity. Completion requires a PASS review; REDO means correct and recheck.'}}))
        else:
            print('{}')
        return 0
    except Exception as exc:
        # No credentials/tool content in exception logs. Capture failure never passes Stop.
        reason = 'KStore ' + mode + ' failed: ' + type(exc).__name__ + '. Repair capture/review and retry; completion is unverified.'
        if mode == 'post':
            print(json.dumps({'decision': 'block', 'reason': reason}))
            return 0
        print(reason, file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
