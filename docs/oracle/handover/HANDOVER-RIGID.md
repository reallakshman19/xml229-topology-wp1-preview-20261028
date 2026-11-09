# Handover — RIGID Task 2: split RIGID weights proven in CII bytes · checkpoint 9 Nov 2026

LOCAL/DRIVE ONLY (contains chat URLs and Owner-file details). Never publish.

| Item | Value |
|---|---|
| Repo | reallakshman19/3D_Converters (PUBLIC) — PR #406, draft, never merge without Owner word |
| Head | 461c0d1d89b642c1e2ea0ce5c9c8a4499c336dff (S2-R2) · S1 accepted at df545b74 · ordinary-output control main 3377b7f4 |
| Coder | rigid-coder-3 — <CHAT_URL_REDACTED> (title "Test repair pass"; loads slowly, wait for the spinner) |
| State | S2-R2 gated REPAIR 9 Nov 02:57Z (runner SUPPORTS, fresh reviewer 69). Coder idle. Card RIGID-S2-R3 DRAFTED, NOT SENT. Release BLOCKED. |
| Route | S1 = BM2's 14 flange/PCOM checkpoint pairs (ACCEPTED 7 Nov); S2 = full owner/mass budget (in repair); S3 = independent actual-byte release proof (later). |

## Owner rulings (binding)
- R-LT9: the 19.1 mm span is not a flange; the 109 mm element is the flange, 15 kg / 150 N, counted once.
- R-LT10: unknown component W = W_ref × L / L_ref; L < flange L + 6 mm → row 252 (109 mm, 15 kg) → 19.1 mm = 2.63 kg / 26.3 N SUGGESTED; else row 974 (368 mm, 47 kg); missing/NaN → REVIEW/null.
- 9 Nov: R9-derived fixture leak — "Replace, keep history" (no force-push; old commit ef4fae3e stays in public history).

## Facts established (exact-R9, reproduced by Oracle runners)
- Product path (stage_native_original_lineage → bind_native_final_xml → _parse_xml_document → serializer) on R9: 433 elements, 143 RIGID (the source ledger had 144; 5 named differences from 3.2 mm node-pair merges: E59 570-579→570-580, E403 3370-3379→3370-3380, E404 not RIGID).
- Mass budget: 82 known sources 1,870 kg = 50 OWNED 894 kg + 32 HELD 976 kg; 72 sources unknown (null).
- Exact-R9 test CII sha 9bd0f4ae…; status sidecar dbf64dac…: 50 OWNED (10 × kg once), 14 SUGGESTED (26.3 N), 32 HELD sources / 976 kg exactly once, 79 zero-force records = REVIEW/HELD only.
- F1 ordinary-output control: 5,718 B sha 53080e6e… byte-identical to main.

## Still open (S2-R2 reviewer, scratch\rev-s2r2\REVIEW-S2-R2.md)
- Synthetic CI test asserts labels instead of deriving (2.63 kg written into the input; statuses hard-coded).
- 4 CI steps named as R9 checks pass by skipping.
- P3 position rule and the 3.2 mm merge window are untested (mutants X1, X2, X3, X9 survive).

## Running the exact-R9 proof locally (Owner data, never in CI/git)
```
$env:RIGID_S2_R9_XML   = "<path>\bm2-enriched-R9.xml"      # Drive Handoffs/RIGID-2.4-R9/
$env:RIGID_S2_R9_SHA256 = "5cf2bfbe4cbe88361afcb3374c5230ee4badf42d9f503ec2cb5b2f0b7414e00c"
$env:RIGID_S2_R9_BYTES  = "687252"
$env:RIGID_S2_R9_LEDGER = "<path>\rigid-s2-r9-ledger.json"  # Drive pack inputs\ (removed from the repo in S2-R2)
python -I tests\rigid-s2-r1-native-proof.test.py   # expect 17/17, CII 9bd0f4ae
```
3D_Converters checkouts need `git -c core.protectNTFS=false`. Runner tools: oracle\scratch\run-s2\tools (runner_mutants.py, cii_check.py, native_check.py, held_geom.py), run-s2r1, run-s2r2.

## Next 5 actions
1. Ask the Owner: send RIGID-S2-R3 (plans/cards/RIGID-S2-R3.md)?
2. On OK: stage in Drive Handoffs/RIGID-S2-R3/ (verify sha), send to rigid-coder-3.
3. Gate S2-R3 (runner with R9 env vars + fresh reviewer; exact-R9 CII must stay 9bd0f4ae; no CI step passes by skipping).
4. Plan S3 (independent actual-byte release proof) with the Owner; release stays BLOCKED until S3 + Owner decision.
5. Sequence rigid aim 2 (continuity after split, with lane A) and the REDUCERS converter bug so two coders never edit xml_to_cii2019* at once.

## Local-only code (now pushed as backup)
3D_Converters_v0.5a wip/handover-20261109/rigid-mass-verify (a61c3788): unreviewed rigid mass prototype from 4 Nov (Owner override of "rigid local-only").
