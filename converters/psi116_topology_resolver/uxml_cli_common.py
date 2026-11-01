"""Shared CLI custody loader: XCU owns the reader; this repo never copies it."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .uxml_edit_ops import UxmlPatchError


def load_pinned_uxml(original: Path, *, uxml_file: Path | None = None,
                     xcu_root: Path | None = None) -> dict:
    if uxml_file is not None:
        value = json.loads(uxml_file.read_text(encoding="utf-8"))
    else:
        root = xcu_root or (Path(os.environ["XCU_UXML_ROOT"])
                            if os.environ.get("XCU_UXML_ROOT") else None)
        if root is None or not (root / "tools" / "psi116-to-uxml.mjs").is_file():
            raise UxmlPatchError(
                "XCU_PINNED_READER_REQUIRED: supply --uxml or --xcu-root "
                "(CI pinned checkout via .github/workflows/uxml-s2-patch.yml).")
        process = subprocess.run(
            ["node", str(root / "tools" / "psi116-to-uxml.mjs"), str(original.resolve())],
            cwd=root, capture_output=True, text=True, timeout=60, check=False)
        if process.returncode:
            raise UxmlPatchError("XCU_PSI116_READER_FAILED: " +
                                 (process.stderr.strip() or str(process.returncode)))
        value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise UxmlPatchError("UXML_DOCUMENT_REQUIRED")
    return value


def print_difference(differences: list[str]) -> int:
    if differences:
        print("DIFFERENT")
        for line in differences:
            print(line)
        return 1
    print("EQUAL")
    return 0
