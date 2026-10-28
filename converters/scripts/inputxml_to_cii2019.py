#!/usr/bin/env python3
"""
Convert CAESARII Input XML (`XML_TYPE=Input`) into CII text.

Functionality:
- Parses `CAESARII > PIPINGMODEL > PIPINGELEMENT` records.
- Converts element attributes and auxiliary tags (`BEND`, `RIGID`,
  `RESTRAINT`, `SIF`) into CII sections.
- Maps each element's six possible `RESTRAINT` slots into one 24-line
  `RESTRANT` auxiliary block, including support tag and GUID strings.
- Handles CAESAR missing sentinel values with configurable defaults.

Parameters expected:
- `--input`: input XML path (CAESARII Input XML).
- `--output`: output CII path.
- Optional defaults for missing diameter/wall/temp/reducer-angle values.

Outputs passed:
- One `.cii` file.
- Summary printed to stdout.

Fallback:
- Node-name and absolute coordinate seed data may not be present in Input XML.
  Defaults are used for missing node names. When endpoint coordinate seeds are
  absent, absolute coordinates are reconstructed from element deltas with a
  local origin.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import json
import math
import re
from pathlib import Path
from typing import Final
import xml.etree.ElementTree as ET

try:
    import cii2019_section_rules
except ImportError:
    cii2019_section_rules = None

try:
    import cii_syntax_check_2019
except ImportError:
    cii_syntax_check_2019 = None

try:
    import cii2019_hanger_miscel_control
except ImportError:
    cii2019_hanger_miscel_control = None


SENTINEL_MISSING: Final[float] = -1.0101
VERSION_PAYLOAD_LINES: Final[int] = 61
DEFAULT_LINEAR_STIFFNESS: Final[float] = 1.75127e12
# CAESAR neutral-file token for the rigid/linear default stiffness. Used for any
# restraint whose source RESTRAINT/STIFFNESS is missing. A 0 (or non-positive)
# stiffness must never reach CII - CAESAR reads a 0-stiffness restraint as no
# restraint at all - so this is the fallback the never-zero guard coerces to.
DEFAULT_STIFFNESS_TOKEN: Final[str] = "0.175120E+13"
DEFAULT_VERSION_HEADER: Final[str] = "CAESARII Input XML to CII converter"
DEFAULT_2019_CONFIG_FILE: Final[str] = "inputxml_to_cii2019_config.json"
UNIVERSAL_VERSION_PREFIX_FALLBACK: Final[tuple[str, ...]] = (
    "       5.000000     11.000000     1252",
    "  ",
)
RAW_OVERRIDE_MODE_SCHEMA: Final[str] = "schema_validated"
RAW_OVERRIDE_MODE_COMPATIBILITY: Final[str] = "compatibility"
RESTRAINT_MAPPING_POLICY_IDENTITY: Final[str] = "identity"
RESTRAINT_MAPPING_POLICY_EXPLICIT: Final[str] = "explicit_map"
RESTRAINT_SLOTS_PER_AUX: Final[int] = 6
RESTRAINT_LINES_PER_SLOT: Final[int] = 4
RESTRAINT_LINES_PER_AUX_BLOCK: Final[int] = RESTRAINT_SLOTS_PER_AUX * RESTRAINT_LINES_PER_SLOT
UNIVERSAL_VERSION_PAYLOAD_CACHE: list[str] | None = None

# Diagnostics collected during a single conversion run. Reset at the start
# of _parse_model() (the entry point every conversion goes through) so
# repeated in-process calls - e.g. from the test suite - don't leak state
# between runs. Module-level rather than threaded as an explicit parameter
# deliberately: this script converts exactly one file per process/call, so
# there is no concurrency or reentrancy to guard against, and threading a
# diagnostics list through every parsing/formatting function on the call
# path would be a much larger, riskier change for the same effect.
_DIAGNOSTICS: list[dict[str, object]] = []
_STRICT_DIAGNOSTICS: bool = False


def _reset_diagnostics() -> None:
    _DIAGNOSTICS.clear()


def _warn(code: str, message: str, **context: object) -> None:
    """Record a recoverable data-quality issue and apply a documented fallback.

    In --strict mode this raises instead, so CI/validation callers that
    want the old fail-fast behavior for these specific situations can opt
    into it explicitly.
    """
    if _STRICT_DIAGNOSTICS:
        raise ValueError(f"[--strict] {message}")
    entry: dict[str, object] = {"severity": "warning", "code": code, "message": message}
    entry.update(context)
    _DIAGNOSTICS.append(entry)


@dataclass(frozen=True)
class ConverterDefaults:
    diameter: float
    wall_thickness: float
    insulation_thickness: float
    corrosion_allowance: float
    temperature1: float
    temperature2: float
    temperature3: float
    pressure1: float
    pressure2: float
    pressure3: float
    reducer_angle: float


@dataclass(frozen=True)
class BendAux:
    radius: float
    type_code: float
    angle1: float
    node1: float
    angle2: float
    node2: float
    angle3: float
    node3: float
    num_miter: float
    fitting_thickness: float
    kfactor: float


@dataclass(frozen=True)
class RestraintAux:
    slot: int
    node: float
    type_code: float
    stiffness: float
    gap: float
    friction: float
    connecting_node: float
    xcos: float
    ycos: float
    zcos: float
    tag: str
    guid: str


@dataclass(frozen=True)
class SifAux:
    node: float


@dataclass(frozen=True)
class NozzleAux:
    kind: str
    attributes: dict[str, str]


@dataclass(frozen=True)
class HangerAux:
    node: float
    stiffness: float
    load_variation: float
    operating_load: float
    rigid_support: float
    available_space: float
    cold_load: float
    hot_load: float
    max_travel: float
    hardware_weight: float
    const_eff_load: float
    multi_lc: float
    free_anchor1: float
    free_anchor2: float
    dof_type1: float
    num_hgr: float
    hgr_table: float
    short_range: float
    connecting_node: float
    tag: str
    guid: str


@dataclass(frozen=True)
class ElementResolved:
    from_node: float
    to_node: float
    delta_x: float
    delta_y: float
    delta_z: float
    diameter: float
    wall_thickness: float
    insulation_thickness: float
    corrosion_allowance: float
    temperature1: float
    temperature2: float
    temperature3: float
    material_id: float | None
    bend: BendAux | None
    rigid_weight: float | None
    restraints: list[RestraintAux]
    sifs: list[SifAux]
    name_from: str = ""
    name_to: str = ""
    line: str = ""
    from_coordinate_seed: NodeCoordinate | None = None
    to_coordinate_seed: NodeCoordinate | None = None
    # REL(N1,98) items 13-18, 19-27, 31-32, 36 per the CAESAR II neutral file
    # spec (Basic Element Data / #$ ELEMENTS). Each defaults to 0.0, matching
    # "Non-specified real values are assigned a value of 0.0 by this interface."
    temperature4: float = 0.0
    temperature5: float = 0.0
    temperature6: float = 0.0
    temperature7: float = 0.0
    temperature8: float = 0.0
    temperature9: float = 0.0
    pressure1: float = 0.0
    pressure2: float = 0.0
    pressure3: float = 0.0
    pressure4: float = 0.0
    pressure5: float = 0.0
    pressure6: float = 0.0
    pressure7: float = 0.0
    pressure8: float = 0.0
    pressure9: float = 0.0
    insulation_density: float = 0.0
    fluid_density: float = 0.0
    hydro_pressure: float = 0.0


@dataclass(frozen=True)
class ParsedModel:
    job_name: str
    time_text: str
    version_text: str
    elements: list[ElementResolved]
    nozzles: list[NozzleAux]
    hangers: list[HangerAux]


@dataclass(frozen=True)
class NodeCoordinate:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class ReferenceElementOverrides:
    version_payload: list[str]
    nonam_count: int
    node_name_pointers: list[int]
    nodename_payload: list[str]
    bend_payload: list[str]
    reducers_payload: list[str]
    coords_payload: list[str]


@dataclass(frozen=True)
class CompatibilityConfig:
    raw_override_mode: str


@dataclass(frozen=True)
class RestraintTypeMappingPolicy:
    policy: str
    explicit_type_map: dict[str, str]


@dataclass(frozen=True)
class SectionPayloadModel:
    version: list[str]
    control: list[str]
    elements: list[str]
    aux_data: list[str]
    nodename: list[str]
    bend: list[str]
    rigid: list[str]
    expjt: list[str]
    restrant: list[str]
    displmnt: list[str]
    forcmnt: list[str]
    uniform: list[str]
    wind: list[str]
    offsets: list[str]
    allowbls: list[str]
    sif_tees: list[str]
    reducers: list[str]
    flanges: list[str]
    equipmnt: list[str]
    miscel_1: list[str]
    units: list[str]
    coords: list[str]


def _safe_text(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


# Canonical namespace for InputXML per contracts/inputxml/v1/inputxml-canonical-v1.xsd
# and inputxml-dialect-registry.json. This function is a lightweight,
# diagnostic-only mirror of that registry's "signals" - it never blocks or
# alters parsing (this engine has always tolerated non-canonical dialects via
# _local_name()'s namespace-stripping), it only decides what to warn about.
# Keep in sync with contracts/inputxml/v1/inputxml-dialect-registry.json if
# dialects are added, renamed, or their signals change there.
_CANONICAL_NAMESPACE: Final[str] = "COADE"


def _classify_inputxml_dialect(root: ET.Element, piping_model: ET.Element) -> tuple[str, list[str]]:
    deviations: list[str] = []
    root_ns = root.tag.split("}", 1)[0][1:] if root.tag.startswith("{") else ""
    xml_type = root.attrib.get("XML_TYPE")
    numelt = piping_model.attrib.get("NUMELT")
    numelements = piping_model.attrib.get("NUMELEMENTS")

    if root_ns != _CANONICAL_NAMESPACE:
        deviations.append(f"root namespace is {root_ns or '(none)'}, expected {_CANONICAL_NAMESPACE!r}")
    if xml_type != "Input":
        deviations.append(f"CAESARII/@XML_TYPE is {xml_type!r}, expected 'Input'")
    if numelt is None and numelements is not None:
        deviations.append("PIPINGMODEL uses NUMELEMENTS instead of the canonical NUMELT attribute")
    elif numelt is None:
        deviations.append("PIPINGMODEL is missing NUMELT")

    if not deviations:
        return "canonical-inputxml-v1", deviations

    # Best-effort guess at the closest registered vendor/application dialect
    # (see inputxml-dialect-registry.json), for diagnostic context only.
    sample_attribs: set[str] = set()
    for elem in piping_model.findall("PIPINGELEMENT"):
        sample_attribs.update(elem.attrib.keys())
        break
    child_names = {_local_name(child.tag) for child in piping_model.iter()}

    if "PRESSURE1" in sample_attribs:
        dialect_id = "caesar-inputxml-pressure1"
    elif "PRESSURE_C1" in sample_attribs:
        dialect_id = "caesar-inputxml-pressure-c"
    elif {"DTXR_POS", "PipingClass", "Point_properties_basis"} & child_names:
        dialect_id = "enriched-inputxml-app"
    else:
        dialect_id = "unregistered"
    return dialect_id, deviations


def _to_float(value: str | None, field_name: str) -> float:
    text = _safe_text(value)
    if not text:
        raise ValueError(f"Missing numeric field '{field_name}'.")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric field '{field_name}': '{text}'.") from exc


def _to_float_or_default(value: str | None, field_name: str, default: float) -> float:
    text = _safe_text(value)
    if not text:
        return default
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric field '{field_name}': '{text}'.") from exc


def _is_missing(value: float) -> bool:
    return abs(value - SENTINEL_MISSING) < 1e-6


def _value_or_default(value: float, fallback: float) -> float:
    if _is_missing(value):
        return fallback
    return value


def _parse_node_coordinate_seed(attributes: dict[str, str], prefix: str) -> NodeCoordinate | None:
    """Read canonical global coordinates, with legacy short names for compatibility."""
    global_names = (
        f"{prefix}_GLOBAL_X",
        f"{prefix}_GLOBAL_Y",
        f"{prefix}_GLOBAL_Z",
    )
    legacy_names = (f"{prefix}_X", f"{prefix}_Y", f"{prefix}_Z")
    names = global_names if any(_safe_text(attributes.get(name)) for name in global_names) else legacy_names
    raw_values = [attributes.get(name) for name in names]
    if all(not _safe_text(value) for value in raw_values):
        return None
    if any(not _safe_text(value) for value in raw_values):
        missing = ", ".join(name for name, value in zip(names, raw_values) if not _safe_text(value))
        # A partial seed (some but not all of X/Y/Z given) can't anchor this
        # node on its own. Treating it as "no seed" is safe: that's already
        # the normal, default, exercised code path used by every element
        # that supplies no seed at all - absolute coordinates for this node
        # get reconstructed from element deltas instead.
        _warn(
            "PARTIAL_COORDINATE_SEED_IGNORED",
            f"Incomplete PIPINGELEMENT {prefix} coordinate seed (missing {missing}); "
            "falling back to delta-reconstructed coordinates for this node.",
            attribute_prefix=prefix,
            missing_fields=missing,
        )
        return None
    return NodeCoordinate(
        x=_to_float(raw_values[0], f"PIPINGELEMENT/{names[0]}"),
        y=_to_float(raw_values[1], f"PIPINGELEMENT/{names[1]}"),
        z=_to_float(raw_values[2], f"PIPINGELEMENT/{names[2]}"),
    )


def _parse_restraint_slot(value: str | None, fallback_slot: int) -> int:
    text = _safe_text(value)
    if not text:
        return fallback_slot
    try:
        raw = float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric field 'RESTRAINT/NUM': '{text}'.") from exc
    slot = int(round(raw))
    if abs(raw - slot) > 1e-6 or slot < 1 or slot > RESTRAINT_SLOTS_PER_AUX:
        raise ValueError(
            f"Invalid RESTRAINT/NUM '{text}'; expected an integer slot from 1 to {RESTRAINT_SLOTS_PER_AUX}."
        )
    return slot


def _parse_time_text(value: str) -> str:
    text = _safe_text(value)
    if not text:
        now = datetime.now()
        return f"{now:%H:%M:%S} {now.day} {now:%B %Y}"
    try:
        parsed = datetime.strptime(text, "%Y/%m/%d %H:%M:%S")
    except ValueError:
        now = datetime.now()
        return f"{now:%H:%M:%S} {now.day} {now:%B %Y}"
    return f"{parsed:%H:%M:%S} {parsed.day} {parsed:%B %Y}"


def _parse_bend(element: ET.Element) -> BendAux | None:
    bend = element.find("BEND")
    if bend is None:
        return None
    return BendAux(
        radius=_to_float_or_default(bend.attrib.get("RADIUS"), "BEND/RADIUS", SENTINEL_MISSING),
        type_code=_to_float_or_default(bend.attrib.get("TYPE"), "BEND/TYPE", SENTINEL_MISSING),
        angle1=_to_float_or_default(bend.attrib.get("ANGLE1"), "BEND/ANGLE1", SENTINEL_MISSING),
        node1=_to_float_or_default(bend.attrib.get("NODE1"), "BEND/NODE1", SENTINEL_MISSING),
        angle2=_to_float_or_default(bend.attrib.get("ANGLE2"), "BEND/ANGLE2", SENTINEL_MISSING),
        node2=_to_float_or_default(bend.attrib.get("NODE2"), "BEND/NODE2", SENTINEL_MISSING),
        angle3=_to_float_or_default(bend.attrib.get("ANGLE3"), "BEND/ANGLE3", SENTINEL_MISSING),
        node3=_to_float_or_default(bend.attrib.get("NODE3"), "BEND/NODE3", SENTINEL_MISSING),
        num_miter=_to_float_or_default(bend.attrib.get("NUM_MITER"), "BEND/NUM_MITER", SENTINEL_MISSING),
        fitting_thickness=_to_float_or_default(bend.attrib.get("FITTINGTHICKNESS"), "BEND/FITTINGTHICKNESS", SENTINEL_MISSING),
        kfactor=_to_float_or_default(bend.attrib.get("KFACTOR"), "BEND/KFACTOR", SENTINEL_MISSING),
    )


def _parse_rigid_weight(element: ET.Element) -> float | None:
    rigid = element.find("RIGID")
    if rigid is None:
        return None
    return _to_float_or_default(rigid.attrib.get("WEIGHT"), "RIGID/WEIGHT", 0.0)


def _allowbls_value_is_meaningful(value: str | None) -> bool:
    text = _safe_text(value)
    if not text:
        return False
    try:
        parsed = float(text)
    except ValueError:
        return True
    # -1.0101 is the standard InputXML sentinel; a bare -1 is this dialect's
    # separate "unset" convention for boolean/flag-like ALLOWABLESTRESS
    # fields (e.g. SUPP_RQR, BURST_OPE); 0.0 is a placeholder, not a real
    # override; NaN/inf (seen as a literal "-nan" in at least one real
    # sample) is not usable data either.
    if not math.isfinite(parsed):
        return False
    if _is_missing(parsed) or abs(parsed + 1.0) < 1e-9 or abs(parsed) < 1e-9:
        return False
    return True


def _has_meaningful_allowablestress(element: ET.Element) -> bool:
    for child in list(element):
        if _local_name(child.tag) != "ALLOWABLESTRESS":
            continue
        if any(_allowbls_value_is_meaningful(value) for key, value in child.attrib.items()):
            return True
        for case in list(child):
            if any(
                _allowbls_value_is_meaningful(value)
                for key, value in case.attrib.items()
                if key != "NUM"
            ):
                return True
    return False


def _parse_restraints(element: ET.Element) -> list[RestraintAux]:
    restraints: list[RestraintAux] = []
    for restraint in element.findall("RESTRAINT"):
        node = _to_float_or_default(restraint.attrib.get("NODE"), "RESTRAINT/NODE", SENTINEL_MISSING)
        if _is_missing(node):
            continue
        try:
            slot = _parse_restraint_slot(restraint.attrib.get("NUM"), len(restraints) + 1)
        except ValueError as exc:
            # A malformed slot number on one RESTRAINT record shouldn't take
            # down the whole element's other restraints, let alone the rest
            # of the file - drop just this one record. This mirrors the
            # existing, already-shipped precedent in
            # inputxml-field-adapter.js, which does the same thing (drops
            # overflow/unparseable RESTRAINT slots with a logged reason)
            # at the InputXML-normalization boundary.
            _warn(
                "INVALID_RESTRAINT_SLOT_DROPPED",
                f"Dropping RESTRAINT on node {_format_node_id(node)}: {exc}",
                node=node,
            )
            continue
        friction_raw = restraint.attrib.get("FRIC_COEF") or restraint.attrib.get("MU")
        restraints.append(
            RestraintAux(
                slot=slot,
                node=node,
                type_code=_to_float_or_default(restraint.attrib.get("TYPE"), "RESTRAINT/TYPE", SENTINEL_MISSING),
                stiffness=_to_float_or_default(restraint.attrib.get("STIFFNESS"), "RESTRAINT/STIFFNESS", SENTINEL_MISSING),
                gap=_to_float_or_default(restraint.attrib.get("GAP"), "RESTRAINT/GAP", SENTINEL_MISSING),
                friction=_to_float_or_default(friction_raw, "RESTRAINT/FRIC_COEF", SENTINEL_MISSING),
                connecting_node=_to_float_or_default(restraint.attrib.get("CNODE"), "RESTRAINT/CNODE", SENTINEL_MISSING),
                xcos=_to_float_or_default(restraint.attrib.get("XCOSINE"), "RESTRAINT/XCOSINE", SENTINEL_MISSING),
                ycos=_to_float_or_default(restraint.attrib.get("YCOSINE"), "RESTRAINT/YCOSINE", SENTINEL_MISSING),
                zcos=_to_float_or_default(restraint.attrib.get("ZCOSINE"), "RESTRAINT/ZCOSINE", SENTINEL_MISSING),
                tag=_safe_text(restraint.attrib.get("TAG")),
                guid=_safe_text(restraint.attrib.get("GUID")),
            )
        )
    return restraints


def _parse_sifs(element: ET.Element) -> list[SifAux]:
    sifs: list[SifAux] = []
    for sif in element.findall("SIF"):
        node = _to_float_or_default(sif.attrib.get("NODE"), "SIF/NODE", SENTINEL_MISSING)
        if _is_missing(node):
            continue
        sifs.append(SifAux(node=node))
    return sifs


def _parse_hangers(element: ET.Element) -> list[HangerAux]:
    hangers: list[HangerAux] = []
    for hanger in element.findall("HANGER"):
        node = _to_float(hanger.attrib.get("NODE"), "HANGER/NODE")
        if _is_missing(node):
            continue
        hangers.append(
            HangerAux(
                node=node,
                stiffness=_to_float_or_default(hanger.attrib.get("STIFFNESS"), "HANGER/STIFFNESS", SENTINEL_MISSING),
                load_variation=_to_float_or_default(hanger.attrib.get("LOAD_VAR"), "HANGER/LOAD_VAR", SENTINEL_MISSING),
                operating_load=_to_float_or_default(hanger.attrib.get("OPERATING_LOAD"), "HANGER/OPERATING_LOAD", SENTINEL_MISSING),
                rigid_support=_to_float_or_default(hanger.attrib.get("RIGID_SUP"), "HANGER/RIGID_SUP", SENTINEL_MISSING),
                available_space=_to_float_or_default(hanger.attrib.get("AVAIL_SPACE"), "HANGER/AVAIL_SPACE", SENTINEL_MISSING),
                cold_load=_to_float_or_default(hanger.attrib.get("COLD_LOAD"), "HANGER/COLD_LOAD", SENTINEL_MISSING),
                hot_load=_to_float_or_default(hanger.attrib.get("HOT_LOAD"), "HANGER/HOT_LOAD", SENTINEL_MISSING),
                max_travel=_to_float_or_default(hanger.attrib.get("MAX_TRAVEL"), "HANGER/MAX_TRAVEL", SENTINEL_MISSING),
                hardware_weight=_to_float_or_default(hanger.attrib.get("HARDWARE_WEIGHT"), "HANGER/HARDWARE_WEIGHT", SENTINEL_MISSING),
                const_eff_load=_to_float_or_default(hanger.attrib.get("CONST_EFF_LOAD"), "HANGER/CONST_EFF_LOAD", SENTINEL_MISSING),
                multi_lc=_to_float_or_default(hanger.attrib.get("MULTI_LC"), "HANGER/MULTI_LC", SENTINEL_MISSING),
                free_anchor1=_to_float_or_default(hanger.attrib.get("FREEANCHOR1"), "HANGER/FREEANCHOR1", SENTINEL_MISSING),
                free_anchor2=_to_float_or_default(hanger.attrib.get("FREEANCHOR2"), "HANGER/FREEANCHOR2", SENTINEL_MISSING),
                dof_type1=_to_float_or_default(hanger.attrib.get("DOFTYPE1"), "HANGER/DOFTYPE1", SENTINEL_MISSING),
                num_hgr=_to_float_or_default(hanger.attrib.get("NUM_HGR"), "HANGER/NUM_HGR", SENTINEL_MISSING),
                hgr_table=_to_float_or_default(hanger.attrib.get("HGR_TABLE"), "HANGER/HGR_TABLE", SENTINEL_MISSING),
                short_range=_to_float_or_default(hanger.attrib.get("SHORT_RANGE"), "HANGER/SHORT_RANGE", SENTINEL_MISSING),
                connecting_node=_to_float_or_default(hanger.attrib.get("CNODE"), "HANGER/CNODE", SENTINEL_MISSING),
                tag=_safe_text(hanger.attrib.get("TAG")),
                guid=_safe_text(hanger.attrib.get("GUID")),
            )
        )
    return hangers


def _parse_nozzles(root: ET.Element) -> list[NozzleAux]:
    nozzles: list[NozzleAux] = []
    nozzle_tags = ("WRC_297_NOZZLE", "API650_NOZZLE", "PD5500_NOZZLE", "CUSTOM_NOZZLE")
    for element in root.iter():
        local_tag = _local_name(element.tag)
        if local_tag not in nozzle_tags:
            continue
        nozzles.append(
            NozzleAux(
                kind=local_tag,
                attributes={str(key): _safe_text(value) for key, value in element.attrib.items()},
            )
        )
    return nozzles


def _parse_model(path: Path, defaults: ConverterDefaults) -> ParsedModel:
    _reset_diagnostics()
    root = ET.parse(path).getroot()
    if _local_name(root.tag) != "CAESARII":
        raise ValueError("Input root must be CAESARII.")

    piping_model = None
    for element in root.iter():
        if _local_name(element.tag) == "PIPINGMODEL":
            piping_model = element
            break
    if piping_model is None:
        raise ValueError("Input XML does not contain PIPINGMODEL.")

    _dialect_id, _dialect_deviations = _classify_inputxml_dialect(root, piping_model)
    if _dialect_deviations:
        _warn(
            "INPUTXML_DIALECT_NOT_CANONICAL",
            "Input XML does not match the canonical InputXML contract "
            f"(contracts/inputxml/v1/inputxml-canonical-v1.xsd); closest known dialect: {_dialect_id}. "
            "Converting tolerantly, but field coverage/behavior for this dialect is not guaranteed: "
            + "; ".join(_dialect_deviations),
            dialect_id=_dialect_id,
            deviations=_dialect_deviations,
        )

    carry_diameter = defaults.diameter
    carry_wall = defaults.wall_thickness
    carry_insulation = defaults.insulation_thickness
    carry_corrosion = defaults.corrosion_allowance
    carry_temperature1 = defaults.temperature1
    carry_temperature2 = defaults.temperature2
    carry_temperature3 = defaults.temperature3
    carry_material: float | None = None
    # REL items 13-18 (temp cases 4-9), 19-27 (pressure cases 1-9), 31-32
    # (insulation/fluid density), 36 (hydro pressure) - default 0.0 per spec.
    carry_temperature4 = 0.0
    carry_temperature5 = 0.0
    carry_temperature6 = 0.0
    carry_temperature7 = 0.0
    carry_temperature8 = 0.0
    carry_temperature9 = 0.0
    carry_pressure1 = 0.0
    carry_pressure2 = 0.0
    carry_pressure3 = 0.0
    carry_pressure4 = 0.0
    carry_pressure5 = 0.0
    carry_pressure6 = 0.0
    carry_pressure7 = 0.0
    carry_pressure8 = 0.0
    carry_pressure9 = 0.0
    carry_insulation_density = 0.0
    carry_fluid_density = 0.0
    carry_hydro_pressure = 0.0

    parsed_elements: list[ElementResolved] = []
    parsed_hangers: list[HangerAux] = []
    allowablestress_elements_dropped = 0
    for element in piping_model.findall("PIPINGELEMENT"):
        diameter_raw = _to_float_or_default(element.attrib.get("DIAMETER"), "PIPINGELEMENT/DIAMETER", SENTINEL_MISSING)
        wall_raw = _to_float_or_default(element.attrib.get("WALL_THICK"), "PIPINGELEMENT/WALL_THICK", SENTINEL_MISSING)
        insulation_raw = _to_float_or_default(element.attrib.get("INSUL_THICK"), "PIPINGELEMENT/INSUL_THICK", SENTINEL_MISSING)
        corrosion_raw = _to_float_or_default(element.attrib.get("CORR_ALLOW"), "PIPINGELEMENT/CORR_ALLOW", SENTINEL_MISSING)
        t1_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C1"), "PIPINGELEMENT/TEMP_EXP_C1", SENTINEL_MISSING)
        t2_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C2"), "PIPINGELEMENT/TEMP_EXP_C2", SENTINEL_MISSING)
        t3_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C3"), "PIPINGELEMENT/TEMP_EXP_C3", SENTINEL_MISSING)
        t4_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C4"), "PIPINGELEMENT/TEMP_EXP_C4", SENTINEL_MISSING)
        t5_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C5"), "PIPINGELEMENT/TEMP_EXP_C5", SENTINEL_MISSING)
        t6_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C6"), "PIPINGELEMENT/TEMP_EXP_C6", SENTINEL_MISSING)
        t7_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C7"), "PIPINGELEMENT/TEMP_EXP_C7", SENTINEL_MISSING)
        t8_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C8"), "PIPINGELEMENT/TEMP_EXP_C8", SENTINEL_MISSING)
        t9_raw = _to_float_or_default(element.attrib.get("TEMP_EXP_C9"), "PIPINGELEMENT/TEMP_EXP_C9", SENTINEL_MISSING)
        p1_raw = _to_float_or_default(element.attrib.get("PRESSURE_C1"), "PIPINGELEMENT/PRESSURE_C1", SENTINEL_MISSING)
        p2_raw = _to_float_or_default(element.attrib.get("PRESSURE_C2"), "PIPINGELEMENT/PRESSURE_C2", SENTINEL_MISSING)
        p3_raw = _to_float_or_default(element.attrib.get("PRESSURE_C3"), "PIPINGELEMENT/PRESSURE_C3", SENTINEL_MISSING)
        p4_raw = _to_float_or_default(element.attrib.get("PRESSURE_C4"), "PIPINGELEMENT/PRESSURE_C4", SENTINEL_MISSING)
        p5_raw = _to_float_or_default(element.attrib.get("PRESSURE_C5"), "PIPINGELEMENT/PRESSURE_C5", SENTINEL_MISSING)
        p6_raw = _to_float_or_default(element.attrib.get("PRESSURE_C6"), "PIPINGELEMENT/PRESSURE_C6", SENTINEL_MISSING)
        p7_raw = _to_float_or_default(element.attrib.get("PRESSURE_C7"), "PIPINGELEMENT/PRESSURE_C7", SENTINEL_MISSING)
        p8_raw = _to_float_or_default(element.attrib.get("PRESSURE_C8"), "PIPINGELEMENT/PRESSURE_C8", SENTINEL_MISSING)
        p9_raw = _to_float_or_default(element.attrib.get("PRESSURE_C9"), "PIPINGELEMENT/PRESSURE_C9", SENTINEL_MISSING)
        insul_density_raw = _to_float_or_default(
            element.attrib.get("INSUL_DENSITY"), "PIPINGELEMENT/INSUL_DENSITY", SENTINEL_MISSING
        )
        fluid_density_raw = _to_float_or_default(
            element.attrib.get("FLUID_DENSITY"), "PIPINGELEMENT/FLUID_DENSITY", SENTINEL_MISSING
        )
        hydro_pressure_raw = _to_float_or_default(
            element.attrib.get("HYDRO_PRESSURE"), "PIPINGELEMENT/HYDRO_PRESSURE", SENTINEL_MISSING
        )
        material_raw = _to_float_or_default(
            element.attrib.get("MATERIAL_NUM"),
            "PIPINGELEMENT/MATERIAL_NUM",
            SENTINEL_MISSING,
        )

        if not _is_missing(diameter_raw):
            carry_diameter = diameter_raw
        if not _is_missing(wall_raw):
            carry_wall = wall_raw
        if not _is_missing(insulation_raw):
            carry_insulation = insulation_raw
        if not _is_missing(corrosion_raw):
            carry_corrosion = corrosion_raw
        if not _is_missing(t1_raw):
            carry_temperature1 = t1_raw
        if not _is_missing(t2_raw):
            carry_temperature2 = t2_raw
        if not _is_missing(t3_raw):
            carry_temperature3 = t3_raw
        if not _is_missing(t4_raw):
            carry_temperature4 = t4_raw
        if not _is_missing(t5_raw):
            carry_temperature5 = t5_raw
        if not _is_missing(t6_raw):
            carry_temperature6 = t6_raw
        if not _is_missing(t7_raw):
            carry_temperature7 = t7_raw
        if not _is_missing(t8_raw):
            carry_temperature8 = t8_raw
        if not _is_missing(t9_raw):
            carry_temperature9 = t9_raw
        if not _is_missing(p1_raw):
            carry_pressure1 = p1_raw
        if not _is_missing(p2_raw):
            carry_pressure2 = p2_raw
        if not _is_missing(p3_raw):
            carry_pressure3 = p3_raw
        if not _is_missing(p4_raw):
            carry_pressure4 = p4_raw
        if not _is_missing(p5_raw):
            carry_pressure5 = p5_raw
        if not _is_missing(p6_raw):
            carry_pressure6 = p6_raw
        if not _is_missing(p7_raw):
            carry_pressure7 = p7_raw
        if not _is_missing(p8_raw):
            carry_pressure8 = p8_raw
        if not _is_missing(p9_raw):
            carry_pressure9 = p9_raw
        if not _is_missing(insul_density_raw):
            carry_insulation_density = insul_density_raw
        if not _is_missing(fluid_density_raw):
            carry_fluid_density = fluid_density_raw
        if not _is_missing(hydro_pressure_raw):
            carry_hydro_pressure = hydro_pressure_raw
        if not _is_missing(material_raw):
            carry_material = material_raw
        material_value = carry_material if carry_material is not None else None

        if _has_meaningful_allowablestress(element):
            allowablestress_elements_dropped += 1

        parsed_hangers.extend(_parse_hangers(element))
        parsed_elements.append(
            ElementResolved(
                from_node=_to_float(element.attrib.get("FROM_NODE"), "PIPINGELEMENT/FROM_NODE"),
                to_node=_to_float(element.attrib.get("TO_NODE"), "PIPINGELEMENT/TO_NODE"),
                delta_x=_value_or_default(
                    _to_float_or_default(element.attrib.get("DELTA_X"), "PIPINGELEMENT/DELTA_X", SENTINEL_MISSING),
                    0.0,
                ),
                delta_y=_value_or_default(
                    _to_float_or_default(element.attrib.get("DELTA_Y"), "PIPINGELEMENT/DELTA_Y", SENTINEL_MISSING),
                    0.0,
                ),
                delta_z=_value_or_default(
                    _to_float_or_default(element.attrib.get("DELTA_Z"), "PIPINGELEMENT/DELTA_Z", SENTINEL_MISSING),
                    0.0,
                ),
                diameter=carry_diameter,
                wall_thickness=carry_wall,
                insulation_thickness=carry_insulation,
                corrosion_allowance=carry_corrosion,
                temperature1=carry_temperature1,
                temperature2=carry_temperature2,
                temperature3=carry_temperature3,
                material_id=material_value,
                bend=_parse_bend(element),
                rigid_weight=_parse_rigid_weight(element),
                restraints=_parse_restraints(element),
                sifs=_parse_sifs(element),
                name_from=_safe_text(element.attrib.get("FROM_NAME")),
                name_to=_safe_text(element.attrib.get("TO_NAME")),
                line=_safe_text(element.attrib.get("LINE") or element.attrib.get("LINE_ID")),
                from_coordinate_seed=_parse_node_coordinate_seed(element.attrib, "FROM"),
                to_coordinate_seed=_parse_node_coordinate_seed(element.attrib, "TO"),
                temperature4=carry_temperature4,
                temperature5=carry_temperature5,
                temperature6=carry_temperature6,
                temperature7=carry_temperature7,
                temperature8=carry_temperature8,
                temperature9=carry_temperature9,
                pressure1=carry_pressure1,
                pressure2=carry_pressure2,
                pressure3=carry_pressure3,
                pressure4=carry_pressure4,
                pressure5=carry_pressure5,
                pressure6=carry_pressure6,
                pressure7=carry_pressure7,
                pressure8=carry_pressure8,
                pressure9=carry_pressure9,
                insulation_density=carry_insulation_density,
                fluid_density=carry_fluid_density,
                hydro_pressure=carry_hydro_pressure,
            )
        )

    if not parsed_elements:
        raise ValueError("Input XML does not contain PIPINGELEMENT rows.")

    if allowablestress_elements_dropped:
        # ALLOWABLESTRESS/CASE data (item 10, "Pointer to Allowable Stress
        # Auxiliary field" per the CAESAR II Neutral File spec) is real,
        # per-element source data this engine does not currently parse or
        # emit into #$ ALLOWBLS - unlike DISPLMNT/FLANGES, many of its 153
        # documented values have different meanings depending on the active
        # piping code, which this engine has no way to determine safely.
        # Rather than guess and silently produce wrong allowable-stress
        # data, this is surfaced as a warning so real overrides aren't lost
        # without a trace.
        _warn(
            "ALLOWABLESTRESS_DATA_NOT_EMITTED",
            f"{allowablestress_elements_dropped} element(s) have real (non-placeholder) "
            "ALLOWABLESTRESS/CASE override data in the source InputXML that this converter "
            "does not currently parse or emit into #$ ALLOWBLS - CAESAR will use its own "
            "code-computed allowable stress instead of these overrides.",
            affected_element_count=allowablestress_elements_dropped,
        )

    return ParsedModel(
        job_name=_safe_text(piping_model.attrib.get("JOBNAME")),
        time_text=_parse_time_text(_safe_text(piping_model.attrib.get("TIME"))),
        version_text=_safe_text(root.attrib.get("VERSION")) or "0.0",
        elements=parsed_elements,
        nozzles=_parse_nozzles(root),
        hangers=parsed_hangers,
    )


def _row(values: list[str]) -> str:
    if not values:
        return ""
    widths = [15] + [13] * (len(values) - 1)
    chunks = [f"{values[index]:>{widths[index]}}" for index in range(len(values))]
    return "".join(chunks)


def _length_prefixed_a100(value: str) -> str:
    text = _safe_text(value)[:100]
    return f"{'':7}{len(text):5d} {text:<100}"


def _format_auto_float(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"Non-finite numeric value encountered: {value}")
    absolute = abs(value)
    if absolute < 1e-12:
        return "0.000000"
    if absolute >= 1e9:
        return f"{value:.6E}"
    if absolute < 0.1:
        return f"{value:.6E}"
    return f"{value:#.6G}"


def _format_fixed_float(value: float, decimals: int) -> str:
    if not math.isfinite(value):
        raise ValueError(f"Non-finite numeric value encountered: {value}")
    return f"{value:.{decimals}f}"


def _format_sig6(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError(f"Non-finite numeric value encountered: {value}")
    absolute = abs(value)
    if absolute < 1e-12:
        return "0.000000"
    if absolute >= 1e9 or absolute < 1e-6:
        return f"{value:.6E}"
    if absolute < 1.0:
        return f"{value:.6f}"
    integer_digits = len(str(int(absolute)))
    # CAESAR II requires at least one decimal digit to recognize a fixed
    # ELEMENTS-block numeric field as being in the file's working unit
    # (mm); a bare integer with no decimal point is silently reinterpreted
    # at a different magnitude (assumed as m). Below 6 integer digits this
    # was already guaranteed by the 6-significant-figure budget; at 6+
    # integer digits decimals hit exactly 0 and a bare integer (e.g.
    # "210164") slipped out - min 1 closes that gap without changing
    # anything below that threshold.
    decimals = max(1, 6 - integer_digits)
    return f"{value:.{decimals}f}"


def _section_header(name: str, suffixes: dict[str, str]) -> str:
    return f"#$ {name}{suffixes.get(name, '')}"


def _default_2019_layout_config() -> dict[str, object]:
    return {
        "compatibility": {
            "raw_override_mode": RAW_OVERRIDE_MODE_SCHEMA,
        },
        "version": {},
        "elements": {
            "row3": ["0.000000", "0.000000", "0.000000", "0.000000", "0.000000", "0.000000"],
            "row4": ["10.0000", "30.0000", "0.000000", "0.000000", "0.000000", "0.000000"],
            "row5": ["0.000000", "0.000000", "0.000000", "0.000000", "0.000000", "0.000000"],
            "row6": ["0.499901E-04", "0.965312E-03", "0.000000", "0.000000", "0.000000", "15.0000"],
            "row7": ["0.000000", "0.000000", "0.000000", "0.000000", "0.000000", "0.000000"],
            "row8": ["0.000000", "0.000000", "0.000000", "0.000000", "9999.99", "9999.99"],
            "row9": ["0.000000", "0.000000", "0.000000", "0.000000", "0.000000"],
            "row10": ["0"],
            "row11": ["-1", "-1"],
            "row12": ["{bend}", "{rigid}", "0", "{restraint}", "0", "0"],
            "row13": ["0", "0", "0", "0", "{sif}", "{nodename}"],
            "row14": ["{reducer}", "0", "0"],
            "line_label": {
                "mode": "zero",
                "pointer_start": 0,
                "label_index_start": 1,
                "label_prefix": "LINENO",
                "label_width": 1,
                "default_line": "0",
                "to_node_template": "{to_node}",
                "line_labels": [],
            },
        },
        "nodename": {
            "mode": "auto",
            "auto_prefix": "N",
            "nonam_count": 0,
            "from_label": "PS-XXX",
            "to_label": "PS-XXX",
            "from_labels": [],
            "to_labels": [],
            "to_node_labels": {},
        },
        "control": {
            "line1": ["{elements}", "{nozzles}", "{hangers}", "{nonam}", "{reducers}", "{flanges}"],
            "line2": ["{bends}", "{rigids}", "{expjts}", "{restraints}", "{displmnt}", "{forcmnt}"],
            "line3": ["{uniform}", "{wind}", "{offsets}", "{allowbls}", "{sifs}", "0"],
            "line4": ["{equipmnt}"],
        },
        "bend": {
            "row2": ["{angle3}", "{node3}", "{num_miter}", "{fitting_thickness}", "{kfactor}", "0.000000"],
            "row3": ["0.000000", "0.000000"],
        },
        "rigid": {},
        "restraint": {
            "line1": ["{node}", "{type}", "{stiffness}", "{gap}", "{friction}", "{connecting_node}"],
            "line2": ["{xcos}", "{ycos}", "{zcos}"],
            "mapping_policy": RESTRAINT_MAPPING_POLICY_IDENTITY,
            "explicit_type_map": {},
            "stiffness_default_token": "0.175120E+13",
            "type_direction_cosines": {
                "1": ["0.000000", "0.000000", "0.000000"],
                "2": ["1.00000", "0.000000", "0.000000"],
                "3": ["0.000000", "1.00000", "0.000000"],
                "4": ["0.000000", "0.000000", "1.00000"],
                "13": ["1.00000", "0.000000", "0.000000"],
                "14": ["0.000000", "1.00000", "0.000000"],
                "15": ["0.000000", "0.000000", "1.00000"],
                "16": ["1.00000", "0.000000", "0.000000"],
                "17": ["0.000000", "1.00000", "0.000000"],
                "18": ["0.000000", "0.000000", "1.00000"],
            },
            "tail_lines": [
                "            0",
                "            0",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000",
                "            0",
                "            0",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000",
                "            0",
                "            0",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000",
                "            0",
                "            0",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000",
                "            0",
                "            0",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000",
                "            0",
                "            0",
            ],
        },
        "sections": {
            "include_nodename": True,
            "include_flanges": True,
            "include_equipmnt": True,
        },
        "displmnt": {
            "node_ids": [],
            "auto_from_equipmnt_nodes": True,
            "block_lines": [
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "      0.000000",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
                "    9999.99      9999.99      9999.99      9999.99      9999.99      9999.99",
            ],
        },
        "allowbls": {
            "lines": [
                "      0.000000     0.000000     0.000000     0.000000      1.00000      1.00000",
                "      1.00000     0.000000     0.000000      9999.99     0.000000      3.00000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      1.00000      1.00000      1.00000      1.00000      1.00000      1.00000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000      1.00000     0.000000      1.00000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000     0.000000     0.000000     0.000000",
                "      0.000000     0.000000     0.000000",
            ]
        },
        "flanges": {
            "include_section": True,
        },
        "equipmnt": {
            "entries": [],
        },
        "miscel_1": {
            "material": {
                "source": "xml",
                "fallback_default": "0.000",
                "format_decimals": 3,
            },
            "nozzles": {
                "source": "xml",
                "type_indicator": {
                    "WRC_297_NOZZLE": "0.000000",
                    "API650_NOZZLE": "1.000000",
                    "PD5500_NOZZLE": "2.000000",
                    "CUSTOM_NOZZLE": "3.000000",
                },
                "defaults": {
                    "infinity": "9999.99",
                    "spare": "0.000000",
                    "displacement_vector": "0.000000",
                },
                "entries": [],
            },
            "hangers": {
                "source": "xml",
                "defaults": {
                    "table": "1",
                    "load_variation": "25.0000",
                    "rigid_support": "0.000000",
                    "max_travel": "9999.99",
                    "cold_load": "0.000000",
                    "hot_load": "0.000000",
                    "free_anchor1": "0",
                    "free_anchor2": "0",
                    "dof_type1": "0",
                    "default_support_node": "0",
                    "default_connecting_node": "0",
                    "num_hgr": "0",
                    "short_range": "0",
                    "stiffness": "0.000000",
                    "operating_load": "0.000000",
                    "hardware_weight": "0.000000",
                    "const_eff_load": "0.000000",
                    "available_space": "9999.99",
                    "multi_lc": "0",
                },
                "entries": [],
            },
            "execution_options": {
                "print_forces": 0,
                "print_alphas": 0,
                "bourdon": 0,
                "branch_prompts": 2,
                "thermal_bowing_delta_temp": 0.0,
                "use_liberal_stress": 0,
                "uniform_load_in_g": 0,
                "stress_stiffening": 0.0,
                "ambient_temp": 21.0,
                "frp_expansion_times_1e6": 21.6,
                "optimizer": 0,
                "next_node_selection": 0,
                "final_ordering": 0,
                "collins_ordering": 0,
                "degree_determination": 0,
                "user_control": 0,
                "frp_shear_ratio": 0.25,
                "laminate_type": 3,
                "north_arrow": 0,
            },
            # Legacy compatibility keys retained. Typed sections above take precedence.
            "material_id_default": "0.000",
            "material_ids": [],
            "execution_lines": [
                "              0            0            0            2       0.0000            0",
                "              0            0      21.0000      21.6000            0            0",
                "              0            0            0            0       0.2500            3",
                "              0",
            ],
        },
        "coords": {
            "mode": "discontinuous_starts",
            "node_ids": [],
            "origin_offset": ["0.0", "0.0", "0.0"],
            "decimals": 4,
        },
        "units": {
            "numeric_lines": [
                # CAESAR import requires real conversion constants; all-zero
                # units can pass text conversion and still create a corrupt C2.
                "        25.4000      4.44822     0.453592     0.112985     0.112985      6.89476",
                "       0.555556     -17.7778      6.89476      6.89476 2.768000E-02 2.768000E-02",
                "   2.768000E-02      1.75127     0.112985      1.75127      1.00000      6.89476",
                "   2.540000E-02      25.4000      25.4000      25.4000",
            ],
            "text_lines": [
                "  SI (mm)        ",
                "  on ",
                "  mm.",
                "  N. ",
                "  Kg.",
                "  N.m.  ",
                "  N.m.. ",
                "  KPa       ",
                "  C",
                "  C",
                "  KPa       ",
                "  KPa       ",
                "  kg.cu.cm. ",
                "  kg.cu.cm. ",
                "  kg.cu.cm. ",
                "  N./cm. ",
                "  N.m./deg  ",
                "  N./cm. ",
                "  g's",
                "  Kpa       ",
                "  m. ",
                "  mm.",
                "  mm.",
                "  mm.",
            ],
        },
    }


def _load_2019_layout_config() -> dict[str, object]:
    config = _default_2019_layout_config()
    config_path = Path(__file__).resolve().parent / DEFAULT_2019_CONFIG_FILE
    if not config_path.is_file():
        return config
    loaded = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Invalid 2019 config: expected object at {config_path}.")
    _merge_2019_layout_config(config, loaded)
    return config


def _merge_2019_layout_config(target: dict[str, object], source: dict[str, object]) -> None:
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _merge_2019_layout_config(target[key], value)
            continue
        target[key] = value


def _as_object(value: object, field_path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"Invalid 2019 layout config: '{field_path}' must be an object.")
    return value


def _as_string_list(value: object, field_path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Invalid 2019 layout config: '{field_path}' must be an array.")
    return [str(entry) for entry in value]


def _parse_compatibility_config(layout_config: dict[str, object]) -> CompatibilityConfig:
    compatibility_cfg_raw = layout_config.get("compatibility", {})
    compatibility_cfg = _as_object(compatibility_cfg_raw, "compatibility")
    raw_override_mode = str(
        compatibility_cfg.get("raw_override_mode", RAW_OVERRIDE_MODE_SCHEMA)
    ).strip()
    if raw_override_mode not in (RAW_OVERRIDE_MODE_SCHEMA, RAW_OVERRIDE_MODE_COMPATIBILITY):
        raise ValueError(
            "Invalid 2019 layout config: 'compatibility.raw_override_mode' must be "
            f"'{RAW_OVERRIDE_MODE_SCHEMA}' or '{RAW_OVERRIDE_MODE_COMPATIBILITY}'."
        )
    return CompatibilityConfig(raw_override_mode=raw_override_mode)


def _is_compatibility_mode(compatibility: CompatibilityConfig) -> bool:
    return compatibility.raw_override_mode == RAW_OVERRIDE_MODE_COMPATIBILITY


def _validate_raw_overrides_allowed(
    compatibility: CompatibilityConfig,
    override_name: str,
    has_override: bool,
) -> None:
    if has_override and not _is_compatibility_mode(compatibility):
        raise ValueError(
            "Raw override usage is disabled in schema-validated mode. "
            f"Set compatibility.raw_override_mode='{RAW_OVERRIDE_MODE_COMPATIBILITY}' "
            f"to use '{override_name}'."
        )


def _parse_restraint_mapping_policy(restraint_cfg: dict[str, object]) -> RestraintTypeMappingPolicy:
    policy = str(restraint_cfg.get("mapping_policy", RESTRAINT_MAPPING_POLICY_IDENTITY)).strip()
    if policy not in (RESTRAINT_MAPPING_POLICY_IDENTITY, RESTRAINT_MAPPING_POLICY_EXPLICIT):
        raise ValueError(
            "Invalid 2019 layout config: 'restraint.mapping_policy' must be "
            f"'{RESTRAINT_MAPPING_POLICY_IDENTITY}' or '{RESTRAINT_MAPPING_POLICY_EXPLICIT}'."
        )
    explicit_type_map_raw = restraint_cfg.get("explicit_type_map", {})
    explicit_type_map_obj = _as_object(explicit_type_map_raw, "restraint.explicit_type_map")
    explicit_type_map: dict[str, str] = {
        str(source_key): str(mapped_value)
        for source_key, mapped_value in explicit_type_map_obj.items()
    }
    return RestraintTypeMappingPolicy(policy=policy, explicit_type_map=explicit_type_map)


def _resolve_restraint_type_token(
    source_type_token: str,
    mapping_policy: RestraintTypeMappingPolicy,
) -> str:
    if mapping_policy.policy == RESTRAINT_MAPPING_POLICY_IDENTITY:
        return source_type_token
    return mapping_policy.explicit_type_map.get(source_type_token, source_type_token)


def _build_section_payload_model(
    version: list[str],
    control: list[str],
    elements: list[str],
    nodename: list[str],
    bend: list[str],
    rigid: list[str],
    restrant: list[str],
    displmnt: list[str],
    allowbls: list[str],
    sif_tees: list[str],
    reducers: list[str],
    equipmnt: list[str],
    miscel_1: list[str],
    units: list[str],
    coords: list[str],
) -> SectionPayloadModel:
    return SectionPayloadModel(
        version=[str(line) for line in version],
        control=[str(line) for line in control],
        elements=[str(line) for line in elements],
        aux_data=[],
        nodename=[str(line) for line in nodename],
        bend=[str(line) for line in bend],
        rigid=[str(line) for line in rigid],
        expjt=[],
        restrant=[str(line) for line in restrant],
        displmnt=[str(line) for line in displmnt],
        forcmnt=[],
        uniform=[],
        wind=[],
        offsets=[],
        allowbls=[str(line) for line in allowbls],
        sif_tees=[str(line) for line in sif_tees],
        reducers=[str(line) for line in reducers],
        flanges=[],
        equipmnt=[str(line) for line in equipmnt],
        miscel_1=[str(line) for line in miscel_1],
        units=[str(line) for line in units],
        coords=[str(line) for line in coords],
    )


def _serialize_sections(
    payload_model: SectionPayloadModel,
    include_nodename: bool,
    include_flanges: bool,
) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = [
        ("VERSION", payload_model.version),
        ("CONTROL", payload_model.control),
        ("ELEMENTS", payload_model.elements),
        ("AUX_DATA", payload_model.aux_data),
    ]
    if include_nodename:
        sections.append(("NODENAME", payload_model.nodename))
    sections.extend(
        [
            ("BEND", payload_model.bend),
            ("RIGID", payload_model.rigid),
            ("EXPJT", payload_model.expjt),
            ("RESTRANT", payload_model.restrant),
            ("DISPLMNT", payload_model.displmnt),
            ("FORCMNT", payload_model.forcmnt),
            ("UNIFORM", payload_model.uniform),
            ("WIND", payload_model.wind),
            ("OFFSETS", payload_model.offsets),
            ("ALLOWBLS", payload_model.allowbls),
            ("SIF&TEES", payload_model.sif_tees),
            ("REDUCERS", payload_model.reducers),
        ]
    )
    if include_flanges:
        sections.append(("FLANGES", payload_model.flanges))
    sections.extend(
        [
            ("EQUIPMNT", payload_model.equipmnt),
            ("MISCEL_1", payload_model.miscel_1),
            ("UNITS", payload_model.units),
            ("COORDS", payload_model.coords),
        ]
    )
    return sections


def _render_control_line(template: list[str], metrics: dict[str, int]) -> str:
    rendered: list[str] = []
    for token in template:
        current = token
        for name, value in metrics.items():
            current = current.replace(f"{{{name}}}", str(value))
        rendered.append(current)
    return _row(rendered)


def _render_length_prefixed_label(label: str) -> str:
    """Render an ELEMENTS Element-Name / Line-Number row per the neutral file spec.

    Spec (CAESAR II User's Guide, External Interfaces, ELEMENTS section):
    format (7X, I5, 1X, A500) where "The value before the string indicates
    the LENGTH of the string" - it is NOT a pointer or element index.
    Verified against every vendor benchmark with non-blank labels
    (e.g. "           5 Valve", "          18 16\"-W7810049-13421",
    "           7 LINENO1"): the integer always equals len(label).
    Writing anything else makes CAESAR read the wrong number of characters
    (an element index of 0 reads an empty line number; 1 reads "P" of
    "PL-XX"; etc.), which presented as "Line No not propagated / not
    consistent" in real CAESAR imports.
    """
    text = str(label or "").strip()
    if not text:
        return f"{0:12d} "
    return f"{len(text):12d} {text}"


def _render_label_line(label_index: int, label_prefix: str, label_width: int) -> str:
    label_value = f"{label_prefix}{label_index:0{label_width}d}"
    return _render_length_prefixed_label(label_value)


def _render_element_label_payload(value: object) -> str:
    """Render an ELEMENTS Element-Name / Line-Number row from a configured payload.

    Config payloads historically stored these rows as "<number> <label>" under
    the (incorrect) belief that the number was a pointer. Per the neutral file
    spec the number is the label's string length, so the prefix is now always
    re-derived from the label text and never trusted from the config: legacy
    payloads whose prefix already equals the label length (all
    benchmark-derived ones, e.g. "10 unassigned", "7 LINENO1") are
    byte-stable, while payloads carrying a stale pointer-style prefix are
    silently corrected instead of making CAESAR read a wrong-length string.
    """
    text = str(value).strip()
    if not text:
        return f"{0:12d} "
    parts = text.split(maxsplit=1)
    try:
        int(parts[0])
    except ValueError:
        # No numeric prefix: the whole payload is the label itself.
        return _render_length_prefixed_label(text)
    if len(parts) == 1:
        # Bare number with no label: a blank-label row (length 0).
        return f"{0:12d} "
    return _render_length_prefixed_label(parts[1])


# NODENAME record layout per the neutral file spec: FORTRAN (2X, A10, 16X,
# A10) - FROM name at columns 3-12, TO name at columns 29-38. Every vendor
# benchmark with node names confirms the column positions (FROM at col 3, TO
# at col 29) and shows the writer padding each line to 53 characters, with
# names longer than 10 characters allowed to overflow the A10 field into the
# following gap (e.g. "PS-171001.1", "17-VBL-20012"). The FROM field
# therefore has 26 usable columns (3-28) and the TO field 25 (29-53).
_NODENAME_FROM_FIELD_WIDTH: Final[int] = 26
_NODENAME_TO_FIELD_WIDTH: Final[int] = 25


def _format_nodename_pair(from_label: str, to_label: str) -> str:
    from_text = _safe_text(from_label)
    to_text = _safe_text(to_label)
    if len(from_text) > _NODENAME_FROM_FIELD_WIDTH:
        _warn(
            "NODENAME_LABEL_TRUNCATED",
            f"FROM node name {from_text!r} exceeds the {_NODENAME_FROM_FIELD_WIDTH}-column NODENAME field and was truncated.",
            label=from_text,
        )
        from_text = from_text[:_NODENAME_FROM_FIELD_WIDTH]
    if len(to_text) > _NODENAME_TO_FIELD_WIDTH:
        _warn(
            "NODENAME_LABEL_TRUNCATED",
            f"TO node name {to_text!r} exceeds the {_NODENAME_TO_FIELD_WIDTH}-column NODENAME field and was truncated.",
            label=to_text,
        )
        to_text = to_text[:_NODENAME_TO_FIELD_WIDTH]
    return "  " + from_text.ljust(_NODENAME_FROM_FIELD_WIDTH) + to_text.ljust(_NODENAME_TO_FIELD_WIDTH)


def _render_tokens_row(template: list[str], values: dict[str, int]) -> str:
    rendered: list[str] = []
    for token in template:
        current = token
        for name, value in values.items():
            current = current.replace(f"{{{name}}}", str(value))
        rendered.append(current)
    return _row(rendered)


def _render_template_row(template: list[str], values: dict[str, str]) -> str:
    rendered: list[str] = []
    for token in template:
        current = token
        for name, value in values.items():
            current = current.replace(f"{{{name}}}", value)
        rendered.append(current)
    return _row(rendered)


def _read_universal_version_payload_from_template() -> list[str]:
    # Keep runtime defaults self-contained. Benchmark/template files are optional
    # mapping inputs and must not be required for default value generation.
    return list(UNIVERSAL_VERSION_PREFIX_FALLBACK)


def _build_universal_version_payload() -> list[str]:
    global UNIVERSAL_VERSION_PAYLOAD_CACHE
    if UNIVERSAL_VERSION_PAYLOAD_CACHE is None:
        UNIVERSAL_VERSION_PAYLOAD_CACHE = _read_universal_version_payload_from_template()
    return list(UNIVERSAL_VERSION_PAYLOAD_CACHE)


def _apply_universal_version_prefix(payload: list[str], prefix_lines: int) -> list[str]:
    result = list(payload)
    if prefix_lines <= 0:
        return result
    universal_payload = _build_universal_version_payload()
    if not universal_payload:
        return result
    lines_to_apply = min(prefix_lines, len(result), len(universal_payload))
    for index in range(lines_to_apply):
        result[index] = universal_payload[index]
    return result


def _build_version_payload(model: ParsedModel) -> list[str]:
    payload: list[str] = []
    payload.append(
        _row(
            [
                _format_fixed_float(4.0, 5),
                _format_fixed_float(4.5, 5),
                _format_fixed_float(0.0, 6),
                _format_fixed_float(0.0, 6),
            ]
        )
    )
    payload.append(f"  DateTime: {model.time_text}")
    payload.append("  Source: CAESARII Input XML")
    payload.append(f"  Version: {model.version_text} ({DEFAULT_VERSION_HEADER})")
    payload.append("  UserName: ")
    payload.append("  Purpose: Converted from CAESARII Input XML")
    payload.append(f"  ProjectName: {Path(model.job_name).stem if model.job_name else ''}")
    payload.append("  MDBName: ")
    payload.append("  Converted CII Output")

    while len(payload) < VERSION_PAYLOAD_LINES:
        payload.append("  ")
    if len(payload) > VERSION_PAYLOAD_LINES:
        payload = payload[:VERSION_PAYLOAD_LINES]
    return payload


def _format_node_id(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 1e-6:
        return str(int(rounded))
    return _format_auto_float(value)


def _coordinate_mismatch(left: NodeCoordinate, right: NodeCoordinate, tolerance: float) -> bool:
    return (
        abs(left.x - right.x) > tolerance
        or abs(left.y - right.y) > tolerance
        or abs(left.z - right.z) > tolerance
    )


def _merge_coordinate_seed(
    coordinates: dict[float, NodeCoordinate],
    node: float,
    seed: NodeCoordinate | None,
    tolerance: float,
    source_label: str,
) -> None:
    if seed is None:
        return
    existing = coordinates.get(node)
    if existing is None:
        coordinates[node] = seed
        return
    if _coordinate_mismatch(existing, seed, tolerance):
        raise ValueError(
            "Inconsistent absolute coordinate seed for node "
            f"{_format_node_id(node)} from {source_label}. "
            f"Existing=({existing.x:.6f}, {existing.y:.6f}, {existing.z:.6f}), "
            f"Seed=({seed.x:.6f}, {seed.y:.6f}, {seed.z:.6f})."
        )


def _build_absolute_coordinates(
    elements: list[ElementResolved],
    tolerance: float,
    required_nodes: set[float] | None = None,
) -> dict[float, NodeCoordinate]:
    # required_nodes narrows which nodes' reconstructed coordinates actually
    # need to agree across redundant paths. It does not change which nodes
    # get reconstructed (the BFS below still walks the whole graph, since a
    # required node may only be reachable through others) - it only changes
    # what happens when two paths to the SAME node disagree beyond
    # tolerance. When required_nodes is None (the "all_nodes" COORDS mode),
    # behavior is unchanged: any disagreement anywhere raises. When a node
    # set is given (a narrow COORDS mode that only emits a handful of
    # nodes), a disagreement on a node that will never be emitted is kept
    # at its first-seen value instead of aborting the whole conversion -
    # the emitted COORDS payload never has ambiguous data because only
    # required_nodes' own coordinates (which still raise on disagreement)
    # ever get selected for output.
    adjacency: dict[float, list[tuple[float, float, float, float]]] = {}
    for element in elements:
        from_node = element.from_node
        to_node = element.to_node
        dx = element.delta_x
        dy = element.delta_y
        dz = element.delta_z

        adjacency.setdefault(from_node, []).append((to_node, dx, dy, dz))
        adjacency.setdefault(to_node, []).append((from_node, -dx, -dy, -dz))

    coordinates: dict[float, NodeCoordinate] = {}
    for element in elements:
        _merge_coordinate_seed(
            coordinates,
            element.from_node,
            element.from_coordinate_seed,
            tolerance,
            f"element {_format_node_id(element.from_node)}->{_format_node_id(element.to_node)} FROM",
        )
        _merge_coordinate_seed(
            coordinates,
            element.to_node,
            element.to_coordinate_seed,
            tolerance,
            f"element {_format_node_id(element.from_node)}->{_format_node_id(element.to_node)} TO",
        )

    queue: list[float] = sorted(coordinates.keys())
    visited: set[float] = set()
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        current_coord = coordinates[current]
        for neighbor, dx, dy, dz in adjacency.get(current, []):
            candidate = NodeCoordinate(
                x=current_coord.x + dx,
                y=current_coord.y + dy,
                z=current_coord.z + dz,
            )
            if neighbor not in coordinates:
                coordinates[neighbor] = candidate
                queue.append(neighbor)
                continue

            existing = coordinates[neighbor]
            if _coordinate_mismatch(existing, candidate, tolerance):
                if required_nodes is not None and neighbor not in required_nodes:
                    continue
                raise ValueError(
                    "Inconsistent coordinate reconstruction for node "
                    f"{_format_node_id(neighbor)} via edge "
                    f"{_format_node_id(current)} -> {_format_node_id(neighbor)}. "
                    f"Existing=({existing.x:.6f}, {existing.y:.6f}, {existing.z:.6f}), "
                    f"Candidate=({candidate.x:.6f}, {candidate.y:.6f}, {candidate.z:.6f})."
                )

    for seed_node in sorted(adjacency.keys()):
        if seed_node in coordinates:
            continue

        coordinates[seed_node] = NodeCoordinate(x=0.0, y=0.0, z=0.0)
        queue: list[float] = [seed_node]

        while queue:
            current = queue.pop()
            current_coord = coordinates[current]
            for neighbor, dx, dy, dz in adjacency[current]:
                candidate = NodeCoordinate(
                    x=current_coord.x + dx,
                    y=current_coord.y + dy,
                    z=current_coord.z + dz,
                )
                if neighbor not in coordinates:
                    coordinates[neighbor] = candidate
                    queue.append(neighbor)
                    continue

                existing = coordinates[neighbor]
                if (
                    abs(existing.x - candidate.x) > tolerance
                    or abs(existing.y - candidate.y) > tolerance
                    or abs(existing.z - candidate.z) > tolerance
                ):
                    if required_nodes is not None and neighbor not in required_nodes:
                        continue
                    raise ValueError(
                        "Inconsistent coordinate reconstruction for node "
                        f"{_format_node_id(neighbor)} via edge "
                        f"{_format_node_id(current)} -> {_format_node_id(neighbor)}. "
                        f"Existing=({existing.x:.6f}, {existing.y:.6f}, {existing.z:.6f}), "
                        f"Candidate=({candidate.x:.6f}, {candidate.y:.6f}, {candidate.z:.6f})."
                    )

    return coordinates


def _build_coords_payload(elements: list[ElementResolved], tolerance: float) -> list[str]:
    coordinates = _build_absolute_coordinates(elements, tolerance=tolerance)
    payload: list[str] = [_row([str(len(coordinates))])]
    for node in sorted(coordinates.keys()):
        coord = coordinates[node]
        payload.append(
            _row(
                [
                    _format_node_id(node),
                    _format_fixed_float(coord.x, 4),
                    _format_fixed_float(coord.y, 4),
                    _format_fixed_float(coord.z, 4),
                ]
            )
        )
    return payload


def _parse_fixed_i13_row(line: str, fields: int) -> list[int]:
    widths = [15] + [13] * (fields - 1)
    values: list[int] = []
    offset = 0
    for width in widths:
        token = line[offset : offset + width].strip()
        offset += width
        if not token:
            values.append(0)
            continue
        values.append(int(float(token)))
    return values


def _load_reference_element_overrides(path: Path, expected_elements: int) -> ReferenceElementOverrides:
    lines = path.read_text(encoding="utf-8", errors="strict").splitlines()
    required_sections = (
        "VERSION",
        "CONTROL",
        "ELEMENTS",
        "AUX_DATA",
        "NODENAME",
        "BEND",
        "RIGID",
        "REDUCERS",
        "MISCEL_1",
        "COORDS",
    )
    section_indices: dict[str, int] = {}
    for index, raw_line in enumerate(lines):
        normalized = re.sub(r"\s+", " ", raw_line.strip())
        for section_name in required_sections:
            if normalized == f"#$ {section_name}" and section_name not in section_indices:
                section_indices[section_name] = index
                break
    missing_sections = [name for name in required_sections if name not in section_indices]
    if missing_sections:
        raise ValueError(f"Reference CII is missing required section(s): {', '.join(missing_sections)}")

    version_index = section_indices["VERSION"]
    control_index = section_indices["CONTROL"]
    elements_index = section_indices["ELEMENTS"]
    aux_index = section_indices["AUX_DATA"]
    nodename_index = section_indices["NODENAME"]
    bend_index = section_indices["BEND"]
    rigid_index = section_indices["RIGID"]
    reducers_index = section_indices["REDUCERS"]
    miscel_index = section_indices["MISCEL_1"]
    coords_index = section_indices["COORDS"]

    version_payload = lines[version_index + 1 : control_index]
    control_line_1 = _parse_fixed_i13_row(lines[control_index + 1], fields=5)
    nonam_count = control_line_1[3]

    element_lines = lines[elements_index + 1 : aux_index]
    if expected_elements <= 0:
        raise ValueError("Expected element count must be positive for reference alignment.")
    if len(element_lines) % expected_elements != 0:
        raise ValueError(
            "Reference CII ELEMENTS section size does not divide by expected element count: "
            f"{len(element_lines)} lines for {expected_elements} elements."
        )
    element_block_size = len(element_lines) // expected_elements
    if element_block_size < 9:
        raise ValueError(
            "Reference CII ELEMENTS block size is unsupported; expected at least 9 lines per element."
        )
    reference_elements = expected_elements

    pointers: list[int] = []
    for element_index in range(reference_elements):
        row8 = element_lines[element_index * element_block_size + 7]
        row8_values = _parse_fixed_i13_row(row8, fields=6)
        pointers.append(row8_values[5])

    nodename_payload = lines[nodename_index + 1 : bend_index]
    bend_payload = lines[bend_index + 1 : rigid_index]
    reducers_payload = lines[reducers_index + 1 : miscel_index]
    coords_payload = lines[coords_index + 1 :]
    return ReferenceElementOverrides(
        version_payload=version_payload,
        nonam_count=nonam_count,
        node_name_pointers=pointers,
        nodename_payload=nodename_payload,
        bend_payload=bend_payload,
        reducers_payload=reducers_payload,
        coords_payload=coords_payload,
    )


def _restraint_type_from_input(restraint: RestraintAux) -> float:
    if not _is_missing(restraint.type_code):
        if abs(restraint.type_code) < 1e-9:
            return 1.0
        return restraint.type_code
    return 1.0


def _validate_restraint_type(value: float, edge_index: int, slot: int) -> float:
    if not math.isfinite(value):
        raise ValueError(
            f"Invalid RESTRANT type for element {edge_index + 1}, slot {slot}: non-finite value {value}."
        )
    rounded = int(round(value))
    if abs(value - rounded) > 1e-6 or rounded < 1 or rounded > 62:
        raise ValueError(
            f"Invalid RESTRANT type for element {edge_index + 1}, slot {slot}: "
            f"{value}. Expected integer 1..62."
        )
    return float(rounded)


def _restraint_line2_cosines(restraint: RestraintAux) -> tuple[float, float, float]:
    if _is_missing(restraint.xcos) and _is_missing(restraint.ycos) and _is_missing(restraint.zcos):
        return 0.0, 0.0, 0.0
    x = 0.0 if _is_missing(restraint.xcos) else restraint.xcos
    y = 0.0 if _is_missing(restraint.ycos) else restraint.ycos
    z = 0.0 if _is_missing(restraint.zcos) else restraint.zcos
    return x, y, z


def _empty_restraint_numeric_lines(
    line1_template: list[str],
    line2_template: list[str],
    stiffness_token: str | None = None,
) -> list[str]:
    zero = _format_sig6(0.0)
    # Empty DOF slots carry node/type 0; AVEVA fills the stiffness column with the
    # default token (CAESAR ignores stiffness for node-0 slots). Default to that
    # token so generated blocks match the benchmark byte-for-byte in this column.
    stiff = stiffness_token if stiffness_token is not None else zero
    return [
        _render_template_row(
            line1_template,
            {
                "node": zero,
                "type": zero,
                "stiffness": stiff,
                "gap": zero,
                "friction": zero,
                "connecting_node": zero,
            },
        ),
        _render_template_row(
            line2_template,
            {
                "xcos": zero,
                "ycos": zero,
                "zcos": zero,
            },
        ),
    ]


def _slot_restraints_for_aux_block(restraints: list[RestraintAux], edge_index: int) -> list[RestraintAux | None]:
    slots: list[RestraintAux | None] = [None] * RESTRAINT_SLOTS_PER_AUX

    for restraint in restraints:
        slot_index = restraint.slot - 1
        if slot_index < 0 or slot_index >= RESTRAINT_SLOTS_PER_AUX:
            raise ValueError(
                f"Invalid RESTRAINT/NUM for element {edge_index + 1}: {restraint.slot}. "
                f"Expected 1..{RESTRAINT_SLOTS_PER_AUX}."
            )
        if slots[slot_index] is not None:
            raise ValueError(
                f"Duplicate RESTRAINT/NUM for element {edge_index + 1}: slot {restraint.slot}."
            )
        slots[slot_index] = restraint

    return slots


def _infer_reducer_indices(
    elements: list[ElementResolved],
    defaults: ConverterDefaults,
    infer_angle_from_geometry: bool,
) -> tuple[dict[int, int], list[tuple[float, float]]]:
    edge_to_reducer_index: dict[int, int] = {}
    reducers: list[tuple[float, float]] = []

    for index in range(len(elements) - 1):
        current = elements[index]
        following = elements[index + 1]
        if abs(current.to_node - following.from_node) > 1e-6:
            continue
        # Skip wrap/loop transition segments; they often represent run jumps,
        # not physical reducers.
        if following.to_node < following.from_node - 1e-6:
            continue
        if abs(current.diameter - following.diameter) <= 1e-6:
            continue

        # Geometry (DELTA_X/Y/Z + the diameters either side of the reducer) is
        # real data already present in the source InputXML. Previously that
        # data was only used when the "Infer Reducer Angle From Geometry"
        # checkbox was explicitly ticked; otherwise every detected reducer
        # was silently forced to Default Reducer Angle (0 by default),
        # discarding an angle that could be computed from the file itself.
        # Now geometry wins whenever it is computable and the user hasn't
        # explicitly configured a non-zero override; a configured default is
        # still honored (explicit intent), and the checkbox still forces
        # geometry to win over a configured default too.
        run = math.sqrt(
            current.delta_x * current.delta_x
            + current.delta_y * current.delta_y
            + current.delta_z * current.delta_z
        )
        geometry_angle = None
        if run > 1e-9:
            geometry_angle = math.degrees(
                math.atan(abs(following.diameter - current.diameter) / (2.0 * run))
            )

        if geometry_angle is not None and (infer_angle_from_geometry or defaults.reducer_angle <= 0.0):
            angle_value = geometry_angle
        else:
            angle_value = defaults.reducer_angle
        reducers.append((following.diameter, angle_value))
        edge_to_reducer_index[index] = len(reducers)

    return edge_to_reducer_index, reducers


def _format_float_list(values: list[str]) -> list[str]:
    return [str(entry) for entry in values]


def _build_bend_payload(
    elements: list[ElementResolved],
    layout_config: dict[str, object],
) -> tuple[list[str], dict[int, int]]:
    bend_cfg = layout_config.get("bend", {})
    if not isinstance(bend_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'bend' must be an object.")
    row2_template = list(bend_cfg.get("row2", ["{angle3}", "{node3}", "{num_miter}", "{fitting_thickness}", "{kfactor}", "0.000000"]))
    row3_values = _format_float_list(list(bend_cfg.get("row3", ["0.000000", "0.000000"])))
    fitting_thickness_default = float(bend_cfg.get("fitting_thickness_default", 0.0))
    fitting_thickness_default_when_zero = bool(bend_cfg.get("fitting_thickness_default_when_zero", False))
    kfactor_default = float(bend_cfg.get("kfactor_default", 0.0))
    kfactor_default_when_zero = bool(bend_cfg.get("kfactor_default_when_zero", False))

    payload: list[str] = []
    edge_to_bend_index: dict[int, int] = {}
    for edge_index, element in enumerate(elements):
        bend = element.bend
        if bend is None:
            continue
        edge_to_bend_index[edge_index] = (len(payload) // 3) + 1
        payload.append(
            _row(
                [
                    _format_sig6(_value_or_default(bend.radius, 0.0)),
                    _format_sig6(_value_or_default(bend.type_code, 0.0)),
                    _format_sig6(_value_or_default(bend.angle1, 0.0)),
                    _format_sig6(_value_or_default(bend.node1, 0.0)),
                    _format_sig6(_value_or_default(bend.angle2, 0.0)),
                    _format_sig6(_value_or_default(bend.node2, 0.0)),
                ]
            )
        )
        payload.append(
            _render_template_row(
                row2_template,
                {
                    "angle3": _format_sig6(_value_or_default(bend.angle3, 0.0)),
                    "node3": _format_sig6(_value_or_default(bend.node3, 0.0)),
                    "num_miter": _format_sig6(_value_or_default(bend.num_miter, 0.0)),
                    "fitting_thickness": _format_sig6(
                        fitting_thickness_default
                        if (fitting_thickness_default_when_zero and abs(_value_or_default(bend.fitting_thickness, 0.0)) < 1e-9)
                        else _value_or_default(bend.fitting_thickness, fitting_thickness_default)
                    ),
                    "kfactor": _format_sig6(
                        kfactor_default
                        if (kfactor_default_when_zero and abs(_value_or_default(bend.kfactor, 0.0)) < 1e-9)
                        else _value_or_default(bend.kfactor, kfactor_default)
                    ),
                },
            )
        )
        payload.append(_row(row3_values))
    return payload, edge_to_bend_index


def _build_rigid_payload(elements: list[ElementResolved]) -> tuple[list[str], dict[int, int]]:
    payload: list[str] = []
    edge_to_rigid_index: dict[int, int] = {}
    for edge_index, element in enumerate(elements):
        if element.rigid_weight is None:
            continue
        edge_to_rigid_index[edge_index] = len(payload) + 1
        payload.append(_row([_format_sig6(_value_or_default(element.rigid_weight, 0.0))]))
    return payload, edge_to_rigid_index


def _build_restraint_payload(
    elements: list[ElementResolved],
    layout_config: dict[str, object],
    compatibility: CompatibilityConfig,
) -> tuple[list[str], dict[int, int]]:
    restraint_cfg = layout_config.get("restraint", {})
    if not isinstance(restraint_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'restraint' must be an object.")
    line1_template = list(restraint_cfg.get("line1", ["{node}", "{type}", "{stiffness}", "{gap}", "{friction}", "{connecting_node}"]))
    line2_template = list(restraint_cfg.get("line2", ["{xcos}", "{ycos}", "{zcos}"]))
    mapping_policy = _parse_restraint_mapping_policy(restraint_cfg)
    legacy_type_map = restraint_cfg.get("type_map")
    if legacy_type_map is not None:
        if not isinstance(legacy_type_map, dict):
            raise ValueError("Invalid 2019 layout config: 'restraint.type_map' must be an object when provided.")
        if legacy_type_map:
            _validate_raw_overrides_allowed(compatibility, "restraint.type_map", has_override=True)
            mapping_policy = RestraintTypeMappingPolicy(
                policy=RESTRAINT_MAPPING_POLICY_EXPLICIT,
                explicit_type_map={str(k): str(v) for k, v in legacy_type_map.items()},
            )
    type_direction_cfg = restraint_cfg.get("type_direction_cosines", {})
    if not isinstance(type_direction_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'restraint.type_direction_cosines' must be an object.")
    stiffness_default_token = str(restraint_cfg.get("stiffness_default_token", DEFAULT_STIFFNESS_TOKEN))
    # Never-zero guard: a 0 / non-positive / unparseable default stiffness would
    # make CAESAR treat the restraint as absent. Coerce to the rigid default and
    # record a diagnostic instead of silently emitting a broken model.
    try:
        _stiffness_default_value = float(stiffness_default_token)
    except (TypeError, ValueError):
        _stiffness_default_value = None
    if _stiffness_default_value is None or not math.isfinite(_stiffness_default_value) or _stiffness_default_value <= 0.0:
        _warn(
            "RESTRAINT_STIFFNESS_ZERO_COERCED",
            f"restraint.stiffness_default_token {stiffness_default_token!r} is not a usable stiffness "
            f"(must be a positive number); using the CAESAR rigid default {DEFAULT_STIFFNESS_TOKEN} instead.",
            supplied=stiffness_default_token,
        )
        stiffness_default_token = DEFAULT_STIFFNESS_TOKEN
    payload: list[str] = []
    edge_to_restraint_index: dict[int, int] = {}

    for edge_index, element in enumerate(elements):
        if not element.restraints:
            continue
        slots = _slot_restraints_for_aux_block(element.restraints, edge_index)
        edge_to_restraint_index[edge_index] = (len(payload) // RESTRAINT_LINES_PER_AUX_BLOCK) + 1

        for slot_index, restraint in enumerate(slots):
            if restraint is None:
                # Empty slot: two zero numeric lines + two empty A100 name lines,
                # emitted together so each slot is a contiguous 4-line block
                # (CAESAR II expects line1, line2, tag, guid per DOF slot).
                payload.extend(_empty_restraint_numeric_lines(
                    line1_template, line2_template, stiffness_default_token))
                payload.append(_length_prefixed_a100(""))
                payload.append(_length_prefixed_a100(""))
                continue

            original_type = _restraint_type_from_input(restraint)
            if abs(original_type - round(original_type)) < 1e-6:
                original_type_key = str(int(round(original_type)))
            else:
                original_type_key = _format_sig6(original_type)
            mapped_type_token = _resolve_restraint_type_token(original_type_key, mapping_policy)
            restraint_type = _validate_restraint_type(float(mapped_type_token), edge_index, slot_index + 1)
            stiffness_token = (
                stiffness_default_token
                if _is_missing(restraint.stiffness)
                else _format_sig6(restraint.stiffness)
            )
            gap = _value_or_default(restraint.gap, 0.0)
            friction = _value_or_default(restraint.friction, 0.0)
            connecting_node = _value_or_default(restraint.connecting_node, 0.0)
            xcos, ycos, zcos = _restraint_line2_cosines(restraint)
            if _is_missing(restraint.xcos) and _is_missing(restraint.ycos) and _is_missing(restraint.zcos):
                fallback_cos = type_direction_cfg.get(mapped_type_token) or type_direction_cfg.get(str(int(restraint_type)))
                if isinstance(fallback_cos, list) and len(fallback_cos) == 3:
                    xcos = float(fallback_cos[0])
                    ycos = float(fallback_cos[1])
                    zcos = float(fallback_cos[2])

            payload.append(
                _render_template_row(
                    line1_template,
                    {
                        "node": _format_sig6(restraint.node),
                        "type": _format_sig6(restraint_type),
                        "stiffness": stiffness_token,
                        "gap": _format_sig6(gap),
                        "friction": _format_sig6(friction),
                        "connecting_node": _format_sig6(connecting_node),
                    },
                )
            )
            payload.append(
                _render_template_row(
                    line2_template,
                    {
                        "xcos": _format_sig6(xcos),
                        "ycos": _format_sig6(ycos),
                        "zcos": _format_sig6(zcos),
                    },
                )
            )
            payload.append(_length_prefixed_a100(restraint.tag))
            payload.append(_length_prefixed_a100(restraint.guid))

    return payload, edge_to_restraint_index


def _build_sif_payload(elements: list[ElementResolved]) -> tuple[list[str], dict[int, int]]:
    payload: list[str] = []
    edge_to_sif_index: dict[int, int] = {}
    for edge_index, element in enumerate(elements):
        if not element.sifs:
            continue
        edge_to_sif_index[edge_index] = (len(payload) // 10) + 1
        first_node = element.sifs[0].node
        payload.append(
            _row(
                [
                    _format_auto_float(first_node),
                    _format_fixed_float(0.0, 6),
                    _format_fixed_float(0.0, 6),
                    _format_fixed_float(0.0, 6),
                    _format_fixed_float(0.0, 6),
                    _format_fixed_float(0.0, 6),
                ]
            )
        )
        zero_row = _row(
            [
                _format_fixed_float(0.0, 6),
                _format_fixed_float(0.0, 6),
                _format_fixed_float(0.0, 6),
                _format_fixed_float(0.0, 6),
                _format_fixed_float(0.0, 6),
                _format_fixed_float(0.0, 6),
            ]
        )
        for _ in range(9):
            payload.append(zero_row)
    return payload, edge_to_sif_index


def _build_equipmnt_payload(layout_config: dict[str, object]) -> tuple[list[str], list[float]]:
    equip_cfg = layout_config.get("equipmnt", {})
    if not isinstance(equip_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'equipmnt' must be an object.")
    entries = equip_cfg.get("entries", [])
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise ValueError("Invalid 2019 layout config: 'equipmnt.entries' must be an array.")

    payload: list[str] = []
    nodes: list[float] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid 2019 layout config: each equipmnt entry must be an object.")
        node_raw = entry.get("node", "0")
        node_value = float(node_raw)
        nodes.append(node_value)

        row1_values = [str(node_raw)] + [str(token) for token in list(entry.get("row1", []))]
        row2_values = [str(token) for token in list(entry.get("row2", []))]
        row3_values = [str(token) for token in list(entry.get("row3", []))]
        row4_values = [str(token) for token in list(entry.get("row4", []))]
        row5_values = [str(token) for token in list(entry.get("row5", []))]
        row6_values = [str(token) for token in list(entry.get("row6", []))]
        payload.extend(
            [
                _row(row1_values),
                _row(row2_values),
                _row(row3_values),
                _row(row4_values),
                _row(row5_values),
                _row(row6_values),
            ]
        )
    return payload, nodes


def _build_displmnt_payload(layout_config: dict[str, object], equipmnt_nodes: list[float]) -> tuple[list[str], list[float]]:
    displmnt_cfg = layout_config.get("displmnt", {})
    if not isinstance(displmnt_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'displmnt' must be an object.")
    node_ids = displmnt_cfg.get("node_ids", [])
    if node_ids is None:
        node_ids = []
    if not isinstance(node_ids, list):
        raise ValueError("Invalid 2019 layout config: 'displmnt.node_ids' must be an array.")

    nodes: list[float] = [float(node) for node in node_ids]
    if not nodes and bool(displmnt_cfg.get("auto_from_equipmnt_nodes", True)):
        nodes = list(equipmnt_nodes)

    block_lines = [str(entry) for entry in list(displmnt_cfg.get("block_lines", []))]
    payload: list[str] = []
    for node in nodes:
        payload.append(_row([_format_fixed_float(node, 4)]))
        payload.extend(block_lines)
    return payload, nodes


def _build_allowbls_payload(layout_config: dict[str, object]) -> list[str]:
    allow_cfg = layout_config.get("allowbls", {})
    if not isinstance(allow_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'allowbls' must be an object.")
    return [str(entry) for entry in list(allow_cfg.get("lines", []))]


def _format_misc_int(value: float, field_name: str) -> str:
    rounded = int(round(value))
    if abs(value - rounded) > 1e-6:
        raise ValueError(f"Invalid integer-like value for '{field_name}': {value}")
    return str(rounded)


def _parse_misc_float(value: object, field_name: str) -> float:
    text = _safe_text(str(value))
    if not text:
        raise ValueError(f"Missing numeric value for '{field_name}'.")
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for '{field_name}': '{text}'.") from exc


def _parse_optional_misc_float(value: object | None, field_name: str, fallback: float) -> float:
    if value is None:
        return fallback
    text = _safe_text(str(value))
    if not text:
        return fallback
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid numeric value for '{field_name}': '{text}'.") from exc


def _chunk_rows(values: list[str], width: int) -> list[str]:
    rows: list[str] = []
    for start in range(0, len(values), width):
        rows.append(_row(values[start : start + width]))
    return rows


def _first_attr(attributes: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        value = _safe_text(attributes.get(candidate))
        if value:
            return value
    return None


def _resolve_nozzle_kind(kind_raw: str) -> str:
    kind = _safe_text(kind_raw).upper()
    if kind in ("WRC_297", "WRC", "WRC297", "WRC_297_NOZZLE"):
        return "WRC_297_NOZZLE"
    if kind in ("API650", "API_650", "API650_NOZZLE", "API650_NOZ", "API650_NOZZLE"):
        return "API650_NOZZLE"
    if kind in ("PD5500", "PD_5500", "PD5500_NOZZLE"):
        return "PD5500_NOZZLE"
    if kind in ("CUSTOM", "CUSTOM_NOZZLE"):
        return "CUSTOM_NOZZLE"
    return kind


def _build_vflex_values_from_attributes(
    kind: str,
    attributes: dict[str, str],
    type_indicator_tokens: dict[str, str],
    nozzle_defaults: dict[str, object],
) -> list[str]:
    type_token = str(type_indicator_tokens.get(kind, "0.000000"))
    spare_token = str(nozzle_defaults.get("spare", "0.000000"))
    infinity_token = str(nozzle_defaults.get("infinity", "9999.99"))
    disp_vector_token = str(nozzle_defaults.get("displacement_vector", "0.000000"))

    def pick_float(field: str, aliases: tuple[str, ...], default_token: str) -> str:
        value = _first_attr(attributes, aliases)
        if value is None:
            return _format_sig6(_parse_misc_float(default_token, field))
        parsed = _parse_misc_float(value, field)
        if _is_missing(parsed):
            parsed = _parse_misc_float(default_token, field)
        return _format_sig6(parsed)

    values: list[str] = [spare_token] * 22
    values[0] = pick_float("nozzle_node", ("NOZZLE_NODE", "NOZ_NODE", "NODE", "NODE1"), "0.000000")
    values[1] = pick_float("vessel_node", ("VESSEL_NODE", "TANK_NODE", "NODE2"), "0.000000")
    values[2] = _format_sig6(_parse_misc_float(type_token, "nozzle_type_indicator"))

    if kind == "API650_NOZZLE":
        values[3] = pick_float("nozzle_od", ("NOZ_OD", "NOZZLE_OD", "OD"), spare_token)
        values[4] = pick_float("nozzle_wt", ("NOZ_WT", "NOZZLE_WT", "WT"), spare_token)
        values[5] = pick_float("tank_od", ("TANK_OD", "VESSEL_OD"), spare_token)
        values[6] = pick_float("tank_wt", ("TANK_WT", "VESSEL_WT"), spare_token)
        values[7] = spare_token
        values[8] = pick_float("reinforce", ("REINFORCE",), spare_token)
        values[9] = pick_float("nozzle_height", ("NOZ_HEIGHT", "NOZZLE_HEIGHT"), spare_token)
        values[10] = pick_float("fluid_height", ("FLUID_HEIGHT",), spare_token)
        values[11] = pick_float("displacement_vector", ("DISP_VECTOR",), disp_vector_token)
        values[12] = pick_float("fluid_sg", ("FLUID_SG",), "1.000000")
        values[13] = pick_float("thermal_exp_coeff", ("THERM_EXP_COEFF",), spare_token)
        values[14] = pick_float("delta_t", ("DELTAT", "DELTA_T"), spare_token)
        values[15] = pick_float("emod", ("EMOD",), spare_token)
    else:
        # Generic mapping for WRC/PD5500/CUSTOM nozzle families.
        values[3] = pick_float("nozzle_od", ("NOZ_OD", "NOZZLE_OD", "OD"), spare_token)
        values[4] = pick_float("nozzle_wt", ("NOZ_WT", "NOZZLE_WT", "WT"), spare_token)
        values[5] = pick_float("vessel_od", ("VESSEL_OD", "TANK_OD"), spare_token)
        values[6] = pick_float("vessel_wt", ("VESSEL_WT", "TANK_WT"), spare_token)
        values[7] = pick_float("value8", ("VALUE8", "PAD_THK", "REINF_PAD_THK"), spare_token)
        values[8] = pick_float("value9", ("VALUE9", "REINFORCE"), spare_token)
        values[9] = pick_float("value10", ("VALUE10",), spare_token)
        values[10] = pick_float("value11", ("VALUE11",), spare_token)
        values[11] = pick_float("value12", ("VALUE12", "VCOS_X", "VEC_X"), spare_token)
        values[12] = pick_float("value13", ("VALUE13", "VCOS_Y", "VEC_Y"), spare_token)
        values[13] = pick_float("value14", ("VALUE14", "VCOS_Z", "VEC_Z"), spare_token)
        values[14] = pick_float("value15", ("VALUE15", "DELTAT", "DELTA_T"), spare_token)
        values[15] = pick_float("value16", ("VALUE16", "EMOD"), spare_token)

    for index in range(16, 22):
        values[index] = spare_token

    return values


def _build_vflex_lines(model: ParsedModel, miscel_cfg: dict[str, object]) -> list[str]:
    nozzle_cfg_raw = miscel_cfg.get("nozzles", {})
    nozzle_cfg = _as_object(nozzle_cfg_raw, "miscel_1.nozzles") if nozzle_cfg_raw is not None else {}
    source = str(nozzle_cfg.get("source", "xml")).strip().lower()
    if source not in ("xml", "manual", "none"):
        raise ValueError("Invalid 2019 layout config: 'miscel_1.nozzles.source' must be xml, manual, or none.")

    type_indicators_raw = nozzle_cfg.get("type_indicator", {})
    type_indicators_cfg = _as_object(type_indicators_raw, "miscel_1.nozzles.type_indicator") if type_indicators_raw is not None else {}
    type_indicators = {
        "WRC_297_NOZZLE": str(type_indicators_cfg.get("WRC_297_NOZZLE", "0.000000")),
        "API650_NOZZLE": str(type_indicators_cfg.get("API650_NOZZLE", "1.000000")),
        "PD5500_NOZZLE": str(type_indicators_cfg.get("PD5500_NOZZLE", "2.000000")),
        "CUSTOM_NOZZLE": str(type_indicators_cfg.get("CUSTOM_NOZZLE", "3.000000")),
    }
    nozzle_defaults_raw = nozzle_cfg.get("defaults", {})
    nozzle_defaults = _as_object(nozzle_defaults_raw, "miscel_1.nozzles.defaults") if nozzle_defaults_raw is not None else {}

    entries_raw = nozzle_cfg.get("entries", [])
    if entries_raw is None:
        entries_raw = []
    if not isinstance(entries_raw, list):
        raise ValueError("Invalid 2019 layout config: 'miscel_1.nozzles.entries' must be an array.")

    records: list[NozzleAux] = []
    if source == "xml":
        records.extend(model.nozzles)

    for index, entry in enumerate(entries_raw):
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid 2019 layout config: miscel_1.nozzles.entries[{index}] must be an object.")
        kind = _resolve_nozzle_kind(str(entry.get("kind", "CUSTOM_NOZZLE")))
        attributes: dict[str, str] = {}
        for key, value in entry.items():
            if key == "kind":
                continue
            if isinstance(value, (list, dict)):
                attributes[str(key)] = json.dumps(value)
            else:
                attributes[str(key)] = _safe_text(str(value))
        records.append(NozzleAux(kind=kind, attributes=attributes))

    if source == "none":
        records = []

    lines: list[str] = []
    for index, nozzle in enumerate(records):
        values_override = nozzle.attributes.get("values")
        if values_override:
            try:
                parsed_override = json.loads(values_override)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid 2019 layout config: miscel_1.nozzles entry {index} has non-JSON 'values'."
                ) from exc
            if not isinstance(parsed_override, list):
                raise ValueError(
                    f"Invalid 2019 layout config: miscel_1.nozzles entry {index} 'values' must be an array."
                )
            values = [_format_sig6(_parse_misc_float(token, f"miscel_1.nozzles.entries[{index}].values")) for token in parsed_override]
        else:
            values = _build_vflex_values_from_attributes(
                kind=nozzle.kind,
                attributes=nozzle.attributes,
                type_indicator_tokens=type_indicators,
                nozzle_defaults=nozzle_defaults,
            )
        if len(values) != 22:
            raise ValueError(
                f"Invalid 2019 layout config: nozzle entry {index} must resolve to exactly 22 values."
            )
        lines.extend(_chunk_rows(values, 6))
    return lines


def _build_hanger_lines(model: ParsedModel, miscel_cfg: dict[str, object]) -> list[str]:
    hanger_cfg_raw = miscel_cfg.get("hangers", {})
    hanger_cfg = _as_object(hanger_cfg_raw, "miscel_1.hangers") if hanger_cfg_raw is not None else {}
    source = str(hanger_cfg.get("source", "xml")).strip().lower()
    if source not in ("xml", "manual", "none"):
        raise ValueError("Invalid 2019 layout config: 'miscel_1.hangers.source' must be xml, manual, or none.")

    defaults_raw = hanger_cfg.get("defaults", {})
    defaults = _as_object(defaults_raw, "miscel_1.hangers.defaults") if defaults_raw is not None else {}
    entries_raw = hanger_cfg.get("entries", [])
    if entries_raw is None:
        entries_raw = []
    if not isinstance(entries_raw, list):
        raise ValueError("Invalid 2019 layout config: 'miscel_1.hangers.entries' must be an array.")

    hangers: list[HangerAux] = []
    if source == "xml":
        hangers.extend(model.hangers)

    for index, entry in enumerate(entries_raw):
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid 2019 layout config: miscel_1.hangers.entries[{index}] must be an object.")
        hangers.append(
            HangerAux(
                node=_parse_optional_misc_float(entry.get("node"), f"miscel_1.hangers.entries[{index}].node", SENTINEL_MISSING),
                stiffness=_parse_optional_misc_float(entry.get("stiffness"), f"miscel_1.hangers.entries[{index}].stiffness", SENTINEL_MISSING),
                load_variation=_parse_optional_misc_float(entry.get("load_variation"), f"miscel_1.hangers.entries[{index}].load_variation", SENTINEL_MISSING),
                operating_load=_parse_optional_misc_float(entry.get("operating_load"), f"miscel_1.hangers.entries[{index}].operating_load", SENTINEL_MISSING),
                rigid_support=_parse_optional_misc_float(entry.get("rigid_support"), f"miscel_1.hangers.entries[{index}].rigid_support", SENTINEL_MISSING),
                available_space=_parse_optional_misc_float(entry.get("available_space"), f"miscel_1.hangers.entries[{index}].available_space", SENTINEL_MISSING),
                cold_load=_parse_optional_misc_float(entry.get("cold_load"), f"miscel_1.hangers.entries[{index}].cold_load", SENTINEL_MISSING),
                hot_load=_parse_optional_misc_float(entry.get("hot_load"), f"miscel_1.hangers.entries[{index}].hot_load", SENTINEL_MISSING),
                max_travel=_parse_optional_misc_float(entry.get("max_travel"), f"miscel_1.hangers.entries[{index}].max_travel", SENTINEL_MISSING),
                hardware_weight=_parse_optional_misc_float(entry.get("hardware_weight"), f"miscel_1.hangers.entries[{index}].hardware_weight", SENTINEL_MISSING),
                const_eff_load=_parse_optional_misc_float(entry.get("const_eff_load"), f"miscel_1.hangers.entries[{index}].const_eff_load", SENTINEL_MISSING),
                multi_lc=_parse_optional_misc_float(entry.get("multi_lc"), f"miscel_1.hangers.entries[{index}].multi_lc", SENTINEL_MISSING),
                free_anchor1=_parse_optional_misc_float(entry.get("free_anchor1"), f"miscel_1.hangers.entries[{index}].free_anchor1", SENTINEL_MISSING),
                free_anchor2=_parse_optional_misc_float(entry.get("free_anchor2"), f"miscel_1.hangers.entries[{index}].free_anchor2", SENTINEL_MISSING),
                dof_type1=_parse_optional_misc_float(entry.get("dof_type1"), f"miscel_1.hangers.entries[{index}].dof_type1", SENTINEL_MISSING),
                num_hgr=_parse_optional_misc_float(entry.get("num_hgr"), f"miscel_1.hangers.entries[{index}].num_hgr", SENTINEL_MISSING),
                hgr_table=_parse_optional_misc_float(entry.get("hgr_table"), f"miscel_1.hangers.entries[{index}].hgr_table", SENTINEL_MISSING),
                short_range=_parse_optional_misc_float(entry.get("short_range"), f"miscel_1.hangers.entries[{index}].short_range", SENTINEL_MISSING),
                connecting_node=_parse_optional_misc_float(entry.get("connecting_node"), f"miscel_1.hangers.entries[{index}].connecting_node", SENTINEL_MISSING),
                tag=_safe_text(str(entry.get("tag", ""))),
                guid=_safe_text(str(entry.get("guid", ""))),
            )
        )

    if source == "none":
        hangers = []
    if not hangers:
        return []

    default_line1 = _row(
        [
            _format_misc_int(_parse_optional_misc_float(defaults.get("table"), "miscel_1.hangers.defaults.table", 0.0), "miscel_1.hangers.defaults.table"),
            _format_sig6(_parse_optional_misc_float(defaults.get("load_variation"), "miscel_1.hangers.defaults.load_variation", 0.0)),
            _format_sig6(_parse_optional_misc_float(defaults.get("rigid_support"), "miscel_1.hangers.defaults.rigid_support", 0.0)),
            _format_sig6(_parse_optional_misc_float(defaults.get("max_travel"), "miscel_1.hangers.defaults.max_travel", 9999.99)),
            _format_sig6(_parse_optional_misc_float(defaults.get("cold_load"), "miscel_1.hangers.defaults.cold_load", 0.0)),
            _format_sig6(_parse_optional_misc_float(defaults.get("hot_load"), "miscel_1.hangers.defaults.hot_load", 0.0)),
        ]
    )
    default_line2 = _row(
        [
            _format_misc_int(_parse_optional_misc_float(defaults.get("free_anchor1"), "miscel_1.hangers.defaults.free_anchor1", 0.0), "miscel_1.hangers.defaults.free_anchor1"),
            _format_misc_int(_parse_optional_misc_float(defaults.get("free_anchor2"), "miscel_1.hangers.defaults.free_anchor2", 0.0), "miscel_1.hangers.defaults.free_anchor2"),
            _format_misc_int(_parse_optional_misc_float(defaults.get("dof_type1"), "miscel_1.hangers.defaults.dof_type1", 0.0), "miscel_1.hangers.defaults.dof_type1"),
            _format_misc_int(_parse_optional_misc_float(defaults.get("default_support_node"), "miscel_1.hangers.defaults.default_support_node", 0.0), "miscel_1.hangers.defaults.default_support_node"),
            _format_misc_int(_parse_optional_misc_float(defaults.get("default_connecting_node"), "miscel_1.hangers.defaults.default_connecting_node", 0.0), "miscel_1.hangers.defaults.default_connecting_node"),
        ]
    )

    def value_or_default(raw: float, default_value: float) -> float:
        return default_value if _is_missing(raw) else raw

    lines: list[str] = [default_line1, default_line2]
    ihgrnode_tokens: list[str] = []
    ihgrnum_tokens: list[str] = []
    ihgrtable_tokens: list[str] = []
    ihgrshort_tokens: list[str] = []
    ihgrcn_tokens: list[str] = []

    for index, hanger in enumerate(hangers):
        node_value = value_or_default(hanger.node, 0.0)
        ihgrnode_tokens.append(_format_sig6(node_value))
        ihgrnum_tokens.append(
            _format_misc_int(
                value_or_default(hanger.num_hgr, _parse_optional_misc_float(defaults.get("num_hgr"), "miscel_1.hangers.defaults.num_hgr", 0.0)),
                f"miscel_1.hangers[{index}].num_hgr",
            )
        )
        ihgrtable_tokens.append(
            _format_misc_int(
                value_or_default(hanger.hgr_table, _parse_optional_misc_float(defaults.get("table"), "miscel_1.hangers.defaults.table", 1.0)),
                f"miscel_1.hangers[{index}].hgr_table",
            )
        )
        ihgrshort_tokens.append(
            _format_misc_int(
                value_or_default(hanger.short_range, _parse_optional_misc_float(defaults.get("short_range"), "miscel_1.hangers.defaults.short_range", 0.0)),
                f"miscel_1.hangers[{index}].short_range",
            )
        )
        ihgrcn_tokens.append(_format_sig6(value_or_default(hanger.connecting_node, 0.0)))

        hgrdat_1 = [
            _format_sig6(value_or_default(hanger.stiffness, _parse_optional_misc_float(defaults.get("stiffness"), "miscel_1.hangers.defaults.stiffness", 0.0))),
            _format_sig6(value_or_default(hanger.load_variation, _parse_optional_misc_float(defaults.get("load_variation"), "miscel_1.hangers.defaults.load_variation", 0.0))),
            _format_sig6(value_or_default(hanger.rigid_support, _parse_optional_misc_float(defaults.get("rigid_support"), "miscel_1.hangers.defaults.rigid_support", 0.0))),
            _format_sig6(value_or_default(hanger.available_space, _parse_optional_misc_float(defaults.get("available_space"), "miscel_1.hangers.defaults.available_space", 9999.99))),
            _format_sig6(value_or_default(hanger.cold_load, _parse_optional_misc_float(defaults.get("cold_load"), "miscel_1.hangers.defaults.cold_load", 0.0))),
            _format_sig6(value_or_default(hanger.hot_load, _parse_optional_misc_float(defaults.get("hot_load"), "miscel_1.hangers.defaults.hot_load", 0.0))),
        ]
        hgrdat_2 = [
            _format_sig6(value_or_default(hanger.operating_load, _parse_optional_misc_float(defaults.get("operating_load"), "miscel_1.hangers.defaults.operating_load", 0.0))),
            _format_sig6(value_or_default(hanger.max_travel, _parse_optional_misc_float(defaults.get("max_travel"), "miscel_1.hangers.defaults.max_travel", 9999.99))),
            _format_misc_int(value_or_default(hanger.multi_lc, _parse_optional_misc_float(defaults.get("multi_lc"), "miscel_1.hangers.defaults.multi_lc", 0.0)), f"miscel_1.hangers[{index}].multi_lc"),
            _format_sig6(value_or_default(hanger.hardware_weight, _parse_optional_misc_float(defaults.get("hardware_weight"), "miscel_1.hangers.defaults.hardware_weight", 0.0))),
            _format_sig6(value_or_default(hanger.const_eff_load, _parse_optional_misc_float(defaults.get("const_eff_load"), "miscel_1.hangers.defaults.const_eff_load", 0.0))),
        ]
        lines.append(_row(hgrdat_1))
        lines.append(_row(hgrdat_2))
        lines.append(_length_prefixed_a100(hanger.tag))
        lines.append(_length_prefixed_a100(hanger.guid))
        lines.append(
            _row(
                [
                    _format_misc_int(value_or_default(hanger.free_anchor1, _parse_optional_misc_float(defaults.get("free_anchor1"), "miscel_1.hangers.defaults.free_anchor1", 0.0)), f"miscel_1.hangers[{index}].free_anchor1"),
                    _format_misc_int(value_or_default(hanger.free_anchor2, _parse_optional_misc_float(defaults.get("free_anchor2"), "miscel_1.hangers.defaults.free_anchor2", 0.0)), f"miscel_1.hangers[{index}].free_anchor2"),
                    _format_misc_int(value_or_default(hanger.dof_type1, _parse_optional_misc_float(defaults.get("dof_type1"), "miscel_1.hangers.defaults.dof_type1", 0.0)), f"miscel_1.hangers[{index}].dof_type1"),
                    _format_misc_int(value_or_default(hanger.connecting_node, _parse_optional_misc_float(defaults.get("default_support_node"), "miscel_1.hangers.defaults.default_support_node", 0.0)), f"miscel_1.hangers[{index}].support_node"),
                ]
            )
        )

    lines.extend(_chunk_rows(ihgrnode_tokens, 6))
    lines.extend(_chunk_rows(ihgrnum_tokens, 6))
    lines.extend(_chunk_rows(ihgrtable_tokens, 6))
    lines.extend(_chunk_rows(ihgrshort_tokens, 6))
    lines.extend(_chunk_rows(ihgrcn_tokens, 6))
    return lines


def _build_execution_option_lines(miscel_cfg: dict[str, object]) -> list[str]:
    execution_cfg_raw = miscel_cfg.get("execution_options")
    if execution_cfg_raw is None:
        legacy_lines = _as_string_list(miscel_cfg.get("execution_lines", []), "miscel_1.execution_lines")
        return legacy_lines
    execution_cfg = _as_object(execution_cfg_raw, "miscel_1.execution_options")

    line1 = _row(
        [
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("print_forces"), "miscel_1.execution_options.print_forces", 0.0), "miscel_1.execution_options.print_forces"),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("print_alphas"), "miscel_1.execution_options.print_alphas", 0.0), "miscel_1.execution_options.print_alphas"),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("bourdon"), "miscel_1.execution_options.bourdon", 0.0), "miscel_1.execution_options.bourdon"),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("branch_prompts"), "miscel_1.execution_options.branch_prompts", 2.0), "miscel_1.execution_options.branch_prompts"),
            _format_sig6(_parse_optional_misc_float(execution_cfg.get("thermal_bowing_delta_temp"), "miscel_1.execution_options.thermal_bowing_delta_temp", 0.0)),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("use_liberal_stress"), "miscel_1.execution_options.use_liberal_stress", 0.0), "miscel_1.execution_options.use_liberal_stress"),
        ]
    )
    line2 = _row(
        [
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("uniform_load_in_g"), "miscel_1.execution_options.uniform_load_in_g", 0.0), "miscel_1.execution_options.uniform_load_in_g"),
            _format_sig6(_parse_optional_misc_float(execution_cfg.get("stress_stiffening"), "miscel_1.execution_options.stress_stiffening", 0.0)),
            _format_sig6(_parse_optional_misc_float(execution_cfg.get("ambient_temp"), "miscel_1.execution_options.ambient_temp", 21.0)),
            _format_sig6(_parse_optional_misc_float(execution_cfg.get("frp_expansion_times_1e6"), "miscel_1.execution_options.frp_expansion_times_1e6", 21.6)),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("optimizer"), "miscel_1.execution_options.optimizer", 0.0), "miscel_1.execution_options.optimizer"),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("next_node_selection"), "miscel_1.execution_options.next_node_selection", 0.0), "miscel_1.execution_options.next_node_selection"),
        ]
    )
    line3 = _row(
        [
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("final_ordering"), "miscel_1.execution_options.final_ordering", 0.0), "miscel_1.execution_options.final_ordering"),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("collins_ordering"), "miscel_1.execution_options.collins_ordering", 0.0), "miscel_1.execution_options.collins_ordering"),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("degree_determination"), "miscel_1.execution_options.degree_determination", 0.0), "miscel_1.execution_options.degree_determination"),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("user_control"), "miscel_1.execution_options.user_control", 0.0), "miscel_1.execution_options.user_control"),
            _format_sig6(_parse_optional_misc_float(execution_cfg.get("frp_shear_ratio"), "miscel_1.execution_options.frp_shear_ratio", 0.25)),
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("laminate_type"), "miscel_1.execution_options.laminate_type", 3.0), "miscel_1.execution_options.laminate_type"),
        ]
    )
    line4 = _row(
        [
            _format_misc_int(_parse_optional_misc_float(execution_cfg.get("north_arrow"), "miscel_1.execution_options.north_arrow", 0.0), "miscel_1.execution_options.north_arrow"),
        ]
    )
    return [line1, line2, line3, line4]


def _count_misc_records(
    model_records_count: int,
    miscel_cfg: dict[str, object],
    group_name: str,
) -> int:
    group_raw = miscel_cfg.get(group_name, {})
    group_cfg = _as_object(group_raw, f"miscel_1.{group_name}") if group_raw is not None else {}
    source = str(group_cfg.get("source", "xml")).strip().lower()
    entries_raw = group_cfg.get("entries", [])
    if entries_raw is None:
        entries_raw = []
    if not isinstance(entries_raw, list):
        raise ValueError(f"Invalid 2019 layout config: 'miscel_1.{group_name}.entries' must be an array.")
    if source == "none":
        return 0
    if source == "xml":
        return model_records_count + len(entries_raw)
    if source == "manual":
        return len(entries_raw)
    raise ValueError(f"Invalid 2019 layout config: 'miscel_1.{group_name}.source' must be xml, manual, or none.")


def _build_miscel_payload(model: ParsedModel, miscel_cfg: dict[str, object]) -> list[str]:
    material_cfg_raw = miscel_cfg.get("material", {})
    material_cfg = _as_object(material_cfg_raw, "miscel_1.material") if material_cfg_raw is not None else {}
    material_source = str(material_cfg.get("source", "xml")).strip().lower()
    if material_source not in ("xml", "manual", "legacy"):
        raise ValueError("Invalid 2019 layout config: 'miscel_1.material.source' must be xml, manual, or legacy.")
    material_fallback_token = str(
        material_cfg.get(
            "fallback_default",
            miscel_cfg.get("material_id_default", "0.000"),
        )
    )
    material_decimals = int(material_cfg.get("format_decimals", 3))

    material_ids_legacy = _as_string_list(miscel_cfg.get("material_ids", []), "miscel_1.material_ids")
    material_values: list[str] = []
    if material_source in ("manual", "legacy"):
        material_values = [str(token) for token in material_ids_legacy]
    else:
        for element in model.elements:
            if element.material_id is None or _is_missing(element.material_id):
                fallback_value = _parse_misc_float(material_fallback_token, "miscel_1.material.fallback_default")
                material_values.append(_format_fixed_float(fallback_value, material_decimals))
            else:
                material_values.append(_format_fixed_float(element.material_id, material_decimals))
        if material_ids_legacy:
            # Legacy explicit list takes precedence when provided.
            material_values = [str(token) for token in material_ids_legacy]

    if len(material_values) > len(model.elements):
        material_values = material_values[: len(model.elements)]
    if len(material_values) < len(model.elements):
        material_values.extend([material_fallback_token] * (len(model.elements) - len(material_values)))
    if len(material_values) != len(model.elements):
        raise ValueError(
            "Invalid MISCEL_1 material list length after normalization; "
            f"expected {len(model.elements)} values."
        )

    material_lines = _chunk_rows(material_values, 6)
    vflex_lines = _build_vflex_lines(model, miscel_cfg)
    hanger_lines = _build_hanger_lines(model, miscel_cfg)
    execution_lines = _build_execution_option_lines(miscel_cfg)
    return material_lines + vflex_lines + hanger_lines + execution_lines


def _discontinuous_segment_start_nodes(elements: list[ElementResolved]) -> list[float]:
    """Return the first source-order node in every disconnected element component."""
    parent: dict[float, float] = {}
    node_order: list[float] = []

    def add(node: float) -> None:
        if node not in parent:
            parent[node] = node
            node_order.append(node)

    def find(node: float) -> float:
        root = node
        while parent[root] != root:
            root = parent[root]
        while parent[node] != node:
            next_node = parent[node]
            parent[node] = root
            node = next_node
        return root

    for element in elements:
        add(element.from_node)
        add(element.to_node)
        from_root = find(element.from_node)
        to_root = find(element.to_node)
        if from_root != to_root:
            parent[to_root] = from_root

    start_by_component: dict[float, float] = {}
    for node in node_order:
        start_by_component.setdefault(find(node), node)
    return list(start_by_component.values())


def _build_coords_payload_with_layout(
    elements: list[ElementResolved],
    tolerance: float,
    layout_config: dict[str, object],
    candidate_nodes: list[float],
) -> list[str]:
    coords_cfg = layout_config.get("coords", {})
    if not isinstance(coords_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'coords' must be an object.")
    mode = str(coords_cfg.get("mode", "all_nodes")).strip().lower()
    decimals = int(coords_cfg.get("decimals", 4))

    configured_node_ids: list[float] = []
    if mode != "all_nodes":
        configured_node_ids_raw = coords_cfg.get("node_ids", [])
        if configured_node_ids_raw is None:
            configured_node_ids_raw = []
        if not isinstance(configured_node_ids_raw, list):
            raise ValueError("Invalid 2019 layout config: 'coords.node_ids' must be an array.")
        configured_node_ids = [float(node_id) for node_id in configured_node_ids_raw]

    segment_start_nodes = (
        _discontinuous_segment_start_nodes(elements)
        if mode == "discontinuous_starts" and not configured_node_ids
        else []
    )

    # Real CII 2019 COORDS sections emitted by CAESAR II itself are sparse -
    # typically a handful of reference/anchor nodes, not one row per node in
    # the model. When mode isn't "all_nodes", figure out up front which
    # node(s) will actually be emitted, so the reconstruction below only has
    # to guarantee those are unambiguous. A redundant-path disagreement
    # anywhere else in a large model (which never reaches this payload
    # either way) no longer aborts the whole conversion.
    if mode == "all_nodes":
        required_nodes = None
    elif configured_node_ids:
        required_nodes = set(configured_node_ids)
    elif segment_start_nodes:
        required_nodes = set(segment_start_nodes)
    elif candidate_nodes:
        required_nodes = {candidate_nodes[0]}
    else:
        # No configured node and no candidate: which single node gets
        # emitted depends on the full reconstructed set (lowest node id),
        # so this rare, fully-unconfigured case keeps the original strict,
        # whole-graph behavior.
        required_nodes = None

    coordinates = _build_absolute_coordinates(elements, tolerance=tolerance, required_nodes=required_nodes)

    origin_offset_values = coords_cfg.get("origin_offset", ["0.0", "0.0", "0.0"])
    if not isinstance(origin_offset_values, list) or len(origin_offset_values) != 3:
        raise ValueError("Invalid 2019 layout config: 'coords.origin_offset' must be an array of three values.")
    origin_offset = tuple(float(entry) for entry in origin_offset_values)

    if mode == "all_nodes":
        nodes = sorted(coordinates.keys())
    elif configured_node_ids:
        nodes = configured_node_ids
    elif segment_start_nodes:
        nodes = segment_start_nodes
    elif candidate_nodes:
        nodes = [candidate_nodes[0]]
    else:
        nodes = [sorted(coordinates.keys())[0]]

    payload: list[str] = [_row([str(len(nodes))])]
    for node in nodes:
        if node not in coordinates:
            raise ValueError(
                f"Configured COORDS node {_format_node_id(node)} is not present in reconstructed node set."
            )
        coord = coordinates[node]
        payload.append(
            _row(
                [
                    _format_node_id(node),
                    _format_fixed_float(coord.x + origin_offset[0], decimals),
                    _format_fixed_float(coord.y + origin_offset[1], decimals),
                    _format_fixed_float(coord.z + origin_offset[2], decimals),
                ]
            )
        )
    return payload


def _build_cii_text(
    model: ParsedModel,
    defaults: ConverterDefaults,
    infer_reducer_angle_from_geometry: bool,
    reference_overrides: ReferenceElementOverrides | None,
    coord_reconstruction_tolerance: float,
    layout_config: dict[str, object],
) -> tuple[str, dict[str, int]]:
    elements = model.elements
    compatibility = _parse_compatibility_config(layout_config)
    coords_payload: list[str] = []
    version_payload = _build_version_payload(model)
    edge_to_reducer_index, reducers = _infer_reducer_indices(
        elements,
        defaults,
        infer_reducer_angle_from_geometry,
    )

    bend_payload, edge_to_bend_index = _build_bend_payload(elements, layout_config)
    rigid_payload, edge_to_rigid_index = _build_rigid_payload(elements)
    restraint_payload, edge_to_restraint_index = _build_restraint_payload(
        elements,
        layout_config,
        compatibility,
    )
    sif_payload, edge_to_sif_index = _build_sif_payload(elements)

    elements_cfg = layout_config.get("elements", {})
    if not isinstance(elements_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'elements' must be an object.")

    # row3/row4 = REL items 13-24 (temp cases 4-9, pressure cases 1-6) - fully
    # per-element now (see ElementResolved.temperature4-9/pressure1-6). row5/row6
    # = REL items 25-36; only the positions with an XML source (pressure cases
    # 7-9, insulation/fluid density, hydro pressure) are per-element - the rest
    # (Elastic Modulus cold, Poisson's Ratio, Pipe Density, Mill Tolerances,
    # Seam Weld) keep the existing config-template fallback, since no PIPINGELEMENT
    # attribute supplies them.
    def _padded_cfg(key: str, length: int) -> list[str]:
        values = [str(v) for v in elements_cfg.get(key, [])]
        if len(values) < length:
            values = values + ["0.000000"] * (length - len(values))
        return values

    row5_cfg = _padded_cfg("row5", 6)
    row6_cfg = _padded_cfg("row6", 6)
    row7 = _row(list(elements_cfg.get("row7", ["0.000000"] * 6)))
    row8 = _row(list(elements_cfg.get("row8", ["0.000000"] * 6)))
    row9 = _row(list(elements_cfg.get("row9", ["0.000000"] * 5)))
    row10_cfg = elements_cfg.get("row10", ["0"])
    if isinstance(row10_cfg, list):
        row10 = _render_element_label_payload(" ".join(str(item) for item in row10_cfg))
    else:
        row10 = _render_element_label_payload(row10_cfg)
    row11 = _row(list(elements_cfg.get("row11", ["-1", "-1"])))
    # IEL auxiliary-pointer array item order per the CAESAR II neutral file
    # spec: row12=[1 bend, 2 rigid, 3 expjt, 4 restraint, 5 displmnt,
    # 6 forcmnt], row13=[7 uniform, 8 wind, 9 offset, 10 allowbl,
    # 11 intersection/SIF&TEES, 12 nodename], row14=[13 reducer, 14 flange,
    # 15 equipmnt/nozzle check]. Only bend/rigid/restraint/sif/reducer/
    # nodename are built with real per-element tracking today; the rest
    # (expjt/displmnt/forcmnt/uniform/wind/offset/allowbl/flange/equipmnt)
    # have no per-element association in this engine yet, so their slots
    # stay literal "0" ("no auxiliary data of this type for this element"
    # is simply always true for them right now).
    row12_tpl = list(elements_cfg.get("row12", ["{bend}", "{rigid}", "0", "{restraint}", "0", "0"]))
    row13_tpl = list(elements_cfg.get("row13", ["0", "0", "0", "0", "{sif}", "{nodename}"]))
    row14_tpl = list(elements_cfg.get("row14", ["{reducer}", "0", "0"]))

    # NODENAME payload/pointer-count must be known before the per-element
    # ELEMENTS loop below (it needs edge_to_nodename_index for row13's
    # "{nodename}" token), so this is computed here rather than after the
    # loop like the other section payloads.
    nodename_cfg = layout_config.get("nodename", {})
    if not isinstance(nodename_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'nodename' must be an object.")
    nodename_mode = str(nodename_cfg.get("mode", "auto")).strip().lower()
    if nodename_mode not in ("disabled", "manual", "to_node_map", "auto"):
        raise ValueError("Invalid 2019 layout config: 'nodename.mode' must be disabled, manual, to_node_map, or auto.")
    from_labels = nodename_cfg.get("from_labels", [])
    to_labels = nodename_cfg.get("to_labels", [])
    if from_labels is None:
        from_labels = []
    if to_labels is None:
        to_labels = []
    if not isinstance(from_labels, list) or not isinstance(to_labels, list):
        raise ValueError("Invalid 2019 layout config: 'nodename.from_labels' and 'nodename.to_labels' must be arrays.")
    configured_pairs = min(len(from_labels), len(to_labels))
    default_from_label = str(nodename_cfg.get("from_label", "PS-XXX"))
    default_to_label = str(nodename_cfg.get("to_label", "PS-XXX"))
    nodename_payload: list[str] = []
    nonam_count = 0
    if nodename_mode == "manual":
        nonam_count = int(nodename_cfg.get("nonam_count", configured_pairs))
        if nonam_count < 0:
            raise ValueError("Invalid 2019 layout config: 'nodename.nonam_count' must be non-negative.")
        for pair_index in range(nonam_count):
            # One line per (from, to) pair in the spec's (2X, A10, 16X, A10)
            # column layout - previously each label was emitted on its own
            # line, which doubled the payload line count vs the declared
            # NONAM pair count and broke the reader's column positions.
            if pair_index < configured_pairs:
                nodename_payload.append(_format_nodename_pair(str(from_labels[pair_index]), str(to_labels[pair_index])))
            else:
                nodename_payload.append(_format_nodename_pair(default_from_label, default_to_label))
    elif nodename_mode == "to_node_map":
        to_node_labels_raw = nodename_cfg.get("to_node_labels", {})
        if not isinstance(to_node_labels_raw, dict):
            raise ValueError("Invalid 2019 layout config: 'nodename.to_node_labels' must be an object.")
        mapped_pairs: list[tuple[str, str]] = []
        for element in elements:
            to_node_text = _format_node_id(element.to_node)
            candidates = (to_node_text, f"{element.to_node:.6f}", str(int(round(element.to_node))))
            to_label_value = ""
            for candidate in candidates:
                mapped = to_node_labels_raw.get(candidate)
                if mapped is not None and _safe_text(str(mapped)):
                    to_label_value = str(mapped)
                    break
            if not to_label_value:
                continue
            mapped_pairs.append((default_from_label, to_label_value))

        default_nonam = len(mapped_pairs)
        nonam_count = int(nodename_cfg.get("nonam_count", default_nonam))
        if nonam_count <= 0 and default_nonam > 0:
            nonam_count = default_nonam
        if nonam_count < 0:
            raise ValueError("Invalid 2019 layout config: 'nodename.nonam_count' must be non-negative.")
        for pair_index in range(nonam_count):
            if pair_index < len(mapped_pairs):
                nodename_payload.append(_format_nodename_pair(mapped_pairs[pair_index][0], mapped_pairs[pair_index][1]))
            else:
                nodename_payload.append(_format_nodename_pair(default_from_label, default_to_label))
    elif nodename_mode == "auto":
        # One NODENAME row per element edge: a two-column (from, to) line. Real
        # names emitted by the upstream (FROM_NAME/TO_NAME) are used verbatim;
        # nodes without a source name receive a deterministic label
        # "{prefix}{node}" (configurable). Restores node traceability without
        # inventing data.
        auto_prefix = str(nodename_cfg.get("auto_prefix", "N"))

        def _auto_label(name: str, node: float) -> str:
            text = _safe_text(name)
            if text:
                return text
            return f"{auto_prefix}{int(round(node))}"

        for element in elements:
            from_name = _auto_label(element.name_from, element.from_node)
            to_name = _auto_label(element.name_to, element.to_node)
            nodename_payload.append(_format_nodename_pair(from_name, to_name))
        nonam_count = len(elements)

    # NODENAME payload is built one entry per element, in element order, in
    # every active mode above (auto always; manual/to_node_map up to
    # nonam_count, matching the same element order) - so the 1-based pointer
    # for edge_index is simply its position, as long as that element got an
    # entry at all.
    edge_to_nodename_index: dict[int, int] = {
        edge_index: edge_index + 1 for edge_index in range(min(nonam_count, len(elements)))
    }

    line_label_cfg = elements_cfg.get("line_label", {})
    if not isinstance(line_label_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'elements.line_label' must be an object.")
    line_label_mode = str(line_label_cfg.get("mode", "zero")).strip().lower()
    if line_label_mode not in ("zero", "auto", "to_node"):
        raise ValueError("Invalid 2019 layout config: 'elements.line_label.mode' must be zero, auto, or to_node.")
    # NOTE: the legacy 'pointer_start' config key is intentionally ignored now.
    # The integer that precedes an Element-Name / Line-Number string is the
    # string's LENGTH per the neutral file spec (7X, I5, 1X, A500), not a
    # running pointer/index - so it is always derived from the label text
    # (see _render_length_prefixed_label), never from a configured start.
    label_index_start = int(line_label_cfg.get("label_index_start", 0))
    label_prefix = str(line_label_cfg.get("label_prefix", "LINENO"))
    label_width = int(line_label_cfg.get("label_width", 2))
    default_line_label = str(line_label_cfg.get("default_line", "0"))
    to_node_template = str(line_label_cfg.get("to_node_template", "{to_node}"))
    configured_line_labels = line_label_cfg.get("line_labels", [])
    if configured_line_labels is None:
        configured_line_labels = []
    if not isinstance(configured_line_labels, list):
        raise ValueError("Invalid 2019 layout config: 'elements.line_label.line_labels' must be an array.")

    elements_payload: list[str] = []
    for edge_index, element in enumerate(elements):
        line1 = _row(
            [
                _format_sig6(element.from_node),
                _format_sig6(element.to_node),
                _format_sig6(element.delta_x),
                _format_sig6(element.delta_y),
                _format_sig6(element.delta_z),
                _format_fixed_float(element.diameter, 5),
            ]
        )
        line2 = _row(
            [
                _format_sig6(element.wall_thickness),
                _format_sig6(element.insulation_thickness),
                _format_sig6(element.corrosion_allowance),
                _format_sig6(element.temperature1),
                _format_sig6(element.temperature2),
                _format_sig6(element.temperature3),
            ]
        )
        row3 = _row(
            [
                _format_sig6(element.temperature4),
                _format_sig6(element.temperature5),
                _format_sig6(element.temperature6),
                _format_sig6(element.temperature7),
                _format_sig6(element.temperature8),
                _format_sig6(element.temperature9),
            ]
        )
        row4 = _row(
            [
                _format_sig6(element.pressure1),
                _format_sig6(element.pressure2),
                _format_sig6(element.pressure3),
                _format_sig6(element.pressure4),
                _format_sig6(element.pressure5),
                _format_sig6(element.pressure6),
            ]
        )
        row5 = _row(
            [
                _format_sig6(element.pressure7),
                _format_sig6(element.pressure8),
                _format_sig6(element.pressure9),
                row5_cfg[3],
                row5_cfg[4],
                row5_cfg[5],
            ]
        )
        row6 = _row(
            [
                _format_sig6(element.insulation_density),
                _format_sig6(element.fluid_density),
                row6_cfg[2],
                row6_cfg[3],
                row6_cfg[4],
                _format_sig6(element.hydro_pressure),
            ]
        )
        line10 = ""
        if element.line:
            # Line Number row: length-prefixed string per spec (see
            # _render_length_prefixed_label). Same label => same prefix on
            # every element, e.g. "           5 PL-XX" for all of them.
            line10 = _render_length_prefixed_label(element.line)
        elif edge_index < len(configured_line_labels):
            line10 = _render_element_label_payload(configured_line_labels[edge_index])
        else:
            if line_label_mode == "to_node":
                line10 = _render_element_label_payload(to_node_template.replace("{to_node}", _format_node_id(element.to_node)))
            elif line_label_mode == "auto" and not default_line_label:
                line10 = _render_label_line(
                    label_index=label_index_start + edge_index,
                    label_prefix=label_prefix,
                    label_width=label_width,
                )
            elif default_line_label:
                line10 = _render_element_label_payload(default_line_label)
            else:
                line10 = _render_element_label_payload("0")
        token_values = {
            "bend": edge_to_bend_index.get(edge_index, 0),
            "rigid": edge_to_rigid_index.get(edge_index, 0),
            "restraint": edge_to_restraint_index.get(edge_index, 0),
            "sif": edge_to_sif_index.get(edge_index, 0),
            "reducer": edge_to_reducer_index.get(edge_index, 0),
            "nodename": edge_to_nodename_index.get(edge_index, 0),
        }
        line12 = _render_tokens_row(row12_tpl, token_values)
        line13 = _render_tokens_row(row13_tpl, token_values)
        line14 = _render_tokens_row(row14_tpl, token_values)
        elements_payload.extend(
            [
                line1,
                line2,
                row3,
                row4,
                row5,
                row6,
                row7,
                row8,
                row9,
                row10,
                line10,
                row11,
                line12,
                line13,
                line14,
            ]
        )

    # Validate that every aux-block type with real per-element data (bend,
    # rigid, restraint, sif, reducer, nodename) actually has its pointer
    # token somewhere in row12/row13/row14 - if a custom config's template
    # omits or overwrites a token, CAESAR gets a permanent 0 pointer for
    # every element of that type and silently drops the association (this
    # is exactly how the NODENAME pointer was broken before this token
    # existed at all: real name data was written to #$ NODENAME, but every
    # element's IEL pointer to it stayed 0, so CAESAR never showed the name).
    _tracked_pointer_types = {
        "bend": edge_to_bend_index,
        "rigid": edge_to_rigid_index,
        "restraint": edge_to_restraint_index,
        "sif": edge_to_sif_index,
        "reducer": edge_to_reducer_index,
        "nodename": edge_to_nodename_index,
    }
    _all_pointer_templates = row12_tpl + row13_tpl + row14_tpl
    for _pointer_name, _index_map in _tracked_pointer_types.items():
        if _index_map and f"{{{_pointer_name}}}" not in _all_pointer_templates:
            _warn(
                "AUX_POINTER_MISSING_FROM_TEMPLATE",
                f"{len(_index_map)} element(s) have {_pointer_name} auxiliary data, but "
                f"elements.row12/row13/row14 config does not reference the '{{{_pointer_name}}}' "
                "token anywhere - CAESAR will not associate this data with any element "
                "(the IEL pointer for this type stays 0 for all elements).",
                pointer_type=_pointer_name,
                affected_element_count=len(_index_map),
            )

    raw_block_overrides = elements_cfg.get("raw_block_overrides", [])
    if raw_block_overrides is None:
        raw_block_overrides = []
    if not isinstance(raw_block_overrides, list):
        raise ValueError("Invalid 2019 layout config: 'elements.raw_block_overrides' must be an array.")
    if raw_block_overrides:
        _validate_raw_overrides_allowed(
            compatibility,
            "elements.raw_block_overrides",
            has_override=True,
        )
        if len(raw_block_overrides) != len(elements):
            raise ValueError(
                "Invalid 2019 layout config: 'elements.raw_block_overrides' length must match element count."
            )
        overridden_elements_payload: list[str] = []
        for block_index, block in enumerate(raw_block_overrides):
            if not isinstance(block, list):
                raise ValueError(
                    "Invalid 2019 layout config: each 'elements.raw_block_overrides' entry must be an array."
                )
            if len(block) != 15:
                raise ValueError(
                    f"Invalid 2019 layout config: elements.raw_block_overrides[{block_index}] must contain 15 lines."
                )
            overridden_elements_payload.extend(_as_string_list(block, f"elements.raw_block_overrides[{block_index}]"))
        elements_payload = overridden_elements_payload

    reducer_payload = [
        _row(
            [
                _format_auto_float(second_diameter),
                _format_fixed_float(0.0, 6),
                _format_fixed_float(angle_value, 4),
                _format_fixed_float(0.0, 6),
                _format_fixed_float(0.0, 6),
            ]
        )
        for second_diameter, angle_value in reducers
    ]

    miscel_cfg = layout_config.get("miscel_1", {})
    if not isinstance(miscel_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'miscel_1' must be an object.")
    miscel_payload = _build_miscel_payload(model, miscel_cfg)

    units_cfg = layout_config.get("units", {})
    if not isinstance(units_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'units' must be an object.")
    units_payload = list(units_cfg.get("numeric_lines", [])) + list(units_cfg.get("text_lines", []))

    equipmnt_payload, equipmnt_nodes = _build_equipmnt_payload(layout_config)
    displmnt_payload, displmnt_nodes = _build_displmnt_payload(layout_config, equipmnt_nodes)
    allowbls_payload = _build_allowbls_payload(layout_config)
    flanges_cfg = layout_config.get("flanges", {})
    if not isinstance(flanges_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'flanges' must be an object.")
    include_flanges = bool(flanges_cfg.get("include_section", True))
    restraint_cfg = layout_config.get("restraint", {})
    if not isinstance(restraint_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'restraint' must be an object.")
    restraint_block_size = RESTRAINT_LINES_PER_AUX_BLOCK

    # A raw_payload_overrides entry for COORDS (set below, but checked here
    # too) replaces whatever this computes wholesale - most commonly when a
    # layout config is derived from an existing reference CII, which passes
    # every one of its own sections through verbatim. Reconstructing (and
    # strictly cross-validating) absolute coordinates for the whole model
    # is real work whose result would just be discarded in that case, so
    # skip it rather than let a benign, irrelevant inconsistency somewhere
    # in a large model abort a conversion whose COORDS section was never
    # going to use the computed result anyway.
    _sections_cfg_probe = layout_config.get("sections", {})
    _coords_override_present = (
        isinstance(_sections_cfg_probe, dict)
        and isinstance(_sections_cfg_probe.get("raw_payload_overrides"), dict)
        and "COORDS" in _sections_cfg_probe["raw_payload_overrides"]
    )

    if reference_overrides is not None:
        version_payload = reference_overrides.version_payload
        nonam_count = reference_overrides.nonam_count
        nodename_payload = reference_overrides.nodename_payload
        bend_payload = reference_overrides.bend_payload
        reducer_payload = reference_overrides.reducers_payload
        coords_payload = reference_overrides.coords_payload
    elif _coords_override_present:
        coords_payload = []
    else:
        coords_payload = _build_coords_payload_with_layout(
            elements=elements,
            tolerance=coord_reconstruction_tolerance,
            layout_config=layout_config,
            candidate_nodes=displmnt_nodes if displmnt_nodes else equipmnt_nodes,
        )

    version_cfg = layout_config.get("version", {})
    if not isinstance(version_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'version' must be an object.")
    version_raw_lines = version_cfg.get("raw_lines", [])
    version_raw_payload = _as_string_list(version_raw_lines, "version.raw_lines")
    if version_raw_payload:
        _validate_raw_overrides_allowed(compatibility, "version.raw_lines", has_override=True)
        version_payload = version_raw_payload
    apply_universal_prefix = bool(version_cfg.get("apply_universal_prefix", True))
    universal_prefix_lines = int(version_cfg.get("universal_prefix_lines", 2))
    if apply_universal_prefix and universal_prefix_lines > 0:
        version_payload = _apply_universal_version_prefix(version_payload, universal_prefix_lines)

    bend_cfg_main = layout_config.get("bend", {})
    if not isinstance(bend_cfg_main, dict):
        raise ValueError("Invalid 2019 layout config: 'bend' must be an object.")
    bend_raw_lines = bend_cfg_main.get("raw_lines", [])
    bend_raw_payload = _as_string_list(bend_raw_lines, "bend.raw_lines")
    if bend_raw_payload:
        _validate_raw_overrides_allowed(compatibility, "bend.raw_lines", has_override=True)
        bend_payload = bend_raw_payload

    rigid_cfg = layout_config.get("rigid", {})
    if not isinstance(rigid_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'rigid' must be an object.")
    rigid_raw_lines = rigid_cfg.get("raw_lines", [])
    rigid_raw_payload = _as_string_list(rigid_raw_lines, "rigid.raw_lines")
    if rigid_raw_payload:
        _validate_raw_overrides_allowed(compatibility, "rigid.raw_lines", has_override=True)
        rigid_payload = rigid_raw_payload

    restraint_raw_lines = restraint_cfg.get("raw_lines", [])
    restraint_raw_payload = _as_string_list(restraint_raw_lines, "restraint.raw_lines")
    if restraint_raw_payload:
        _validate_raw_overrides_allowed(compatibility, "restraint.raw_lines", has_override=True)
        restraint_payload = restraint_raw_payload

    restraint_count = len(restraint_payload) // restraint_block_size if restraint_block_size > 0 else 0

    metrics = {
        "elements": len(elements),
        "nozzles": _count_misc_records(len(model.nozzles), miscel_cfg, "nozzles"),
        "hangers": _count_misc_records(len(model.hangers), miscel_cfg, "hangers"),
        "nonam": nonam_count,
        "flanges": 0,
        "bends": len(bend_payload) // 3,
        "rigids": len(rigid_payload),
        "expjts": 0,
        "restraints": restraint_count,
        "displmnt": len(displmnt_nodes),
        "forcmnt": 0,
        "uniform": 0,
        "wind": 0,
        "offsets": 0,
        "allowbls": 1 if allowbls_payload else 0,
        "sifs": len(sif_payload) // 10,
        "reducers": len(reducer_payload),
        "equipmnt": len(equipmnt_nodes),
    }
    control_cfg = layout_config.get("control", {})
    if not isinstance(control_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'control' must be an object.")
    control_line_1 = _render_control_line(
        list(control_cfg.get("line1", ["{elements}", "{nozzles}", "{hangers}", "{nonam}", "{reducers}", "{flanges}"])),
        metrics,
    )
    control_line_2 = _render_control_line(
        list(control_cfg.get("line2", ["{bends}", "{rigids}", "{expjts}", "{restraints}", "{displmnt}", "{forcmnt}"])),
        metrics,
    )
    control_line_3 = _render_control_line(
        list(control_cfg.get("line3", ["{uniform}", "{wind}", "{offsets}", "{allowbls}", "{sifs}", "0"])),
        metrics,
    )
    control_line_4 = _render_control_line(list(control_cfg.get("line4", ["{equipmnt}"])), metrics)

    sections_cfg = layout_config.get("sections", {})
    if not isinstance(sections_cfg, dict):
        raise ValueError("Invalid 2019 layout config: 'sections' must be an object.")
    include_nodename = bool(sections_cfg.get("include_nodename", False))
    header_suffixes_raw = sections_cfg.get("header_suffixes", {})
    if not isinstance(header_suffixes_raw, dict):
        raise ValueError("Invalid 2019 layout config: 'sections.header_suffixes' must be an object.")
    header_suffixes: dict[str, str] = {str(k): str(v) for k, v in header_suffixes_raw.items()}
    raw_payload_overrides_raw = sections_cfg.get("raw_payload_overrides", {})
    if not isinstance(raw_payload_overrides_raw, dict):
        raise ValueError("Invalid 2019 layout config: 'sections.raw_payload_overrides' must be an object.")
    raw_payload_overrides: dict[str, list[str]] = {}
    for section_name, payload in raw_payload_overrides_raw.items():
        raw_payload_overrides[str(section_name)] = _as_string_list(
            payload,
            f"sections.raw_payload_overrides['{section_name}']",
        )

    _validate_raw_overrides_allowed(
        compatibility,
        "sections.raw_payload_overrides",
        has_override=bool(raw_payload_overrides),
    )

    if cii2019_section_rules is not None:
        payload_map = {
            "ELEMENTS": elements_payload,
            "BEND": bend_payload,
            "RIGID": rigid_payload,
            "EXPJT": [],
            "RESTRANT": restraint_payload,
            "DISPLMNT": displmnt_payload,
            "FORCMNT": [],
            "UNIFORM": [],
            "WIND": [],
            "OFFSETS": [],
            "ALLOWBLS": allowbls_payload,
            "SIF&TEES": sif_payload,
            "REDUCERS": reducer_payload,
            "FLANGES": [],
            "EQUIPMNT": equipmnt_payload,
            "MISCEL_1": miscel_payload,
            "UNITS": units_payload,
        }
        if raw_payload_overrides:
            for k, v in raw_payload_overrides.items():
                payload_map[k] = v

        derived_control = cii2019_section_rules.build_control_from_sections(
            payload_map,
            numelt=metrics["elements"],
            numnoz=metrics["nozzles"],
            nohgrs=metrics["hangers"],
            nonam=metrics["nonam"],
            izup=0,
        )
        control_payload = cii2019_section_rules.format_control_rows(derived_control)
    else:
        control_payload = [control_line_1, control_line_2, control_line_3, control_line_4]

    payload_model = _build_section_payload_model(
        version=version_payload,
        control=control_payload,
        elements=elements_payload,
        nodename=nodename_payload,
        bend=bend_payload,
        rigid=rigid_payload,
        restrant=restraint_payload,
        displmnt=displmnt_payload,
        allowbls=allowbls_payload,
        sif_tees=sif_payload,
        reducers=reducer_payload,
        equipmnt=equipmnt_payload,
        miscel_1=miscel_payload,
        units=units_payload,
        coords=coords_payload,
    )
    sections = _serialize_sections(
        payload_model=payload_model,
        include_nodename=include_nodename,
        include_flanges=include_flanges,
    )
    if raw_payload_overrides:
        overridden_sections: list[tuple[str, list[str]]] = []
        for name, payload in sections:
            overridden_sections.append((name, raw_payload_overrides.get(name, payload)))
        sections = overridden_sections

    lines: list[str] = []
    for name, payload in sections:
        lines.append(_section_header(name, header_suffixes))
        lines.extend(payload)

    cii_text = "\n".join(lines) + "\n"

    if cii2019_section_rules is not None:
        cii2019_section_rules.assert_cii2019_sections_valid(cii_text)

    stats = {
        "elements": len(elements),
        "bends": len(bend_payload) // 3,
        "rigids": len(rigid_payload),
        "restraints": restraint_count,
        "sifs": len(sif_payload) // 10,
        "reducers": len(reducer_payload),
        "coords": max(len(coords_payload) - 1, 0),
    }
    return cii_text, stats


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert CAESARII Input XML to CII.")
    parser.add_argument("--input", required=True, type=Path, help="Input XML path (CAESARII Input XML).")
    parser.add_argument("--output", required=True, type=Path, help="Output CII path.")
    parser.add_argument("--default-diameter", required=False, type=float, default=0.0, help="Fallback diameter.")
    parser.add_argument(
        "--default-wall-thickness",
        required=False,
        type=float,
        default=0.01,
        help="Fallback wall thickness when missing.",
    )
    parser.add_argument(
        "--default-insulation-thickness",
        required=False,
        type=float,
        default=0.0,
        help="Fallback insulation thickness when missing.",
    )
    parser.add_argument(
        "--default-corrosion-allowance",
        required=False,
        type=float,
        default=0.0,
        help="Fallback corrosion allowance when missing.",
    )
    parser.add_argument(
        "--default-temperature1",
        required=False,
        type=float,
        default=0.0,
        help="Fallback TEMP_EXP_C1 value when missing.",
    )
    parser.add_argument(
        "--default-temperature2",
        required=False,
        type=float,
        default=0.0,
        help="Fallback TEMP_EXP_C2 value when missing.",
    )
    parser.add_argument(
        "--default-temperature3",
        required=False,
        type=float,
        default=0.0,
        help="Fallback TEMP_EXP_C3 value when missing.",
    )
    parser.add_argument(
        "--default-pressure1",
        required=False,
        type=float,
        default=0.0,
        help="Reserved fallback pressure value (not currently emitted to CII block).",
    )
    parser.add_argument(
        "--default-pressure2",
        required=False,
        type=float,
        default=0.0,
        help="Reserved fallback pressure value (not currently emitted to CII block).",
    )
    parser.add_argument(
        "--default-pressure3",
        required=False,
        type=float,
        default=0.0,
        help="Reserved fallback pressure value (not currently emitted to CII block).",
    )
    parser.add_argument(
        "--default-reducer-angle",
        required=False,
        type=float,
        default=0.0,
        help="Fallback reducer half-angle when reducer is inferred but angle data is missing.",
    )
    parser.add_argument(
        "--infer-reducer-angle-from-geometry",
        action="store_true",
        help="Infer reducer half-angle from diameter delta and element run length.",
    )
    parser.add_argument(
        "--coord-reconstruction-tolerance",
        required=False,
        type=float,
        default=25.0,
        help=(
            "Tolerance in model length units for absolute coordinate closure checks "
            "during COORDS reconstruction (default: 25.0)."
        ),
    )
    # Compatibility with invocation-builder.js options for InputXML->CII variants.
    # These values are accepted even when not used by this converter profile.
    parser.add_argument("--header-datetime", required=False, type=str, default=None)
    parser.add_argument("--header-source", required=False, type=str, default=None)
    parser.add_argument("--header-version", required=False, type=str, default=None)
    parser.add_argument("--header-user-name", required=False, type=str, default=None)
    parser.add_argument("--header-purpose", required=False, type=str, default=None)
    parser.add_argument("--header-project-name", required=False, type=str, default=None)
    parser.add_argument("--header-mdb-name", required=False, type=str, default=None)
    parser.add_argument(
        "--layout-config-json",
        required=False,
        type=str,
        default=None,
        help=(
            "Optional JSON override for 2019 layout config. Use this for element-wise "
            "LINE labels, NODENAME payload, MISCEL_1 material IDs, CONTROL templates, and UNITS values."
        ),
    )
    parser.add_argument(
        "--hanger-miscel-default-profile-cii",
        type=Path,
        default=None,
        help=(
            "Optional CII profile used only to complete missing/sentinel HANGER and MISCEL_1 "
            "default values. Hangers are still detected from explicit InputXML "
            "<HANGER/> records."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail immediately on data-quality issues that would otherwise be logged as a "
            "warning and handled with a documented fallback (partial coordinate seeds, "
            "unparseable RESTRAINT slot numbers). Does not affect structural validation "
            "(malformed input XML, invalid --layout-config-json), which always fails "
            "immediately regardless of this flag."
        ),
    )
    return parser


def _auto_detect_reference_cii(input_xml_path: Path) -> Path | None:
    stem = input_xml_path.stem
    if not stem.lower().endswith("_input"):
        return None

    base_name = stem[:-6].rstrip()
    parent = input_xml_path.parent
    candidate_names = (
        f"{base_name}.CII",
        f"{base_name}.cii",
        f"{base_name}[BENCHMARK].CII",
        f"{base_name}[BENCHMARK].cii",
        f"{base_name} [BENCHMARK].CII",
        f"{base_name} [BENCHMARK].cii",
        f"{base_name} [CII BENCHMARK].CII",
        f"{base_name} [CII BENCHMARK].cii",
    )
    for candidate_name in candidate_names:
        candidate_path = parent / candidate_name
        if candidate_path.is_file():
            return candidate_path
    return None


def _assert_cii2019_compatible(cii_text: str, output_path: Path) -> None:
    if cii_syntax_check_2019 is None:
        raise RuntimeError("CII 2019 compatibility checker is unavailable.")

    options = cii_syntax_check_2019.RuleOptions(
        allow_missing_nodename=True,
        allow_zero_line_no=True,
        allow_missing_coords=True,
    )
    report = cii_syntax_check_2019.validate_cii_text(cii_text, output_path, options)
    if report.get("ok") is True:
        return

    errors = report.get("errors", [])
    if not isinstance(errors, list):
        raise ValueError("CII 2019 compatibility validation failed with an invalid report shape.")
    messages: list[str] = []
    for issue in errors[:12]:
        if not isinstance(issue, dict):
            continue
        section = issue.get("section", "GLOBAL")
        line = issue.get("line", 0)
        code = issue.get("code", "validation_error")
        message = issue.get("message", "")
        messages.append(f"{section}:{line} {code}: {message}")
    if len(errors) > len(messages):
        messages.append(f"... {len(errors) - len(messages)} more validation error(s).")
    raise ValueError(
        "CII 2019 compatibility validation failed before writing output:\n"
        + "\n".join(messages)
    )


def main() -> int:
    global _STRICT_DIAGNOSTICS

    parser = _build_parser()
    args = parser.parse_args()
    _STRICT_DIAGNOSTICS = bool(args.strict)

    defaults = ConverterDefaults(
        diameter=args.default_diameter,
        wall_thickness=args.default_wall_thickness,
        insulation_thickness=args.default_insulation_thickness,
        corrosion_allowance=args.default_corrosion_allowance,
        temperature1=args.default_temperature1,
        temperature2=args.default_temperature2,
        temperature3=args.default_temperature3,
        pressure1=args.default_pressure1,
        pressure2=args.default_pressure2,
        pressure3=args.default_pressure3,
        reducer_angle=args.default_reducer_angle,
    )

    model = _parse_model(args.input, defaults)
    reference_overrides: ReferenceElementOverrides | None = None
    layout_config = _load_2019_layout_config()
    if args.layout_config_json:
        layout_override = json.loads(args.layout_config_json)
        if not isinstance(layout_override, dict):
            raise ValueError("Invalid --layout-config-json: expected JSON object.")
        _merge_2019_layout_config(layout_config, layout_override)

    cii_text, stats = _build_cii_text(
        model=model,
        defaults=defaults,
        infer_reducer_angle_from_geometry=args.infer_reducer_angle_from_geometry,
        reference_overrides=reference_overrides,
        coord_reconstruction_tolerance=args.coord_reconstruction_tolerance,
        layout_config=layout_config,
    )

    if cii2019_hanger_miscel_control is not None:
        cii_text = cii2019_hanger_miscel_control.enforce_hanger_miscel_control(
            input_xml=args.input,
            cii_text=cii_text,
            default_profile_cii=args.hanger_miscel_default_profile_cii,
        )

    _assert_cii2019_compatible(cii_text, args.output)

    args.output.write_text(cii_text, encoding="utf-8")

    summary = (
        f"Wrote {args.output} from {args.input} with "
        f"{stats['elements']} elements, {stats['bends']} bends, {stats['rigids']} rigids, "
        f"{stats['restraints']} restraints, {stats['sifs']} SIF blocks, "
        f"{stats['reducers']} reducers, {stats['coords']} coordinates."
    )
    if _DIAGNOSTICS:
        warnings_path = args.output.with_name(args.output.name + ".warnings.json")
        warnings_path.write_text(
            json.dumps({"input": str(args.input), "output": str(args.output), "warnings": _DIAGNOSTICS}, indent=2),
            encoding="utf-8",
        )
        summary += f" {len(_DIAGNOSTICS)} warning(s) - see {warnings_path}."
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
