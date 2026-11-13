"""Bounded, opt-in, per-Apply short-drop memo. No persistent or disk cache.

Public entry points are scoped by the Worker bulk-session token or a Python
with-block. Exact source bytes, source identity, policy, config and code tag
form the native key. Full UXML JSON is separately hashed for reconstructed
UXML input, so a changed/lossy UXML witness can never inherit a prior result.
Cache snapshots contain only immutable bytes and verified frozen geometry.
Mutable receipt evidence is materialized independently; exact-byte digest
reuse is bounded to the current bulk session.
"""
from __future__ import annotations
from collections import OrderedDict, Counter
from contextlib import contextmanager
from copy import deepcopy  # compatibility hook for the existing speed meter
import io
import pickle
from dataclasses import fields, is_dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from .models import (Psi116Document, BranchRecord, NodeRecord, Position,
                     ComponentOccurrence, RouteSpan, ResolverConfig)

CODE_VERSION = "uxml-short-memo-v3-immutable-snapshot-20261113"
_active = None


def _digest(data: bytes) -> str:
    return sha256(data).hexdigest()


def _json(value) -> bytes:
    # Same JSON as asdict() for the model dataclasses, without recursively
    # deepcopying scalar leaves and duplicating entire immutable geometries.
    def encode(obj):
        if is_dataclass(obj) and not isinstance(obj, type):
            return {field.name: getattr(obj, field.name) for field in fields(obj)}
        raise TypeError(f"Unsupported memo JSON type: {type(obj).__name__}")
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False, default=encode).encode("utf-8")


def _cached_digest(data: bytes, compute=None) -> str:
    # Dictionary lookup compares the actual bytes, including on hash collision;
    # no object-id or claimed source SHA is trusted. Strong keys are bounded.
    if type(data) is not bytes:
        raise TypeError("SHORT_MEMO_DIGEST_BYTES_REQUIRED")
    if _active is None:
        return (compute or _digest)(data)
    return _active.digest(data, compute) if compute is not None else _active.digest(data)


# The default configuration is immutable and its canonical bytes are known
# independently of any model, owner or session. Compute once, compare bytes
# on every use; non-default configurations still use the exact-byte cache.
_DEFAULT_CONFIG_BYTES = _json(ResolverConfig())
_DEFAULT_CONFIG_DIGEST = _digest(_DEFAULT_CONFIG_BYTES)


def _config(config) -> str:
    data = _json(config)
    return (_DEFAULT_CONFIG_DIGEST if data == _DEFAULT_CONFIG_BYTES
            else _cached_digest(data))


def _key(kind, source_bytes, policy, config, source_name="", provenance=""):
    return (CODE_VERSION, kind, _cached_digest(source_bytes),
            _cached_digest(_json(policy)) if policy is not None else "",
            _config(config), source_name, provenance)


# These frozen dataclasses are the large geometry graph. Never share a value
# merely because its outer dataclass is frozen: verify its entire graph.
_GEOMETRY = (Psi116Document, BranchRecord, NodeRecord, Position,
             ComponentOccurrence, RouteSpan, ResolverConfig)


def _immutable(value, seen):
    kind = type(value)
    if kind in (str, bytes, int, float, bool, type(None)):
        return True
    if id(value) in seen:
        return True
    if kind is tuple:
        seen.add(id(value))
        return all(_immutable(item, seen) for item in value)
    if kind in _GEOMETRY:
        seen.add(id(value))
        return all(_immutable(getattr(value, f.name), seen) for f in fields(value))
    return False


def _snapshot(value):
    # Pickle is only an in-process serialization of internally computed Python
    # values; no pickle is accepted from a file, UXML or other external input.
    # Keep the large verified-frozen geometry by reference, serialize mutable
    # receipt fields (including policy, checks and findings) to immutable bytes.
    shared = []
    indexes = {}
    class Writer(pickle.Pickler):
        def persistent_id(self, obj):
            if type(obj) is Psi116Document:
                index = indexes.get(id(obj))
                if index is not None:
                    return index
                if _immutable(obj, set()):
                    index = len(shared)
                    indexes[id(obj)] = index
                    shared.append(obj)
                    return index
            return None
    buffer = io.BytesIO()
    Writer(buffer, protocol=pickle.HIGHEST_PROTOCOL).dump(value)
    return buffer.getvalue(), tuple(shared)


def _restore(snapshot):
    payload, shared = snapshot
    class Reader(pickle.Unpickler):
        def persistent_load(self, index):
            return shared[index]
    return Reader(io.BytesIO(payload)).load()


