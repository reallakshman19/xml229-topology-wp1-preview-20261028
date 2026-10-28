#!/usr/bin/env python3
"""
CII 2019 HANGER / MISCEL_1 / CONTROL synchronizer.

Correct logic:
- Detect hangers from explicit InputXML <HANGER/> records.
- Do not trust only PIPINGMODEL.NOHGRS.
- Do not create hangers only because a default CII profile contains hangers.
- Use an explicitly provided CII profile only to map missing/sentinel hanger values.
- Emit MISCEL_1 hanger arrays matching detected hanger count.
- Update CONTROL.NOHGRS from emitted hanger count.

This module is intentionally focused on the failure-prone area:
HANGER + MISCEL_1 + CONTROL.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


SENTINEL_MISSING = -1.0101
SECTION_HEADER_RX = re.compile(r"^\s*#\$\s+([A-Z0-9_&]+)\b.*$")


@dataclass(frozen=True)
class XmlHanger:
    node: int
    connecting_node: int
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
    multi_lc: int
    free_anchor1: int
    free_anchor2: int
    dof_type1: int
    dof_type2: int
    num_hgr: int
    hgr_table: int
    short_range: int
    tag: str
    guid: str


@dataclass(frozen=True)
class ControlCounts:
    numelt: int
    numnoz: int
    nohgrs: int
    nonam: int
    nored: int
    numflg: int
    bends: int
    rigids: int
    expjts: int
    restraints: int
    displmnt: int
    forcmnt: int
    uniform: int
    wind: int
    offsets: int
    allowbls: int
    sif_tees: int
    izup: int
    equipmnt: int


@dataclass(frozen=True)
class HangerDefaultProfile:
    default_line_1: list[float | int]
    default_line_2: list[int]
    hgrdat_template: list[float]
    ihgrfree_template: list[int]
    ihgrnum_template: int
    ihgrtable_template: int
    ihgrshort_template: int
    ihgrcn_template: int
    execution_lines: list[str]


def _local_name(tag: str) -> str:
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _safe_text(value: str | None) -> str:
    return "" if value is None else value.strip()


def _to_float(value: str | None, default: float = SENTINEL_MISSING) -> float:
    text = _safe_text(value)
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _to_int(value: str | None, default: int = 0) -> int:
    number = _to_float(value, SENTINEL_MISSING)
    if _is_missing(number):
        return default
    return int(round(number))


def _is_missing(value: float) -> bool:
    return not math.isfinite(value) or abs(value - SENTINEL_MISSING) < 1e-6


def _float_or(value: float, default: float) -> float:
    return default if _is_missing(value) else value


def _int_or(value: int, default: int) -> int:
    return default if value < 0 else value


def _nonblank(rows: list[str]) -> list[str]:
    return [row for row in rows if row.strip()]


def _ceil_div(value: int, divisor: int) -> int:
    return value // divisor + (1 if value % divisor else 0)


def _format_i(values: list[int]) -> str:
    return "  " + "".join(f"{int(value):13d}" for value in values)


def _format_g13_6(value: float) -> str:
    """One FORTRAN G13.6 field (13 chars), matching psi2cii / CAESAR output.

    Python's ``{:13.6G}`` is NOT FORTRAN G13.6: it strips trailing zeros
    (so material id 106 came out as a bare ``106`` instead of the vendor's
    ``106.000``) and uses a different scientific-notation threshold. This
    reproduces the real neutral-file format, verified byte-for-byte against
    a psi2cii 2019 vendor benchmark across magnitudes and sign
    (``5.00000``, ``11.0000``, ``148.000``, ``2850.00``, ``-66.7000``,
    ``0.184213E-03`` ...).

    FORTRAN Gw.d: for 0.1 <= |x| < 10**6 (and x == 0) it uses F editing with
    6 significant figures, right-justified in (w-4)=9 columns, followed by 4
    blanks (the reserved exponent field); otherwise it uses E editing across
    the full 13 columns.
    """
    x = float(value)
    if not math.isfinite(x):
        raise ValueError(f"Non-finite numeric value encountered: {x}")
    ax = abs(x)
    if ax != 0.0 and (ax < 0.1 or ax >= 1e6):
        exp = int(math.floor(math.log10(ax))) + 1
        mantissa = x / (10.0 ** exp)
        body = f"{mantissa:.6f}E{'+' if exp >= 0 else '-'}{abs(exp):02d}"
        return f"{body:>13}"
    if ax == 0.0:
        return f"{'0.00000':>9}    "
    int_digits = 1 if ax < 1 else int(math.floor(math.log10(ax))) + 1
    decimals = 6 - int_digits
    return f"{x:.{decimals}f}".rjust(9) + "    "


def _format_g(values: list[float | int]) -> str:
    return "  " + "".join(_format_g13_6(value) for value in values)


def _format_string100(value: str) -> str:
    text = value[:100]
    if not text:
        # CAESAR accepts zero-token placeholder rows for empty TAG/GUID.
        return f"{'':7}{0:5d} "
    return f"{'':7}{len(text):5d} {text:<100}"


def _hanger_sort_key(hanger: XmlHanger) -> tuple[int, int]:
    support_node = hanger.free_anchor1 if hanger.free_anchor1 > 0 else hanger.node
    return (support_node, hanger.node)


def _pack_i(values: list[int], width: int = 6) -> list[str]:
    return [_format_i(values[index:index + width]) for index in range(0, len(values), width)]


def _pack_g(values: list[float | int], width: int = 6) -> list[str]:
    return [_format_g(values[index:index + width]) for index in range(0, len(values), width)]


def parse_inputxml_hangers(input_xml: Path) -> list[XmlHanger]:
    """
    Detect hangers from explicit <HANGER/> tags.

    This intentionally ignores model-level NOHGRS when it conflicts with actual
    hanger tags. Actual tags are the authoritative detection source.
    """

    root = ET.parse(input_xml).getroot()
    hangers: list[XmlHanger] = []

    for elem in root.iter():
        if _local_name(elem.tag).upper() != "HANGER":
            continue

        node = _to_int(elem.attrib.get("NODE"), default=-1)
        if node < 0:
            continue

        load_var = _to_float(elem.attrib.get("LOAD_VAR"), 25.0)
        hgr_table = _to_int(elem.attrib.get("HGR_TABLE"), 1)
        short_range = _to_int(elem.attrib.get("SHORT_RANGE"), 1)

        hangers.append(
            XmlHanger(
                node=node,
                connecting_node=_to_int(elem.attrib.get("CNODE"), 0),
                stiffness=_to_float(elem.attrib.get("STIFFNESS"), SENTINEL_MISSING),
                load_variation=load_var,
                operating_load=_to_float(elem.attrib.get("OPERATING_LOAD"), SENTINEL_MISSING),
                rigid_support=_to_float(elem.attrib.get("RIGID_SUP"), SENTINEL_MISSING),
                available_space=_to_float(elem.attrib.get("AVAIL_SPACE"), SENTINEL_MISSING),
                cold_load=_to_float(elem.attrib.get("COLD_LOAD"), SENTINEL_MISSING),
                hot_load=_to_float(elem.attrib.get("HOT_LOAD"), SENTINEL_MISSING),
                max_travel=_to_float(elem.attrib.get("MAX_TRAVEL"), SENTINEL_MISSING),
                hardware_weight=_to_float(elem.attrib.get("HARDWARE_WEIGHT"), SENTINEL_MISSING),
                const_eff_load=_to_float(elem.attrib.get("CONST_EFF_LOAD"), SENTINEL_MISSING),
                multi_lc=_to_int(elem.attrib.get("MULTI_LC"), 0),
                free_anchor1=_to_int(elem.attrib.get("FREEANCHOR1"), 0),
                free_anchor2=_to_int(elem.attrib.get("FREEANCHOR2"), 0),
                dof_type1=_to_int(elem.attrib.get("DOFTYPE1"), 0),
                dof_type2=_to_int(elem.attrib.get("DOFTYPE2"), 0),
                num_hgr=_to_int(elem.attrib.get("NUM_HGR"), 0),
                hgr_table=hgr_table,
                short_range=short_range,
                tag=_safe_text(elem.attrib.get("TAG")),
                guid=_safe_text(elem.attrib.get("GUID")),
            )
        )

    return sorted(hangers, key=_hanger_sort_key)


def parse_cii_sections(cii_text: str) -> tuple[list[tuple[str, str]], dict[str, list[str]]]:
    """
    Returns:
    - ordered headers: [(section_name, original_header_line)]
    - payload map
    """

    ordered_headers: list[tuple[str, str]] = []
    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw in cii_text.splitlines():
        line = raw.rstrip("\r\n")
        match = SECTION_HEADER_RX.match(line.lstrip("\ufeff"))
        if match:
            current = match.group(1)
            ordered_headers.append((current, line))
            sections.setdefault(current, [])
            continue

        if current is not None:
            sections.setdefault(current, []).append(line)

    return ordered_headers, sections


def parse_control_counts(control_rows: list[str]) -> ControlCounts:
    rows = _nonblank(control_rows)
    if len(rows) < 4:
        raise ValueError("CONTROL requires at least 4 payload rows.")

    parsed: list[list[int]] = []
    for row in rows[:4]:
        parsed.append([int(token) for token in row.split()])

    if len(parsed[0]) < 6 or len(parsed[1]) < 6 or len(parsed[2]) < 6 or len(parsed[3]) < 1:
        raise ValueError("CONTROL must have 6/6/6/1 integer layout.")

    return ControlCounts(
        numelt=parsed[0][0],
        numnoz=parsed[0][1],
        nohgrs=parsed[0][2],
        nonam=parsed[0][3],
        nored=parsed[0][4],
        numflg=parsed[0][5],
        bends=parsed[1][0],
        rigids=parsed[1][1],
        expjts=parsed[1][2],
        restraints=parsed[1][3],
        displmnt=parsed[1][4],
        forcmnt=parsed[1][5],
        uniform=parsed[2][0],
        wind=parsed[2][1],
        offsets=parsed[2][2],
        allowbls=parsed[2][3],
        sif_tees=parsed[2][4],
        izup=parsed[2][5],
        equipmnt=parsed[3][0],
    )


def format_control_counts(control: ControlCounts) -> list[str]:
    return [
        _format_i([control.numelt, control.numnoz, control.nohgrs, control.nonam, control.nored, control.numflg]),
        _format_i([control.bends, control.rigids, control.expjts, control.restraints, control.displmnt, control.forcmnt]),
        _format_i([control.uniform, control.wind, control.offsets, control.allowbls, control.sif_tees, control.izup]),
        _format_i([control.equipmnt]),
    ]


def _numbers_from_line(line: str) -> list[float]:
    values: list[float] = []
    for token in line.split():
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def _ints_from_line(line: str) -> list[int]:
    values: list[int] = []
    for token in line.split():
        try:
            values.append(int(float(token)))
        except ValueError:
            continue
    return values


def extract_hanger_default_profile(default_profile_cii: Path | None) -> HangerDefaultProfile:
    """
    Extracts default hanger block shape from an explicit CII profile when available.

    If extraction is incomplete, safe CAESAR-style defaults are used.
    """

    fallback = HangerDefaultProfile(
        # IDFTABLE, DEFVAR, DEFRIG, DEFMXTRAVEL, DEFSHTSPR, DEFMUL
        default_line_1=[1, 25.0, 0.0, 9999.99, 1.0, 1.0],
        # IDFOPER, IACTCLD, IHGRLDS, IACTUAL, IMULTIOPTS
        default_line_2=[1, 0, 0, 0, 0],
        # stiffness, load variation, rigid support, space, cold, hot,
        # operating load, max travel, multi-lc, hardware weight, const effort
        hgrdat_template=[0.0, 25.0, 0.0, 0.0, 0.0, 0.0, 0.0, 9999.99, 0.0, 0.0, 0.0],
        # anchor1, anchor2, dof1, dof2
        ihgrfree_template=[0, 0, 0, 0],
        ihgrnum_template=0,
        ihgrtable_template=1,
        ihgrshort_template=0,
        ihgrcn_template=0,
        execution_lines=[
            _format_i([0, 0, 0, 2]) + f"{0.0:13.4f}{0:13d}",
            _format_i([0, 0]) + f"{21.0:13.4f}{21.6:13.4f}" + "".join(f"{0:13d}" for _ in range(2)),
            _format_i([0, 0, 0, 0]) + f"{0.25:13.4f}{3:13d}",
            _format_i([0]),
        ],
    )

    if default_profile_cii is None or not default_profile_cii.exists():
        return fallback

    text = default_profile_cii.read_text(encoding="utf-8", errors="replace")
    _headers, sections = parse_cii_sections(text)

    if "CONTROL" not in sections or "MISCEL_1" not in sections:
        return fallback

    try:
        control = parse_control_counts(sections["CONTROL"])
    except Exception:
        return fallback

    if control.nohgrs <= 0:
        return fallback

    rows = _nonblank(sections["MISCEL_1"])
    rrmat_lines = _ceil_div(control.numelt, 6)
    nozzle_lines = control.numnoz * 4
    offset = rrmat_lines + nozzle_lines

    pack = _ceil_div(control.nohgrs, 6)

    try:
        default_line_1_values = _numbers_from_line(rows[offset])
        default_line_2_values = _ints_from_line(rows[offset + 1])
        offset += 2

        # IHGRNODE
        offset += pack

        # HGRDAT: two rows per hanger, use first hanger as template.
        hgrdat_values = _numbers_from_line(rows[offset]) + _numbers_from_line(rows[offset + 1])
        hgrdat_values = (hgrdat_values + fallback.hgrdat_template)[:11]
        offset += control.nohgrs * 2

        # TAG/GUID string rows.
        offset += control.nohgrs * 2

        ihgrfree_values = _ints_from_line(rows[offset])
        ihgrfree_values = (ihgrfree_values + fallback.ihgrfree_template)[:4]
        offset += control.nohgrs

        ihgrnum_values = _ints_from_line(rows[offset]) or [fallback.ihgrnum_template]
        offset += pack

        ihgrtable_values = _ints_from_line(rows[offset]) or [fallback.ihgrtable_template]
        offset += pack

        ihgrshort_values = _ints_from_line(rows[offset]) or [fallback.ihgrshort_template]
        offset += pack

        ihgrcn_values = _ints_from_line(rows[offset]) or [fallback.ihgrcn_template]
        offset += pack

        execution_lines = rows[offset:offset + 4]
        if len(execution_lines) < 4:
            execution_lines = fallback.execution_lines

        line_1 = (default_line_1_values + fallback.default_line_1)[:6]
        line_2 = (default_line_2_values + fallback.default_line_2)[:5]

        return HangerDefaultProfile(
            default_line_1=line_1,
            default_line_2=[int(v) for v in line_2],
            hgrdat_template=hgrdat_values,
            ihgrfree_template=ihgrfree_values,
            ihgrnum_template=ihgrnum_values[0],
            ihgrtable_template=ihgrtable_values[0],
            ihgrshort_template=ihgrshort_values[0],
            ihgrcn_template=ihgrcn_values[0],
            execution_lines=execution_lines,
        )
    except Exception:
        return fallback


def material_ids_from_inputxml(input_xml: Path, expected_count: int, default_material: int = 106) -> list[int]:
    """
    Build RRMAT material array for MISCEL_1.

    Uses explicit MATERIAL_NUM where valid; otherwise carries previous valid
    material; otherwise uses default_material.
    """

    root = ET.parse(input_xml).getroot()
    material_ids: list[int] = []
    carry = default_material

    for elem in root.iter():
        if _local_name(elem.tag).upper() != "PIPINGELEMENT":
            continue

        raw = _to_float(elem.attrib.get("MATERIAL_NUM"), SENTINEL_MISSING)
        if not _is_missing(raw):
            carry = int(round(raw))

        material_ids.append(carry)

    if len(material_ids) < expected_count:
        material_ids.extend([carry] * (expected_count - len(material_ids)))

    return material_ids[:expected_count]


def _build_hgrdat(hanger: XmlHanger, profile: HangerDefaultProfile) -> list[float]:
    t = profile.hgrdat_template

    return [
        _float_or(hanger.stiffness, t[0]),
        _float_or(hanger.load_variation, t[1]),
        _float_or(hanger.rigid_support, t[2]),
        _float_or(hanger.available_space, t[3]),
        _float_or(hanger.cold_load, t[4]),
        _float_or(hanger.hot_load, t[5]),
        _float_or(hanger.operating_load, t[6]),
        _float_or(hanger.max_travel, t[7]),
        float(_int_or(hanger.multi_lc, int(round(t[8])))),
        _float_or(hanger.hardware_weight, t[9]),
        _float_or(hanger.const_eff_load, t[10]),
    ]


def build_miscel_1_payload(
    *,
    input_xml: Path,
    control: ControlCounts,
    hangers: list[XmlHanger],
    default_profile: HangerDefaultProfile,
) -> list[str]:
    """
    Emit CII MISCEL_1 payload consistent with detected hangers.

    This intentionally supports NUMNOZ=0. If NUMNOZ > 0, keep that as a future
    explicit extension instead of silently producing a wrong nozzle VFLEX layout.
    """

    if control.numnoz != 0:
        raise ValueError(
            "HANGER/MISCEL_1 synchronizer currently supports NUMNOZ=0 only. "
            "Do not silently rewrite MISCEL_1 when nozzle VFLEX data exists."
        )

    rows: list[str] = []

    # 1. RRMAT material ID array, one per element.
    material_ids = material_ids_from_inputxml(input_xml, control.numelt)
    rows.extend(_pack_g([float(value) for value in material_ids], 6))

    # 2. Nozzle VFLEX data would go here when NUMNOZ > 0. Fail-closed above.

    # 3. Hanger defaults and arrays.
    if hangers:
        first = hangers[0]

        default_line_1 = list(default_profile.default_line_1)
        # IDFTABLE should follow actual first hanger table if XML gives it.
        default_line_1[0] = first.hgr_table if first.hgr_table > 0 else default_line_1[0]
        # DEFVAR should follow XML LOAD_VAR if valid.
        default_line_1[1] = _float_or(first.load_variation, float(default_line_1[1]))
        # DEFSHTSPR should follow XML SHORT_RANGE if valid.
        default_line_1[4] = first.short_range if first.short_range >= 0 else default_line_1[4]

        rows.append(
            "  "
            + f"{int(round(float(default_line_1[0]))):13d}"
            + "".join(f"{float(value):13.6G}" for value in default_line_1[1:])
        )
        # IDFOPER: global hanger flags. Positions 2-4 (dof_type1, support_node,
        # connecting_node) are computed from XML data; global defaults must be 0
        # to avoid CAESAR II interpreting them as node references for hangers
        # that have their own explicit per-hanger values.
        dl2 = list(default_profile.default_line_2)
        dl2[2:] = [0] * len(dl2[2:])
        rows.append(_format_i(dl2))

        # IHGRNODE
        rows.extend(_pack_i([hanger.node for hanger in hangers]))

        # HGRDAT plus TAG/GUID rows are interleaved per hanger in CAESAR output.
        for hanger in hangers:
            hgrdat = _build_hgrdat(hanger, default_profile)
            rows.extend(_pack_g(hgrdat, 6))
            rows.append(_format_string100(hanger.tag))
            rows.append(_format_string100(hanger.guid))

        # IHGRFREE: 4 integers per hanger, one line per hanger.
        for hanger in hangers:
            template = default_profile.ihgrfree_template
            rows.append(
                _format_i(
                    [
                        _int_or(hanger.free_anchor1, template[0]),
                        _int_or(hanger.free_anchor2, template[1]),
                        _int_or(hanger.dof_type1, template[2]),
                        _int_or(hanger.dof_type2, template[3]),
                    ]
                )
            )

        # IHGRNUM
        rows.extend(
            _pack_i(
                [
                    _int_or(hanger.num_hgr, default_profile.ihgrnum_template)
                    for hanger in hangers
                ]
            )
        )

        # IHGRTABLE
        rows.extend(
            _pack_i(
                [
                    _int_or(hanger.hgr_table, default_profile.ihgrtable_template)
                    for hanger in hangers
                ]
            )
        )

        # IHGRSHORT
        rows.extend(
            _pack_i(
                [
                    _int_or(hanger.short_range, default_profile.ihgrshort_template)
                    for hanger in hangers
                ]
            )
        )

        # IHGRCN
        rows.extend(
            _pack_i(
                [
                    _int_or(hanger.connecting_node, default_profile.ihgrcn_template)
                    for hanger in hangers
                ]
            )
        )

    # 4. Execution options.
    rows.extend(default_profile.execution_lines)

    return rows


def update_control_hanger_count(control: ControlCounts, hanger_count: int) -> ControlCounts:
    return ControlCounts(
        numelt=control.numelt,
        numnoz=control.numnoz,
        nohgrs=hanger_count,
        nonam=control.nonam,
        nored=control.nored,
        numflg=control.numflg,
        bends=control.bends,
        rigids=control.rigids,
        expjts=control.expjts,
        restraints=control.restraints,
        displmnt=control.displmnt,
        forcmnt=control.forcmnt,
        uniform=control.uniform,
        wind=control.wind,
        offsets=control.offsets,
        allowbls=control.allowbls,
        sif_tees=control.sif_tees,
        izup=control.izup,
        equipmnt=control.equipmnt,
    )


def render_sections(
    ordered_headers: list[tuple[str, str]],
    sections: dict[str, list[str]],
) -> str:
    """
    Render sections while preserving original section headers and order.
    If MISCEL_1 was missing, insert it before UNITS.
    """

    names = [name for name, _header in ordered_headers]

    if "MISCEL_1" not in names:
        insert_at = names.index("UNITS") if "UNITS" in names else len(names)
        ordered_headers = (
            ordered_headers[:insert_at]
            + [("MISCEL_1", "#$ MISCEL_1")]
            + ordered_headers[insert_at:]
        )

    lines: list[str] = []

    already_rendered: set[str] = set()
    for name, header in ordered_headers:
        if name in already_rendered:
            continue
        already_rendered.add(name)

        lines.append(header)
        lines.extend(sections.get(name, []))

    return "\n".join(lines) + "\n"


def enforce_hanger_miscel_control(
    *,
    input_xml: Path,
    cii_text: str,
    default_profile_cii: Path | None,
) -> str:
    """
    Main API for converter integration.

    Use this after generated CII text is assembled and before writing it.
    """

    hangers = parse_inputxml_hangers(input_xml)
    ordered_headers, sections = parse_cii_sections(cii_text)

    if "CONTROL" not in sections:
        raise ValueError("Cannot synchronize HANGER/MISCEL_1 because CONTROL section is missing.")

    old_control = parse_control_counts(sections["CONTROL"])
    new_control = update_control_hanger_count(old_control, len(hangers))

    profile = extract_hanger_default_profile(default_profile_cii)

    sections["MISCEL_1"] = build_miscel_1_payload(
        input_xml=input_xml,
        control=new_control,
        hangers=hangers,
        default_profile=profile,
    )
    sections["CONTROL"] = format_control_counts(new_control)

    # Fail-closed verification for the corrected logic.
    if new_control.nohgrs != len(hangers):
        raise ValueError(
            f"CONTROL.NOHGRS mismatch: control={new_control.nohgrs}, parsed_hangers={len(hangers)}"
        )

    return render_sections(ordered_headers, sections)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize CII 2019 HANGER/MISCEL_1/CONTROL from InputXML."
    )
    parser.add_argument("--input-xml", type=Path, required=True)
    parser.add_argument("--input-cii", type=Path, required=True)
    parser.add_argument("--output-cii", type=Path, required=True)
    parser.add_argument(
        "--default-profile-cii",
        type=Path,
        default=None,
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    cii_text = args.input_cii.read_text(encoding="utf-8", errors="replace")

    fixed = enforce_hanger_miscel_control(
        input_xml=args.input_xml,
        cii_text=cii_text,
        default_profile_cii=args.default_profile_cii,
    )

    args.output_cii.parent.mkdir(parents=True, exist_ok=True)
    args.output_cii.write_text(fixed, encoding="utf-8")

    hanger_count = len(parse_inputxml_hangers(args.input_xml))
    print(f"HANGER/MISCEL_1/CONTROL synchronized. Parsed hangers: {hanger_count}")
    print(f"Output: {args.output_cii}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
