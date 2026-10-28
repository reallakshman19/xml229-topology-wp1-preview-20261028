#!/usr/bin/env python3
"""
Validate CAESAR II 2019-style CII syntax and import compatibility.

This checker validates:
- Section framing and order by '#$ <SECTION>' blocks.
- Numeric/string token classes and lightweight precision shapes.
- Required block completeness and CONTROL-driven section sizes.
- Optional behavior for NODENAME, line numbers, and COORDS.
- C2-risk conditions that loose syntax checks miss, such as zero unit
  conversion constants, leaked InputXML sentinels, bad pointers, and bad
  COORDS node references.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

try:
    import cii2019_section_rules
except ImportError:
    cii2019_section_rules = None


SECTION_HEADER_RX = re.compile(r"^\s*#\$\s+([A-Z0-9_&]+)\s*$")
INTEGER_TOKEN_RX = re.compile(r"^[+-]?\d+$")
REAL_TOKEN_RX = re.compile(
    r"^[+-]?(?:(?:\d+\.\d*|\d*\.\d+|\d+)(?:[Ee][+-]?\d+)?|\d+[Ee][+-]?\d+)$"
)

EXPECTED_SECTION_ORDER = [
    "VERSION",
    "CONTROL",
    "ELEMENTS",
    "AUX_DATA",
    "NODENAME",
    "BEND",
    "RIGID",
    "EXPJT",
    "RESTRANT",
    "DISPLMNT",
    "FORCMNT",
    "UNIFORM",
    "WIND",
    "OFFSETS",
    "ALLOWBLS",
    "SIF&TEES",
    "REDUCERS",
    "FLANGES",
    "EQUIPMNT",
    "MISCEL_1",
    "UNITS",
    "COORDS",
]

REQUIRED_SECTIONS = {
    "VERSION",
    "CONTROL",
    "ELEMENTS",
    "AUX_DATA",
    "BEND",
    "RIGID",
    "EXPJT",
    "RESTRANT",
    "DISPLMNT",
    "FORCMNT",
    "UNIFORM",
    "WIND",
    "OFFSETS",
    "ALLOWBLS",
    "SIF&TEES",
    "REDUCERS",
    "FLANGES",
    "EQUIPMNT",
    "MISCEL_1",
    "UNITS",
}

# Based on CAESAR neutral syntax docs + benchmarked 2019 family patterns.
TOKENS_PER_ELEMENT_ROW = [6, 6, 6, 6, 6, 6, 6, 6, 5, None, None, 2, 6, 6, 3]
BLOCK_LINES_PER_SECTION = {
    "BEND": 3,
    "RIGID": 1,
    "EXPJT": 1,
    "RESTRANT": 24,
    "DISPLMNT": 20,
    "FORCMNT": 20,
    "UNIFORM": 6,
    "WIND": 1,
    "OFFSETS": 1,
    "ALLOWBLS": 26,
    "SIF&TEES": 10,
    "REDUCERS": 1,
    "FLANGES": 12,
    "EQUIPMNT": 6,
}

UNITS_NUMERIC_TOKEN_COUNTS = [6, 6, 6, 4]
UNITS_TOTAL_PAYLOAD_ROWS = 28
CAESAR_INPUTXML_MISSING_SENTINEL = -1.0101


@dataclass(frozen=True)
class Section:
    name: str
    header_line: int
    payload: list[tuple[int, str]]


@dataclass(frozen=True)
class RuleOptions:
    allow_missing_nodename: bool
    allow_zero_line_no: bool
    allow_missing_coords: bool


def _tokens(line: str) -> list[str]:
    return line.strip().split()


def _fixed_fortran_fields(line: str, field_count: int) -> list[str]:
    # FORTRAN rows in CII are column-based with two leading spaces and 13-char fields.
    raw = line.rstrip("\n\r")
    start = 2 if len(raw) >= 2 else 0
    fields: list[str] = []
    cursor = start
    for _ in range(field_count):
        fields.append(raw[cursor : cursor + 13].strip())
        cursor += 13
    return fields


def _is_int(token: str) -> bool:
    return bool(INTEGER_TOKEN_RX.fullmatch(token))


def _is_real(token: str) -> bool:
    return bool(REAL_TOKEN_RX.fullmatch(token))


def _real_value(token: str) -> float:
    if not _is_real(token):
        raise ValueError(f"Token is not a real number: {token}")
    return float(token)


def _ceil_div(value: int, divisor: int) -> int:
    return value // divisor + (1 if value % divisor else 0)


def _is_element_label_payload(line: str) -> bool:
    """Validate ELEMENTS rows 10/11 as a 12-char integer pointer plus separator."""
    raw = line.rstrip("\n\r")
    if len(raw) < 13:
        return False
    first_field = raw[:12].strip()
    return bool(_is_int(first_field) and raw[12] == " ")


def _parse_sections(lines: list[str]) -> list[Section]:
    sections: list[Section] = []
    current_name = ""
    current_header_line = -1
    current_payload: list[tuple[int, str]] = []

    for line_index, raw_line in enumerate(lines, start=1):
        match = SECTION_HEADER_RX.match(raw_line.lstrip("\ufeff"))
        if match:
            if current_name:
                sections.append(
                    Section(
                        name=current_name,
                        header_line=current_header_line,
                        payload=current_payload,
                    )
                )
            current_name = match.group(1).strip()
            current_header_line = line_index
            current_payload = []
            continue
        if current_name:
            current_payload.append((line_index, raw_line.rstrip("\n\r")))

    if current_name:
        sections.append(
            Section(
                name=current_name,
                header_line=current_header_line,
                payload=current_payload,
            )
        )
    return sections


def _add_error(
    errors: list[dict[str, object]],
    code: str,
    section: str,
    line: int,
    message: str,
) -> None:
    errors.append(
        {
            "code": code,
            "section": section,
            "line": line,
            "message": message,
        }
    )


def _add_warning(
    warnings: list[dict[str, object]],
    code: str,
    section: str,
    line: int,
    message: str,
) -> None:
    warnings.append(
        {
            "code": code,
            "section": section,
            "line": line,
            "message": message,
        }
    )


def _validate_order(
    sections: list[Section],
    options: RuleOptions,
    errors: list[dict[str, object]],
    warnings: list[dict[str, object]],
) -> None:
    found_names = [section.name for section in sections]
    name_set = set(found_names)

    required = set(REQUIRED_SECTIONS)
    if not options.allow_missing_nodename:
        required.add("NODENAME")
    if not options.allow_missing_coords:
        required.add("COORDS")

    for required_name in required:
        if required_name not in name_set:
            _add_error(
                errors,
                "missing_section",
                required_name,
                0,
                f"Missing required section '#$ {required_name}'.",
            )

    if options.allow_missing_nodename and "NODENAME" not in name_set:
        _add_warning(
            warnings,
            "optional_section_missing",
            "NODENAME",
            0,
            "Optional section '#$ NODENAME' is missing.",
        )
    if options.allow_missing_coords and "COORDS" not in name_set:
        _add_warning(
            warnings,
            "optional_section_missing",
            "COORDS",
            0,
            "Optional section '#$ COORDS' is missing.",
        )

    expected_indices: dict[str, int] = {
        name: index for index, name in enumerate(EXPECTED_SECTION_ORDER)
    }
    previous = -1
    for section in sections:
        if section.name not in expected_indices:
            _add_warning(
                warnings,
                "unknown_section",
                section.name,
                section.header_line,
                f"Unknown section '#$ {section.name}' encountered.",
            )
            continue
        current = expected_indices[section.name]
        if current < previous:
            _add_error(
                errors,
                "section_order",
                section.name,
                section.header_line,
                f"Section '#$ {section.name}' appears out of expected 2019 order.",
            )
        previous = max(previous, current)


def _get_section_map(sections: list[Section]) -> dict[str, Section]:
    section_map: dict[str, Section] = {}
    for section in sections:
        if section.name in section_map:
            # Keep first; duplicate detection is reported by caller.
            continue
        section_map[section.name] = section
    return section_map


def _validate_duplicates(sections: list[Section], errors: list[dict[str, object]]) -> None:
    seen: dict[str, int] = {}
    for section in sections:
        if section.name in seen:
            _add_error(
                errors,
                "duplicate_section",
                section.name,
                section.header_line,
                f"Duplicate section '#$ {section.name}' found.",
            )
        else:
            seen[section.name] = section.header_line


def _validate_control(
    section: Section | None,
    errors: list[dict[str, object]],
) -> dict[str, int]:
    if section is None:
        return {}
    rows = [entry for entry in section.payload if entry[1].strip()]
    if len(rows) < 4:
        _add_error(
            errors,
            "control_rows",
            "CONTROL",
            section.header_line,
            "CONTROL must contain at least 4 data rows.",
        )
        return {}

    parsed_rows: list[list[int]] = []
    expected_tokens = [6, 6, 6, 1]
    for row_index, expected_count in enumerate(expected_tokens, start=1):
        line_no, line_text = rows[row_index - 1]
        tokens = _fixed_fortran_fields(line_text, expected_count)
        if len(tokens) != expected_count:
            _add_error(
                errors,
                "control_token_count",
                "CONTROL",
                line_no,
                f"CONTROL row {row_index} must have {expected_count} tokens.",
            )
            return {}
        if not all(_is_int(token) for token in tokens):
            _add_error(
                errors,
                "control_token_type",
                "CONTROL",
                line_no,
                f"CONTROL row {row_index} must contain integer tokens only.",
            )
            return {}
        parsed_rows.append([int(token) for token in tokens])

    line1 = parsed_rows[0]
    line2 = parsed_rows[1]
    line3 = parsed_rows[2]
    line4 = parsed_rows[3]

    metrics = {
        "elements": line1[0],
        "nozzles": line1[1],
        "hangers": line1[2],
        "nodename_blocks": line1[3],
        "reducers": line1[4],
        "flanges": line1[5],
        "bends": line2[0],
        "rigids": line2[1],
        "expjts": line2[2],
        "restraints": line2[3],
        "displmnt": line2[4],
        "forcmnt": line2[5],
        "uniform": line3[0],
        "wind": line3[1],
        "offsets": line3[2],
        "allowbls": line3[3],
        "sif_tees": line3[4],
        "control_line3_field6": line3[5],
        "equipmnt": line4[0],
        "vertical_axis_flag": line4[0],
    }
    return metrics


def _validate_elements(
    section: Section | None,
    metrics: dict[str, int],
    options: RuleOptions,
    errors: list[dict[str, object]],
) -> None:
    if section is None:
        return
    element_count = int(metrics.get("elements", 0))
    if element_count <= 0:
        return

    rows = [entry for entry in section.payload if entry[1].strip()]
    expected_rows = element_count * 15
    if len(rows) < expected_rows:
        _add_error(
            errors,
            "elements_rows",
            "ELEMENTS",
            section.header_line,
            f"ELEMENTS has {len(rows)} rows, expected at least {expected_rows}.",
        )
        return

    for element_index in range(element_count):
        base = element_index * 15
        for row_offset, token_count in enumerate(TOKENS_PER_ELEMENT_ROW):
            line_no, line_text = rows[base + row_offset]
            row_no = row_offset + 1

            if row_no <= 9:
                if token_count is None:
                    _add_error(
                        errors,
                        "elements_internal_rule",
                        "ELEMENTS",
                        line_no,
                        "Internal checker rule error for ELEMENTS numeric row.",
                    )
                    continue
                tokens = _fixed_fortran_fields(line_text, token_count)
                for token in tokens:
                    if not _is_real(token):
                        _add_error(
                            errors,
                            "elements_numeric_format",
                            "ELEMENTS",
                            line_no,
                            f"ELEMENTS row {row_no} of element {element_index + 1} has non-real token '{token}'.",
                        )
                        break
            elif row_no == 10:
                # Element-name row (leading integer + optional text payload).
                if not _is_element_label_payload(line_text):
                    _add_error(
                        errors,
                        "element_name_fixed_width",
                        "ELEMENTS",
                        line_no,
                        "Element-name row must use a 12-character integer pointer field followed by a separator space.",
                    )
                    continue
                tokens = _tokens(line_text)
                if not tokens:
                    _add_error(
                        errors,
                        "element_name_missing",
                        "ELEMENTS",
                        line_no,
                        "Element-name row is empty.",
                    )
                else:
                    first = tokens[0]
                    if not _is_int(first):
                        _add_error(
                            errors,
                            "element_name_prefix_type",
                            "ELEMENTS",
                            line_no,
                            "Element-name row must start with an integer token.",
                        )
            elif row_no == 11:
                # Line number row (leading integer + optional text payload).
                if line_text.strip() and not _is_element_label_payload(line_text):
                    _add_error(
                        errors,
                        "line_label_fixed_width",
                        "ELEMENTS",
                        line_no,
                        "Line-number row must use a 12-character integer pointer field followed by a separator space.",
                    )
                    continue
                tokens = _tokens(line_text)
                if not tokens:
                    if not options.allow_zero_line_no:
                        _add_error(
                            errors,
                            "line_no_missing",
                            "ELEMENTS",
                            line_no,
                            "Line-number row is empty but allow-zero-line-no=false.",
                        )
                    continue
                if not _is_int(tokens[0]):
                    _add_error(
                        errors,
                        "line_label_prefix_type",
                        "ELEMENTS",
                        line_no,
                        "Line-number row must start with an integer token.",
                    )
                    continue
                if int(tokens[0]) == 0 and not options.allow_zero_line_no:
                    _add_error(
                        errors,
                        "line_no_zero",
                        "ELEMENTS",
                        line_no,
                        "Line-number token is zero but allow-zero-line-no=false.",
                    )
            elif row_no in (12, 13, 14, 15):
                if token_count is None:
                    _add_error(
                        errors,
                        "elements_internal_rule",
                        "ELEMENTS",
                        line_no,
                        "Internal checker rule error for ELEMENTS pointer row.",
                    )
                    continue
                tokens = _fixed_fortran_fields(line_text, token_count)
                if not all(_is_int(token) for token in tokens):
                    _add_error(
                        errors,
                        "elements_pointer_type",
                        "ELEMENTS",
                        line_no,
                        f"ELEMENTS pointer row {row_no} of element {element_index + 1} must contain integers.",
                    )


def _validate_pointer_range(
    errors: list[dict[str, object]],
    line_no: int,
    section_name: str,
    value_token: str,
    target_count: int,
    target_name: str,
) -> None:
    if not _is_int(value_token):
        return
    value = int(value_token)
    if value == 0:
        return
    if value < 0:
        _add_error(
            errors,
            "elements_pointer_negative",
            "ELEMENTS",
            line_no,
            f"{section_name} pointer {value} cannot be negative.",
        )
        return
    if value > target_count:
        _add_error(
            errors,
            "elements_pointer_range",
            "ELEMENTS",
            line_no,
            f"{section_name} pointer {value} exceeds {target_name} count {target_count}.",
        )


def _validate_element_pointer_ranges(
    section: Section | None,
    metrics: dict[str, int],
    errors: list[dict[str, object]],
) -> None:
    if section is None:
        return
    element_count = int(metrics.get("elements", 0))
    if element_count <= 0:
        return

    rows = [entry for entry in section.payload if entry[1].strip()]
    if len(rows) < element_count * 15:
        return

    for element_index in range(element_count):
        base = element_index * 15
        row13_line_no, row13_text = rows[base + 12]
        row14_line_no, row14_text = rows[base + 13]
        row15_line_no, row15_text = rows[base + 14]

        row13 = _fixed_fortran_fields(row13_text, 6)
        row14 = _fixed_fortran_fields(row14_text, 6)
        row15 = _fixed_fortran_fields(row15_text, 3)

        _validate_pointer_range(errors, row13_line_no, "BEND", row13[0], int(metrics.get("bends", 0)), "BEND")
        _validate_pointer_range(errors, row13_line_no, "RIGID", row13[1], int(metrics.get("rigids", 0)), "RIGID")
        _validate_pointer_range(errors, row13_line_no, "RESTRANT", row13[3], int(metrics.get("restraints", 0)), "RESTRANT")
        _validate_pointer_range(errors, row15_line_no, "REDUCERS", row15[0], int(metrics.get("reducers", 0)), "REDUCERS")


def _collect_element_node_ids(section: Section | None, metrics: dict[str, int]) -> set[int]:
    if section is None:
        return set()
    element_count = int(metrics.get("elements", 0))
    if element_count <= 0:
        return set()

    rows = [entry for entry in section.payload if entry[1].strip()]
    if len(rows) < element_count * 15:
        return set()

    node_ids: set[int] = set()
    for element_index in range(element_count):
        _line_no, line_text = rows[element_index * 15]
        tokens = _fixed_fortran_fields(line_text, 6)
        for token in tokens[:2]:
            if not _is_real(token):
                continue
            value = _real_value(token)
            rounded = int(round(value))
            if abs(value - rounded) < 1e-6:
                node_ids.add(rounded)
    return node_ids


def _validate_coords_node_references(
    coords_section: Section | None,
    elements_section: Section | None,
    metrics: dict[str, int],
    errors: list[dict[str, object]],
) -> None:
    if coords_section is None:
        return
    element_nodes = _collect_element_node_ids(elements_section, metrics)
    if not element_nodes:
        return

    rows = [entry for entry in coords_section.payload if entry[1].strip()]
    if len(rows) <= 1:
        return

    seen_nodes: set[int] = set()
    for line_no, line_text in rows[1:]:
        tokens = _fixed_fortran_fields(line_text, 4)
        node_token = tokens[0]
        if not _is_int(node_token):
            continue
        node_id = int(node_token)
        if node_id in seen_nodes:
            _add_error(
                errors,
                "coords_duplicate_node",
                "COORDS",
                line_no,
                f"COORDS contains duplicate node {node_id}.",
            )
        seen_nodes.add(node_id)
        if node_id not in element_nodes:
            _add_error(
                errors,
                "coords_unknown_node",
                "COORDS",
                line_no,
                f"COORDS node {node_id} does not appear in ELEMENTS connectivity.",
            )


def _validate_blocked_section(
    section: Section | None,
    section_name: str,
    expected_blocks: int,
    errors: list[dict[str, object]],
) -> None:
    if section is None:
        return
    lines_per_block = BLOCK_LINES_PER_SECTION[section_name]
    rows = list(section.payload)
    expected_rows = expected_blocks * lines_per_block
    if len(rows) != expected_rows:
        _add_error(
            errors,
            "section_block_rows",
            section_name,
            section.header_line,
            f"{section_name} has {len(rows)} rows, expected {expected_rows} "
            f"({expected_blocks} blocks x {lines_per_block} rows).",
        )


def _validate_nodename(
    section: Section | None,
    metrics: dict[str, int],
    options: RuleOptions,
    errors: list[dict[str, object]],
    warnings: list[dict[str, object]],
) -> None:
    expected_blocks = int(metrics.get("nodename_blocks", 0))
    if section is None:
        if expected_blocks > 0:
            if options.allow_missing_nodename:
                _add_warning(
                    warnings,
                    "nodename_missing_with_nonzero_control",
                    "NODENAME",
                    0,
                    "NODENAME section is missing while CONTROL NONAM > 0.",
                )
            else:
                _add_error(
                    errors,
                    "nodename_missing_with_nonzero_control",
                    "NODENAME",
                    0,
                    "NODENAME section is required when CONTROL NONAM > 0.",
                )
        return

    rows = [entry for entry in section.payload if entry[1].strip()]
    expected_rows = expected_blocks
    actual_rows = len(rows)
    if actual_rows > expected_rows:
        _add_error(
            errors,
            "nodename_rows",
            "NODENAME",
            section.header_line,
            f"NODENAME has {actual_rows} rows, expected at most {expected_rows} (NONAM count).",
        )
        return

    if actual_rows < expected_rows:
        _add_warning(
            warnings,
            "nodename_rows_short",
            "NODENAME",
            section.header_line,
            f"NODENAME has {actual_rows} rows, less than CONTROL NONAM {expected_rows}.",
        )

    for line_no, line_text in rows:
        if len(line_text) > 80:
            _add_warning(
                warnings,
                "nodename_line_length",
                "NODENAME",
                line_no,
                "NODENAME row exceeds 80 characters.",
            )


def _validate_units(section: Section | None, errors: list[dict[str, object]]) -> None:
    if section is None:
        return
    rows = list(section.payload)
    if len(rows) != UNITS_TOTAL_PAYLOAD_ROWS:
        _add_error(
            errors,
            "units_row_count",
            "UNITS",
            section.header_line,
            f"UNITS must contain exactly {UNITS_TOTAL_PAYLOAD_ROWS} payload rows.",
        )
    if len(rows) < len(UNITS_NUMERIC_TOKEN_COUNTS):
        _add_error(
            errors,
            "units_rows",
            "UNITS",
            section.header_line,
            "UNITS must contain at least 4 numeric rows.",
        )
        return

    numeric_values: list[float] = []
    for row_index, token_count in enumerate(UNITS_NUMERIC_TOKEN_COUNTS, start=1):
        line_no, line_text = rows[row_index - 1]
        tokens = _fixed_fortran_fields(line_text, token_count)
        for token in tokens:
            if not _is_real(token):
                _add_error(
                    errors,
                    "units_numeric_type",
                    "UNITS",
                    line_no,
                    f"UNITS numeric row {row_index} has non-real token '{token}'.",
                )
                break
            numeric_values.append(float(token))

    if numeric_values and all(abs(value) < 1e-12 for value in numeric_values):
        _add_error(
            errors,
            "units_numeric_all_zero",
            "UNITS",
            rows[0][0],
            "UNITS conversion constants are all zero; CAESAR can create a corrupted C2 from this file.",
        )


def _validate_coords(
    section: Section | None,
    options: RuleOptions,
    errors: list[dict[str, object]],
) -> None:
    if section is None:
        if not options.allow_missing_coords:
            _add_error(
                errors,
                "coords_missing",
                "COORDS",
                0,
                "COORDS section is required by checker options.",
            )
        return

    rows = [entry for entry in section.payload if entry[1].strip()]
    if not rows:
        _add_error(
            errors,
            "coords_empty",
            "COORDS",
            section.header_line,
            "COORDS section is empty.",
        )
        return

    header_line_no, header_text = rows[0]
    header_tokens = _fixed_fortran_fields(header_text, 1)
    if len(header_tokens) != 1 or not _is_int(header_tokens[0]):
        _add_error(
            errors,
            "coords_header",
            "COORDS",
            header_line_no,
            "COORDS first row must contain a single integer (NXYZ).",
        )
        return
    expected_points = int(header_tokens[0])
    remaining = rows[1:]
    if len(remaining) != expected_points:
        _add_error(
            errors,
            "coords_count",
            "COORDS",
            section.header_line,
            f"COORDS declares {expected_points} points but has {len(remaining)} coordinate rows.",
        )
        return
    for line_no, line_text in remaining:
        node = _fixed_fortran_fields(line_text, 1)
        coords = _fixed_fortran_fields(line_text, 4)
        tokens = [coords[0], coords[1], coords[2], coords[3]]
        if len(tokens) != 4:
            _add_error(
                errors,
                "coords_row_token_count",
                "COORDS",
                line_no,
                "Each COORDS row must contain 4 tokens (node, X, Y, Z).",
            )
            continue
        if not _is_int(node[0]):
            _add_error(
                errors,
                "coords_node_type",
                "COORDS",
                line_no,
                "COORDS node token must be integer.",
            )
        for token in tokens[1:]:
            if not _is_real(token):
                _add_error(
                    errors,
                    "coords_real_type",
                    "COORDS",
                    line_no,
                    f"COORDS coordinate token '{token}' is not a real number.",
                )
                break


def _validate_miscel_1(
    section: Section | None,
    metrics: dict[str, int],
    errors: list[dict[str, object]],
) -> None:
    if section is None:
        return
    rows = [entry for entry in section.payload if entry[1].strip()]
    if not rows:
        _add_error(
            errors,
            "miscel_empty",
            "MISCEL_1",
            section.header_line,
            "MISCEL_1 section is empty.",
        )
        return

    numelt = int(metrics.get("elements", 0))
    rrmat_lines = numelt // 6 + (1 if numelt % 6 else 0)
    cursor = 0
    if len(rows) < rrmat_lines:
        _add_error(
            errors,
            "miscel_rrmat_rows",
            "MISCEL_1",
            section.header_line,
            f"MISCEL_1 has insufficient RRMAT rows: expected {rrmat_lines}.",
        )
        return

    for rrm_index in range(rrmat_lines):
        line_no, line_text = rows[cursor + rrm_index]
        tokens = _tokens(line_text)
        if not tokens:
            _add_error(
                errors,
                "miscel_rrmat_empty_row",
                "MISCEL_1",
                line_no,
                "RRMAT row is empty.",
            )
            continue
        if len(tokens) > 6:
            _add_error(
                errors,
                "miscel_rrmat_token_count",
                "MISCEL_1",
                line_no,
                "RRMAT rows may contain at most 6 numeric tokens.",
            )
        for token in tokens:
            if not _is_real(token):
                _add_error(
                    errors,
                    "miscel_rrmat_token_type",
                    "MISCEL_1",
                    line_no,
                    f"RRMAT token '{token}' is not a real number.",
                )
                break
    cursor += rrmat_lines

    numnoz = int(metrics.get("nozzles", 0))
    hanger_count = int(metrics.get("hangers", 0))
    packed_hanger_rows = _ceil_div(hanger_count, 6) if hanger_count > 0 else 0
    nozzle_rows = numnoz * 4
    if len(rows) < cursor + nozzle_rows:
        _add_error(
            errors,
            "miscel_nozzle_rows",
            "MISCEL_1",
            section.header_line,
            f"MISCEL_1 has insufficient nozzle rows: expected {nozzle_rows}.",
        )
        return
    cursor += nozzle_rows

    if hanger_count > 0:
        expected_hanger_rows = 2 + packed_hanger_rows + (2 * hanger_count) + (2 * hanger_count) + hanger_count + (4 * packed_hanger_rows)
        if len(rows) < cursor + expected_hanger_rows:
            _add_error(
                errors,
                "miscel_hanger_rows",
                "MISCEL_1",
                section.header_line,
                f"MISCEL_1 has insufficient hanger rows: expected {expected_hanger_rows} after RRMAT/nozzle rows.",
            )
            return

        default_1_line, default_1_text = rows[cursor]
        default_1_tokens = _tokens(default_1_text)
        if len(default_1_tokens) != 6 or any(not _is_real(token) for token in default_1_tokens):
            _add_error(
                errors,
                "miscel_hanger_default_1",
                "MISCEL_1",
                default_1_line,
                "Hanger default row 1 must have 6 numeric tokens.",
            )
        cursor += 1

        default_2_line, default_2_text = rows[cursor]
        default_2_tokens = _tokens(default_2_text)
        if len(default_2_tokens) != 5 or any(not _is_int(token) for token in default_2_tokens):
            _add_error(
                errors,
                "miscel_hanger_default_2",
                "MISCEL_1",
                default_2_line,
                "Hanger default row 2 must have 5 integer tokens.",
            )
        cursor += 1

        def validate_packed_int_array(field_name: str) -> None:
            nonlocal cursor
            tokens: list[str] = []
            for row_offset in range(packed_hanger_rows):
                line_no, line_text = rows[cursor + row_offset]
                row_tokens = _tokens(line_text)
                if len(row_tokens) > 6:
                    _add_error(errors, f"miscel_{field_name}_row_width", "MISCEL_1", line_no, f"{field_name} row may contain at most 6 tokens.")
                for token in row_tokens:
                    if not _is_int(token):
                        _add_error(errors, f"miscel_{field_name}_token_type", "MISCEL_1", line_no, f"{field_name} token '{token}' is not an integer.")
                        break
                tokens.extend(row_tokens)
            if len(tokens) != hanger_count:
                line_no = rows[cursor][0]
                _add_error(errors, f"miscel_{field_name}_count", "MISCEL_1", line_no, f"{field_name} has {len(tokens)} tokens; expected {hanger_count}.")
            cursor += packed_hanger_rows

        validate_packed_int_array("ihgrnode")

        for hanger_index in range(hanger_count):
            row_1_line, row_1_text = rows[cursor]
            row_1_tokens = _tokens(row_1_text)
            if len(row_1_tokens) != 6 or any(not _is_real(token) for token in row_1_tokens):
                _add_error(errors, "miscel_hgrdat_row_1", "MISCEL_1", row_1_line, f"HGRDAT row 1 for hanger {hanger_index + 1} must have 6 numeric tokens.")
            cursor += 1

            row_2_line, row_2_text = rows[cursor]
            row_2_tokens = _tokens(row_2_text)
            if len(row_2_tokens) != 5 or any(not _is_real(token) for token in row_2_tokens):
                _add_error(errors, "miscel_hgrdat_row_2", "MISCEL_1", row_2_line, f"HGRDAT row 2 for hanger {hanger_index + 1} must have 5 numeric tokens.")
            cursor += 1

            for text_kind in ("TAG", "GUID"):
                line_no, line_text = rows[cursor]
                tokens = _tokens(line_text)
                if not tokens or not _is_int(tokens[0]):
                    _add_error(
                        errors,
                        "miscel_hanger_text_length",
                        "MISCEL_1",
                        line_no,
                        f"Hanger {text_kind} row for hanger {hanger_index + 1} must start with an integer length token.",
                    )
                cursor += 1

        for hanger_index in range(hanger_count):
            line_no, line_text = rows[cursor]
            tokens = _tokens(line_text)
            if len(tokens) != 4 or any(not _is_int(token) for token in tokens):
                _add_error(errors, "miscel_ihgrfree_row", "MISCEL_1", line_no, f"IHGRFREE row for hanger {hanger_index + 1} must have 4 integer tokens.")
            cursor += 1

        validate_packed_int_array("ihgrnum")
        validate_packed_int_array("ihgrtable")
        validate_packed_int_array("ihgrshort")
        validate_packed_int_array("ihgrcn")

    if len(rows) != cursor + 4:
        _add_error(
            errors,
            "miscel_row_count_exact",
            "MISCEL_1",
            section.header_line,
            f"MISCEL_1 has {len(rows)} nonblank rows; expected {cursor + 4} from CONTROL counts and section structure.",
        )
        return

    # Validate execution option syntax at the structural cursor, not by slicing from the end.
    exec_rows = rows[cursor:cursor + 4]
    for exec_index, (line_no, line_text) in enumerate(exec_rows, start=1):
        tokens = _tokens(line_text)
        expected = 6 if exec_index < 4 else 1
        if len(tokens) != expected:
            _add_error(
                errors,
                "miscel_execution_token_count",
                "MISCEL_1",
                line_no,
                f"MISCEL_1 execution row {exec_index} must have {expected} tokens.",
            )
            continue
        if exec_index < 4:
            for token in tokens:
                if not _is_real(token):
                    _add_error(
                        errors,
                        "miscel_execution_token_type",
                        "MISCEL_1",
                        line_no,
                        f"MISCEL_1 execution token '{token}' is not numeric.",
                    )
                    break
        else:
            if not _is_real(tokens[0]) and not _is_int(tokens[0]):
                _add_error(
                    errors,
                    "miscel_execution_north_arrow_type",
                    "MISCEL_1",
                    line_no,
                    "MISCEL_1 north-arrow token must be numeric.",
                )


def _validate_auxiliary_sections(
    section_map: dict[str, Section],
    metrics: dict[str, int],
    errors: list[dict[str, object]],
) -> None:
    metric_key_by_section = {
        "BEND": "bends",
        "RIGID": "rigids",
        "EXPJT": "expjts",
        "RESTRANT": "restraints",
        "DISPLMNT": "displmnt",
        "FORCMNT": "forcmnt",
        "UNIFORM": "uniform",
        "WIND": "wind",
        "OFFSETS": "offsets",
        "ALLOWBLS": "allowbls",
        "SIF&TEES": "sif_tees",
        "REDUCERS": "reducers",
        "FLANGES": "flanges",
        "EQUIPMNT": "equipmnt",
    }
    for section_name in BLOCK_LINES_PER_SECTION:
        metric_key = metric_key_by_section[section_name]
        expected_blocks = int(metrics.get(metric_key, 0))
        section = section_map.get(section_name)
        _validate_blocked_section(section, section_name, expected_blocks, errors)


def _validate_c2_risk_tokens(sections: list[Section], errors: list[dict[str, object]]) -> None:
    for section in sections:
        for line_no, line_text in section.payload:
            for raw_token in _tokens(line_text):
                token = raw_token.strip(" ,;\t")
                upper = token.upper()
                if upper in {"NAN", "+NAN", "-NAN", "INF", "+INF", "-INF", "INFINITY", "+INFINITY", "-INFINITY"}:
                    _add_error(
                        errors,
                        "non_finite_token",
                        section.name,
                        line_no,
                        f"Non-finite numeric token '{raw_token}' is not valid in CAESAR CII.",
                    )
                    continue
                if not _is_real(token):
                    continue
                value = float(token)
                if abs(value - CAESAR_INPUTXML_MISSING_SENTINEL) < 1e-6:
                    _add_error(
                        errors,
                        "inputxml_sentinel_leak",
                        section.name,
                        line_no,
                        "InputXML missing-value sentinel -1.0101 leaked into generated CII.",
                    )


def _build_report(
    input_path: Path,
    sections: list[Section],
    metrics: dict[str, int],
    errors: list[dict[str, object]],
    warnings: list[dict[str, object]],
    text: str | None = None,
) -> dict[str, object]:
    section_map = _get_section_map(sections)
    derived_counts: dict[str, object] = {}
    for section_name, lines_per_block in BLOCK_LINES_PER_SECTION.items():
        section = section_map.get(section_name)
        if section is None:
            continue
        rows = len(section.payload)
        derived_counts[section_name] = {
            "rows": rows,
            "linesPerBlock": lines_per_block,
            "derivedBlocks": rows // lines_per_block,
            "remainderRows": rows % lines_per_block,
        }

    spec_section_rules = None

    if cii2019_section_rules is not None and text is not None:
        try:
            section_report = cii2019_section_rules.validate_cii2019_sections(text)
            spec_section_rules = section_report.to_dict()
        except Exception as exc:
            spec_section_rules = {
                "ok": False,
                "issues": [
                    {
                        "code": "CII2019-SECTION-RULES-EXCEPTION",
                        "severity": "error",
                        "section": "GLOBAL",
                        "message": str(exc),
                        "expected": None,
                        "actual": None,
                    }
                ],
            }

    return {
        "ok": len(errors) == 0,
        "profile": "cii2019",
        "inputFile": str(input_path),
        "specSectionRules": spec_section_rules,
        "sectionsFound": [section.name for section in sections],
        "metrics": metrics,
        "derivedBlockCounts": derived_counts,
        "errors": errors,
        "warnings": warnings,
    }


def validate_cii_text(
    text: str,
    input_path: Path,
    options: RuleOptions,
) -> dict[str, object]:
    lines = text.splitlines()
    sections = _parse_sections(lines)
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []

    if not sections:
        _add_error(
            errors,
            "no_sections",
            "GLOBAL",
            0,
            "No '#$ <SECTION>' headers found in file.",
        )
        return _build_report(input_path, sections, {}, errors, warnings, text=text)

    _validate_duplicates(sections, errors)
    _validate_order(sections, options, errors, warnings)
    _validate_c2_risk_tokens(sections, errors)

    section_map = _get_section_map(sections)
    metrics = _validate_control(section_map.get("CONTROL"), errors)

    _validate_elements(section_map.get("ELEMENTS"), metrics, options, errors)
    _validate_element_pointer_ranges(section_map.get("ELEMENTS"), metrics, errors)
    _validate_auxiliary_sections(section_map, metrics, errors)
    _validate_nodename(
        section_map.get("NODENAME"),
        metrics,
        options,
        errors,
        warnings,
    )
    _validate_miscel_1(section_map.get("MISCEL_1"), metrics, errors)
    _validate_units(section_map.get("UNITS"), errors)
    _validate_coords(section_map.get("COORDS"), options, errors)
    _validate_coords_node_references(
        section_map.get("COORDS"),
        section_map.get("ELEMENTS"),
        metrics,
        errors,
    )

    return _build_report(input_path, sections, metrics, errors, warnings, text=text)


def _validate(
    input_path: Path,
    options: RuleOptions,
) -> dict[str, object]:
    text = input_path.read_text(encoding="utf-8", errors="replace")
    return validate_cii_text(text, input_path, options)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate CAESAR II CII syntax for 2019 neutral format (format-only)."
    )
    parser.add_argument("--input", required=True, type=Path, help="Input CII file path.")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON report path.")

    parser.add_argument(
        "--allow-missing-nodename",
        dest="allow_missing_nodename",
        action="store_true",
        default=True,
        help="Allow missing NODENAME section (default: true).",
    )
    parser.add_argument(
        "--disallow-missing-nodename",
        dest="allow_missing_nodename",
        action="store_false",
        help="Require NODENAME section to exist.",
    )
    parser.add_argument(
        "--allow-zero-line-no",
        dest="allow_zero_line_no",
        action="store_true",
        default=True,
        help="Allow zero/blank line number payload in ELEMENTS line row (default: true).",
    )
    parser.add_argument(
        "--disallow-zero-line-no",
        dest="allow_zero_line_no",
        action="store_false",
        help="Disallow zero/blank line number payload in ELEMENTS line row.",
    )
    parser.add_argument(
        "--allow-missing-coords",
        dest="allow_missing_coords",
        action="store_true",
        default=True,
        help="Allow missing COORDS section (default: true).",
    )
    parser.add_argument(
        "--disallow-missing-coords",
        dest="allow_missing_coords",
        action="store_false",
        help="Require COORDS section to exist.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    options = RuleOptions(
        allow_missing_nodename=bool(args.allow_missing_nodename),
        allow_zero_line_no=bool(args.allow_zero_line_no),
        allow_missing_coords=bool(args.allow_missing_coords),
    )
    report = _validate(args.input, options)
    report_text = json.dumps(report, indent=2, sort_keys=False)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report_text, encoding="utf-8")
    print(report_text)

    if report["ok"]:
        return 0

    first_error = report["errors"][0] if report.get("errors") else None
    if first_error:
        print(
            f"Syntax check failed at line {first_error.get('line', 0)} "
            f"[{first_error.get('section', 'GLOBAL')}]: {first_error.get('message', '')}",
            file=sys.stderr,
        )
    else:
        print("Syntax check failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
