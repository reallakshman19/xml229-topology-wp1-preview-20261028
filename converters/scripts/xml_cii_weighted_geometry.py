"""Preserve source weighted components within the existing standalone model."""
import math
import sys


def _text(element, name):
    return next((child.text or "" for child in element
                 if child.tag.split("}")[-1] == name), "").strip()


def _has_weight(element):
    weight = float(_text(element, "Weight") or "0")
    return _text(element, "Rigid") == "2" and math.isfinite(weight) and (
        weight > 0 or (weight == 0 and bool(_text(element, "XML229OriginalPhysicalId"))))


def prepare_weighted_node_numbers(root):
    """Allocate IDs only for weighted sentinels and their actual predecessor."""
    elements = [node for node in root.iter() if node.tag.split("}")[-1] == "Node"]
    numbers = [int(_text(node, "NodeNumber")) for node in elements if _text(node, "NodeNumber")]
    next_number = max([0, *numbers]) + 10
    source_numbers = {}
    predecessors = set()
    for branch in root.iter():
        if branch.tag.split("}")[-1] != "Branch":
            continue
        nodes = [node for node in branch if node.tag.split("}")[-1] == "Node"]
        needed = {i for i, node in enumerate(nodes) if _has_weight(node)}
        predecessors.update(id(nodes[i - 1]) for i in needed if i > 0)
        needed |= {i - 1 for i in needed if i > 0}
        for index in sorted(needed):
            node = nodes[index]
            number = int(_text(node, "NodeNumber"))
            if number > 0:
                continue
            source_numbers[id(node)] = number
            field = next(child for child in node if child.tag.split("}")[-1] == "NodeNumber")
            field.text = str(next_number)
            print(f"WEIGHT_COMPONENT_NODE_ID branch={_text(branch, 'Branchname')} "
                  f"source_node={number} runtime_node={next_number} reference={_text(node, 'ComponentRefNo')}", file=sys.stderr)
            next_number += 10
    return source_numbers, predecessors


def preserve_weighted_short_hop(kept, node, protected, length):
    """Keep nonzero physical component hops; never shift or sum their mass."""
    previous = kept[-1]
    arriving_weighted = node.rigid == 2 and math.isfinite(node.weight) and (
        node.weight > 0 or (node.weight == 0 and bool(node.xml229_original_physical_id)))
    previous_weighted = previous.rigid == 2 and math.isfinite(previous.weight) and (
        previous.weight > 0 or (previous.weight == 0 and bool(previous.xml229_original_physical_id)))
    if (arriving_weighted or node.weighted_component_start) and length > 0:
        return [*kept, node]
    if previous_weighted and not arriving_weighted and node.node_number in protected and length > 0:
        return [*kept, node]
    return None
