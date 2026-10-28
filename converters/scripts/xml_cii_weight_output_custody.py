"""Audit existing CII owners before publication; never transfer component mass."""
from collections import defaultdict
import math
import xml.etree.ElementTree as ET


def _text(element, name):
    return next((child.text or "" for child in element
                 if child.tag.split("}")[-1] == name), "").strip()


def _identity(branch, number, reference, endpoint, component, position):
    return (branch, number, reference.strip(), endpoint, component.upper(), position)


def audit_rigid_weight_owners(xml_path, model):
    """Return unresolved positive Rigid=2 weights using the existing to-node owner."""
    owners = defaultdict(list)
    for edge in model.rigid_edges:
        node = edge.to_node
        source_number = node.source_node_number if node.source_node_number is not None else node.node_number
        key = _identity(edge.branch_name, source_number, node.component_ref_no,
                        node.endpoint, node.component_type, node.position)
        owners[key].append(node.weight)
    unresolved = []
    source_keys = set()
    for branch in ET.parse(xml_path).getroot().iter():
        if branch.tag.split("}")[-1] != "Branch":
            continue
        name = _text(branch, "Branchname")
        for node in branch:
            if node.tag.split("}")[-1] != "Node" or _text(node, "Rigid") != "2":
                continue
            weight = float(_text(node, "Weight") or "0")
            if not math.isfinite(weight):
                raise ValueError(f"CII_WEIGHT_INVALID: {name}::{_text(node, 'NodeNumber')}")
            if weight <= 0:
                continue
            number = int(_text(node, "NodeNumber"))
            endpoint = int(_text(node, "Endpoint")) if _text(node, "Endpoint") else None
            key = _identity(name, number, _text(node, "ComponentRefNo"), endpoint,
                            _text(node, "ComponentType"), tuple(map(float, _text(node, "Position").split())))
            if key in source_keys:
                raise ValueError(f"CII_WEIGHT_OWNER_AMBIGUOUS: duplicate source component {name}::{number}")
            source_keys.add(key)
            values = owners.get(key, [])
            if len(values) != 1 or values[0] != weight:
                unresolved.append({"branch": name, "nodeNumber": number, "weight": weight,
                                   "reference": _text(node, "ComponentRefNo"), "ownerCount": len(values)})
    return unresolved


def require_rigid_weight_owners(xml_path, model):
    unresolved = audit_rigid_weight_owners(xml_path, model)
    if unresolved:
        details = "; ".join(f"{row['branch']}::{row['nodeNumber']} ({row['weight']} kg)"
                            for row in unresolved)
        raise ValueError(f"CII_WEIGHT_OWNER_UNRESOLVED: {len(unresolved)} weighted components "
                         f"lack one matching CII owner. CII withheld; enriched XML retained. {details}")
