"""Public synthetic interconnected PSI116: strict preview parity and baseline profile.

Unlike the original separated-branch benchmark, these short owners are beside
source-connected BRAN/TEE records, with shared positive port identities.
No Owner-model fixture, coordinate, digest or record enters this repository.
"""
from __future__ import annotations
import cProfile, io, json, os, pstats, subprocess, sys, tempfile, time, unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"converters"))

from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import TransactionPolicy
from psi116_topology_resolver.uxml_adapter import resolve_from_uxml
from psi116_topology_resolver.uxml_edit_ops import export_edit_ops, _source_record_paths
from psi116_topology_resolver.uxml_operations_preview import _ShortPreviewSourceScope, build_operation_preview
from test_port_policy import doc, node
from test_uxml_psi116_s1 import verified_synthetic

N = 60
def interconnected_tee_fixture(count=N):
    branches=[]
    for i in range(count):
        x=1500*i
        k=1000*(i+1)
        # The synthetic parent owns a three-port tee with an explicit center.
        parent=(node(-1,"TEE",f"TEE-{i}",1,f"{x} 0 0")+
                node(k+50,"TEE",f"TEE-{i}",0,f"{x+100} 0 0")+
                node(-1,"TEE",f"TEE-{i}",2,f"{x+200} 0 0")+
                node(-1,"TEE",f"TEE-{i}",3,f"{x+100} 100 0"))
        # Explicit BRAN source declaration shares positive parent identity.
        side=(node(k+50,"BRAN",f"BRAN-{i}",1,f"{x+100} 0 0",
                   "<ConnectionType>TEE</ConnectionType>")+
              node(k+10,"PIPE",f"PIPE-{i}",1,f"{x+100} 0 0")+
              node(k+20,"PIPE",f"PIPE-{i}",2,f"{x+300} 0 0")+
              node(-1,"GASK",f"SHORT-{i:03d}",1,f"{x+300} 0 0")+
              node(k+30,"RIGID",f"SHORT-{i:03d}",2,f"{x+303} 0 0")+
              node(-1,"FLAN",f"FLAN-{i}",1,f"{x+303} 0 0")+
              node(k+40,"RIGID",f"FLAN-{i}",2,f"{x+389} 0 0"))
        branches.extend((parent,side))
    return verified_synthetic(doc(*branches))

def source_bound_input(reader, temp):
    source = Path(temp)/"public-synthetic-interconnected.xml"
    xml=interconnected_tee_fixture()
    source.write_bytes(xml.encode("utf-8"))
    command=["node",str(Path(reader)/"tools"/"psi116-to-uxml.mjs"),str(source)]
    r=subprocess.run(command,cwd=reader,capture_output=True,text=True,timeout=120)
    if r.returncode:raise AssertionError(r.stderr)
    uxml=json.loads(r.stdout)
    cfg=ResolverConfig()
    resolved=resolve_from_uxml(uxml,cfg,source_name=str(source))
    allrows=short_elements(resolved.document,cfg)
    rows=[x for x in allrows if x["componentRefNo"].startswith("SHORT-")]
    if len(rows)!=N:raise AssertionError(f"expected {N} short rows, got {len(rows)}")
    # Three synthetic source-bound losses refuse on exact deleted OWNER path;
    # no raw-only child exemption applies to owner-path losses.
    paths=_source_record_paths(resolved.document.source_text,resolved)
    for row in rows[:3]:
        key=row["nodeKeys"][0]
        uxml.setdefault("lossContract",[]).append({
            "code":"PSI116_RAW_SOURCE_ONLY_NOT_SEMANTICALLY_CARRIED",
            "details":{"sourcePath":paths[key]}})
    return source,xml,uxml,rows,cfg

def capture(one):
    try:
        return ("READY",json.dumps(one()["ops"][0],sort_keys=True,ensure_ascii=False).encode("utf-8"))
    except ValueError as error:
        return ("REFUSED",str(error))

class InterconnectedBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reader=os.environ.get("XCU_UXML_ROOT")
    def test_profile_interconnected_old_and_current_preview(self):
        if os.environ.get("UXML_INTERCONNECTED_BENCHMARK")!="1":
            self.skipTest("UXML_INTERCONNECTED_BENCHMARK=1 required for explicit timing")
        if not self.reader or not (Path(self.reader)/"tools"/"psi116-to-uxml.mjs").is_file():
            self.skipTest("Pinned XCU_UXML_ROOT needed")
        with tempfile.TemporaryDirectory(prefix="public-tee-preview-") as temp:
            source,xml,uxml,rows,cfg=source_bound_input(self.reader,temp)
            self.assertTrue(all(row["eligible"] for row in rows),
                            "each candidate must qualify before per-owner preview")
            self.assertEqual(len(rows),N)
            self.assertEqual(rows[0]["branchIndex"],1)
            self.assertEqual(rows[-1]["branchIndex"],2*N-1)
            request=[{k:r[k] for k in ("id","sourceSha256","nodeKeys")} for r in rows]
            policies=[TransactionPolicy(selected_action_ids=(r["id"],),
                      short_element_requests=(r,)) for r in request]
            old=[]
            profile=cProfile.Profile()
            start=time.perf_counter()
            for i,policy in enumerate(policies):
                call=lambda p=policy:export_edit_ops(uxml,policy=p,config=cfg,source_name=str(source))
                if i<5:
                    profile.enable()
                    value=capture(call)
                    profile.disable()
                else:value=capture(call)
                old.append(value)
            baseline_seconds=time.perf_counter()-start
            report=io.StringIO()
            pstats.Stats(profile,stream=report).strip_dirs().sort_stats("cumulative").print_stats(18)
            print("INTERCONNECTED_BASELINE_PROFILE_TOP_CUMULATIVE\n"+report.getvalue())
            start=time.perf_counter()
            optimized=build_operation_preview(uxml,source_name=str(source),
                                              config=cfg,short_requests=request)
            optimized_seconds=time.perf_counter()-start
            accepted={op["sourceActionId"] for op in optimized["ops"] if op["kind"]=="DROP_SHORT_ELEMENT"}
            refused={row["id"]:row["code"] for row in optimized["shortPreview"]["refused"]}
            current=[]
            # One full-source authority for this entire current-preview pass.
            # The real builder is measured separately above.
            resolved=resolve_from_uxml(uxml,cfg,source_name=str(source))
            scope=_ShortPreviewSourceScope(uxml,resolved,cfg)
            by_id={r["id"]:r for r in scope.rows}
            for req in request:
                if req["id"] in accepted:
                    # Compare complete canonical operation in the cache-backed
                    # source context, not merely rendered preview row fields.
                    policy=TransactionPolicy(selected_action_ids=(req["id"],),
                                             short_element_requests=(req,))
                    call=lambda p=policy:export_edit_ops(
                        uxml,policy=p,config=cfg,source_name=str(source),
                        _preview_result=resolved,_preview_short_rows=scope.rows,
                        _preview_native=scope.native_witness(by_id[req["id"]]),
                        _preview_indexes=scope.indexes)
                    current.append(capture(call))
                else:
                    current.append(("REFUSED",refused[req["id"]]))
            self.assertEqual(current,old,"canonical operation/refusal bytes MUST match for all sources")
            self.assertEqual(len(accepted)+len(refused),N)
            self.assertGreaterEqual(len(refused),3)
            self.assertEqual(source.read_bytes(),xml.encode("utf-8"))
            print(f"INTERCONNECTED_SYNTHETIC_OWNERS={N}")
            print(f"INTERCONNECTED_SYNTHETIC_READY={len(accepted)}")
            print(f"INTERCONNECTED_SYNTHETIC_REFUSED={len(refused)}")
            print(f"INTERCONNECTED_BASELINE_SECONDS={baseline_seconds:.5f}")
            print(f"INTERCONNECTED_PREVIEW_SECONDS={optimized_seconds:.5f}")
            print(f"INTERCONNECTED_PREVIEW_SPEEDUP={baseline_seconds/optimized_seconds:.2f}x")
