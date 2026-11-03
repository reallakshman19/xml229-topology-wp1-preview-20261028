"""Public dense A6b fixture: adjacent owners within branches, distant branches."""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"converters"))
import psi116_topology_resolver.short_batch as batch
from psi116_topology_resolver import ResolverConfig,resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from test_port_policy import doc,node
from test_uxml_psi116_s1 import verified_synthetic
from test_short_batch_engine import owner_policy

def dense_fixture(branches=24,each=4):
    """24 branch clusters x four independent-looking, adjacent short owners."""
    all_branches=[]
    for i in range(branches):
        pieces=[]
        for j in range(each):
            x=float(3000*i+189*j)
            k=1000*(i+1)+100*j
            pieces.append(
                node(k+10,"PIPE",f"PIPE-{i}-{j}",1,f"{x:g} 0 0")+
                node(k+20,"PIPE",f"PIPE-{i}-{j}",2,f"{x+100:g} 0 0")+
                node(-1,"GASK",f"SHORT-{i:03d}-{j}",1,f"{x+100:g} 0 0")+
                node(k+30,"RIGID",f"SHORT-{i:03d}-{j}",2,f"{x+103:g} 0 0")+
                node(-1,"FLAN",f"FLAN-{i}-{j}",1,f"{x+103:g} 0 0")+
                node(k+40,"RIGID",f"FLAN-{i}-{j}",2,f"{x+189:g} 0 0"))
        all_branches.append("".join(pieces))
    return verified_synthetic(doc(*all_branches))


def valve_chain_fixture():
    """Public B0 -> B1 finite VALV -> B2 cross-branch closure regression."""
    b0=(node(10,"PIPE","A-PIPE",1,"0 0 0")+
        node(20,"PIPE","A-PIPE",2,"100 0 0")+
        node(-1,"GASK","SHORT-A",1,"100 0 0")+
        node(30,"RIGID","SHORT-A",2,"103 0 0")+
        node(-1,"FLAN","A-FLAN",1,"103 0 0")+
        node(40,"RIGID","A-FLAN",2,"189 0 0"))
    b1=(node(20,"VALV","BRIDGE-VALVE",1,"100 0 0")+
        node(50,"VALV","BRIDGE-VALVE",2,"100 500 0"))
    b2=(node(50,"PIPE","B-PIPE",1,"100 500 0")+
        node(60,"PIPE","B-PIPE",2,"200 500 0")+
        node(-1,"GASK","SHORT-B",1,"200 500 0")+
        node(70,"RIGID","SHORT-B",2,"203 500 0")+
        node(-1,"FLAN","B-FLAN",1,"203 500 0")+
        node(80,"RIGID","B-FLAN",2,"289 500 0"))
    return verified_synthetic(doc(b0,b1,b2))


def close_cross_branch_fixture():
    """Distinct branches 20mm apart, outside exact contacts, inside 25mm."""
    def branch(offset,prefix,base):
        return (node(base+10,"PIPE",prefix+"-PIPE",1,f"0 {offset} 0")+
                node(base+20,"PIPE",prefix+"-PIPE",2,f"100 {offset} 0")+
                node(-1,"GASK","SHORT-"+prefix,1,f"100 {offset} 0")+
                node(base+30,"RIGID","SHORT-"+prefix,2,f"103 {offset} 0")+
                node(-1,"FLAN",prefix+"-FLAN",1,f"103 {offset} 0")+
                node(base+40,"RIGID",prefix+"-FLAN",2,f"189 {offset} 0"))
    return verified_synthetic(doc(branch(0,"A",0),branch(20,"B",100)))


def eligible_owners(before,cfg,n):
    rows=[row for row in short_elements(before.document,cfg)
          if row["componentRefNo"].startswith("SHORT-") and row["eligible"]]
    if len(rows)<n:raise AssertionError("DENSE_ELIGIBLE_OWNERS:%d<%d"%(len(rows),n))
    return rows[:n]

def contiguous_plan(before,owners,cfg,maximum=32):
    groups=[];current=[];zones=[]
    for row in owners:
        zone=batch.owner_footprint(before,row,cfg)
        if current and (len(current)>=maximum or
                        any(zone.intersection(z) for z in zones)):
            groups.append(tuple(current));current=[];zones=[]
        current.append(row["id"]);zones.append(zone)
    if current:groups.append(tuple(current))
    return tuple(groups)

def size_histogram(groups):
    return dict(sorted(Counter(map(len,groups)).items()))

def conflict_reasons(before,owners,cfg):
    zones=[batch.owner_footprint(before,row,cfg) for row in owners]
    counts=Counter()
    for i,row in enumerate(owners):
        for j in range(i):
            if not zones[i].intersection(zones[j]):continue
            counts["conflictingPairs"]+=1
            earlier=owners[j]
            if row["branchIndex"]==earlier["branchIndex"]:
                counts["sharedOwnerBranch"]+=1
                here=set(row["nodeKeys"])|{row["leftKey"],row["rightKey"]}
                prior=set(earlier["nodeKeys"])|{
                    earlier["leftKey"],earlier["rightKey"]}
                counts["sharedNeighbourRecord" if here.intersection(prior)
                       else "sameBranchWithoutDirectKeyShare"]+=1
            else:
                counts["crossBranchAliasOr25mmContact"]+=1
    return dict(sorted(counts.items()))