class ShortMemo:
    def __init__(self, token: str):
        self.token = token
        self.stores = {name: OrderedDict() for name in
                       ("transaction", "source_resolve", "uxml_resolve")}
        self.counts = Counter()
        self.digests = OrderedDict()
        self.digest_bytes = 0

    def digest(self, data, compute=None):
        if data in self.digests:
            self.digests.move_to_end(data)
            return self.digests[data]
        result = (compute or _digest)(data)
        self.digests[data] = result
        self.digest_bytes += len(data)
        # A large model may exceed the budget; eviction loses speed, not safety.
        while len(self.digests) > 32 or self.digest_bytes > 64 * 1024 * 1024:
            old, _ = self.digests.popitem(last=False)
            self.digest_bytes -= len(old)
        return result

    def get(self, kind, key):
        store = self.stores[kind]
        if key not in store:
            self.counts[kind + "_miss"] += 1
            return None
        store.move_to_end(key)
        self.counts[kind + "_hit"] += 1
        return _restore(store[key])

    def put(self, kind, key, value):
        store = self.stores[kind]
        store[key] = _snapshot(value)
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


def _document_bytes(before):
    """Hash ALL topology witnesses consumed by native short-drop authority.

    The source-byte key separately covers original XML text and its exact SHA.
    Do not fold source_text/source_sha256 into this digest: independently
    removing the byte-key component must remain a detectable safety mutant.
    Include every reconstructed UXML record, raw fragment, span, finding,
    fix-action blocker and connection resolution. Never trust sourceText as
    proof that a UXML-fed document contains identical semantic records.
    """
    payload = {f.name: getattr(before, f.name) for f in fields(before)}
    payload["document"] = {f.name: getattr(before.document, f.name)
                           for f in fields(before.document)
                           if f.name not in ("source_text", "source_sha256", "source_path")}
    return _json(payload)


def _document_digest(before):
    # Digest the canonical witness on a cache miss. Accept precomputed bytes
    # to avoid repeating serialization; preserve the independent witness seam.
    return _digest(before if type(before) is bytes else _document_bytes(before))


def transaction_key(before, policy, config, *, route="native"):
    if route not in ("native", "uxml"):
        raise ValueError("SHORT_MEMO_TRANSACTION_ROUTE_INVALID")
    source = before.document
    # Independent key components: exact XML bytes, policy/config/code/path,
    # route custody, and the complete analyzed record/authority witness.
    # A direct result can NEVER satisfy a UXML transaction cache lookup,
    # even when both consume the same original XML and source_name.
    return _key("transaction", source.source_text.encode("utf-8"),
                policy, config, source.source_path) + (route, _cached_digest(_document_bytes(before), _document_digest))


def lookup_transaction(before, policy, config, *, route="native"):
    if _active is None:
        return None
    return _active.get("transaction", transaction_key(before, policy, config, route=route))


def remember_transaction(before, policy, config, result, *, route="native"):
    if _active is not None:
        _active.put("transaction", transaction_key(before, policy, config, route=route), result)
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
    # Analysis has no dependency on source_path; only its receipt metadata
    # does. Key by exact bytes and config, then rewrite ONLY the requested
    # path in an isolated copy. This allows the next owner's original source
    # to reuse the prior owner's post-closure resolve despite .topofix paths.
    key = _key("source_resolve", exact_bytes, None, config)
    hit = _active.get("source_resolve", key)
    if hit is not None:
        # read_psi116_xml() also calls ET.register_namespace("", namespace).
        # This hit skips that process-global serializer side effect.
        # Serializers must not rely on a cache miss to set namespace state.
        return replace(hit, document=replace(hit.document, source_path=name))
    value = analyze_document(read_psi116_xml(source, source_name=source_name), config)
    _active.put("source_resolve", key, value)
    return value


def uxml_resolve(uxml, config, *, source_name=None, resolver=None):
    from .uxml_adapter import resolve_from_uxml as canonical_resolver
    if resolver is None:
        resolver = canonical_resolver
    # A test/injected reader is an independent semantic input. Do not reuse
    # a result produced by a different resolver implementation.
    if _active is None or resolver is not canonical_resolver:
        return resolver(uxml, config, source_name=source_name)
    # Include every structural field, raw node fragment and sourceRef in the
    # key. A malformed/changed UXML cannot receive a cached validated result.
    source = uxml.get("sources") if isinstance(uxml, dict) else None
    first = source[0] if isinstance(source, list) and len(source) == 1 else {}
    raw = first.get("sourceText") if isinstance(first, dict) else None
    if not isinstance(raw, str):
        return resolver(uxml, config, source_name=source_name)
    key = _key("uxml_resolve", raw.encode("utf-8"), None, config,
               source_name or "<memory>", _cached_digest(_json(uxml)))
    hit = _active.get("uxml_resolve", key)
    if hit is not None:
        return hit
    value = resolver(uxml, config, source_name=source_name)
    _active.put("uxml_resolve", key, value)
    return value
