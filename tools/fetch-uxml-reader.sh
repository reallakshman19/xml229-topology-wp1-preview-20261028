#!/usr/bin/env bash
# Public XCU reader, fetched to an untracked build directory. Fail closed.
set -euo pipefail
destination="dist"
if [[ $# -gt 0 ]]; then destination="$1"; fi
xcu_commit='9f51bfcaf98af4041ec0c0615dc67c9c357b0632'
upstream="https://raw.githubusercontent.com/reallakshman19/XML_Compare_Utilities/$xcu_commit"
mkdir -p "$destination/vendor/uxml/uxml" "$destination/vendor/uxml/tools"
fetch_pinned() {
  local relative="$1" expected="$2" target
  target="$destination/vendor/uxml/$1"
  curl --fail --location --retry 3 "$upstream/$relative" -o "$target"
  local got
  got="$(git hash-object "$target")"
  if [[ "$got" != "$expected" ]]; then
    rm -f "$target"
    echo "UXML_READER_BLOB_HASH_MISMATCH: $relative expected=$expected got=$got" >&2
    exit 1
  fi
}
fetch_pinned package.json 8b0cc1e976ef2cd3cd10f344b37463738d22ea3d
fetch_pinned uxml/UxmlConstants.js 457b970f9cbccd29d38cecd0842614c339108107
fetch_pinned uxml/UxmlProfileDetector.js b4edfc1b47337a0ad62d2a01c0c8f2ff86844803
fetch_pinned uxml/UxmlTypes.js 5bac50ca692c483c3800ae7ec712710e7ae08572
fetch_pinned uxml/UxmlValidationGate.js 7a6070f9b77602f227a30d7e06a3e425d17c9c16
fetch_pinned uxml/UxmlPsi116SchemaMapper.js 978a63141fb94ef9cad3c8eaa637a37675a605f9
fetch_pinned tools/psi116-to-uxml.mjs 7148fc20000963c5a32be27a7787705745e1d30b
echo "UXML_READER_PIN_VERIFIED: $xcu_commit 7/7 Git blob identities"
