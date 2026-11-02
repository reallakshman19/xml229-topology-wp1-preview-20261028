"""Run existing short-drop tests with the per-test short memo explicitly OFF or ON.

Each test case has a distinct cache lifetime, so no fixture or refusal witness
can leak across tests. The normal default Python discovery remains unaffected.
"""
import argparse
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"converters"))
sys.path.insert(0,str(ROOT/"tests"))
from psi116_topology_resolver.short_memo import memo_session

FILES=[
    "test_short_elements.py",
    "test_short_length_basis.py",
    "test_short_namespace_replay.py",
    "test_uxml_short_drop_hub.py",
    "test_uxml_short_memo.py",
]
parser=argparse.ArgumentParser()
parser.add_argument("--enabled",choices=("on","off"),required=True)
args=parser.parse_args()
original=unittest.TestCase.run

def run_in_isolated_scope(self,result=None):
    with memo_session("test:"+self.id(),enabled=args.enabled=="on"):
        return original(self,result)

unittest.TestCase.run=run_in_isolated_scope
suite=unittest.TestSuite()
loader=unittest.TestLoader()
for filename in FILES:
    module=filename.removesuffix(".py")
    suite.addTests(loader.loadTestsFromName(module))
count=suite.countTestCases()
result=unittest.TextTestRunner(verbosity=2).run(suite)
print("SHORT_MEMO_ALL_SHORT_TESTS="+args.enabled+
      " total="+str(count)+" run="+str(result.testsRun)+
      " failures="+str(len(result.failures))+
      " errors="+str(len(result.errors))+
      " skips="+str(len(result.skipped)))
sys.exit(0 if result.wasSuccessful() else 1)
