#!/usr/bin/env python3
"""Runtime custody wrapper for standalone PSI116 XML -> CII 2019.

Adds four narrow mechanics on top of xml_to_cii2019_direction:
1. Synthetic RestrainOpenEnds ANC restraints are allowed only at true physical
   open ends. A degree-1 engineering node coincident with another retained node
   number is a branch/continuation occurrence and is not auto-anchored.
2. Bend-radius field authority follows the app toggle. OFF writes zero in the
   CII BEND radius slot; ON writes 1.5 * OD.
3. Explicit restraint identities collapsed by short-node cleanup are audited
   against the retained engineering node without inventing one replacement
   NodeName when several physical support identities share the same position.
4. Source Position values fail closed when malformed, and default COORDS
   authority remains the first retained source node of each connected component
   instead of being reassigned to a later synthetic open-end restraint.
"""
from __future__ import annotations

from collections import Counter
import math
import sys
import xml.etree.ElementTree as ET

import xml_to_cii2019 as base
import xml_to_cii2019_patched as patched
import xml_to_cii2019_direction as direction
from xml_to_cii2019_bend_radius_policy import apply_bend_radius_policy, publish_one_point_five_d
from xml_cii_weight_output_custody import require_rigid_weight_owners


OPEN_END_COINCIDENT_TOLERANCE_MM = 0.5
EXPLICIT_RESTRAINT_IDENTITY_TOLERANCE_MM = 0.5
_ORIGINAL_PARSE_XML_DOCUMENT = base._parse_xml_document
_ORIGINAL_BUILD_RESTRAINTS = base._build_restraints
_ORIGINAL_BUILD_COORDS_PAYLOAD = base._build_coords_payload
_PUBLISH_BEND_RADIUS_1_5D = False
_XML229_FINALIZED_GEOMETRY_ACTIVE = False
EXPLICIT_RESTRAINT_CUSTODY_EVENTS: list[dict] = []


def _distance(left, right) -> float:
    return math.sqrt(sum((float(left[i]) - float(right[i])) ** 2 for i in range(3)))


def _xml_local_name(tag: str) -> str:
    return str(tag or '').split('}', 1)[-1]


def _xml_child_text(parent: ET.Element, name: str) -> str:
    for child in list(parent):
        if _xml_local_name(child.tag) == name:
            return (child.text or '').strip()
    return ''


def _source_position(value: str) -> tuple[float, float, float] | None:
    parts = str(value or '').split()
    if len(parts) != 3:
        return None
    try:
        values = tuple(float(part) for part in parts)
    except ValueError:
        return None
    if not all(math.isfinite(value) for value in values):
        return None
    return values


def _strict_parse_position(value: str) -> tuple[float, float, float]:
    text = base._safe_text(value)
    parts = text.split()
    if len(parts) != 3:
        raise ValueError(
            "Invalid Position: expected exactly three finite numeric coordinates; "
            f"got {text!r}. Refusing implicit (0,0,0) coordinate fallback."
        )
    try:
        values = tuple(float(part) for part in parts)
    except ValueError as exc:
        raise ValueError(
            "Invalid Position: expected exactly three finite numeric coordinates; "
            f"got {text!r}. Refusing implicit (0,0,0) coordinate fallback."
        ) from exc
    if not all(math.isfinite(value) for value in values):
        raise ValueError(
            "Invalid Position: non-finite coordinate encountered; "
            f"got {text!r}. Refusing implicit (0,0,0) coordinate fallback."
        )
    return values  # type: ignore[return-value]


def _source_node_number(value: str) -> int | None:
    try:
        return int(str(value or '').strip())
    except (TypeError, ValueError):
        return None


def _source_explicit_restraint_identity_rows(path) -> list[dict]:
    rows: list[dict] = []
    try:
        root = ET.parse(path).getroot()
    except Exception:
        return rows
    for branch in root.iter():
        if _xml_local_name(branch.tag) != 'Branch':
            continue
        branch_name = _xml_child_text(branch, 'Branchname')
        for node in list(branch):
            if _xml_local_name(node.tag) != 'Node':
                continue
            node_name = _xml_child_text(node, 'NodeName')
            position = _source_position(_xml_child_text(node, 'Position'))
            restraints = [child for child in list(node) if _xml_local_name(child.tag) == 'Restraint']
            if not node_name or position is None or not restraints:
                continue
            type_codes: list[int] = []
            for restraint in restraints:
                restraint_type = _xml_child_text(restraint, 'Type')
                if not restraint_type:
                    continue
                type_codes.append(int(base._restraint_type_to_code(restraint_type)))
            if not type_codes:
                continue
            rows.append({
                'branchName': branch_name,
                'sourceNodeNumber': _source_node_number(_xml_child_text(node, 'NodeNumber')),
                'nodeName': node_name,
                'position': position,
                'typeCodes': tuple(sorted(type_codes)),
            })
    return rows


