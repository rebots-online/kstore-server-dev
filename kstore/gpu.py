"""Exclusive GPU use with durable, independently recoverable mining intent."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
import httpx
from . import config

class GpuBusy(RuntimeError):
    pass

def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=15).stdout.strip()

def identity(pid):
    """Privileged helper reads only identity, never miner command-line credentials."""
    code = "import pathlib,json,sys;p=pathlib.Path('/proc')/sys.argv[1];s=(p/'stat').read_text();print(json.dumps([str((p/'exe').resolve()),s[s.rfind(')')+2:].split()[19]]))"
    try:
        return tuple(json.loads(command('sudo', '-n', 'python3', '-c', code, str(pid))))
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

def owner_identity(pid):
    try:
        s = Path(f'/proc/{pid}/stat').read_text()
        return s[s.rfind(')') + 2:].split()[19]
    except FileNotFoundError:
        return None

def probe():
    gpu = command('nvidia-smi', '-i', str(config.GPU_INDEX), '--query-gpu=uuid,memory.free', '--format=csv,noheader,nounits').split(',')
    apps = command('nvidia-smi', '--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory', '--format=csv,noheader,nounits')
    processes = []
    for line in apps.splitlines():
        fields = [x.strip() for x in line.split(',')]
        if fields and fields[0] == gpu[0].strip():
            processes.append({'pid': int(fields[1]), 'exe': fields[2]})
    return {'uuid': gpu[0].strip(), 'free_mb': int(gpu[1]), 'processes': processes}

def unload_embedder():
    r = httpx.get(f'{config.OLLAMA_URL}/api/ps', timeout=10)
    r.raise_for_status()
    models = r.json()['models']
    if any(m['name'] != config.EMBED_MODEL for m in models):
        raise GpuBusy('Unrelated Ollama model resident; refusing eviction')
    if not models:
        return
    r = httpx.post(f'{config.OLLAMA_URL}/api/embed', json={'model': config.EMBED_MODEL, 'input': [], 'keep_alive': 0}, timeout=config.GPU_RELEASE_TIMEOUT)
    r.raise_for_status()
    deadline = time.monotonic() + config.GPU_RELEASE_TIMEOUT
    while time.monotonic() < deadline:
        r = httpx.get(f'{config.OLLAMA_URL}/api/ps', timeout=10)
        r.raise_for_status()
        if not any(m['name'] == config.EMBED_MODEL for m in r.json()['models']):
            return
        time.sleep(.5)
    raise GpuBusy('Embedding model did not unload')

class GpuLease:
    def __init__(self):
        self.path = Path(config.GPU_STATE_PATH).expanduser()
        self.lock = None
        self.state = {}
        self.deadline = 0.0

    def _lock(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = open(str(self.path) + '.lock', 'a+')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            raise GpuBusy('GPU lease held') from None
        if self.path.exists():
            try:
                self.state = json.loads(self.path.read_text())
            except (ValueError, OSError):
                self._unlock()
                raise GpuBusy('Unreadable GPU recovery journal') from None

    def _unlock(self):
        if self.lock:
            self.lock.close()
            self.lock = None

    def save(self):
        tmp = self.path.with_suffix('.new')
        with open(tmp, 'w') as f:
            os.chmod(tmp, 0o600)
            json.dump(self.state, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        fd = os.open(self.path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def miners(self, snapshot):
        expected = str(Path(config.MINER_EXE).expanduser().resolve())
        miners = []
        allowed = set(config.GPU_DISPLAY_ALLOWLIST)
        for p in snapshot['processes']:
            ident = identity(p['pid'])
            if ident is None and not Path(f"/proc/{p['pid']}").exists():
                # NVIDIA can retain a just-exited PID for one accounting sample.
                # Live but unreadable PIDs still fail closed below.
                continue
            if ident and ident[0] == expected:
                miners.append((p['pid'], ident))
            elif Path(p['exe']).name not in allowed:
                raise GpuBusy(f"Unowned GPU process {p['pid']}")
        return miners

    def restore(self):
        cancel = Path(str(self.path) + '.cancel')
        if cancel.exists():
            self.state.update(restore_mining=False, phase='operator-cancelled')
            self.save()
            cancel.unlink()
        if not self.state.get('restore_mining'):
            return
        unload_embedder()
        expected = str(Path(config.MINER_EXE).expanduser().resolve())
        snapshot = probe()
        present = any((identity(p['pid']) or ('', ''))[0] == expected for p in snapshot['processes'])
        if not present:
            command('sudo', '-n', 'systemctl', 'start', config.MINER_SERVICE)
            until = time.monotonic() + config.GPU_RELEASE_TIMEOUT
            while time.monotonic() < until:
                if any((identity(p['pid']) or ('', ''))[0] == expected for p in probe()['processes']):
                    break
                time.sleep(.5)
            else:
                raise GpuBusy('Mining restart not observed; restoration intent retained')
        self.state.update(restore_mining=False, phase='restored', cooldown_until=time.time() + config.GPU_COOLDOWN)
        self.save()

    def __enter__(self):
        self._lock()
        try:
            self.restore()
            if time.time() < self.state.get('cooldown_until', 0):
                raise GpuBusy('Mining cooldown active')
            unload_embedder()
            snap = probe()
            miners = self.miners(snap)
            self.deadline = time.monotonic() + config.GPU_WINDOW
            self.state.update(owner_pid=os.getpid(), owner_start=owner_identity(os.getpid()), deadline=time.time()+config.GPU_WINDOW, phase='acquiring', restore_mining=bool(miners), miners=[{'pid': p, 'identity': list(i)} for p,i in miners], gpu_uuid=snap['uuid'])
            self.save()
            if miners:
                # Service stop is used only when every attributed PID belongs to it.
                supervised = all(config.MINER_SERVICE in Path(f'/proc/{p}/cgroup').read_text() for p,_ in miners)
                for p, ident in miners:
                    if identity(p) != ident:
                        raise GpuBusy('Miner identity changed before stop')
                if supervised:
                    command('sudo', '-n', 'systemctl', 'stop', config.MINER_SERVICE)
                else:
                    for p, ident in miners:
                        if identity(p) != ident:
                            raise GpuBusy('Miner identity changed before TERM')
                        command('sudo', '-n', 'kill', '-TERM', str(p))
            until = time.monotonic() + config.GPU_RELEASE_TIMEOUT
            while True:
                snap = probe()
                reason = 'GPU memory not released within deadline'
                try:
                    remaining_miners = self.miners(snap)
                    if not remaining_miners and snap['free_mb'] >= config.GPU_MIN_FREE_MB:
                        break
                except GpuBusy as exc:
                    # Transient processes must disappear before inference starts;
                    # never reclassify or kill an unowned process.
                    reason = str(exc)
                if time.monotonic() >= until:
                    raise GpuBusy('GPU release timeout: ' + reason)
                time.sleep(.5)
            self.state['phase'] = 'embedding'
            self.save()
            return self
        except BaseException:
            try:
                self.restore()
            finally:
                self._unlock()
            raise

    def __exit__(self, *_):
        try:
            unload_embedder()
            self.restore()
            self.state['phase'] = 'idle'
            self.save()
        finally:
            self._unlock()

    def recover(self, cancel=False):
        if cancel:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(str(self.path) + '.cancel', 'w') as f:
                f.write('cancel restoration\n')
                f.flush()
                os.fsync(f.fileno())
            fd = os.open(self.path.parent, os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            return
        self._lock()
        try:
            # Exclusive flock proves no active lease; the recorded process may
            # remain alive after a failed cleanup and must not veto retries.
            self.restore()
        finally:
            self._unlock()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['recover', 'cancel-restore'])
    args = parser.parse_args()
    try:
        GpuLease().recover(cancel=args.action == 'cancel-restore')
    except GpuBusy as exc:
        print(str(exc))
        raise SystemExit(1)

if __name__ == '__main__':
    main()