class DenseGraphPlanning(unittest.TestCase):
    def setUp(self):self.cfg=ResolverConfig()
    def test_dense_eight_owner_group_layers_and_reason_counts(self):
        before=resolve_psi116(dense_fixture(2),self.cfg)
        owners=eligible_owners(before,self.cfg,8)
        ids=[row["id"] for row in owners]
        previous=contiguous_plan(before,owners,self.cfg)
        planned=batch.plan_short_groups(before,ids,self.cfg)
        self.assertEqual(len(planned),4)
        self.assertEqual([len(g) for g in planned],[2,2,2,2])
        self.assertLess(len(planned),len(previous))
        for group in planned:
            batch.assert_independent(
                before,[owners[ids.index(x)] for x in group],self.cfg)
        print("A6B_DENSE_GREEN:old="+str(size_histogram(previous))+
              ":new="+str(size_histogram(planned))+
              ":reasons="+str(conflict_reasons(before,owners,self.cfg)))


    def test_valve_chain_transitive_cross_branch_footprint_and_guard_mutants(self):
        source=valve_chain_fixture()
        before=resolve_psi116(source,self.cfg)
        owners=eligible_owners(before,self.cfg,2)
        ids=[r["id"] for r in owners]
        zones=[batch.owner_footprint(before,r,self.cfg) for r in owners]
        self.assertIn("B1:N50:S1",zones[0],"B0 closure owns VALV second port")
        self.assertIn("B2:N50:S0",zones[0],"B0 closure follows VALV into B2")
        self.assertTrue(zones[0]&zones[1])
        planned=batch.plan_short_groups(before,ids,self.cfg)
        self.assertEqual(planned,((ids[0],),(ids[1],)))
        print("A6B_R1_GREEN:valve-chain-transitive-closure-separated=PASS")
        with patch.object(batch,"_expand_owner_closure_keys",
                          side_effect=lambda before,seed,config:set(seed)):
            broken=batch.plan_short_groups(before,ids,self.cfg)
            with self.assertRaises(AssertionError) as red:
                self.assertEqual(broken,planned,
                    "CROSS_BRANCH_CLOSURE_RECURSION_MUTANT_UNSAFE_GROUPING")
            # With the planner deliberately damaged, the runtime edited-key
            # guard must refuse the unsafe group before it can publish bytes.
            with self.assertRaisesRegex(batch.ShortBatchRefused,
                     "SHORT_BATCH_OWNER_WRITE_OUTSIDE_FOOTPRINT"):
                batch.apply_independent_short_batch(
                    before,policy=owner_policy(before,ids,self.cfg),
                    config=self.cfg)
        print("A6B_R1_RED:closure-recursion-removed:AssertionError:"+
              str(red.exception).splitlines()[-1])
        print("A6B_R1_GREEN:runtime-cross-branch-edit-guard=PASS")

    def test_25mm_cross_branch_contacts_are_not_omitted(self):
        source=close_cross_branch_fixture()
        before=resolve_psi116(source,self.cfg)
        owners=eligible_owners(before,self.cfg,2)
        ids=[r["id"] for r in owners]
        safe=batch.plan_short_groups(before,ids,self.cfg)
        self.assertEqual(safe,((ids[0],),(ids[1],)))
        print("A6B_R1_GREEN:twenty-mm-cross-branch-contact-separated=PASS")
        def missing_contacts(before,row,config):
            branch=before.document.branches[row["branchIndex"]]
            return frozenset(n.key for n in branch.nodes)
        with patch.object(batch,"owner_footprint",side_effect=missing_contacts):
            unsafe=batch.plan_short_groups(before,ids,self.cfg)
        with self.assertRaises(AssertionError) as red:
            self.assertEqual(unsafe,safe,
                "CROSS_BRANCH_25MM_CONTACT_MUTANT_UNSAFE_GROUPING")
        print("A6B_R1_RED:25mm-contacts-removed:AssertionError:"+
              str(red.exception).splitlines()[-1])

    def test_overlapping_owner_admission_mutant_red(self):
        before=resolve_psi116(dense_fixture(2),self.cfg)
        owners=eligible_owners(before,self.cfg,8)
        ids=[r["id"] for r in owners]
        correct=batch.plan_short_groups(before,ids,self.cfg)
        self.assertEqual([len(x) for x in correct],[2,2,2,2])
        print("A6B_DENSE_GREEN:overlapping-owners-separated=PASS")
        # Execute the REAL graph planner with its actual source-footprint
        # function removed. The mutated selection must move conflicting
        # same-branch owners into the SAME group; original control stays
        # separated. Do not kill a tautological set-intersection assertion.
        with patch("psi116_topology_resolver.short_batch.owner_footprint",
                   return_value=frozenset()):
            broken=batch.plan_short_groups(before,ids,self.cfg)
        with self.assertRaises(AssertionError) as red:
            self.assertEqual(broken,correct,
                "A6B_DENSE_MUTANT_OVERLAP_SAME_LAYER")
        self.assertIn(ids[0],broken[0])
        self.assertIn(ids[1],broken[0])
        print("A6B_DENSE_RED:planner-footprint-removed:AssertionError:"+
              str(red.exception).splitlines()[-1])
        with self.assertRaisesRegex(batch.ShortBatchRefused,
                                    "SHORT_BATCH_INDEPENDENCE_CONFLICT"):
            batch.apply_independent_short_batch(
                before,policy=owner_policy(before,ids[:2],self.cfg),
                config=self.cfg)
