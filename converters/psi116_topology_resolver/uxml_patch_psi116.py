"""Owner local gate: patch exact original PSI116 using approved UXML ops.

python -m converters.psi116_topology_resolver.uxml_patch_psi116 \
  original.xml authorized.ops.json [--uxml source.uxml.json | --xcu-root pinned-XCU] \
  [--output corrected-copy.xml] [--validation validation.json]

Always benchmarks against the direct transaction before emitting a new file.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from .uxml_cli_common import load_pinned_uxml, print_difference
from .uxml_edit_ops import UxmlPatchError, compare_patch_to_direct


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("psi116", type=Path)
    parser.add_argument("ops_json", type=Path)
    parser.add_argument("--uxml", type=Path)
    parser.add_argument("--xcu-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validation", type=Path)
    args = parser.parse_args(argv)
    try:
        protected = {"original": args.psi116, "ops": args.ops_json}
        if args.uxml is not None:
            protected["uxml"] = args.uxml
        for output in (args.output, args.validation):
            if output is None:
                continue
            for name, source in protected.items():
                if output.resolve() == source.resolve():
                    reason = ("UXML_ORIGINAL_OVERWRITE_FORBIDDEN" if name == "original"
                              else "UXML_PROTECTED_INPUT_OVERWRITE_FORBIDDEN:" + name)
                    raise UxmlPatchError(reason)
        if (args.output is not None and args.validation is not None and
                args.output.resolve() == args.validation.resolve()):
            raise UxmlPatchError("UXML_OUTPUT_VALIDATION_PATH_COLLISION")
        uxml = load_pinned_uxml(args.psi116, uxml_file=args.uxml,
                                xcu_root=args.xcu_root)
        ops = json.loads(args.ops_json.read_text(encoding="utf-8"))
        patch, differences = compare_patch_to_direct(args.psi116, uxml, ops)
        if differences:
            return print_difference(differences)
        if patch is not None:
            if not patch.committed:
                print("DIFFERENT")
                print("NATIVE_TRANSACTION_REJECTED: " + ",".join(patch.reject_reasons))
                return 1
            if args.output is not None:
                args.output.write_bytes(patch.fixed_xml.encode("utf-8"))
            if args.validation is not None:
                args.validation.write_text(json.dumps(patch.validation_payload(),
                                                      indent=2, sort_keys=True) + "\n",
                                           encoding="utf-8")
        return print_difference([])
    except (OSError, ValueError, TypeError, KeyError,
            subprocess.TimeoutExpired) as error:
        print("DIFFERENT")
        print("ERROR: " + str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
