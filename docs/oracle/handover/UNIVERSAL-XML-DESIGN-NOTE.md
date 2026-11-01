# Universal XML hub for TopoFix: design note R0

31 Oct 2026 · TopoFix Oracle · status: **D1, D2 and D3 accepted by the Owner (31 Oct 17:28): XML_Compare_Utilities/uxml owns UXML, the way back is a patch, and TopoFix keeps its Python engine fed by UXML.** D4 and D5 are still open. Nothing has been built from it.

## 1. Owner intent (own words, 31 Oct 17:22)

> xml/inputxml/enrichedxml/Categorisedxml → Universalxml → Topofix → Universalxml → xml/inputxml/enrichedxml/Categorisedxml

Every format goes into one Universal XML. TopoFix works only on that. The result goes back out in the same format it came in.

## 2. What exists today (checked in the code, not assumed)

**A Universal XML (UXML) already exists.** It is `uxml-topology-v1`, 20 modules in `XML_Compare_Utilities/uxml/`.
- **What a document holds:** sources, mappings, pipelines, components (each with `sourceRefs`), ports, segments, supports, topology hints, a `lossContract` and diagnostics.
- **Ports are read-only by design:** `fixed: true`, `mutableNow: false`, `futureMovable`. So UXML was built for analysis, with edits planned for later.
- **Readers into UXML:**
  - CAESAR II InputXML (`UxmlInputXmlSchemaMapper`);
  - a `<Project><Component>` "Standard XML" (`UxmlStandardXmlSchemaMapper`);
  - PCF and RVM bridges.
- **No PSI116 reader.** No module in `uxml/` mentions PipeStressExport or Branchname.
- **No Enriched or Categorised XML reader** found in `uxml/`.
- **No writer back to any source format.** The so-called "round trip" route (`InputXmlUxmlRoundTripRoute.js`) goes InputXML → UXML → topology → **viewer**. It never returns to InputXML.
- **Copied in at least five repos:** 3DC, 3D_Converters, 3D_Convertersv1.0, XML_Compare_Utilities v1.0a, plus a frozen `Rvmx` copy. The RVM converter froze its own copy because the shared one "is continually patched by other workflows and has repeatedly regressed". Copies drift.

**TopoFix today handles PSI116 only.**
- **Engine:** Python, about 3,500 lines, run in the browser through Pyodide.
- **Identities:** source keys such as `B32:N7250:S84`, meaning branch, node and sequence in the PSI116 file.
- **How it edits:** it changes the PSI116 element tree in place and writes the whole file out again.
- **How it checks the edit:** it compares a canonical hash of every untouched element, plus counts such as restraints. Untouched records come out **semantically identical, not byte-identical**.

**The TOPO-B classifier already recognises five formats:** PSI116, conventional InputXML, F05, R4 and GLRD. It admits F05 and R4 through a **second graph model**, `extractXmlProfile`/`buildXmlGraph` in `prototypes/ciifr-map`, which is not UXML. So two "universal" graph models already exist side by side.

## 3. Proposed design

```
 PSI116 ─┐                                 ┌─ patch writer ─► PSI116 (same file, edited records only)
InputXML ┼─ reader ─► UXML ─► TopoFix ─► edit operations ─┼─ patch writer ─► InputXML
Enriched ┤   (+ link to each        (findings,            ├─ (no writer yet) ─► read-only: findings + Source Review
Categor. ┘    original record)       review, CLOS rules)  └─ …
```

1. **One hub: UXML.** Extend the existing `uxml-topology-v1`; don't invent a new one. Choose one repo to own it, and have the others consume it rather than copy it.
2. **Every reader keeps a link back.** Each UXML component and port carries `sourceRef = {format, fileSha256, recordKey}`. For PSI116 the record key is today's source key (`B32:N7250:S84`). Without that link nothing can come back safely.
3. **TopoFix reads UXML and outputs edit operations, never a file.** An operation looks like "close port A to port B" or "drop element X", always on UXML ids. Everything already settled stays inside TopoFix and works the same for any format:
   - the findings;
   - the review-only checks and the CLOS refusals;
   - the Source Review Queue.
