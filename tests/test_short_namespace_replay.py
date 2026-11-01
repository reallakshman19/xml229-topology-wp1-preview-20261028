"""Namespaced PSI116 source receipt identity must survive exact transaction replay."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "converters"))

from psi116_topology_resolver import ResolverConfig, resolve_psi116
from psi116_topology_resolver.short_elements import short_elements
from psi116_topology_resolver.transaction import TransactionPolicy, apply_topofix_transaction
from psi116_topology_resolver.lineage import (
    TopoFixLineageError, build_topofix_source_lineage, verify_topofix_pre_final,
)
from test_short_elements import fixture

PSI116_NS = "http://aveva.com/pipeStress116.xsd"


def namespaced_gasket():
    return fixture().replace(
        "<PipeStressExport>", f'<PipeStressExport xmlns="{PSI116_NS}">', 1
    )


def qualified_transaction():
    original = namespaced_gasket()
    config = ResolverConfig()
    resolved = resolve_psi116(original, config, source_name="namespaced-source.xml")
    row = next(
        item for item in short_elements(resolved.document, config)
        if item["eligible"] and item["componentType"] == "GASK"
    )
    request = {key: row[key] for key in ("id", "sourceSha256", "nodeKeys")}
    transaction = apply_topofix_transaction(
        resolved,
        policy=TransactionPolicy(
            selected_action_ids=(row["id"],),
            short_element_requests=(request,),
        ),
        config=config,
    )
    return original, row, resolved, transaction


class NamespacedShortElementReplay(unittest.TestCase):
    def test_first_receipt_matches_exact_replay(self):
        original, row, resolved, transaction = qualified_transaction()
        self.assertTrue(transaction.committed, transaction.reject_reasons)
        self.assertEqual(resolved.document.source_text, original)
        receipt = transaction.transaction_payload()
        removed = [
            operation["before"] for operation in receipt["operations"]
            if operation["operation"] == "REMOVE_SELECTED_SHORT_ELEMENT_RECORD"
        ]
        self.assertEqual(len(removed), 2)
        self.assertTrue(all(
            f'<Node xmlns="{PSI116_NS}">' in node
            for node in removed
        ), "First-pass and replay Node receipts must use the same namespace form")
        lineage = build_topofix_source_lineage(transaction)
        approval = verify_topofix_pre_final(
            original, transaction.fixed_xml, receipt,
            transaction.validation_payload(), lineage,
            reviewed_action_ids=(row["id"],),
        )
        self.assertEqual(approval["schema"], "psi116-topofix-prefinal-handoff/v1")
        self.assertEqual(lineage["counts"]["removedSelectedShortElementOccurrences"], 2)

    def test_tampered_tombstone_still_rejected(self):
        original, row, _resolved, transaction = qualified_transaction()
        self.assertTrue(transaction.committed, transaction.reject_reasons)
        receipt = transaction.transaction_payload()
        for operation in receipt["operations"]:
            if operation["operation"] == "REMOVE_SELECTED_SHORT_ELEMENT_RECORD":
                operation["before"] = operation["before"].replace("GASK", "VALV", 1)
                break
        lineage = build_topofix_source_lineage(transaction)
        with self.assertRaisesRegex(
            TopoFixLineageError, "TOPOFIX_LINEAGE_TRANSACTION_REPLAY_DRIFT"
        ):
            verify_topofix_pre_final(
                original, transaction.fixed_xml, receipt,
                transaction.validation_payload(), lineage,
                reviewed_action_ids=(row["id"],),
            )


if __name__ == "__main__":
    unittest.main()
