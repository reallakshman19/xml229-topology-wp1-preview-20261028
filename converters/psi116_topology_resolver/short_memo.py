"""Bounded, opt-in, per-Apply short-drop memo. No persistent or disk cache.

Public entry points are scoped by the Worker bulk-session token or a Python
with-block. Exact source bytes, source identity, policy, config and code tag
form the native key. Full UXML JSON is separately hashed for reconstructed
UXML input, so a changed/lossy UXML witness can never inherit a prior result.
Every cache entry is deep-copied ON INSERT and ON HIT; original objects may
be mutated without contaminating a later authority check.
"""
from __future__ import annotations
from collections import OrderedDict, Counter
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

CODE_VERSION = "uxml-short-memo-v1-sourcebound-20261102"
_active = None


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf-8")


def _config(config) -> str:
    return _digest(_json(asdict(config)))


def _key(kind, source_bytes, policy, config, source_name="", provenance=""):
    return (CODE_VERSION, kind, _digest(source_bytes),
            _digest(_json(asdict(policy))) if policy is not None else "",
            _config(config), source_name, provenance)


class ShortMemo:
    def __init__(self, token: str):
        self.token = token
        self.stores = {name: OrderedDict() for name in
                       ("transaction", "source_resolve", "uxml_resolve")}
        self.counts = Counter()

    def get(self, kind, key):
        store = self.stores[kind]
        if key not in store:
            self.counts[kind + "_miss"] += 1
            return None
        store.move_to_end(key)
        self.counts[kind + "_hit"] += 1
        return deepcopy(store[key])

    def put(self, kind, key, value):
        store = self.stores[kind]
        store[key] = deepcopy(value)
        store.move_to_end(key)
        # Bound original+derived source memories on long owner selections.
        while len(store) > (6 if kind != "uxml_resolve" else 2):
            store.popitem(last=False)
        self.counts[kind + "_store"] += 1


def start_memo(token: str, enabled=True):
    global _active
    if not enabled:
        _active = None
        return
    if not isinstance(token, str) or not token or len(token) > 160:
        raise ValueError("SHORT_MEMO_SESSION_TOKEN_INVALID")
    if _active is None or _active.token != token:
        _active = ShortMemo(token)


def clear_memo():
    global _active
    _active = None


@contextmanager
def memo_session(token="native-test", enabled=True):
    global _active
    previous = _active
    try:
        _active = None
        start_memo(token, enabled=enabled)
        yield _active
    finally:
        _active = previous


def stats():
    return dict(_active.counts) if _active is not None else {}


def transaction_key(before, policy, config):
    source = before.document
    return _key("transaction", source.source_text.encode("utf-8"),
                policy, config, source.source_path)


def lookup_transaction(before, policy, config):
    if _active is None:
        return None
    return _active.get("transaction", transaction_key(before, policy, config))


def remember_transaction(before, policy, config, result):
    if _active is not None:
        _active.put("transaction", transaction_key(before, policy, config), result)
    return result


def _source_input(source, source_name):
    if isinstance(source, Path) or (isinstance(source, str) and "<" not in source):
        path = Path(source)
        return path.read_bytes(), source_name or str(path)
    return str(source).encode("utf-8"), source_name or "<memory>"


def source_resolve(source, config, *, source_name=None):
    from .parser import read_psi116_xml
    from .resolver import analyze_document
    if _active is None:
        return analyze_document(read_psi116_xml(source, source_name=source_name), config)
    exact_bytes, name = _source_input(source, source_name)
    key = _key("source_resolve", exact_bytes, None, config, name)
    hit = _active.get("source_resolve", key)
    if hit is not None:
        return hit
    value = analyze_document(read_psi116_xml(source, source_name=source_name), config)
    _active.put("source_resolve", key, value)
    return value


def uxml_resolve(uxml, config, *, source_name=None):
    from .uxml_adapter import resolve_from_uxml
    if _active is None:
        return resolve_from_uxml(uxml, config, source_name=source_name)
    # Include every structural field, raw node fragment and sourceRef in the
    # key. A malformed/changed UXML cannot receive a cached validated result.
    source = uxml.get("sources") if isinstance(uxml, dict) else None
    first = source[0] if isinstance(source, list) and len(source) == 1 else {}
    raw = first.get("sourceText") if isinstance(first, dict) else None
    if not isinstance(raw, str):
        return resolve_from_uxml(uxml, config, source_name=source_name)
    key = _key("uxml_resolve", raw.encode("utf-8"), None, config,
               source_name or "<memory>", _digest(_json(uxml)))
    hit = _active.get("uxml_resolve", key)
    if hit is not None:
        return hit
    value = resolve_from_uxml(uxml, config, source_name=source_name)
    _active.put("uxml_resolve", key, value)
    return value
