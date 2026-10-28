#!/usr/bin/env python3
"""Apply the standalone XML->CII bend-radius publication contract.

Policy:
- OFF (default): remove BendRadius elements from enriched PSI116 XML. The CII
  runtime writer emits a zero bend-radius field so CAESAR can apply its own
  default bend radius.
- ON: publish BendRadius = 1.5 * effective outside diameter for ELBO endpoint 0.
  EffectiveOutsideDiameter is preferred when present; OutsideDiameter is the
  fallback. Missing/invalid OD while ON is blocking rather than guessed.
"""
from __future__ import annotations

from pathlib import Path
import math
import tempfile
import xml.etree.ElementTree as ET


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def _q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}" if namespace else name


def _child(parent: ET.Element, namespace: str, name: str) -> ET.Element | None:
    return parent.find(_q(namespace, name))


def _child_text(parent: ET.Element, namespace: str, name: str) -> str:
    node = _child(parent, namespace, name)
    return _text(node.text if node is not None else "")


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return _text(value).lower() in {"1", "true", "yes", "on"}


def publish_one_point_five_d(config: dict | None) -> bool:
    cfg = config if isinstance(config, dict) else {}
    nested = cfg.get("bendRadius") if isinstance(cfg.get("bendRadius"), dict) else {}
    value = nested.get("publishOnePointFiveD")
    if value is None:
        value = cfg.get("publishBendRadiusOnePointFiveD")
    return _truthy(value)


def _positive_float(value: object) -> float | None:
    try:
        number = float(_text(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _ensure_bend_radius(node: ET.Element, namespace: str) -> ET.Element:
    existing = _child(node, namespace, "BendRadius")
    if existing is not None:
        return existing
    created = ET.Element(_q(namespace, "BendRadius"))
    children = list(node)
    insert_at = len(children)
    for index, child in enumerate(children):
        if _local_name(child.tag) == "SIF":
            insert_at = index
            break
    node.insert(insert_at, created)
    return created


def _remove_bend_radius(node: ET.Element) -> int:
    removed = 0
    for child in list(node):
        if _local_name(child.tag) != "BendRadius":
            continue
        node.remove(child)
        removed += 1
    return removed


def _node_od(node: ET.Element, namespace: str) -> tuple[float | None, str]:
    effective = _positive_float(_child_text(node, namespace, "EffectiveOutsideDiameter"))
    if effective is not None:
        return effective, "EffectiveOutsideDiameter"
    raw = _positive_float(_child_text(node, namespace, "OutsideDiameter"))
    return (raw, "OutsideDiameter") if raw is not None else (None, "")


def apply_bend_radius_policy(
    input_path: Path,
    config: dict | None,
    output_path: Path | None = None,
) -> tuple[Path, dict]:
    source = Path(input_path)
    root = ET.parse(source).getroot()
    namespace = _namespace(root.tag)
    if namespace:
        ET.register_namespace("", namespace)

    enabled = publish_one_point_five_d(config)
    stats = {
        "schema": "xml-cii-bend-radius-policy/v1",
        "enabled": enabled,
        "removed": 0,
        "published": 0,
        "formula": "1.5*OD" if enabled else "CAESAR_DEFAULT",
        "rows": [],
    }

    for node in root.iter():
        if _local_name(node.tag) != "Node":
            continue
        component_type = _child_text(node, namespace, "ComponentType").upper()
        endpoint = _child_text(node, namespace, "Endpoint").upper()
        node_number = _child_text(node, namespace, "NodeNumber")

        # BendRadius is an ELBO bend property. Remove the source field from all
        # non-owning nodes in either policy so the enriched XML does not imply
        # a bend-radius authority where none is used by CII.
        if component_type != "ELBO" or endpoint not in {"0", ""}:
            stats["removed"] += _remove_bend_radius(node)
            continue

        if not enabled:
            removed = _remove_bend_radius(node)
            stats["removed"] += removed
            stats["rows"].append({
                "nodeNumber": node_number,
                "action": "OMIT",
                "basis": "toggle-off-caesar-default",
            })
            continue

        outside_diameter, od_source = _node_od(node, namespace)
        if outside_diameter is None:
            raise ValueError(
                f"BEND_RADIUS_1_5D_OD_UNRESOLVED: ELBO NodeNumber {node_number or '?'} "
                "has no positive EffectiveOutsideDiameter/OutsideDiameter."
            )
        radius = 1.5 * outside_diameter
        radius_node = _ensure_bend_radius(node, namespace)
        radius_node.text = f"{radius:.12g}"
        stats["published"] += 1
        stats["rows"].append({
            "nodeNumber": node_number,
            "action": "PUBLISH_1_5D",
            "outsideDiameter": outside_diameter,
            "outsideDiameterSource": od_source,
            "bendRadius": radius,
        })

    if output_path is None:
        fd, name = tempfile.mkstemp(prefix="xml_cii_bend_radius_", suffix=".xml")
        import os
        os.close(fd)
        target = Path(name)
    else:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)

    ET.ElementTree(root).write(target, encoding="utf-8", xml_declaration=True)
    return target, stats
