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
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

CODE_VERSION = "uxml-short-memo-v2-route-document-bound-20261102"
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


def _document_digest(before):
    """Hash ALL topology witnesses consumed by native short-drop authority.

    The source-byte key separately covers original XML text and its exact SHA.
    Do not fold source_text/source_sha256 into this digest: independently
    removing the byte-key component must remain a detectable safety mutant.
    Include every reconstructed UXML record, raw fragment, span, finding,
    fix-action blocker and connection resolution. Never trust sourceText as
    proof that a UXML-fed document contains identical semantic records.
    """
    payload = asdict(before)
    for field in ("source_text", "source_sha256", "source_path"):
        payload["document"].pop(field, None)
    return _digest(_json(payload))


def transaction_key(before, policy, config, *, route="native"):
    if route not in ("native", "uxml"):
        raise ValueError("SHORT_MEMO_TRANSACTION_ROUTE_INVALID")
    source = before.document
    # Independent key components: exact XML bytes, policy/config/code/path,
    # route custody, and the complete analyzed record/authority witness.
    # A direct result can NEVER satisfy a UXML transaction cache lookup,
    # even when both consume the same original XML and source_name.
    return _key("transaction", source.source_text.encode("utf-8"),
                policy, config, source.source_path,
                provenance=source.source_sha256) + (route, _document_digest(before))


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
               source_name or "<memory>", _digest(_json(uxml)))
    hit = _active.get("uxml_resolve", key)
    if hit is not None:
        return hit
    value = resolver(uxml, config, source_name=source_name)
    _active.put("uxml_resolve", key, value)
    return value
