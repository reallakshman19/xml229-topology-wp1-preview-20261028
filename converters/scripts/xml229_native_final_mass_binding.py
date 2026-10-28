"""Strict GC-PW Final -> native XML -> actual CII RIGID mass binding.

Not a release oracle: an *independently sourced* G5 original-to-native-child
geometry/lineage witness and actual Owner basis remain necessary. This module
never accepts a proposal or guesses an original physical owner.
"""
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

SCHEMA = "XML229.NativeFinalPhysicalPacket.v1"
LINEAGE_TAG = "XML229OriginalPhysicalId"
LINEAGE_STAGE = "XML229NativeLineageBasis"



class NativeMassError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(ok, code):
    if not ok:
        raise NativeMassError(code)


def tag(element):
    return element.tag.rsplit("}", 1)[-1]


def child(element, wanted):
    return next((n for n in element if tag(n) == wanted), None)


def txt(element, wanted):
    n = child(element, wanted)
    return (n.text or "").strip() if n is not None else ""


def branches(root):
    return [node for node in root.iter() if tag(node) == "Branch"]


def nodes(branch):
    return [n for n in branch if tag(n) == "Node"]


def signature(node):
    return json.dumps([txt(node, "ComponentType"), txt(node, "ComponentRefNo"),
                       txt(node, "Endpoint"), txt(node, "NodeName")],
                      separators=(",", ":"), ensure_ascii=False)


def identity(node):
    return (signature(node), txt(node, "NodeNumber"), txt(node, "Position"))


