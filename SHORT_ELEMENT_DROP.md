# Optional ≤6 mm element drop and reconnection

The Owner requested a separate button to remove short elements, primarily gaskets, then apply the automatic connection policy. **Drop ≤6 mm elements, then close…** previews complete measured component owners. **Select eligible gaskets** selects GASK owners, including their RIGID endpoint records. Other eligible two-port component types may be selected individually.

The preview shows the component reference, exact source record keys, record count, measured span and removed weight. It does not infer a short physical component from one isolated or zero-length helper record. The maximum distance across all measured owner records must be ≤6 mm, including exactly 6 mm. Records without a complete measurable owner, restraints, declared closures, shared external node identities, boundary-only elements and ambiguous owners remain visible with a reason when a two-port measurement exists.

Apply binds the selected owner and full source-record list to the current XML SHA-256. It rederives the component measurement and compatible surrounding physical ports in Python. Removal and closure are one atomic component transaction. Closure follows **PIPE → FLAN → VALV → ELBO/BEND**, trying the next owner if the first cannot move. The surrounding interfaces require known positive matching diameter and facing directions under the port policy. A failed reconnection emits no XML with that component removed.

Several selected components run as sequential validated transactions. If a later component fails, the prior validated working copy and receipts remain downloadable; the interface reports how many selected elements remain. No unselected short component is removed by ordinary Autofix-All.

The download records the original source hash, explicit source-bound selection, complete removed XML record tombstones, intentional weight reduction, changed retained ports, full transaction/validation receipts and source lineage. Each pass is replayable against its own source revision. Retained records may change only the authorized NodeNumber and Position fields; retained component dimensions and all other XML fields are checked by full source-lineage comparison. The original upload remains available as the source of the repair history.

Validation includes mixed GASK/RIGID ownership, exactly 6 mm, 6.001 mm exclusion, other two-port types, removed mass, stale/partial selection, hidden owner records, shared identities without positions and atomic reconnection failure. A real Chromium/Pyodide journey downloads and checks the four-record result of a six-record gasket fixture, its receipt/tombstones and unchanged retained flange; it also verifies that restrained neighbours prevent removal.

This feature is a separate stacked change above PR #7. Both changes require review; protected PR #346 remains HOLD.
