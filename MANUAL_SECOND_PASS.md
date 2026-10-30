# Manual Fix by rule and explicit connection second pass

Owner intent: “Topo should not burden with finding but provide auditable solution which are auto fixable if not set clear directions for manual review.”

Manual Fix now opens a compact **By Rule** view. Rules show the current unresolved finding count and expand into individual source cases. Case expansion and rule expansion survive a redraw. Search and engineering-class filtering still operate on the actual findings. Saving an intentional-end or repair-needed note does not remove a finding or manufacture engineering acceptance.

For an unverified end or supported connection case, **Add second pass** opens a physical-port selector. This supports a single-witness branch-end finding as well as a two-witness joint. The engineer chooses the intended counterpart using the source-keyed list or one exact canvas selection. The list shows measured 3D distance and owner type; ordering by distance never selects or authorizes a connection.

**Preview second pass** asks the Python engine for the proposed movement without changing XML, revision or counts. It shows the fixed and moving ports, displacement, every changed source record and before/after XYZ and NodeNumber. The engine prefers moving PIPE, then flange, valve and bend, using the existing constrained-owner fallback and complete finite-owner movement. Missing compatibility evidence, closed ends, restraints, shared-position conflicts and pipe collapse still veto the operation.

The engineer supplies the connection reference/reason and confirms the displayed movement. **Apply second pass & recheck** independently recomputes that exact proposal against the current source SHA. Missing confirmation, changed ports, altered affected records, displacement or policy, and stale source are rejected. One connection applies at a time; select the next case from the freshly rebuilt findings.

The separate confirmation permits the selected connection to exceed 25 mm. Automatic discovery, Autofix-All, the existing joint control and the default configuration keep their inclusive 25 mm limit. The new disposition is never an automatic batch candidate.

Application uses the existing atomic XML transaction, full topology reanalysis and pre-Final lineage verification. The current XML changes only after validation and reanalysis succeed. The original source remains retained; failure preserves the last validated working copy and receipt. Downloads include the approved pair, source identity, proposed movement, actual operations, checks, lineage, output hash and before/after finding counts.

## WBS continuation

| WBS | Deliverable | Verification |
| --- | --- | --- |
| 3.2.1 | Collapsed Manual Fix rule groups and individual cases, counts and expansion controls | Node rendering, filtering, unknown-rule and escaping checks; browser rule/case navigation |
| 3.2.2 | Source-witness and intended-partner selection, including canvas selection | Source-port mapping, measured distance, no implicit nearest selection |
| 3.2.3 | Explicit preview/approval and atomic selected-port repair beyond 25 mm | Positive 75 mm PIPE/flange and GASK/PIPE cases; stale/tampered/missing-approval, unknown evidence, closed-end and restraint negatives; unchanged automatic boundary |
| 3.2.4 | Recheck, refreshed counts/canvas and downloadable XML/connection receipt | Browser downloads inspected against literal geometry, approval and SHA expectations |

## Qualification boundaries

Author checks cover this implementation. The existing IR R4 mechanical reconciliation and R5 parser result remain credited; R6 still reports incomplete independent engineering/native/physical Weight witnesses. These UI and selected-geometry operations do not substitute for that evidence or authorize engineering release. PRs #7/#8 are retained unchanged as reviewed dependencies; protected PR #346 remains on HOLD. No native CII or Weight master changes are introduced.
