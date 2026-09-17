"""Single-writer pilot artifacts with explicit protocol and request provenance."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class PilotStore:
    """Refuse changes to a frozen manifest or a concurrent writer."""

    def __init__(self, root: Path, protocol: dict, source_paths: list[Path]):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.lock = (root / "writer.lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = {
            "protocol": protocol,
            "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths},
        }
        self.protocol_hash = digest(manifest)
        path = root / "manifest.json"
        if path.exists():
            if json.loads(path.read_text()) != manifest:
                raise ValueError("Protocol or source changed: use a new pilot directory")
        else:
            with path.open("x") as stream:
                json.dump(manifest, stream, indent=2, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
        (root / "calls").mkdir(exist_ok=True)
        (root / "sessions").mkdir(exist_ok=True)

    def save(self, folder: str, key: str, record: dict):
        path = self.root / folder / (key + ".json")
        staging = path.with_suffix(".partial")
        with staging.open("w") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        staging.replace(path)


class RecordedBackend:
    """Preserve the entire server response, token use and finish reason per call."""

    def __init__(self, model: str, base_url: str, store: PilotStore):
        self.model, self.base_url, self.store = model, base_url, store
        self.call_keys: list[str] = []

    def generate(self, messages, *, temperature=0.0, max_tokens=256):
        request = {"model": self.model, "messages": list(messages),
                   "temperature": temperature, "max_tokens": max_tokens}
        key = digest({"request": request, "protocol": self.store.protocol_hash})
        self.call_keys.append(key)
        path = self.store.root / "calls" / (key + ".json")
        if path.exists():
            response = json.loads(path.read_text())["response"]
        else:
            started = time.time()
            req = urllib.request.Request(self.base_url.rstrip("/") + "/chat/completions",
                                         data=canonical(request).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as handle:
                response = json.load(handle)
            self.store.save("calls", key, {"request": request, "response": response,
                                           "started_unix": started,
                                           "elapsed_seconds": time.time() - started,
                                           "protocol_hash": self.store.protocol_hash})
        return response["choices"][0]["message"]["content"]
