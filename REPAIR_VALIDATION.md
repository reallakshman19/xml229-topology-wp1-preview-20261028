# Navigation, working-copy feedback and confirmed joint closure

Owner's reported failures: canvas navigation and centering are unreliable; Autofix gives no visible applied state or updated counts; a manually confirmed small gap/overlap has no executable closure.

The inspection camera now frames projected bounds at the actual viewport aspect ratio, orbits about the framed world position, zooms at the pointer, and uses XY/XZ/YZ top/front/right projections. Drag pans, Shift/right-drag orbits, F frames the selection, and Home/double-click fits the model. The canvas keeps the largest central column.

A successful fix becomes the next working revision only after its validated XML is reanalyzed. The canvas, occurrences, finding counts and remaining actions all use that revision. A visible banner reports applied actions and before/after finding totals; current XML and the source-hash-linked repair history remain downloadable. Failed, cancelled or stale operations cannot publish a partial working revision.

A two-port PIPE joint below **25 mm**, including a short overlap or coincident pair, now has **Close joint & recheck**. The user chooses the retained endpoint and records the intended connection. The backend moves the other endpoint's Position and NodeNumber, preserving both component records and references. The source hash, exact finding witnesses, unique two-port ownership and unrestrained/non-rigid ports are checked again in Python. Shared node groups, component collapse, wrong witnesses and 25 mm or larger moves are rejected. Full transaction checks and source-lineage replay still apply; complex multi-record/span overlaps retain their manual directions.

This does not qualify the inherited source-order alias heuristic challenged by IR R3, or accept all 39 original aliases. Protected PR #346 remains HOLD. The new candidate is author-assessed and requires review.

Local validation: 21 Python tests and 25 Node tests PASS, including 24.9 mm closure, 2 mm overlap closure, coincident identity, lineage replay, negative ownership/source/threshold controls and camera projection/zoom checks. Syntax and whitespace checks PASS. Local full browser execution is NOT_RUN: browser installation returned truncated archives. The PR-only `Topology repair validation` workflow runs the complete Chromium/Pyodide/download journey, verifies working-copy count changes and exercises all three repair examples. It has read-only repository permissions and does not deploy Pages.
