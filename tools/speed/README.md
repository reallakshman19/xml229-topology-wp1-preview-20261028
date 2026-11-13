# L4-S1 — measure sequential short-drop Apply

This is a diagnostic, not a repair algorithm. It executes the checked-in Python
`TOPOLOGY_SNIPPET` in `topology-integration.js` with one selected owner per job,
using the pinned XCU PSI116 reader and the existing cross-owner short memo ON.
No product files, tolerance, policy, selection authority or output checks change.
Neither the browser nor PR #34 batching is used.

## Run

Prerequisites: Python 3, Node 22, the seven immutable XCU reader files already
staged by the normal TopoFix build (`tools/fetch-uxml-reader.sh dist`). If the
reader lives elsewhere, set `XCU_UXML_ROOT` or pass `--xcu-root <directory>`.
The harness verifies all seven Git blob hashes before it runs. No installations
are needed. Do not put the reader, original models or generated results in Git.

From the repository root, the Oracle runs this **locally** on the Owner's file:

```sh
python3 -B tools/speed/measure.py /local/path/to/model.xml --owners 89 --out /local/path/to/timings.json
```

Omit `--owners` to measure all initially eligible short owners, or set it to
5 for a smoke run. It selects the first N eligible owners in the product's
initial row order, refreshing each request from the last verified revision.
Named no-output owner refusals and no-longer-eligible rows are accounted as
skips, never applied; any other failure stops. Source bytes are never written.
A private temporary directory holds successive copies and sidecars and is
removed when the run ends. By default only the timing JSON is saved; it must be a new file.
The progress lines contain only ordinal, count and time. Share only counts and
timings from private runs; do not share source files, console tracebacks,
paths, IDs or hashes. There is no CII/Final release.

For a local, independent memo ON/OFF byte comparison (S2 round 2):

```sh
python3 -B tools/speed/measure.py /local/path/to/model.xml --owners 89 --out /local/path/to/on.json --final-out /local/path/to/on.xml
python3 -B tools/speed/measure.py /local/path/to/model.xml --owners 89 --memo-off --out /local/path/to/off.json --final-out /local/path/to/off.xml
python3 -B -c "from pathlib import Path; assert Path('/local/path/to/on.xml').read_bytes() == Path('/local/path/to/off.xml').read_bytes(); print('BYTE EQUAL')"
```

`--final-out` writes the exact final PSI116 bytes in binary mode, only after
all selected owners applied with EQUAL parity. All output paths must be new;
the final path must differ from the original source and timing JSON paths.
Keep the generated XML local/private: it is a diagnostic corrected revision,
not an authorized Final/CII publication. `--memo-off` disables the actual
memo, not the measurement probes. Every Worker check remains enabled.

Invented benchmark and acceptance tests:

```sh
python3 -B tools/speed/gen_fixture.py /tmp/l4-synthetic.xml
python3 -B tools/speed/measure.py /tmp/l4-synthetic.xml --owners 89 --out /tmp/l4-timings.json
python3 -B -m unittest discover -s tools/speed -p test_speed_tools.py -v
```

`gen_fixture.py` writes a new deterministic UTF-8 fixture. Seed 116 by default;
41 branches, 1,654 nodes, 89 eligible straight GASKs and 40 restrained GASKs
with spans of 1–6 mm. Geometry is invented; the fixture is not a copy of the
Owner model and is not an estimate of the Owner's browser runtime. Smaller
fixtures are available via `--branches`, `--nodes`, `--owners`, `--blocked`.

## What the numbers mean

`wallSeconds` is the sum of measured per-attempt wall intervals, starting before
the reader, ending after the revised working copy is staged. Initial selection,
pin verification, startup, and output JSON writing are outside the interval.
`requested`, `applied`, `skipped`, `owners` (attempted jobs) distinguish the
immutable selection and completed transactions. Pre-job skips have no timing;
owner refusals after a job starts have timings but are not EQUAL. All successful
attempts execute direct transaction, initial native/UXML findings and plan
comparison, canonical export, independently re-derived validation, original
sourceRef patch-back, exact transaction/validation/XML parity, full pre-Final
lineage reconstruction and independent replay. The worker's authoritative
post-findings/plan become the next selection basis; the harness checks receipts
before advancing. Memo cache hits still invoke the existing policy/route checks.

`stages[*].seconds` is **exclusive** wall time: nested named work is subtracted
from its caller, so the stages add to wall time (including `other`, the measured
residual). `inclusiveSeconds` is diagnostic cumulative elapsed time including
children; **never sum inclusive times**. `calls` counts named stage entries;
`other` is one residual bucket per attempted owner. The `transactionCalls` array
records each direct, export, validate, apply, replay and nested closure call.
The table prints stage total, per-attempt mean, share, count, count per attempt
and repeats. `memoDelta` reports real cache hit/miss/store increments.

- `parse`: complete native reader, transaction XML clone, lineage root parse;
  per-record fragment parsing inside analysis/adapter remains in those stages.
- `model_analyse`: actual analyzer calls, not cache hits. `resolve`: resolver
  overhead excluding parse, analyze, and memo work. `uxml_reader`: pinned Node
  CLI process and JSON decode (includes process start, not browser mapper time).
  `uxml_adapter`: actual Python UXML adapter; `memo_other` includes cached UXML
  resolution bookkeeping. `hub_parity`: two structural comparisons, not patch
  parity. The Python findings/plan payload construction outside those calls is
  included in `other` or its enclosing named stage.
- `native_transaction_*`: full invocation category, exclusive of named nested
  work. Export/validate/apply are distinct calls even when memoized. Replay is
  the fifth short transaction (pre-Final); nested closure calls are separate.
  `canonical_export`, `canonical_rederivation` (the independent `_validate_ops`
  call), `patch_back`, `patch_back_compare` and `lineage_recheck` are separate.
- `memo_digest`: actual document/key digest computations; under S2 the
  canonicalization and cache lookup work outside those computations is timed
  in its enclosing stage. `memo_copy`: snapshot/restore custody work (and any legacy memo deepcopy).
  S2b counts actual store/hit materializations; the historical S1/S2 copy
  counts are not comparable to this expanded definition. `other`: remaining wall (e.g. JSON
  serialization, short-row selection, file I/O and probe overhead).
- `repeatedInputCalls` counts repeated input-byte fingerprints within an owner
  for named parse/analyse/resolve calls, or the same bytes/policy/route for
  transaction calls. `sameTransactionBytesCalls` also counts repeated XML
  bytes regardless of route/policy. The actual memo binds more witness fields;
  identical source bytes alone are **not** proof of redundant authority.
  Fingerprints are transient and never included in timing JSON.

`--measurement-off` disables every probe, keeping the same worker template,
reader, memo, checks and staging logic. It outputs wall/counts only. T3 compares
both modes against separate direct calls to the existing APIs and asserts exact
PSI116 bytes. No runtime code is patched outside the measurement process.

Native CPython wall time is not browser/Pyodide time: Node CLI startup, process
I/O, Python JSON and scratch-file costs differ. No production speed claim or
change is authorized by this measurement. See REPORT.md for the synthetic run.
