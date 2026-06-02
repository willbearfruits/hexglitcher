"""Stable, fast hashing used for pipeline cache keys.

The cache is a prefix cache: each operation folds its identity into a running
hash, and the output *after* that op is stored under the running hash. Editing
op *i* changes the running hash from *i* onward, so everything before *i* is
served from cache and only *i…N* recompute. This mirrors darktable's pixelpipe.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(value: Any) -> str:
    """Deterministic string form of JSON-ish params (sorted keys, stable floats)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=repr)


def hash_bytes(data: bytes) -> str:
    """Content hash of a byte buffer (used once per source image)."""
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def fold(running: str, *parts: Any) -> str:
    """Fold one operation's identity into the running prefix hash.

    `running` is the hash of everything upstream; `parts` describe this op
    (type id, params dict, region, ...). Returns the new running hash.
    """
    h = hashlib.blake2b(digest_size=16)
    h.update(running.encode())
    for part in parts:
        h.update(b"\x1f")  # unit separator between fields
        if isinstance(part, (bytes, bytearray)):
            h.update(bytes(part))
        else:
            h.update(_canonical(part).encode())
    return h.hexdigest()