4. **The way back is a patch, not a rebuild.** A small writer for each format applies each operation to the original records it points to. Untouched records are proven unchanged: by hash per record, as TopoFix does today, and byte-identical where the format allows it.
   - **Rejected alternative:** rebuilding the whole file from UXML. That needs UXML to carry every field of every format, and anything it misses is silently lost.
5. **The `lossContract` gates edits.** Each reader declares which fields it does not carry. An operation that would touch such a field is refused.
6. **No writer means read-only.** A format with a reader but no writer gets findings and the Source Review Queue, and nothing else. This is exactly today's TOPO-B "admitted read-only" idea. The classifier becomes the router.

## 4. Steps, each with an Owner benchmark

| Step | What you can do after it | How you check it |
|---|---|---|
| S1 · PSI116 reader into UXML | See TopoFix findings computed from UXML | On Owner real file and the original, the findings from UXML equal today's: same count, types and ports, including 7250↔6310 as CONFLICTS_WITH_CLOS |
| S2 · PSI116 patch writer | Apply today's Auto fixes through operations | The output passes today's preservation validation and matches today's TopoFix output record for record |
| S3 · InputXML in and back | TopoFix on a CAESAR II InputXML file | A reader already exists. You run one fix and check that only the edited records changed |
| S4 · Enriched and Categorised | TopoFix on them, through the existing Workspace converters | Prove the converters are lossless enough to patch through |
| S5 · F05/R4 RichInput into UXML | One hub; the ciifr-map graph retires | The F05/R4 sample findings from UXML equal today's admitted counts (56 elements / 57 nodes) |

S1 changes no behaviour you can see. That's deliberate: it proves the hub before anything depends on it.

## 5. Decisions only you can make

- **D1 · Which UXML copy owns the model.** Suggested: `XML_Compare_Utilities/uxml`, because it has the most modules and is where TOPO-B lives. The other repos would then consume it rather than copy it.
- **D2 · The way back.** Suggested: patch the original (§3.4). The alternative is rebuilding from UXML.
- **D3 · The TopoFix engine.** Suggested: keep the tested Python and feed it UXML. The alternative is a rewrite in JavaScript, which is cleaner later but means re-earning every test.
- **D4 · Enriched and Categorised XML: ANSWERED by the Owner (snapshot, 31 Oct).** Both are stages of the InputXML Workspace pipeline:
  - Clean XML → 2 InputXML Enrichment → 3 XML to InputXML → 4 Create Categorized XML, which already converts both ways (`input-to-categorized` / `categorized-to-input`).
  - Enriched XML is InputXML with added fields, which the Workspace detects by its enrichment signals.

  So the hub needs only **two native readers and two writers: PSI116 and InputXML**. Categorised rides on the existing two-way converter, and Enriched rides on the InputXML reader. Its extra fields are either carried or listed in the lossContract. Not yet checked: whether those Workspace converters are lossless enough to patch back through.
- **D5 · Two graph models: DECIDED by the Owner (31 Oct 17:41), "Yes, one hub".** At a later step, after PSI116 and InputXML, the existing F05/R4 parser (`extractXmlProfile`) becomes a UXML reader, and the separate ciifr-map graph retires. Until then, F05/R4 stay read-only outside the hub.

## 6. Effect on current work

- **TOPO-A usability round (coder-a):** carries on. It doesn't depend on any format.
- **§3.3 preview:** **on hold** until D2 and D3 are settled. Built now, it would deepen the PSI116-only edit path.
- **TOPO-B:** paused, as you decided. Its classifier becomes the router in §3.6, so the work isn't lost.
- **Risks:**
  - UXML has a record of regressions, so it needs one owner and its own tests.
  - Record ids must stay stable between a read and the patch back.
  - The two graph models must converge.

## 7. Not checked yet (NOT_RUN)

- Whether any branch outside `uxml/` reads PSI116, Enriched or Categorised XML into UXML.
- Whether the UXML copies in the other repos differ from the XML_Compare_Utilities one.
- How complete the existing InputXML reader is (its lossContract).