def _node_restraint_type_codes(node: base.XmlNode) -> set[int]:
    return {int(round(float(spec.type_code))) for spec in node.restraint_specs}


def _retained_candidates_for_source(document: base.XmlDocument, source: dict) -> list[base.XmlNode]:
    candidates: list[base.XmlNode] = []
    source_codes = set(source.get('typeCodes') or ())
    for branch in document.branches:
        if branch.branch_name != source.get('branchName'):
            continue
        for node in branch.nodes:
            if not node.restraint_specs:
                continue
            if _distance(source['position'], node.position) > EXPLICIT_RESTRAINT_IDENTITY_TOLERANCE_MM:
                continue
            if not source_codes.issubset(_node_restraint_type_codes(node)):
                continue
            candidates.append(node)
    return candidates


def _audit_collapsed_explicit_restraint_identity(document: base.XmlDocument, source_rows: list[dict]) -> base.XmlDocument:
    EXPLICIT_RESTRAINT_CUSTODY_EVENTS.clear()
    for source in source_rows:
        candidates = _retained_candidates_for_source(document, source)
        if len(candidates) == 1:
            retained = candidates[0]
            status = 'retained' if (
                retained.node_number == source.get('sourceNodeNumber')
                and str(retained.node_name or '').strip() == str(source.get('nodeName') or '').strip()
            ) else 'transferred'
            event = {
                'status': status,
                'branchName': source.get('branchName'),
                'sourceNodeNumber': source.get('sourceNodeNumber'),
                'retainedNodeNumber': int(retained.node_number),
                'sourceNodeName': source.get('nodeName'),
                'typeCodes': tuple(source.get('typeCodes') or ()),
                'position': tuple(source.get('position') or ()),
            }
            EXPLICIT_RESTRAINT_CUSTODY_EVENTS.append(event)
            if status == 'transferred':
                print(
                    'EXPLICIT_RESTRAINT_CUSTODY_TRANSFER '
                    f"source_node={event['sourceNodeNumber']} retained_node={event['retainedNodeNumber']} "
                    f"source_name={event['sourceNodeName']} "
                    f"type_codes={','.join(map(str, event['typeCodes']))} "
                    f"tol_mm={EXPLICIT_RESTRAINT_IDENTITY_TOLERANCE_MM}",
                    file=sys.stderr,
                )
            continue

        status = 'unresolved' if not candidates else 'ambiguous'
        event = {
            'status': status,
            'branchName': source.get('branchName'),
            'sourceNodeNumber': source.get('sourceNodeNumber'),
            'retainedNodeNumbers': tuple(int(node.node_number) for node in candidates),
            'sourceNodeName': source.get('nodeName'),
            'typeCodes': tuple(source.get('typeCodes') or ()),
            'position': tuple(source.get('position') or ()),
        }
        EXPLICIT_RESTRAINT_CUSTODY_EVENTS.append(event)
        print(
            f"EXPLICIT_RESTRAINT_CUSTODY_{status.upper()} "
            f"source_node={event['sourceNodeNumber']} source_name={event['sourceNodeName']} "
            f"type_codes={','.join(map(str, event['typeCodes']))} "
            f"candidates={','.join(map(str, event['retainedNodeNumbers']))}",
            file=sys.stderr,
        )
    return document


def _runtime_parse_xml_document(path) -> base.XmlDocument:
    source_rows = _source_explicit_restraint_identity_rows(path)
    document = _ORIGINAL_PARSE_XML_DOCUMENT(
        path, preserve_rigid_weight_owners=True,
        preserve_finalized_geometry=_XML229_FINALIZED_GEOMETRY_ACTIVE)
    return _audit_collapsed_explicit_restraint_identity(document, source_rows)


def _unique_edge_nodes(edges: list[base.Edge]) -> list[base.XmlNode]:
    seen: set[tuple[int, tuple[float, float, float]]] = set()
    out: list[base.XmlNode] = []
    for edge in edges:
        for node in (edge.from_node, edge.to_node):
            key = (int(node.node_number), tuple(float(value) for value in node.position))
            if key in seen:
                continue
            seen.add(key)
            out.append(node)
    return out