def parse_bytes(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise NativeMassError("ENGINE_XML_MALFORMED") from None
    require(tag(root) == "PipeStressExport", "ENGINE_XML_NOT_PIPESTRESSEXPORT")
    return root



def _normalized_position(text):
    """A geometry coordinate is a finite numeric triple, not formatted text."""
    try:
        values = tuple(float(v) for v in text.split())
    except ValueError:
        raise NativeMassError("NATIVE_GEOMETRY_POSITION_INVALID") from None
    require(len(values) == 3 and all(math.isfinite(v) for v in values),
            "NATIVE_GEOMETRY_POSITION_INVALID")
    return values


def _assert_preserved_node_connectivity(original_groups, native_groups):
    """Verify node-number remapping is a bijection across branch occurrences.

    Connected repeated source IDs stay connected. Separate source IDs must
    not be accidentally merged by post-acceptance renumbering.
    """
    old_to_new, new_to_old = {}, {}
    for before, after in zip(original_groups, native_groups):
        require(len(before) == len(after),
                "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
        for old, new in zip(before, after):
            require(bool(old) and bool(new),
                    "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
            if old in old_to_new:
                require(old_to_new[old] == new,
                        "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
            if new in new_to_old:
                require(new_to_old[new] == old,
                        "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
            old_to_new[old] = new
            new_to_old[new] = old


def _xml_geometry_row(node):
    """Only topology/ownership fields; process and mass fields may vary.

    NodeNumber is a label, not an ownership key: provenance survives
    topology-neutral renumbering. Bend radius and process values are also
    permitted to be enriched; creation, deletion, relocation or retyping
    of native physical nodes is not.
    """
    return (txt(node, "ComponentType").upper(), txt(node, "ComponentRefNo"),
            txt(node, "Endpoint"), txt(node, "NodeName"),
            txt(node, "Rigid"), _normalized_position(txt(node, "Position")),
            txt(node, "ElementLengthMm"))


def assert_preaccepted_geometry_unchanged(original_path, engine_input_path):
    """Every geometric split/cleanup must precede source-bound Final weights.

    This check is before accepted masses are written. The original XML hash
    is already part of the immutable Worker InputBasis. No child mass
    allocation, source owner interpolation or automatically relaxed HOLD.
    """
    original = parse_bytes(Path(original_path).read_bytes())
    engine = parse_bytes(Path(engine_input_path).read_bytes())
    expected, actual = branches(original), branches(engine)
    require(len(expected) == len(actual),
            "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
    source_numbers, engine_numbers = [], []
    for src, dst in zip(expected, actual):
        require(txt(src, "Branchname") == txt(dst, "Branchname"),
                "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
        before, after = nodes(src), nodes(dst)
        require(len(before) == len(after),
                "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
        source_numbers.append([txt(row, "NodeNumber") for row in before])
        engine_numbers.append([txt(row, "NodeNumber") for row in after])
        for first, second in zip(before, after):
            require(_xml_geometry_row(first) == _xml_geometry_row(second),
                    "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
    _assert_preserved_node_connectivity(source_numbers, engine_numbers)
    return True


def assert_native_model_geometry_unchanged(original_path, document, model):
    """The parsed native graph must also match the preapproved XML geometry.

    The engine parser may collapse small segments or exclude invalid node
    numbers AFTER the XML input check. Those are likewise not allowed after
    weights were accepted; validation must inspect the actual graph.
    """
    source = parse_bytes(Path(original_path).read_bytes())
    src_branches = branches(source)
    require(len(src_branches) == len(document.branches),
            "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
    expected_edges = 0
    source_numbers, model_numbers = [], []
    for original, native in zip(src_branches, document.branches):
        before = nodes(original)
        require(txt(original, "Branchname") == native.branch_name and
                len(before) == len(native.nodes),
                "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
        expected_edges += max(0, len(before) - 1)
        source_numbers.append([txt(row, "NodeNumber") for row in before])
        model_numbers.append([str(row.node_number) for row in native.nodes])
        for old, new in zip(before, native.nodes):
            old_shape = _xml_geometry_row(old)
            new_shape = (new.component_type, new.component_ref_no,
                         str(new.endpoint) if new.endpoint is not None else "",
                         new.node_name,
                         str(new.rigid) if new.rigid is not None else "",
                         tuple(new.position), txt(old, "ElementLengthMm"))
            require(old_shape == new_shape,
                    "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
    _assert_preserved_node_connectivity(source_numbers, model_numbers)
    require(len(model.edges) == expected_edges,
            "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
    # Native graph edges must remain in the same per-branch source order.
    intended = [(branch.branch_name, left.node_number, right.node_number)
                for branch in document.branches
                for left, right in zip(branch.nodes, branch.nodes[1:])]
    actual = [(edge.branch_name, edge.from_node.node_number,
               edge.to_node.node_number) for edge in model.edges]
    require(intended == actual,
            "NATIVE_GEOMETRY_CHANGED_AFTER_WEIGHT_ACCEPTANCE")
    return True


def read_packet(path, xml_path):
    try:
        packet = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise NativeMassError("NATIVE_PACKET_INVALID") from None
    require(isinstance(packet, dict) and packet.get("schema") == SCHEMA,
            "NATIVE_PACKET_SCHEMA")
    original_bytes = Path(xml_path).read_bytes()
    require(packet.get("sourceXmlSha256") == hashlib.sha256(original_bytes).hexdigest(),
            "ORIGINAL_SOURCE_SHA_DRIFT")
    require(isinstance(packet.get("basisId"), str) and
            len(packet["basisId"]) == 64 and
            isinstance(packet.get("finalIntentSha256"), str) and
            len(packet["finalIntentSha256"]) == 64,
            "NATIVE_FINAL_INTENT_REQUIRED")
    physicals = packet.get("components")
    require(isinstance(physicals, list) and
            len(physicals) == packet.get("physicalCount") and len(physicals) > 0,
            "NATIVE_FINAL_POPULATION_INCOMPLETE")
    return packet, parse_bytes(original_bytes)


def _semantic_xml(element):
    """Canonical semantic XML: ignore formatting whitespace, not XML fields.

    A finalized geometry can only REMOVE reviewed-irrelevant Node elements.
    It may not rewrite wall thickness, material, restraints, positions or any
    other original source facts while retaining the same physical IDs.
    """
    return (tag(element), tuple(sorted(element.attrib.items())),
            (element.text or "").strip(),
            tuple(_semantic_xml(c) for c in element if isinstance(c.tag, str)))


def _validate_finalized_geometry(packet, source):
    """Challenge the exact pre-acceptance Worker XML and original ordinal map.

    A finalized snapshot may REMOVE original nodes, but may not change any
    retained source component or invent new geometry. Accepted weights are
    indexed by original ordinals and must all survive this reduction.
    """
    final = packet.get("finalizedGeometry")
    if final is None:
        require(not packet.get("sourceGenerationId"),
                "NATIVE_FINALIZED_GEOMETRY_REQUIRED")
        return source, None
    require(isinstance(final, dict) and
            final.get("schema") == "XML229.FinalizedWeightGeometry.v1" and
            final.get("basisId") == packet.get("basisId") and
            final.get("sourceXmlSha256") == packet.get("sourceXmlSha256") and
            isinstance(final.get("xmlText"), str) and
            len(final["xmlText"]) <= 32 * 1024 * 1024 and
            isinstance(final.get("sha256"), str) and
            final["sha256"] == hashlib.sha256(
                final["xmlText"].encode("utf-8")).hexdigest(),
            "NATIVE_FINALIZED_GEOMETRY_SHA_DRIFT")
    snapshot = parse_bytes(final["xmlText"].encode("utf-8"))
    originals, selected = branches(source), branches(snapshot)
    retained = final.get("retainedSourceOrdinalsByBranch")
    require(isinstance(retained, list) and len(originals) == len(selected)
            and len(retained) == len(originals),
            "NATIVE_FINALIZED_GEOMETRY_CENSUS_DRIFT")
    # Verify the Worker-assigned IDs by recomputing their exact deterministic
    # original-ordinal mapping. Only nonpositive source placeholders can change.
    # Never merge an original positive connected node or invent a new one.
    assigned = final.get("assignedNodeNumbers", [])
    require(isinstance(assigned, list),
            "NATIVE_FINALIZED_NODE_ID_MAP_INVALID")
    originals_all = [node for branch in originals for node in nodes(branch)]
    raw_numbers = [txt(node, "NodeNumber") for node in originals_all]
    try:
        integer_ids = [int(v) for v in raw_numbers]
    except ValueError:
        raise NativeMassError("NATIVE_FINALIZED_NODE_ID_MAP_INVALID") from None
    require(all(str(i) == raw or
                raw.strip().lstrip("+").lstrip("0") == str(i)
                for i, raw in zip(integer_ids, raw_numbers)),
            "NATIVE_FINALIZED_NODE_ID_MAP_INVALID")
    next_id = max([0, *(i for i in integer_ids if i > 0)]) + 10
    expected_assignments = []
    normalized = {}
    for bi, (src, ordinals) in enumerate(zip(originals, retained)):
        src_nodes = nodes(src)
        for original_index in ordinals:
            require(type(original_index) is int and
                    0 <= original_index < len(src_nodes),
                    "NATIVE_FINALIZED_GEOMETRY_ORDINAL_DRIFT")
            raw = txt(src_nodes[original_index], "NodeNumber")
            if int(raw) <= 0:
                require(next_id <= 2**31-1,
                        "NATIVE_FINALIZED_NODE_ID_MAP_INVALID")
                expected_assignments.append({
                    "branchOccurrenceIndex": bi,
                    "sourceNodeOrdinal": original_index,
                    "sourceNodeNumber": raw,
                    "finalNodeNumber": next_id,
                })
                normalized[(bi, original_index)] = next_id
                next_id += 10
    require(assigned == expected_assignments,
            "NATIVE_FINALIZED_NODE_ID_MAP_DRIFT")
    # Independently regenerate the only supported non-original rigid
    # classifications: an EXISTING positive-span 1->2 element, with the same
    # VALV/FLAN/INST reference. The source must have no Rigid authority on
    # the endpoint; post-Final classifications are forbidden.
    expected_promotions = []
    promoted = set()
    for bi, (orig_branch, approved_branch, ordinals) in enumerate(
            zip(originals, selected, retained)):
        source_nodes = nodes(orig_branch)
        final_nodes = nodes(approved_branch)
        for i in range(len(final_nodes) - 1):
            oi, oj = ordinals[i:i+2]
            left, right = source_nodes[oi], source_nodes[oj]
            typ = txt(left, "ComponentType").upper()
            ref = "".join(txt(left, "ComponentRefNo").lstrip("=").split()).upper()
            other_ref = "".join(txt(right, "ComponentRefNo").lstrip("=").split()).upper()
            if (typ not in ("VALV", "FLAN") or not ref or
                    typ != txt(right, "ComponentType").upper() or
                    ref != other_ref or
                    (txt(left, "Endpoint"), txt(right, "Endpoint")) != ("1", "2") or
                    txt(right, "Rigid") or
                    txt(left, "ConnectionType") or txt(right, "ConnectionType")):
                continue
            start = _normalized_position(txt(left, "Position"))
            end = _normalized_position(txt(right, "Position"))
            length = math.dist(start, end)
            if length <= 6:
                continue
            expected_promotions.append({
                "branchOccurrenceIndex": bi,
                "firstSourceNodeOrdinal": oi,
                "secondSourceNodeOrdinal": oj,
                "componentType": typ,
                "componentRefNo": ref,
                "distanceMm": length,
            })
            promoted.add((bi, oj))
    claimed_promotions = final.get("rigidEdgePromotions", [])
    require(isinstance(claimed_promotions, list) and
            len(claimed_promotions) == len(expected_promotions),
            "NATIVE_PREACCEPTANCE_RIGID_EDGE_DRIFT")
    for claimed, expected in zip(claimed_promotions, expected_promotions):
        require(isinstance(claimed, dict) and
                claimed.keys() == expected.keys() and
                all(claimed[k] == v for k, v in expected.items()
                    if k != "distanceMm") and
                type(claimed["distanceMm"]) in (int, float) and
                math.isfinite(claimed["distanceMm"]) and
                math.isclose(claimed["distanceMm"], expected["distanceMm"],
                             rel_tol=1e-12, abs_tol=1e-8),
                "NATIVE_PREACCEPTANCE_RIGID_EDGE_DRIFT")
    lookup = {}
    total = 0
    for bi, (src, dst, ordinals) in enumerate(zip(originals, selected, retained)):
        old_nodes, final_nodes = nodes(src), nodes(dst)
        total += len(old_nodes)
        require(txt(src, "Branchname") == txt(dst, "Branchname") and
                isinstance(ordinals, list) and len(ordinals) == len(final_nodes),
                "NATIVE_FINALIZED_GEOMETRY_CENSUS_DRIFT")
        last = -1
        for source_index, final_node in zip(ordinals, final_nodes):
            require(type(source_index) is int and
                    last < source_index < len(old_nodes),
                    "NATIVE_FINALIZED_GEOMETRY_ORDINAL_DRIFT")
            original = old_nodes[source_index]
            immutable = ("ComponentType", "ComponentRefNo", "Endpoint",
                         "NodeName", "Position",
                         "ElementLengthMm", "Weight", "ConnectionType")
            expected_rigid = ("2" if (bi, source_index) in promoted
                              else txt(original, "Rigid"))
            require(all(txt(original, key) == txt(final_node, key)
                        for key in immutable) and
                    txt(final_node, "Rigid") == expected_rigid and
                    txt(final_node, "NodeNumber") ==
                    str(normalized.get((bi, source_index),
                                       txt(original, "NodeNumber"))),
                    "NATIVE_FINALIZED_GEOMETRY_SOURCE_DRIFT")
            lookup[(bi, source_index)] = final_node
            last = source_index
    require(total == final.get("originalNodeCount"),
            "NATIVE_FINALIZED_GEOMETRY_CENSUS_DRIFT")
    # Compare the ENTIRE cleaned source XML, not a small geometry field list.
    # No other pre-acceptance material, restraints or XML node fields can drift.
    expected = parse_bytes(ET.tostring(source, encoding="utf-8"))
    for bi, (branch, ordinals) in enumerate(zip(branches(expected), retained)):
        keep = set(ordinals)
        for original_index, node in enumerate(nodes(branch)):
            if original_index not in keep:
                branch.remove(node)
            else:
                if (bi, original_index) in normalized:
                    child(node, "NodeNumber").text = str(
                        normalized[(bi, original_index)])
                if (bi, original_index) in promoted:
                    namespace = (node.tag.rsplit("}", 1)[0] + "}"
                                 if "}" in node.tag else "")
                    ET.SubElement(node, namespace + "Rigid").text = "2"
    require(_semantic_xml(expected) == _semantic_xml(snapshot),
            "NATIVE_FINALIZED_GEOMETRY_SOURCE_DRIFT")
    require(child(snapshot, LINEAGE_STAGE) is None and
            not any(child(n, LINEAGE_TAG) is not None
                    for branch in selected for n in nodes(branch)),
            "NATIVE_UNTRUSTED_LINEAGE_TAG")
    return snapshot, lookup


def _physical_component_key(node):
    """Physical item identity requires a real reference, type and endpoint."""
    kind = txt(node, "ComponentType").upper()
    ref = txt(node, "ComponentRefNo").strip().lstrip("=").replace(" ", "").upper()
    endpoint = txt(node, "Endpoint")
    return (kind, ref, endpoint) if kind in {
        "RIGID", "FLAN", "VALV", "INST"} and ref else None


def audit_finalized_physical_endpoints(final_root, packet_components=None):
    """Read-only distinction between XML physical *nodes* and components.

    A consecutive Endpoint=1 -> Endpoint=2 pair with the same reference and
    family is a single physical part with two geometry witnesses, not proof
    of two independently weighted components. No mass is redistributed.

    If packet_components is passed, restrict alias detection to separately
    accepted source occurrences already stamped on the finalized XML.
    """
    records = []
    double_accepted = []
    for bi, branch in enumerate(branches(final_root)):
        entries = nodes(branch)
        candidates = []
        for ni, node in enumerate(entries):
            key = _physical_component_key(node)
            if key:
                candidates.append((ni, node, key))
        consumed = set()
        for (ni, left, key), (nj, right, other) in zip(
                candidates, candidates[1:]):
            same_family = key[:2] == other[:2]
            rigid_continuation = (
                key[0] in ("FLAN", "VALV") and other[0] == "RIGID" and
                key[1] == other[1] and txt(right, "Rigid") == "2")
            if (nj != ni + 1 or not (same_family or rigid_continuation) or
                    (key[2], other[2]) != ("1", "2")):
                continue
            require(ni not in consumed and nj not in consumed,
                    "NATIVE_ENDPOINT_ALIAS_OVERLAP")
            consumed.update((ni, nj))
            row = {
                "branchOccurrenceIndex": bi,
                "componentType": key[0],
                "componentRefNo": key[1],
                "startNodeNumber": txt(left, "NodeNumber"),
                "endNodeNumber": txt(right, "NodeNumber"),
                "firstEngineNodeOrdinal": ni,
                "secondEngineNodeOrdinal": nj,
            }
            records.append(row)
            if packet_components is not None:
                a, b = txt(left, LINEAGE_TAG), txt(right, LINEAGE_TAG)
                if a in packet_components and b in packet_components:
                    double_accepted.append(row)
    return {
        "schema": "XML229.FinalizedPhysicalEndpointAudit.v1",
        "twoEndpointPhysicalParts": len(records),
        "aliasPairs": records,
        "doubleAcceptedPairs": double_accepted,
    }



def _lineage_oid(source_id, bi, ordinal, node):
    return json.dumps([source_id, bi, ordinal, signature(node)],
                      separators=(",", ":"), ensure_ascii=False)


def _expected_branch_aliases(original_branches, final_branches, retained, source_id):
    """Independently reconstruct unique branch connections, not mass owners."""
    result = []
    for bi, branch in enumerate(final_branches):
        entries = nodes(branch)
        if bi == 0 or not entries:
            continue
        inlet = entries[0]
        if (txt(inlet, "Endpoint") != "1" or txt(inlet, "Rigid") != "2" or
                txt(inlet, "ComponentType").upper() != "RIGID"):
            continue
        number, position = txt(inlet, "NodeNumber"), txt(inlet, "Position")
        try:
            valid = int(number) > 0
        except ValueError:
            valid = False
        if not valid or not position:
            continue
        matches = []
        for prior in range(bi):
            earlier = nodes(final_branches[prior])
            if earlier:
                terminal = earlier[-1]
                if (txt(terminal, "Endpoint") == "2" and
                        txt(terminal, "Rigid") == "2" and
                        txt(terminal, "ComponentType").upper() == "RIGID" and
                        txt(terminal, "NodeNumber") == number and
                        txt(terminal, "Position") == position):
                    matches.append((prior, len(earlier)-1))
        if len(matches) != 1:
            continue
        prior, last_index = matches[0]
        left, right = retained[bi][0], retained[prior][last_index]
        result.append({
            "aliasBranchOccurrenceIndex": bi,
            "aliasSourceNodeOrdinal": left,
            "aliasOccurrenceId": _lineage_oid(
                source_id, bi, left, nodes(original_branches[bi])[left]),
            "terminalBranchOccurrenceIndex": prior,
            "terminalSourceNodeOrdinal": right,
            "terminalOccurrenceId": _lineage_oid(
                source_id, prior, right, nodes(original_branches[prior])[right]),
        })
    return result


def _verify_source_physical_lineage(lineage, packet, original, finalized,
                                    retained, expected_pairs):
    require(isinstance(lineage, dict) and
            lineage.get("schema") == "XML229.SourcePhysicalLineage.v1" and
            lineage.get("sourceId") == packet.get("sourceId") and
            lineage.get("basisId") == packet.get("basisId") and
            lineage.get("sourceXmlSha256") == packet.get("sourceXmlSha256") and
            lineage.get("weightsAccepted") is False and
            lineage.get("nativeCiiReleaseAuthorized") is False,
            "NATIVE_PHYSICAL_LINEAGE_SCHEMA_DRIFT")
    accepted = {row["occurrenceId"] for row in packet["components"]}
    owners = lineage.get("physicalOwnerOccurrenceIds")
    require(isinstance(owners, list) and
            len(owners) == packet["physicalCount"] and
            len(set(owners)) == len(owners) and set(owners) == accepted,
            "NATIVE_PHYSICAL_LINEAGE_OWNER_DRIFT")
    require(lineage.get("componentEndpointPairs") == expected_pairs,
            "NATIVE_PHYSICAL_LINEAGE_PAIR_DRIFT")
    suppressed = lineage.get("suppressedComponentEndpointPairs")
    require(isinstance(suppressed, list),
            "NATIVE_PHYSICAL_LINEAGE_SUPPRESSED_PAIR_DRIFT")
    known_pairs = set()
    for pair in expected_pairs:
        first = json.loads(pair["firstOccurrenceId"])
        second = json.loads(pair["secondOccurrenceId"])
        known_pairs.add((pair["branchOccurrenceIndex"], first[2], second[2],
                         pair["componentType"], pair["componentRefNo"]))
    suppressed_seen = set()
    for pair in suppressed:
        require(isinstance(pair, dict) and set(pair) == {
            "branchOccurrenceIndex", "componentType", "componentRefNo",
            "firstSourceNodeOrdinal", "secondSourceNodeOrdinal"},
            "NATIVE_PHYSICAL_LINEAGE_SUPPRESSED_PAIR_DRIFT")
        witness = (pair["branchOccurrenceIndex"],
                   pair["firstSourceNodeOrdinal"], pair["secondSourceNodeOrdinal"],
                   pair["componentType"], pair["componentRefNo"])
        require(witness in known_pairs and witness not in suppressed_seen,
                "NATIVE_PHYSICAL_LINEAGE_SUPPRESSED_PAIR_DRIFT")
        suppressed_seen.add(witness)
    aliases = _expected_branch_aliases(
        original, finalized, retained, packet["sourceId"])
    require(lineage.get("branchConnectionAliases") == aliases,
            "NATIVE_PHYSICAL_LINEAGE_ALIAS_DRIFT")
    require(all(a["aliasOccurrenceId"] not in accepted and
                a["terminalOccurrenceId"] in accepted for a in aliases),
            "NATIVE_PHYSICAL_LINEAGE_OWNER_ALIAS_DRIFT")
    owner_count, pair_count, alias_count = (
        packet["physicalCount"], len(expected_pairs), len(aliases))
    require(lineage.get("sourceOriginalNodeOccurrences") ==
            sum(len(nodes(br)) for br in original) and
            lineage.get("retainedNodeOccurrences") ==
            sum(len(nodes(br)) for br in finalized) and
            lineage.get("counts") == {
                "physicalOwners": owner_count,
                "componentEndpointWitnesses": pair_count,
                "suppressedEndpointWitnesses": len(suppressed),
                "branchConnectionAliases": alias_count,
                "sourcePhysicalCandidateOccurrences":
                    owner_count+len(suppressed)+alias_count,
            },
            "NATIVE_PHYSICAL_LINEAGE_COUNT_DRIFT")
    return True


def stage_native_original_lineage(original_path, packet_path):
    """Annotate exact original source occurrences BEFORE staged-JSON enrichment.

    These temporary private markers are carried by the XML converter's ET
    transformations and parsed into native nodes. They do not authorize any
    geometry split or invent a mass owner.
    """
    packet, source = read_packet(packet_path, original_path)
    require(child(source, LINEAGE_STAGE) is None and
            not any(child(node, LINEAGE_TAG) is not None
                    for branch in branches(source) for node in nodes(branch)),
            "NATIVE_UNTRUSTED_LINEAGE_TAG")
    final_source, retained_by_original = _validate_finalized_geometry(packet, source)
    source_branches = branches(source)
    seen = set()
    for item in packet["components"]:
        require(isinstance(item, dict), "NATIVE_MASS_ROW_INVALID")
        oid = item.get("occurrenceId")
        try:
            decoded = json.loads(oid)
        except (ValueError, TypeError):
            raise NativeMassError("NATIVE_OCCURRENCE_INVALID") from None
        require(isinstance(decoded, list) and len(decoded) == 4 and
                decoded[0] == packet.get("sourceId") and
                type(decoded[1]) is int and type(decoded[2]) is int and
                decoded[1] >= 0 and decoded[2] >= 0 and
                isinstance(decoded[3], str) and
                json.dumps(decoded, separators=(",", ":"), ensure_ascii=False) == oid,
                "NATIVE_OCCURRENCE_INVALID")
        bi, ni = decoded[1:3]
        require(bi < len(source_branches), "NATIVE_BRANCH_OUT_OF_RANGE")
        source_nodes = nodes(source_branches[bi])
        require(ni < len(source_nodes), "NATIVE_NODE_ORDINAL_OUT_OF_RANGE")
        require((bi, ni) not in seen, "NATIVE_OWNER_DUPLICATED")
        seen.add((bi, ni))
        original = source_nodes[ni]
        require(signature(original) == decoded[3],
                "NATIVE_PHYSICAL_SIGNATURE_DRIFT")
        target = (retained_by_original.get((bi, ni))
                  if retained_by_original is not None else original)
        require(target is not None,
                "NATIVE_ACCEPTED_PHYSICAL_NOT_IN_FINAL_GEOMETRY")
        ns = target.tag.rsplit("}", 1)[0] + "}" if "}" in target.tag else ""
        ET.SubElement(target, ns + LINEAGE_TAG).text = oid
    # Final decisions apply to complete physical *components*, not to each
    # end of the same VALV/FLAN/INST occurrence. Never consume two accepted
    # masses into one paired component or silently choose one of them.
    endpoint_audit = audit_finalized_physical_endpoints(
        final_source, {row["occurrenceId"] for row in packet["components"]})
    require(not endpoint_audit["doubleAcceptedPairs"],
            "NATIVE_DOUBLE_ENDPOINT_MASS_OWNER")
    card = (packet.get("finalizedGeometry") or {}).get(
        "physicalOwnerCardinality")
    if card is not None:
        require(isinstance(card, dict) and
                card.get("schema") in (
                    "XML229.PreAcceptancePhysicalPartCardinality.v1",
                    "XML229.PreAcceptancePhysicalPartCardinality.v2") and
                card.get("weightsAccepted") is False and
                card.get("pairedEndpointPhysicalParts") ==
                endpoint_audit["twoEndpointPhysicalParts"] and
                card.get("reviewedPhysicalNodeOccurrences") ==
                packet["physicalCount"] and
                card.get("distinctPhysicalPartCandidates") ==
                packet["physicalCount"] and
                card.get("sourcePhysicalNodeOccurrences") ==
                packet["physicalCount"] +
                endpoint_audit["twoEndpointPhysicalParts"],
                "NATIVE_PREACCEPTANCE_OWNER_CARDINALITY_DRIFT")
        retained = packet["finalizedGeometry"][
            "retainedSourceOrdinalsByBranch"]
        expected_pairs = []
        for pair in endpoint_audit["aliasPairs"]:
            bi = pair["branchOccurrenceIndex"]
            old_nodes = nodes(source_branches[bi])
            left_source_ordinal = retained[bi][
                pair["firstEngineNodeOrdinal"]]
            right_source_ordinal = retained[bi][
                pair["secondEngineNodeOrdinal"]]
            left_oid = json.dumps([
                packet["sourceId"], bi, left_source_ordinal,
                signature(old_nodes[left_source_ordinal])],
                separators=(",", ":"), ensure_ascii=False)
            right_oid = json.dumps([
                packet["sourceId"], bi, right_source_ordinal,
                signature(old_nodes[right_source_ordinal])],
                separators=(",", ":"), ensure_ascii=False)
            expected_pairs.append({
                "componentType": pair["componentType"],
                "componentRefNo": pair["componentRefNo"],
                "branchOccurrenceIndex": bi,
                "firstOccurrenceId": left_oid,
                "secondOccurrenceId": right_oid,
                "firstIsWeightOwner": False,
                "secondIsWeightOwner": True,
            })
        require(card.get("endpointPairs") == expected_pairs,
                "NATIVE_PREACCEPTANCE_OWNER_CARDINALITY_DRIFT")
        accepted = {row["occurrenceId"] for row in packet["components"]}
        require(all(pair["firstOccurrenceId"] not in accepted
                    for pair in expected_pairs),
                "NATIVE_NONCANONICAL_ENDPOINT_OWNER")
        if card["schema"] == "XML229.PreAcceptancePhysicalPartCardinality.v2":
            require(packet["finalizedGeometry"].get("physicalLineage") is not None,
                    "NATIVE_PHYSICAL_LINEAGE_REQUIRED")
    lineage = (packet.get("finalizedGeometry") or {}).get("physicalLineage")
    if lineage is not None:
        require(card is not None and
                card.get("schema") == "XML229.PreAcceptancePhysicalPartCardinality.v2",
                "NATIVE_PHYSICAL_LINEAGE_SCHEMA_DRIFT")
        _verify_source_physical_lineage(
            lineage, packet, source_branches, branches(final_source),
            packet["finalizedGeometry"]["retainedSourceOrdinalsByBranch"],
            expected_pairs)
    ns = final_source.tag.rsplit("}", 1)[0] + "}" if "}" in final_source.tag else ""
    ET.SubElement(final_source, ns + LINEAGE_STAGE).text = packet["basisId"]
    output = Path(original_path).with_name(
        Path(original_path).stem + "_xml229_lineaged.xml")
    ET.ElementTree(final_source).write(output, encoding="utf-8", xml_declaration=True)
    return output


def bind_native_final_xml(original_path, enriched_path, packet_path,
                          require_staged_lineage=False):
    """Transfer accepted masses from exact original physicals to native owners.

    Governed Runs use an occurrence marker placed BEFORE enrichment, not a
    guess from post-enrichment node numbers. The legacy unmarked path is kept
    only for standalone strict one-to-one unit callers.
    """
    packet, source = read_packet(packet_path, original_path)
    source_branches = branches(source)
    enriched_path = Path(enriched_path)
    enriched = parse_bytes(enriched_path.read_bytes())
    engine_branches = branches(enriched)
    if require_staged_lineage:
        require(txt(enriched, LINEAGE_STAGE) == packet["basisId"],
                "NATIVE_LINEAGE_STAGE_LOST")
    require(len(source_branches) == len(engine_branches),
            "NATIVE_BRANCH_OCCURRENCE_DRIFT")
    used = set()
    owners = []
    source_id = packet.get("sourceId")
    require(isinstance(source_id, str) and bool(source_id),
            "NATIVE_SOURCE_ID_REQUIRED")
    for item in packet["components"]:
        require(isinstance(item, dict), "NATIVE_MASS_ROW_INVALID")
        oid = item.get("occurrenceId")
        try:
            decoded = json.loads(oid)
        except (ValueError, TypeError):
            raise NativeMassError("NATIVE_OCCURRENCE_INVALID") from None
        require(isinstance(decoded, list) and len(decoded) == 4 and
                decoded[0] == source_id and type(decoded[1]) is int and
                type(decoded[2]) is int and decoded[1] >= 0 and decoded[2] >= 0 and
                isinstance(decoded[3], str) and bool(decoded[3]) and
                json.dumps(decoded, separators=(",", ":"), ensure_ascii=False) == oid,
                "NATIVE_OCCURRENCE_INVALID")
        kg = item.get("effectiveKg")
        require(type(kg) in (int, float) and math.isfinite(kg) and kg >= 0,
                "NATIVE_FINAL_MASS_REQUIRED")
        # An explicit zero is a mass decision, not a missing mass. Bind it
        # only to the same proven unique RIGID owner required for positive kg;
        # the emitted RIGID row and its ELEMENTS pointer must still exist.
        bi, ni = decoded[1], decoded[2]
        require(bi < len(source_branches), "NATIVE_BRANCH_OUT_OF_RANGE")
        src, dest = source_branches[bi], engine_branches[bi]
        require(txt(src, "Branchname") == txt(dest, "Branchname"),
                "NATIVE_BRANCH_NAME_DRIFT")
        src_nodes = nodes(src)
        require(ni < len(src_nodes), "NATIVE_NODE_ORDINAL_OUT_OF_RANGE")
        original = src_nodes[ni]
        require(signature(original) == decoded[3],
                "NATIVE_PHYSICAL_SIGNATURE_DRIFT")
        witness = identity(original)
        if require_staged_lineage:
            matches = [(j, node) for j, node in enumerate(nodes(dest))
                       if txt(node, LINEAGE_TAG) == oid]
            require(len(matches) == 1, "NATIVE_CHILD_LINEAGE_MISSING_OR_SPLIT")
            j, owner = matches[0]
            require(signature(owner) == signature(original) and
                    txt(owner, "Position") == txt(original, "Position"),
                    "NATIVE_CHILD_GEOMETRY_DRIFT")
        else:
            matches = [(j, node) for j, node in enumerate(nodes(dest))
                       if identity(node) == witness]
            require(len(matches) == 1, "NATIVE_OWNER_LINEAGE_AMBIGUOUS")
            j, owner = matches[0]
        key = (bi, j)
        require(key not in used, "NATIVE_OWNER_DUPLICATED")
        used.add(key)
        # An explicit Final zero on a source-attested INST 1->2 pair
        # represents NO concentrated component mass. It needs an actual
        # *non-rigid* ELEMENTS record, not a fabricated RIGID classification.
        # All positive masses and every other 0 kg family still require
        # their already proven native RIGID owner.
        prior = nodes(dest)[j-1] if j else None
        normalize_ref = lambda value: value.strip().lstrip("=").replace(" ", "").upper()
        ref = normalize_ref(txt(owner, "ComponentRefNo"))
        rigid_present = txt(owner, "Rigid") == "2"
        flange_rigid_edge = (txt(owner, "ComponentType").upper() == "FLAN"
                            and prior is not None and
                            txt(prior, "Rigid") == "2" and
                            bool(ref) and
                            ref == normalize_ref(txt(prior, "ComponentRefNo")))
        source_prior = src_nodes[ni-1] if ni else None
        zero_nonrigid_instrument = (
            kg == 0 and not rigid_present and not flange_rigid_edge and
            txt(original, "ComponentType").upper() == "INST" and
            txt(original, "Endpoint") == "2" and
            not txt(original, "Rigid") and
            source_prior is not None and
            txt(source_prior, "ComponentType").upper() == "INST" and
            txt(source_prior, "Endpoint") == "1" and
            not txt(source_prior, "Rigid") and
            bool(ref) and
            ref == normalize_ref(txt(source_prior, "ComponentRefNo")) and
            prior is not None and
            txt(prior, "ComponentType").upper() == "INST" and
            txt(prior, "Endpoint") == "1" and
            normalize_ref(txt(prior, "ComponentRefNo")) == ref and
            _normalized_position(txt(original, "Position")) !=
            _normalized_position(txt(source_prior, "Position")))
        require(rigid_present or flange_rigid_edge or zero_nonrigid_instrument,
                "NATIVE_RIGID_OWNER_UNSUPPORTED")
        weight = child(owner, "Weight")
        if weight is None:
            weight = ET.SubElement(owner, owner.tag.rsplit("}", 1)[0] + "}Weight"
                                   if "}" in owner.tag else "Weight")
        weight.text = format(kg, ".17g")
        owners.append({
            "occurrenceId": oid, "branchOccurrenceIndex": bi,
            "engineNodeOrdinal": j, "branchName": txt(dest, "Branchname"),
            "nodeNumber": txt(owner, "NodeNumber"),
            "componentType": txt(owner, "ComponentType"),
            "componentRefNo": txt(owner, "ComponentRefNo"),
            "endpoint": txt(owner, "Endpoint"),
            "position": txt(owner, "Position"), "kg": float(kg),
            "zeroNonRigidInstrument": bool(zero_nonrigid_instrument),
            "stagedLineage": bool(require_staged_lineage),
            "finalizedGeometrySha256": (
                packet.get("finalizedGeometry") or {}).get("sha256"),
        })
    require(len(used) == packet["physicalCount"],
            "NATIVE_ORIGINAL_POPULATION_DRIFT")
    output = enriched_path.with_name(enriched_path.stem + "_xml229_final.xml")
    ET.ElementTree(enriched).write(output, encoding="utf-8", xml_declaration=True)
    return output, owners


def emitted_sections(text):
    sections = {}
    current = None
    for line in text.splitlines():
        if line.startswith("#$ "):
            current = line[3:].strip()
            require(bool(current) and current not in sections, "CII_SECTION_DUPLICATED")
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line)
    require({"CONTROL", "ELEMENTS", "RIGID", "UNITS"} <= sections.keys(),
            "CII_MASS_SECTION_MISSING")
    require(any(row.strip() == "N." for row in sections["UNITS"]),
            "CII_FORCE_UNIT_UNVERIFIED")
    control = sections["CONTROL"]
    require(len(control) == 4, "CII_CONTROL_INVALID")
    try:
        nr_elements = int(control[0].split()[0])
        nr_rigid = int(control[1].split()[1])
    except (ValueError, IndexError):
        raise NativeMassError("CII_CONTROL_INVALID") from None
    require(nr_elements >= 0 and nr_rigid >= 0 and
            len(sections["ELEMENTS"]) == 15*nr_elements and
            len(sections["RIGID"]) == nr_rigid, "CII_MASS_RECORD_COUNT_MISMATCH")
    slots = {}
    for i in range(nr_elements):
        element = sections["ELEMENTS"][i*15:(i+1)*15]
        row1, row13 = element[0].split(), element[12].split()
        require(len(row1) == 6 and len(row13) == 6,
                "CII_ELEMENTS_FORMAT_INVALID")
        try:
            pointer = int(row13[1])
        except ValueError:
            raise NativeMassError("CII_RIGID_POINTER_INVALID") from None
        require(0 <= pointer <= nr_rigid, "CII_RIGID_POINTER_INVALID")
        if pointer:
            require(pointer-1 not in slots, "CII_RIGID_DOUBLE_OWNER")
            slots[pointer-1] = (i, row1[0], row1[1])
    require(len(slots) == nr_rigid, "CII_RIGID_ORPHANED")
    weights = []
    for row in sections["RIGID"]:
        vals = row.split()
        require(len(vals) == 2, "CII_RIGID_ROW_INVALID")
        try:
            value = float(vals[0])
            second = float(vals[1])
        except ValueError:
            raise NativeMassError("CII_RIGID_VALUE_INVALID") from None
        require(math.isfinite(value) and math.isfinite(second) and value >= 0,
                "CII_RIGID_VALUE_INVALID")
        weights.append(value)
    return slots, weights


def _cii_elements(cii_text):
    """Exact ELEMENTS index, from/to nodes and rigid pointer from output."""
    lines = cii_text.splitlines()
    try:
        start = lines.index("#$ ELEMENTS") + 1
        stop = next(i for i in range(start, len(lines)) if lines[i].startswith("#$ "))
    except (ValueError, StopIteration):
        raise NativeMassError("CII_ELEMENTS_SECTION_INVALID") from None
    rows = [line.split() for line in lines[start:stop] if line.strip()]
    require(len(rows) % 15 == 0, "CII_ELEMENTS_RECORD_INVALID")
    result = []
    for i in range(len(rows) // 15):
        first, pointer = rows[15*i], rows[15*i+12]
        require(len(first) == 6 and len(pointer) == 6,
                "CII_ELEMENTS_FORMAT_INVALID")
        try:
            value = int(pointer[1])
        except ValueError:
            raise NativeMassError("CII_RIGID_POINTER_INVALID") from None
        result.append((first[0], first[1], value))
    return result


def verify_emitted_native_masses(cii_text, owners, model, scale=10):
    """Independently parse actual emitted CII bytes; reconcile all owners.

    RIGID ownership must be unique, the ELEMENTS -> RIGID pointer must agree,
    and the actual row must equal accepted kg * 10 within 6-digit formatting.
    Any unclaimed nonzero RIGID record or one-to-many ownership fails closed.
    """
    require(scale == 10, "CII_NATIVE_MASS_SCALE_UNSUPPORTED")
    slots, emitted = emitted_sections(cii_text)
    edges = model.rigid_edges
    require(len(edges) == len(emitted), "CII_GRAPH_RIGID_COUNT_DRIFT")
    output_elements = _cii_elements(cii_text)
    require(len(output_elements) == len(model.edges),
            "CII_GRAPH_ELEMENT_COUNT_DRIFT")
    used = set()
    used_zero_elements = set()
    claims = []
    for row in owners:
        if row.get("zeroNonRigidInstrument"):
            require(row["kg"] == 0 and row["componentType"].upper() == "INST"
                    and row["endpoint"] == "2",
                    "CII_ZERO_INSTRUMENT_NOT_CONFIRMED")
            matching = []
            for idx, edge in enumerate(model.edges):
                node = edge.to_node
                if (edge.branch_name == row["branchName"] and
                        ((getattr(node, "xml229_original_physical_id", "") ==
                          row["occurrenceId"]) if row.get("stagedLineage")
                         else str(node.node_number) == row["nodeNumber"]) and
                        node.component_type == row["componentType"] and
                        node.component_ref_no == row["componentRefNo"] and
                        ("" if node.endpoint is None else str(node.endpoint)) == row["endpoint"] and
                        node.position == tuple(map(float, row["position"].split()))):
                    matching.append(idx)
            require(len(matching) == 1, "CII_ZERO_INSTRUMENT_ELEMENT_AMBIGUOUS")
            ei = matching[0]
            require(ei not in used_zero_elements,
                    "CII_ZERO_INSTRUMENT_ELEMENT_DUPLICATED")
            used_zero_elements.add(ei)
            actual_from, actual_to, pointer = output_elements[ei]
            edge = model.edges[ei]
            require(float(actual_from) == edge.from_node.node_number and
                    float(actual_to) == edge.to_node.node_number and pointer == 0 and
                    edge.to_node.weight == 0,
                    "CII_ZERO_INSTRUMENT_OUTPUT_NOT_VERIFIED")
            claims.append({"occurrenceId": row["occurrenceId"],
                           "rigidRecordIndex": None, "nativeElementIndex": ei,
                           "ciiFromNode": actual_from, "ciiToNode": actual_to,
                           "massKg": 0, "emittedForceN": 0,
                           "zeroNonRigidInstrument": True,
                           "branchOccurrenceIndex": row["branchOccurrenceIndex"],
                           "engineNodeOrdinal": row["engineNodeOrdinal"]})
            continue
        matches = []
        for idx, edge in enumerate(edges):
            node = edge.to_node
            n = (node.source_node_number if node.source_node_number is not None
                 else node.node_number)
            if (edge.branch_name == row["branchName"] and
                    (getattr(node, "xml229_original_physical_id", "") ==
                     row["occurrenceId"] if row.get("stagedLineage")
                     else str(n) == row["nodeNumber"])
                    and node.component_type == row["componentType"]
                    and node.component_ref_no == row["componentRefNo"]
                    and ("" if node.endpoint is None else str(node.endpoint)) == row["endpoint"]
                    and node.position == tuple(map(float, row["position"].split()))):
                matches.append(idx)
        # Zero and multiple native owners have different diagnostic causes.
        # Both continue to fail closed: never infer, split or transfer a mass.
        require(bool(matches), "CII_NATIVE_PHYSICAL_OWNER_MISSING")
        require(len(matches) == 1, "CII_NATIVE_PHYSICAL_OWNER_MULTIPLE")
        index = matches[0]
        require(index not in used and index in slots,
                "CII_NATIVE_PHYSICAL_RIGID_POINTER_UNVERIFIED")
        used.add(index)
        # Compare the ACTUAL CII formatter's emitted numeric value, rather
        # than a blanket six-significant-digit approximation. It emits six
        # fractional scientific digits (SEVEN significant digits) for small
        # or huge values, and six significant digits otherwise.
        force = row["kg"] * scale
        require(math.isfinite(force), "CII_NATIVE_MASS_OUT_OF_RANGE")
        if abs(force) < 1e-12:
            expected = 0.0
        elif abs(force) >= 1e9 or abs(force) < 0.1:
            expected = float(f"{force:.6E}")
        else:
            expected = float(f"{force:#.6G}")
        require(not (row["kg"] > 0 and expected == 0),
                "CII_NATIVE_MASS_UNREPRESENTABLE")
        require(emitted[index] == expected,
                "CII_NATIVE_APPLIED_MASS_MISMATCH")
        require(math.isclose(edges[index].to_node.weight, row["kg"],
                             abs_tol=1e-8, rel_tol=1e-9),
                "CII_NATIVE_MODEL_MASS_MISMATCH")
        element, from_node, to_node = slots[index]
        claims.append({"occurrenceId": row["occurrenceId"],
                       "rigidRecordIndex": index, "nativeElementIndex": element,
                       "ciiFromNode": from_node, "ciiToNode": to_node,
                       "massKg": row["kg"], "emittedForceN": emitted[index],
                       "branchOccurrenceIndex": row["branchOccurrenceIndex"],
                       "engineNodeOrdinal": row["engineNodeOrdinal"]})
    require(len(used) + len(used_zero_elements) == len(owners),
            "CII_NATIVE_CENSUS_INCOMPLETE")
    for i, edge in enumerate(edges):
        if i not in used:
            require(emitted[i] == 0,
                    "CII_NATIVE_UNCLAIMED_POSITIVE_RIGID")
    return {"schema": "XML229.NativeRigidConsumptionDiagnostic.v1",
            "sourcePhysicalCount": len(owners),
            "claimedNativeRigidCount": len(used),
            "claimedZeroNonRigidInstrumentCount": len(used_zero_elements),
            "outputRigidCount": len(emitted),
            "actualCiiSha256": hashlib.sha256(cii_text.encode("utf-8")).hexdigest(),
            "finalizedGeometrySha256": (
                owners[0].get("finalizedGeometrySha256") if owners else None),
            "massesConsumedInNativeRigid": True,
            "claims": sorted(claims, key=lambda c: c["occurrenceId"]),
            "independentNativeChildLineageVerified": False,
            "nativeCiiReleaseAuthorized": False}
