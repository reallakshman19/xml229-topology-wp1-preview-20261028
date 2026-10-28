"""Preview-only connection evidence regressions; no native CII or Weight masters."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))
from psi116_topology_resolver import resolve_psi116

def node(num, name, xyz):
    return f"""<Node><NodeNumber>{num}</NodeNumber><NodeName>{name}</NodeName>
    <ComponentType>PIPE</ComponentType><ComponentRefNo>{name}</ComponentRefNo>
    <Endpoint>1</Endpoint><Position>{xyz}</Position></Node>"""

def branch(label, ns):
    return "<Branch><Branchname>" + label + "</Branchname>" + "".join(ns) + "</Branch>"

def doc(branches):
    return '<?xml version="1.0"?><PipeStressExport>' + "".join(branches) + "</PipeStressExport>"

def example(join="201.4 0 0"):
    return doc([
        branch("A",[
            node(10,"P1","0 0 0"),node(20,"P1","100 0 0"),
            node(30,"P2","102 0 0"),node(40,"P2","200 0 0")]),
        branch("B",[
            node(50,"P3",join),node(60,"P3","280 0 0")]),
    ])

class GapEvidence(unittest.TestCase):
    def test_intra_branch_near_miss_is_source_qualified_review_not_auto(self):
        result=resolve_psi116(example())
        matches=[f for f in result.findings if f.code=="NEAR_MISS_PIPE_JOINT"]
        self.assertEqual(len(matches),1)
        f=matches[0]
        self.assertEqual(set(f.node_keys),{"B0:N20:S1","B0:N30:S2"})
        self.assertAlmostEqual(f.length_mm,2.0)
        self.assertEqual(f.severity,"WARNING")
        self.assertFalse(f.blocking)
        self.assertEqual(f.details["certainty"],"POSSIBLE_GAP_REQUIRES_REVIEW")
        action=next(a for a in result.fix_actions if f.finding_id in a.finding_ids)
        self.assertEqual(action.disposition,"REVIEW_CONNECTION")
        self.assertEqual(action.proposed_changes,())
        self.assertFalse(action.blockers)

    def test_branch_ends_nearly_meet_but_are_not_automatically_joined(self):
        result=resolve_psi116(example())
        matches=[f for f in result.findings if f.code=="NEAR_MISS_BRANCH_ENDS"]
        self.assertEqual(len(matches),1)
        self.assertEqual(set(matches[0].node_keys),{"B0:N40:S3","B1:N50:S0"})
        self.assertAlmostEqual(matches[0].details["gapMm"],1.4)
        self.assertEqual(matches[0].details["connectionAuthority"],"NO_EXPLICIT_BRANCH_LINK")
        self.assertEqual(matches[0].details["autofixAuthorized"],False)

    def test_unmatched_branch_ends_are_unverified_not_confirmed_defects(self):
        result=resolve_psi116(example())
        unmatched=[f for f in result.findings if f.code=="BRANCH_END_UNVERIFIED"]
        self.assertGreaterEqual(len(unmatched),2)
        self.assertTrue(all(f.severity=="INFO" and not f.blocking for f in unmatched))
        self.assertTrue(all(f.details["certainty"]=="TERMINATION_INTENT_UNKNOWN" for f in unmatched))
        self.assertTrue(all(f.details["autofixAuthorized"] is False for f in unmatched))

    def test_exact_alignment_not_reported_as_near_miss_or_verified_connection(self):
        result=resolve_psi116(example(join="200 0 0"))
        self.assertFalse(any(f.code=="NEAR_MISS_BRANCH_ENDS" for f in result.findings))
        self.assertFalse(any(f.code=="BRANCH_END_UNVERIFIED" and "B1:N50:S0" in f.node_keys for f in result.findings))
        # Exact position does not authorize a cross-branch PIPE connection:
        self.assertTrue(any(f.code=="COINCIDENT_NODE_IDENTITY_AMBIGUOUS" for f in result.findings))

    def test_long_unreferenced_separation_cannot_be_falsely_called_a_gap(self):
        result=resolve_psi116(example(join="240 0 0"))
        self.assertFalse(any(f.code=="NEAR_MISS_BRANCH_ENDS" for f in result.findings))
        # Without connection intent, this is at most an unverified branch end.
        self.assertTrue(any(f.code=="BRANCH_END_UNVERIFIED" for f in result.findings))

    def test_no_pipe_snap_or_native_output_in_findings_or_action_plan(self):
        result=resolve_psi116(example())
        for a in result.fix_actions:
            if a.disposition=="REVIEW_CONNECTION":
                self.assertFalse(a.proposed_changes)
                self.assertEqual(a.confidence,0.0)
        self.assertFalse(result.fix_plan_payload(__import__(
            "psi116_topology_resolver",fromlist=["ResolverConfig"]).ResolverConfig()
        )["sourceXmlMutated"])

if __name__=="__main__":
    unittest.main()
