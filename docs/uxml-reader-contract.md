# UXML browser reader handshake — UXML-UI

**Consumer proposal awaiting coder-b contract confirmation (31 Oct 2026).**
Owner D1: XCU's uxml owns UXML. D2: patch original PSI116 records by
sourceRefs.recordKey, never rebuild original XML from normalized UXML.
D3: retain the current TopoFix Python engine. All engineering HOLDs remain.

## Immutable source custody

External source: reallakshman19/XML_Compare_Utilities,
commit 9f51bfcaf98af4041ec0c0615dc67c9c357b0632.
Build/preview command: bash tools/fetch-uxml-reader.sh dist
Target: dist/vendor/uxml (untracked, never commit source copies).
Both Pages and repair-validation fetch and verify all seven Git blobs.

| Relative upstream path | Pinned Git blob SHA-1 |
| --- | --- |
| package.json | 8b0cc1e976ef2cd3cd10f344b37463738d22ea3d |
| uxml/UxmlConstants.js | 457b970f9cbccd29d38cecd0842614c339108107 |
| uxml/UxmlProfileDetector.js | b4edfc1b47337a0ad62d2a01c0c8f2ff86844803 |
| uxml/UxmlTypes.js | 5bac50ca692c483c3800ae7ec712710e7ae08572 |
| uxml/UxmlValidationGate.js | 7a6070f9b77602f227a30d7e06a3e425d17c9c16 |
| uxml/UxmlPsi116SchemaMapper.js | 978a63141fb94ef9cad3c8eaa637a37675a605f9 |
| tools/psi116-to-uxml.mjs | 7148fc20000963c5a32be27a7787705745e1d30b |

At runtime the disposable Worker verifies Git blob SHA-1 for the FIVE
JavaScript ES modules (using Git's "blob <length>\0" prefix) BEFORE
executing imports. Imports resolve to verified in-memory Blob URLs
only; no check/import network race. Browser does NOT execute the
Node-only CLI or package.json. A hash mismatch produces
UXML_READER_BLOB_HASH_MISMATCH and a visible UI parity error. The
legacy direct route works when the optional toggle is OFF.

## Exact XCU exports consumed

- uxml/UxmlPsi116SchemaMapper.js exports mapPsi116ToUxml(xmlText,
  {fileSha256}) and UXML_PSI116_MAPPER_SCHEMA equal to
  "uxml-psi116-source-reader/v1".
- That mapper imports SOURCE_FORMATS/XML_PROFILES/CONFIDENCE_LEVELS
  from UxmlConstants.js; detectUxmlProfile from UxmlProfileDetector.js;
  document builders from UxmlTypes.js; validateUxmlDocument from
  UxmlValidationGate.js. The consumer does not modify these modules.
- Input: original UTF-8 file bytes; SHA-256 over the original bytes,
  including optional UTF-8 BOM. Decode using
  TextDecoder('utf-8',{fatal:true,ignoreBOM:true}) to preserve source
  Unicode/BOM/CRLF; do not silently renumber or normalize.
- Output: object schemaVersion "uxml-topology-v1", profile
  "UXML-TOPOLOGY-FULL"; sources[0] with format "PSI116", hash =
  original file SHA-256, sourceText = original decoded source.
  psi116.sourceSha256 equals SHA, outputPolicy =
  "PATCH_ORIGINAL_RECORDS_BY_SOURCE_REFS_ONLY".
  components[*].sourceRefs[0] contains format/fileSha256/
  recordKey/branchName/nodeNumber/endpoint. Also consumes
  pipelines, components, anchors, ports, topologyHints,
  lossContract and validation.blockerCodes (must be an empty array).
  No inferred physical edge or writer is accepted.

## Native TopoFix route and preview gates

The Worker sends this JSON to existing Pyodide via the unchanged
disposable Worker/cancel path. Python resolve_from_uxml(doc) from
psi116_topology_resolver.uxml_adapter produces findings_payload and
fix_plan_payload, compared to existing direct resolve_psi116.
Only current-policy selected mutating Auto fix actions pass
export_edit_ops(doc, policy=TransactionPolicy(selected_action_ids=...)),
which yields uxml-edit-ops/v1. apply_edit_ops(original_path, doc, ops)
patches the original by sourceRefs with existing transaction.py
mutation and validation authority. Compare corrected XML bytes and
complete validation report against direct apply_topofix_transaction.
Parity badge: EQUAL or DIFFERENT with explicit difference paths.
Hub corrections downloadable only at EQUAL; any mismatch blocks
the hub download. Manual, CLOS and review actions do not gain
new mutation authorization. No CII/Final release.

## Pending handshake

Coder-b must acknowledge that these exact exports, schema fields,
SHA/BOM semantics, sourceRefs, lossContract and outputPolicy are
the published XCU 9f51bfca contract. If changed, stop rather
than guess or edit XCU.
