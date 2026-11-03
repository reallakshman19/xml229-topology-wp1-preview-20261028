"""R2 actual Python source-call mutation kills in isolated public temp copies.

Every mutant changes exactly ONE statement in short_batch.py; all other
native functions, public fixtures and tests remain byte-identical. The real
target regression test must be GREEN unmodified and FAIL after mutation.
No private Owner model, identifiers or external files are opened.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"converters"/"psi116_topology_resolver"/"short_batch.py"
TARGET=ROOT/"tests"/"test_short_batch_mutants.py"
GRAPH=ROOT/"tests"/"test_short_batch_graph.py"

MUTANTS=(
    ("GLOBAL_PREFLIGHT_CALL_REMOVED",
     "    _global_intermediate_preflight(middle,policy)",
     "    pass  # MUTANT global preflight call removed",
     "test_global_preflight_call_alone_kills_its_source_mutant"),
    ("OWNER_PREFLIGHT_CALL_REMOVED",
     "        _owner_intermediate_preflight(middle,(*stage_actions,closure),policy)",
     "        pass  # MUTANT owner preflight call removed",
     "test_owner_preflight_call_alone_kills_its_source_mutant"),
    ("POST_APPLY_GUARD_CALL_REMOVED",
     "    _post_apply_owner_write_footprint_guard(operations,footprints_by_owner)",
     "    pass  # MUTANT final actual-edited-key guard call removed",
     "test_post_apply_edited_key_source_guard_kills_mutant_alone"),
    ("SEQUENTIAL_REQUALIFICATION_CALL_REMOVED",
     "            _verify_order_preserving_owner_step(prior_xml,request,current,config)",
     "            pass  # MUTANT source requalification removed",
     "test_n1_earlier_closure_creates_later_25mm_competitor_both_directions"),
    ("STRICT_RUNTIME_CERTIFICATE_FORCED_TRUE",
     "    strictly_isolated=_strict_runtime_order_isolation(before,rows,config)",
     "    strictly_isolated=True  # MUTANT runtime isolation forged",
     "test_n1_earlier_closure_creates_later_25mm_competitor_both_directions"),
)


class RealSourceCallMutantKills(unittest.TestCase):
    def test_each_source_level_guard_mutant_red_with_real_regression_line(self):
        original=SOURCE.read_text(encoding="utf-8")
        for name,needle,replacement,case in MUTANTS:
            with self.subTest(name=name):
                self.assertEqual(original.count(needle),1,
                    "source mutation target must be unique: "+name)
                with tempfile.TemporaryDirectory(prefix="a6b-r2-synthetic-mutant-") as temp:
                    workspace=Path(temp)
                    pkg=workspace/"converters"/"psi116_topology_resolver"
                    tests=workspace/"tests"
                    shutil.copytree(SOURCE.parent,pkg,
                        ignore=shutil.ignore_patterns("__pycache__"))
                    tests.mkdir()
                    shutil.copy2(TARGET,tests/TARGET.name)
                    shutil.copy2(GRAPH,tests/GRAPH.name)
                    source_mutant=pkg/"short_batch.py"
                    env={**os.environ,
                         "PYTHONPATH":os.pathsep.join((
                             str(workspace/"converters"),
                             str(ROOT/"tests")))}
                    def run():
                        args=[sys.executable,"-B","-m","unittest",
                              "discover","-s",str(tests),
                              "-p","test_short_batch_*.py",
                              "-k",case,"-v"]
                        return subprocess.run(args,cwd=workspace,
                            env=env,capture_output=True,text=True,
                            timeout=90,check=False)
                    green=run()
                    self.assertEqual(green.returncode,0,
                        name+" unmodified control failed:\n"+green.stderr[-1800:])
                    self.assertIn("OK",green.stderr)
                    print("A6B_R2_SOURCE_MUTANT_GREEN:"+name+":1/1_PASS",flush=True)
                    source_mutant.write_text(
                        original.replace(needle,replacement),
                        encoding="utf-8")
                    red=run()
                    self.assertNotEqual(red.returncode,0,
                        name+" source-call mutant SURVIVED")
                    self.assertIn("FAIL: ",red.stderr,
                        name+" mutation must FAIL a real unit test, not import")
                    self.assertIn(case,red.stderr,
                        name+" must fail the specifically targeted test")
                    self.assertIn("AssertionError",red.stderr,
                        name+" must be killed by the named refusal assertion")
                    line=next((v.strip() for v in red.stderr.splitlines()
                        if v.strip().startswith("AssertionError:")),None)
                    self.assertIsNotNone(line,
                        name+" requires an actual red assertion line")
                    print("A6B_R2_SOURCE_MUTANT_RED:"+name+":"+line,flush=True)


if __name__=="__main__":
    unittest.main()
