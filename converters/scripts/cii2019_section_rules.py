#!/usr/bin/env python3
"""
CAESAR II 2019 neutral-file section rules.

Purpose:
- Keep fragile CII sections grounded in CAESAR II neutral-file rules.
- Validate generated CII before accepting/writing benchmark result.
- Prevent common failures:
  - CONTROL count mismatch
  - missing MISCEL_1
  - EQUIPMNT swallowing MISCEL_1 rows
  - SIF&TEES wrong row count
  - UNITS wrong row count
  - invalid section order

This module does NOT learn dynamic payload from benchmark CII.
Benchmark CII may be used elsewhere for optional calibration only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Mapping, Sequence


SECTION_HEADER_RX = re.compile(r"^\s*#\$\s+([A-Z0-9_&]+)\b.*$")


# Section order from the neutral-file section sequence.
SECTION_ORDER_2019: tuple[str, ...] = (
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
)


# NODENAME and COORDS are optional per neutral-file guide.
REQUIRED_SECTIONS_2019: frozenset[str] = frozenset(
    {
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
)


# Payload rows per auxiliary block from the neutral-file rules.
# Important: FLANGES is 12 lines, not 11.
LINES_PER_AUX_BLOCK: dict[str, int] = {
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


# ELEMENTS layout currently used by the converter profile:
# 9 real rows + string/name/line rows + 3 IEL rows = 15 payload rows per element.
ELEMENT_LINES_PER_BLOCK = 15


# UNITS = 4 real conversion-constant lines + 24 label lines.
UNITS_CONSTANT_LINES = 4
UNITS_LABEL_LINES = 24
UNITS_TOTAL_LINES = UNITS_CONSTANT_LINES + UNITS_LABEL_LINES


# MISCEL_1 constants from neutral-file guide.
RRMAT_VALUES_PER_LINE = 6
VFLEX_LINES_PER_NOZZLE = 4
MISCEL_EXECUTION_OPTION_LINES = 4

# Hanger arrays:
# - 2 default/header rows
# - IHGRNODE packed integer array
# - HGRDAT: 2 rows per hanger
# - Tag/GUID: 2 rows per hanger
# - IHGRFREE: 1 row per hanger
# - IHGRNUM packed array
# - IHGRTABLE packed array
# - IHGRSHORT packed array
# - IHGRCN packed array
HANGER_HEADER_LINES = 2
HGRDAT_LINES_PER_HANGER = 2
HANGER_TAG_GUID_LINES_PER_HANGER = 2
IHGRFREE_LINES_PER_HANGER = 1


@dataclass(frozen=True)
class ControlCounts:
    """
    CONTROL section values in CAESAR II neutral-file order.

    Row 1:
      NUMELT, NUMNOZ, NOHGRS, NONAM, NORED, NUMFLG

    Row 2:
      BEND, RIGID, EXPJT, RESTRANT, DISPLMNT, FORCMNT

    Row 3:
      UNIFORM, WIND, OFFSETS, ALLOWBLS, SIF&TEES, IZUP

    Row 4:
      EQUIPMNT
    """

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

    def as_control_rows(self) -> list[list[int]]:
        return [
            [self.numelt, self.numnoz, self.nohgrs, self.nonam, self.nored, self.numflg],
            [self.bends, self.rigids, self.expjts, self.restraints, self.displmnt, self.forcmnt],
            [self.uniform, self.wind, self.offsets, self.allowbls, self.sif_tees, self.izup],
            [self.equipmnt],
        ]


@dataclass(frozen=True)
class SectionValidationIssue:
    code: str
    severity: str
    section: str
    message: str
    expected: int | str | None = None
    actual: int | str | None = None


@dataclass
class SectionValidationReport:
    ok: bool = True
    issues: list[SectionValidationIssue] = field(default_factory=list)

    def add(
        self,
        code: str,
        section: str,
        message: str,
        *,
        severity: str = "error",
        expected: int | str | None = None,
        actual: int | str | None = None,
    ) -> None:
        self.issues.append(
            SectionValidationIssue(
                code=code,
                severity=severity,
                section=section,
                message=message,
                expected=expected,
                actual=actual,
            )
        )
        if severity == "error":
            self.ok = False

    def extend(self, other: "SectionValidationReport") -> None:
        self.issues.extend(other.issues)
        self.ok = self.ok and other.ok

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "issues": [issue.__dict__.copy() for issue in self.issues],
        }


def nonblank_rows(rows: Iterable[str]) -> list[str]:
    return [str(row) for row in rows if str(row).strip()]


def aux_block_rows(rows: Iterable[str]) -> list[str]:
    """Row list for aux-block count/chunking arithmetic.

    Unlike nonblank_rows, this does NOT drop blank lines: at least the
    FLANGES block layout has a genuinely blank row at a fixed position
    within every real 12-line record (confirmed against real CAESAR II
    CII 2019 exports), so stripping blanks before dividing by
    LINES_PER_AUX_BLOCK[section] corrupts the block count for any file
    with real flange data - a correctly-formatted section gets rejected
    as malformed. Blank lines within a fixed-width block are content,
    not padding to be discarded.
    """
    return [str(row) for row in rows]


def ceil_div(value: int, divisor: int) -> int:
    if value < 0:
        raise ValueError(f"Cannot ceil-divide negative value {value}.")
    if divisor <= 0:
        raise ValueError(f"Divisor must be positive, got {divisor}.")
    return value // divisor + (1 if value % divisor else 0)


def rrmat_line_count(numelt: int) -> int:
    return ceil_div(numelt, RRMAT_VALUES_PER_LINE)


def packed_integer_array_line_count(count: int, values_per_line: int = 6) -> int:
    return ceil_div(count, values_per_line)


def expected_hanger_payload_lines(nohgrs: int) -> int:
    """
    Expected hanger payload row count inside MISCEL_1 for H hangers.

    Based on the neutral-file hanger data layout:
    - 2 default/control rows
    - IHGRNODE packed integer array
    - HGRDAT: 2 rows per hanger
    - Hanger Tag/GUID: 2 rows per hanger
    - IHGRFREE: 1 row per hanger
    - IHGRNUM packed integer array
    - IHGRTABLE packed integer array
    - IHGRSHORT packed integer array
    - IHGRCN packed integer array
    """

    if nohgrs <= 0:
        return 0

    packed = packed_integer_array_line_count(nohgrs)

    return (
        HANGER_HEADER_LINES
        + packed
        + HGRDAT_LINES_PER_HANGER * nohgrs
        + HANGER_TAG_GUID_LINES_PER_HANGER * nohgrs
        + IHGRFREE_LINES_PER_HANGER * nohgrs
        + packed  # IHGRNUM
        + packed  # IHGRTABLE
        + packed  # IHGRSHORT
        + packed  # IHGRCN
    )


def expected_miscel_1_min_lines(control: ControlCounts) -> int:
    """
    Minimum MISCEL_1 payload rows:

    RRMAT material IDs
    + VFLEX nozzle data
    + hanger arrays
    + execution options
    """

    return (
        rrmat_line_count(control.numelt)
        + control.numnoz * VFLEX_LINES_PER_NOZZLE
        + expected_hanger_payload_lines(control.nohgrs)
        + MISCEL_EXECUTION_OPTION_LINES
    )


def parse_section_map(cii_text: str) -> dict[str, list[str]]:
    """
    Parse CII text into section-name -> payload rows.

    Duplicate sections are merged in encounter order so row-count diagnostics can
    still inspect payload. Duplicate-section errors are reported separately.
    """

    sections: dict[str, list[str]] = {}
    current: str | None = None

    for raw in cii_text.splitlines():
        line = raw.rstrip("\r\n")
        match = SECTION_HEADER_RX.match(line.lstrip("\ufeff"))
        if match:
            current = match.group(1)
            sections.setdefault(current, [])
            continue

        if current is not None:
            sections[current].append(line)

    return sections


def parse_section_order(cii_text: str) -> list[str]:
    order: list[str] = []

    for raw in cii_text.splitlines():
        line = raw.rstrip("\r\n")
        match = SECTION_HEADER_RX.match(line.lstrip("\ufeff"))
        if match:
            order.append(match.group(1))

    return order


def parse_control_counts(control_rows: Sequence[str]) -> ControlCounts:
    rows = nonblank_rows(control_rows)

    if len(rows) < 4:
        raise ValueError(f"CONTROL requires at least 4 payload rows, got {len(rows)}.")

    parsed: list[list[int]] = []

    for index, row in enumerate(rows[:4], start=1):
        tokens = row.split()
        if not tokens:
            raise ValueError(f"CONTROL row {index} is blank.")

        try:
            parsed.append([int(token) for token in tokens])
        except ValueError as exc:
            raise ValueError(f"CONTROL row {index} contains non-integer token: {row!r}.") from exc

    if len(parsed[0]) < 6:
        raise ValueError("CONTROL row 1 must contain at least 6 integers.")
    if len(parsed[1]) < 6:
        raise ValueError("CONTROL row 2 must contain at least 6 integers.")
    if len(parsed[2]) < 6:
        raise ValueError("CONTROL row 3 must contain at least 6 integers.")
    if len(parsed[3]) < 1:
        raise ValueError("CONTROL row 4 must contain at least 1 integer.")

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


def format_control_rows(control: ControlCounts) -> list[str]:
    """
    Format CONTROL rows using the specified fixed-width integer layout:
    2X, 6I13 for rows 1-3 and 2X, I13 for row 4.
    """

    return [
        "  " + "".join(f"{value:13d}" for value in row)
        for row in control.as_control_rows()
    ]


def validate_required_sections(section_order: Sequence[str]) -> SectionValidationReport:
    report = SectionValidationReport()

    for required in sorted(REQUIRED_SECTIONS_2019):
        if required not in section_order:
            report.add(
                "CII2019-MISSING-SECTION",
                required,
                f"Required section #$ {required} is missing.",
                expected="present",
                actual="missing",
            )

    for name in sorted(set(section_order)):
        count = section_order.count(name)
        if count > 1:
            report.add(
                "CII2019-DUPLICATE-SECTION",
                name,
                f"Section #$ {name} appears {count} times.",
                expected=1,
                actual=count,
            )

    return report


def validate_section_order(section_order: Sequence[str]) -> SectionValidationReport:
    report = SectionValidationReport()
    expected_index = {name: index for index, name in enumerate(SECTION_ORDER_2019)}

    last_index = -1
    last_name = ""

    for name in section_order:
        if name not in expected_index:
            report.add(
                "CII2019-UNKNOWN-SECTION",
                name,
                f"Section #$ {name} is not in the CII 2019 expected section order.",
                severity="warning",
            )
            continue

        index = expected_index[name]

        if index < last_index:
            report.add(
                "CII2019-SECTION-ORDER",
                name,
                f"Section #$ {name} appears after #$ {last_name}, violating CII 2019 order.",
                expected=f"index >= {last_index}",
                actual=f"index {index}",
            )
        else:
            last_index = index
            last_name = name

    return report


def validate_aux_block_rows(
    sections: Mapping[str, Sequence[str]],
    control: ControlCounts,
) -> SectionValidationReport:
    report = SectionValidationReport()

    expected_blocks = {
        "BEND": control.bends,
        "RIGID": control.rigids,
        "EXPJT": control.expjts,
        "RESTRANT": control.restraints,
        "DISPLMNT": control.displmnt,
        "FORCMNT": control.forcmnt,
        "UNIFORM": control.uniform,
        "WIND": control.wind,
        "OFFSETS": control.offsets,
        "ALLOWBLS": control.allowbls,
        "SIF&TEES": control.sif_tees,
        "REDUCERS": control.nored,
        "FLANGES": control.numflg,
        "EQUIPMNT": control.equipmnt,
    }

    for section, lines_per_block in LINES_PER_AUX_BLOCK.items():
        rows = aux_block_rows(sections.get(section, []))
        blocks = expected_blocks.get(section, 0)
        expected_rows = blocks * lines_per_block

        if len(rows) != expected_rows:
            report.add(
                "CII2019-AUX-ROW-COUNT",
                section,
                (
                    f"#$ {section} has {len(rows)} payload rows; expected "
                    f"{expected_rows} ({blocks} blocks x {lines_per_block} rows)."
                ),
                expected=expected_rows,
                actual=len(rows),
            )

    return report


def validate_elements_rows(
    sections: Mapping[str, Sequence[str]],
    control: ControlCounts,
) -> SectionValidationReport:
    report = SectionValidationReport()

    rows = nonblank_rows(sections.get("ELEMENTS", []))
    expected_rows = control.numelt * ELEMENT_LINES_PER_BLOCK

    if len(rows) != expected_rows:
        report.add(
            "CII2019-ELEMENTS-ROW-COUNT",
            "ELEMENTS",
            (
                f"#$ ELEMENTS has {len(rows)} payload rows; expected "
                f"{expected_rows} ({control.numelt} elements x {ELEMENT_LINES_PER_BLOCK} rows)."
            ),
            expected=expected_rows,
            actual=len(rows),
        )

    return report


def validate_units(sections: Mapping[str, Sequence[str]]) -> SectionValidationReport:
    report = SectionValidationReport()

    # UNITS has intentional blank label rows in CAESAR output; count payload
    # rows, not only nonblank rows.
    rows = list(sections.get("UNITS", []))

    if len(rows) != UNITS_TOTAL_LINES:
        report.add(
            "CII2019-UNITS-ROW-COUNT",
            "UNITS",
            (
                f"#$ UNITS has {len(rows)} payload rows; expected "
                f"{UNITS_TOTAL_LINES} ({UNITS_CONSTANT_LINES} conversion rows + "
                f"{UNITS_LABEL_LINES} label rows)."
            ),
            expected=UNITS_TOTAL_LINES,
            actual=len(rows),
        )

    return report


def validate_miscel_1(
    sections: Mapping[str, Sequence[str]],
    control: ControlCounts,
    section_order: Sequence[str] | None = None,
) -> SectionValidationReport:
    report = SectionValidationReport()

    rows = nonblank_rows(sections.get("MISCEL_1", []))
    min_rows = expected_miscel_1_min_lines(control)

    if not rows:
        report.add(
            "CII2019-MISCEL1-MISSING-PAYLOAD",
            "MISCEL_1",
            "#$ MISCEL_1 is missing or has no payload rows.",
            expected=f">= {min_rows}",
            actual=0,
        )
        return report

    if len(rows) < min_rows:
        report.add(
            "CII2019-MISCEL1-MIN-ROW-COUNT",
            "MISCEL_1",
            (
                f"#$ MISCEL_1 has {len(rows)} payload rows; expected at least "
                f"{min_rows} for RRMAT + nozzles + hangers + execution options."
            ),
            expected=f">= {min_rows}",
            actual=len(rows),
        )

    rrmat_rows = rrmat_line_count(control.numelt)

    if len(rows) >= rrmat_rows:
        rrmat_tokens: list[str] = []
        for row in rows[:rrmat_rows]:
            rrmat_tokens.extend(row.split())

        if len(rrmat_tokens) < control.numelt:
            report.add(
                "CII2019-MISCEL1-RRMAT-COUNT",
                "MISCEL_1",
                f"RRMAT has {len(rrmat_tokens)} material ID tokens; expected {control.numelt}.",
                expected=control.numelt,
                actual=len(rrmat_tokens),
            )

    if section_order is not None:
        try:
            equip_index = section_order.index("EQUIPMNT")
            miscel_index = section_order.index("MISCEL_1")
            units_index = section_order.index("UNITS")
        except ValueError:
            # Missing-section validator reports missing section.
            return report

        if not (equip_index < miscel_index < units_index):
            report.add(
                "CII2019-MISCEL1-ORDER",
                "MISCEL_1",
                "#$ MISCEL_1 must appear after #$ EQUIPMNT and before #$ UNITS.",
                expected="EQUIPMNT < MISCEL_1 < UNITS",
                actual=" < ".join(section_order),
            )

    return report


def validate_control_against_sections(
    sections: Mapping[str, Sequence[str]],
    control: ControlCounts,
    section_order: Sequence[str] | None = None,
) -> SectionValidationReport:
    report = SectionValidationReport()

    report.extend(validate_elements_rows(sections, control))
    report.extend(validate_aux_block_rows(sections, control))
    report.extend(validate_miscel_1(sections, control, section_order))
    report.extend(validate_units(sections))

    return report


def validate_cii2019_sections(cii_text: str) -> SectionValidationReport:
    """
    Full section-level validation for generated CII 2019 text.

    This is intended to run after generation and before accepting output.
    """

    sections = parse_section_map(cii_text)
    order = parse_section_order(cii_text)

    report = SectionValidationReport()
    report.extend(validate_required_sections(order))
    report.extend(validate_section_order(order))

    if "CONTROL" not in sections:
        return report

    try:
        control = parse_control_counts(sections["CONTROL"])
    except ValueError as exc:
        report.add(
            "CII2019-CONTROL-PARSE",
            "CONTROL",
            str(exc),
        )
        return report

    report.extend(validate_control_against_sections(sections, control, order))

    return report


def assert_cii2019_sections_valid(cii_text: str) -> None:
    """
    Raise ValueError if CII section validation fails.
    Useful for fail-closed converter mode.
    """

    report = validate_cii2019_sections(cii_text)
    if report.ok:
        return

    messages = [
        f"{issue.code} [{issue.section}]: {issue.message}"
        for issue in report.issues
        if issue.severity == "error"
    ]

    raise ValueError("CII 2019 section validation failed:\n" + "\n".join(messages))
def build_control_from_sections(
    sections: Mapping[str, Sequence[str]],
    *,
    numelt: int,
    numnoz: int,
    nohgrs: int,
    nonam: int = 0,
    izup: int = 0,
) -> ControlCounts:
    """
    Build CONTROL counts from already-emitted section payloads.

    This prevents CONTROL from becoming an independent guessed/cached count.
    The caller supplies only source-model counts that are not directly row-derived:
    - numelt
    - numnoz
    - nohgrs
    - nonam
    - izup

    All auxiliary counts are derived from emitted section row counts.
    """

    def _block_count(section_name: str) -> int:
        rows = aux_block_rows(sections.get(section_name, []))
        lines_per_block = LINES_PER_AUX_BLOCK[section_name]

        if len(rows) % lines_per_block != 0:
            raise ValueError(
                f"Cannot build CONTROL: #$ {section_name} has {len(rows)} rows, "
                f"not a multiple of {lines_per_block}."
            )

        return len(rows) // lines_per_block

    return ControlCounts(
        numelt=numelt,
        numnoz=numnoz,
        nohgrs=nohgrs,
        nonam=nonam,
        nored=_block_count("REDUCERS"),
        numflg=_block_count("FLANGES"),
        bends=_block_count("BEND"),
        rigids=_block_count("RIGID"),
        expjts=_block_count("EXPJT"),
        restraints=_block_count("RESTRANT"),
        displmnt=_block_count("DISPLMNT"),
        forcmnt=_block_count("FORCMNT"),
        uniform=_block_count("UNIFORM"),
        wind=_block_count("WIND"),
        offsets=_block_count("OFFSETS"),
        allowbls=_block_count("ALLOWBLS"),
        sif_tees=_block_count("SIF&TEES"),
        izup=izup,
        equipmnt=_block_count("EQUIPMNT"),
    )