def _coincident_aliases(edges: list[base.Edge], tolerance_mm: float = OPEN_END_COINCIDENT_TOLERANCE_MM) -> dict[int, set[int]]:
    nodes = _unique_edge_nodes(edges)
    aliases: dict[int, set[int]] = {}
    for index, left in enumerate(nodes):
        for right in nodes[index + 1:]:
            if left.node_number == right.node_number:
                continue
            if _distance(left.position, right.position) > tolerance_mm:
                continue
            aliases.setdefault(int(left.node_number), set()).add(int(right.node_number))
            aliases.setdefault(int(right.node_number), set()).add(int(left.node_number))
    return aliases


def topology_aware_open_end_degrees(
    edges: list[base.Edge],
    degrees: Counter[int],
    tolerance_mm: float = OPEN_END_COINCIDENT_TOLERANCE_MM,
) -> tuple[Counter[int], list[dict]]:
    adjusted: Counter[int] = Counter(degrees)
    aliases = _coincident_aliases(edges, tolerance_mm)
    suppressed: list[dict] = []
    for node_number, degree in list(degrees.items()):
        if degree != 1:
            continue
        peers = sorted(aliases.get(int(node_number), set()))
        if not peers:
            continue
        adjusted[node_number] = 2
        suppressed.append({
            "nodeNumber": int(node_number),
            "engineeringDegree": int(degree),
            "coincidentNodeNumbers": peers,
            "toleranceMm": tolerance_mm,
            "reason": "coincident-retained-occurrence-is-not-physical-open-end",
        })
    return adjusted, suppressed


def _topology_aware_build_restraints(
    metadata: base.XmlMetadata,
    edges: list[base.Edge],
    degrees: Counter[int],
    explicit_specs: dict[int, tuple[base.RestraintSpec, ...]],
    support_map: dict | None = None,
):
    adjusted, suppressed = topology_aware_open_end_degrees(edges, degrees)
    if metadata.restrain_open_ends:
        for row in suppressed:
            print(
                "OPEN_END_ANC_SUPPRESSED "
                f"node={row['nodeNumber']} peers={','.join(map(str, row['coincidentNodeNumbers']))} "
                f"tol_mm={row['toleranceMm']}",
                file=sys.stderr,
            )
    restraints, edge_to_index = _ORIGINAL_BUILD_RESTRAINTS(metadata, edges, adjusted, explicit_specs, support_map)
    if metadata.restrain_open_ends:
        for assigned in restraints:
            if not any(getattr(spec, "is_open_end", False) for spec in assigned.specs):
                continue
            print(
                "OPEN_END_ANC_CREATED "
                f"node={assigned.node_number} basis=true-physical-open-end "
                f"stiffness={base.OPEN_END_STIFFNESS:.6E}",
                file=sys.stderr,
            )
    return restraints, edge_to_index


def _source_datum_coords_payload(model: base.ConversionModel, coords_mode: str) -> list[str]:
    # Preserve the established semantics of explicit all/none modes. The
    # reported loss occurs only in the default first mode, where the base
    # implementation currently lets an auto-generated open-end restraint
    # replace the source datum for an otherwise connected graph.
    if coords_mode != "first":
        return _ORIGINAL_BUILD_COORDS_PAYLOAD(model, coords_mode)

    component_of, _ = base._coords_component_map(model)
    first_by_component: dict[int, tuple[int, tuple[float, float, float]]] = {}
    for edge in model.edges:
        for node in (edge.from_node, edge.to_node):
            component = component_of.get(int(node.node_number))
            if component is None or component in first_by_component:
                continue
            first_by_component[component] = (
                int(node.node_number),
                tuple(float(value) for value in node.position),
            )

    selected = sorted(first_by_component.values(), key=lambda row: row[0])
    if not selected:
        return [base._row(["0"])]

    payload = [base._row([str(len(selected))])]
    for node_number, position in selected:
        mapped = base._map_position_to_cii(position)
        payload.append(base._row([
            str(node_number),
            base._format_fixed_float(mapped[0], 4),
            base._format_fixed_float(mapped[1], 4),
            base._format_fixed_float(mapped[2], 4),
        ]))
    return payload


