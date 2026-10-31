"""Owner local gate: export today's authorized PSI116 UXML edit ops.

python -m converters.psi116_topology_resolver.uxml_export_ops original.xml \
  authorized.ops.json [--uxml source.uxml.json | --xcu-root pinned-XCU]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from .transaction import TransactionPolicy
from .uxml_edit_ops import UxmlPatchError, compare_patch_to_direct, export_edit_ops
from .uxml_cli_common import load_pinned_uxml, print_difference


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("psi116", type=Path)
    parser.add_argument("ops_json", type=Path)
    parser.add_argument("--uxml", type=Path)
    parser.add_argument("--xcu-root", type=Path)
    parser.add_argument("--action-id", action="append", default=[],
                        help="Explicit currently PROPOSED auto-fix action; repeat for several")
    args = parser.parse_args(argv)
    try:
        if args.psi116.resolve() == args.ops_json.resolve():
            raise UxmlPatchError("UXML_ORIGINAL_OVERWRITE_FORBIDDEN")
        if args.uxml is not None and args.uxml.resolve() == args.ops_json.resolve():
            raise UxmlPatchError("UXML_INPUT_UXML_OVERWRITE_FORBIDDEN")
        uxml = load_pinned_uxml(args.psi116, uxml_file=args.uxml,
                                xcu_root=args.xcu_root)
        policy = TransactionPolicy(
            selected_action_ids=tuple(args.action_id),
            apply_all_safe=not bool(args.action_id),
        )
        ops = export_edit_ops(uxml, policy=policy, source_name=str(args.psi116))
        _, differences = compare_patch_to_direct(args.psi116, uxml, ops)
        if differences:
            return print_difference(differences)
        args.ops_json.write_text(json.dumps(ops, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")
        return print_difference([])
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired) as error:
        print("DIFFERENT")
        print("ERROR: " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