def _runtime_bend_payload(model: base.ConversionModel) -> list[str]:
    lines: list[str] = []
    for edge in model.bend_edges:
        bend_type_value = 0.0 if edge.to_node.bend_type is None else float(edge.to_node.bend_type)
        radius = 1.5 * base._element_outside_diameter(edge) if _PUBLISH_BEND_RADIUS_1_5D else 0.0
        line1 = base._row([
            base._format_auto_float(radius),
            base._format_auto_float(bend_type_value),
            base._format_fixed_float(base.BEND_FLEXIBILITY_CONSTANT, 5),
            base._format_auto_float(float(edge.to_node.node_number - 1)),
            base._format_fixed_float(0.0, 6),
            base._format_fixed_float(0.0, 6),
        ])
        line2 = base._row([
            base._format_fixed_float(0.0, 6),
            base._format_fixed_float(0.0, 6),
            base._format_fixed_float(0.0, 6),
            base._format_fixed_float(0.0, 6),
            base._format_fixed_float(0.0, 6),
            base._format_fixed_float(0.0, 6),
        ])
        line3 = base._row([
            base._format_fixed_float(0.0, 6),
            base._format_fixed_float(0.0, 6),
        ])
        lines.extend([line1, line2, line3])
    return lines


def install_runtime_custody_patch() -> None:
    # direction imported above has already installed its direction-cosine and
    # tolerant-restraint patches. Wrap that active implementation rather than
    # reverting to the older base builder.
    base._parse_position = _strict_parse_position  # type: ignore[assignment]
    base._parse_xml_document = _runtime_parse_xml_document  # type: ignore[assignment]
    base._build_restraints = _topology_aware_build_restraints  # type: ignore[assignment]
    base._build_coords_payload = _source_datum_coords_payload  # type: ignore[assignment]
    base._build_bend_payload = _runtime_bend_payload  # type: ignore[assignment]


def _mark_native_failure_stage(stage: str) -> None:
    # Only a transient in-process diagnostic for the Pyodide runner.
    # No source content, exception message or traceback crosses this port.
    sys._xml229_native_failure_stage = stage


def main() -> None:
    global _PUBLISH_BEND_RADIUS_1_5D, _XML229_FINALIZED_GEOMETRY_ACTIVE

    _mark_native_failure_stage('RUNTIME_OPTIONS')
    args = patched._parse_args()
    support_config = patched._load_support_config(args.support_config_json)
    if args.split_condensed_valve_flange is not None:
        support_config["splitCondensedValveFlange"] = bool(args.split_condensed_valve_flange)
    support_config.setdefault("teeSifTypeMapping", direction.DEFAULT_TEE_SIF_TYPE_MAPPING)
    support_config.setdefault("defaultTeeSifType", 0)
    _PUBLISH_BEND_RADIUS_1_5D = publish_one_point_five_d(support_config)

    # Stage exact original occurrence identities before ANY enrichment,
    # renumbering, or short-element cleanup. Original packet SHA is checked
    # against untouched args.input by the stage and again by the binder.
    staged_original = args.input
    if args.xml229_native_final_packet is not None:
        from xml229_native_final_mass_binding import stage_native_original_lineage
        _mark_native_failure_stage('ORIGINAL_LINEAGE_STAGE')
        staged_original = stage_native_original_lineage(
            args.input, args.xml229_native_final_packet)
    _mark_native_failure_stage('STAGED_ENRICHMENT')
    input_xml = patched._maybe_enrich_from_staged_json(
        staged_original, args.staged_json, support_config)
    input_xml = patched._apply_process_data_to_xml(input_xml, support_config)
    input_xml, bend_policy = apply_bend_radius_policy(input_xml, support_config)
    # Weights are accepted against the immutable original XML geometry.
    # Geometry transformation must be complete BEFORE those decisions, not
    # performed implicitly during this Run. Number-only renaming is allowed;
    # added/deleted/reordered/repositioned/retyped physical nodes are not.
    if args.xml229_native_final_packet is not None:
        from xml229_native_final_mass_binding import assert_preaccepted_geometry_unchanged
        _mark_native_failure_stage('PREACCEPTANCE_GEOMETRY')
        assert_preaccepted_geometry_unchanged(staged_original, input_xml)
    # The *actual* converter input receives accepted Final masses here, not
    # a separate diagnostic copy. No post-acceptance geometry splitting.
    xml229_native_owners = None
    if args.xml229_native_final_packet is not None:
        if args.xml229_native_mass_proof is None or args.weight_scale != 10:
            raise ValueError("XML229_NATIVE_MASS_PROOF_AND_KG_TO_N_REQUIRED")
        from xml229_native_final_mass_binding import bind_native_final_xml
        _mark_native_failure_stage('FINAL_MASS_BINDING')
        input_xml, xml229_native_owners = bind_native_final_xml(
            args.input, input_xml, args.xml229_native_final_packet,
            require_staged_lineage=True)
    elif args.xml229_native_mass_proof is not None:
        raise ValueError("XML229_NATIVE_FINAL_PACKET_REQUIRED")
    for row in bend_policy.get("rows", []):
        print(
            "BEND_RADIUS_POLICY "
            f"node={row.get('nodeNumber','')} action={row.get('action','')} "
            f"basis={row.get('basis', row.get('outsideDiameterSource',''))} "
            f"radius={row.get('bendRadius','')}",
            file=sys.stderr,
        )

    tee_desc_by_node = direction._tee_description_by_node(input_xml)
    insulation_density_map = patched._branch_insulation_density_map(input_xml)
    hydro_pressure_map = patched._branch_hydro_pressure_map(input_xml)
    # The Worker-finalized XML is already cleaned. Skip the second
    # coordinate-based cleanup which was previously applied AFTER Final.
    if args.xml229_native_final_packet is not None:
        from xml229_native_final_mass_binding import read_packet
        _mark_native_failure_stage('FINAL_GEOMETRY_READ')
        active_packet, _ = read_packet(
            args.xml229_native_final_packet, args.input)
        _XML229_FINALIZED_GEOMETRY_ACTIVE = bool(
            active_packet.get("finalizedGeometry"))
    else:
        _XML229_FINALIZED_GEOMETRY_ACTIVE = False
    _mark_native_failure_stage('MODEL_PARSE')
    document = base._parse_xml_document(input_xml)
    component_specs = direction._component_type_restraint_specs(document, support_config)
    dtxr_specs, node_number_kind_map = patched._build_keyword_restraint_specs(input_xml, support_config)
    xml_specs = base._build_explicit_restraint_specs(document.branches)
    explicit_specs = (
        dict(xml_specs)
        if args.use_restraint_type_based_on_json and patched._xml_restraints_are_authoritative(input_xml, support_config)
        else (
            direction._prefer_xml_spec_map(xml_specs, component_specs, dtxr_specs)
            if args.use_restraint_type_based_on_json
            else direction._merge_spec_maps(component_specs, xml_specs, dtxr_specs)
        )
    )
    _mark_native_failure_stage('MODEL_BUILD')
    model = patched._build_conversion_model(
        document,
        explicit_specs,
        patched._node_name_kind_map(document, node_number_kind_map),
        support_config,
    )
    if xml229_native_owners is not None:
        from xml229_native_final_mass_binding import assert_native_model_geometry_unchanged
        _mark_native_failure_stage('MODEL_GEOMETRY_CHECK')
        assert_native_model_geometry_unchanged(staged_original, document, model)
    _mark_native_failure_stage('RIGID_WEIGHT_OWNER_CHECK')
    require_rigid_weight_owners(input_xml, model)
    temperature_map, pressure_map = patched._branch_case_maps(document)
    base._build_restraint_payload = direction._direction_enabled_restraint_payload_factory(support_config)
    base._build_elements_payload = patched._patched_elements_payload_factory(
        temperature_map,
        pressure_map,
        insulation_density_map,
        hydro_pressure_map,
        support_config,
    )  # type: ignore[assignment]
    base._build_sif_payload = direction._sif_payload_factory(tee_desc_by_node, support_config)  # type: ignore[assignment]
    _mark_native_failure_stage('CII_SERIALIZE')
    cii_text = base._build_cii_text(
        model,
        args.coords_mode,
        base._resolve_template_version_line(args.template_cii),
        args.weight_scale,
        support_config,
    )
    if xml229_native_owners is not None:
        from xml229_native_final_mass_binding import verify_emitted_native_masses
        import json as _xml229_json
        # Parse the ACTUAL CII bytes and crosscheck ELEMENTS -> RIGID pointers,
        # exact guarded source owners and numeric kg * 10 before publication.
        _mark_native_failure_stage('EMITTED_MASS_VERIFY')
        mass_diagnostic = verify_emitted_native_masses(
            cii_text, xml229_native_owners, model, scale=args.weight_scale)
        args.xml229_native_mass_proof.write_text(
            _xml229_json.dumps(mass_diagnostic, sort_keys=True), encoding="utf-8")
    _mark_native_failure_stage('OUTPUT_WRITE')
    args.output.write_text(cii_text, encoding="utf-8")
    if args.diagnostics_out:
        args.diagnostics_out.write_text(base._build_diagnostics_report(model), encoding="utf-8")
    print(
        f"Wrote {args.output} with {len(model.edges)} elements and {len(model.restraints)} restraints. "
        f"runtime_custody=1; bend_radius_1_5d={_PUBLISH_BEND_RADIUS_1_5D}; "
        f"use_restraint_type_based_on_json={args.use_restraint_type_based_on_json}; "
        f"split_condensed_valve_flange={support_config.get('splitCondensedValveFlange')}"
    )


install_runtime_custody_patch()


if __name__ == "__main__":
    main()
