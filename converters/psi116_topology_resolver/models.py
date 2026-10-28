from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import math


SCHEMA_FINDINGS = "psi116-topology-findings/v1"
SCHEMA_FIX_PLAN = "psi116-topology-fix-plan/v1"

SPECIAL_TYPES = frozenset({"ELBO", "TEE", "OLET", "REDU", "BRAN"})
POINT_TYPES = frozenset({"ATTA", "SUPPORT", "ANCI"})
INLINE_TYPES = frozenset({"VALV", "FLAN", "GASK", "INST", "RIGID"})
DEFINITELY_NON_RIGID_TYPES = frozenset({"PIPE", "ELBO", "TEE", "OLET", "REDU", "BRAN", "ATTA", "SUPPORT", "ANCI"})
TYPE_ALIASES = {
    "BEND": "ELBO",
    "ELBOW": "ELBO",
    "REDUCER": "REDU",
    "WELDOLET": "OLET",
    "SOCKOLET": "OLET",
    "SUPPORT": "ATTA",
    "ANCI": "ATTA",
}


@dataclass(frozen=True)
class ResolverConfig:
    exact_coincidence_tolerance_mm: float = 0.001
    connection_tolerance_mm: float = 0.5
    short_span_threshold_mm: float = 6.0
    collinear_tolerance_mm: float = 0.5
    angle_tolerance_deg: float = 0.1

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be a non-negative finite number.")
        if self.exact_coincidence_tolerance_mm > self.connection_tolerance_mm:
            raise ValueError("exact coincidence tolerance cannot exceed connection tolerance.")
        if self.connection_tolerance_mm > self.short_span_threshold_mm:
            raise ValueError("connection tolerance cannot exceed short-span threshold.")


@dataclass(frozen=True)
class Position:
    x: float
    y: float
    z: float

    def distance_to(self, other: "Position") -> float:
        return math.dist((self.x, self.y, self.z), (other.x, other.y, other.z))

    def as_list(self) -> list[float]:
        return [self.x, self.y, self.z]


@dataclass(frozen=True)
class NodeRecord:
    branch_index: int
    branch_name: str
    source_index: int
    node_number: int | None
    node_name: str
    endpoint: int | None
    component_type: str
    raw_component_type: str
    component_ref_no: str
    connection_type: str
    position: Position | None
    rigid: int | None
    weight: float | None
    outside_diameter: float | None
    wall_thickness: float | None
    bend_radius: float | None
    alpha_angle: float | None
    has_restraint: bool
    raw_xml: str

    @property
    def key(self) -> str:
        number = "none" if self.node_number is None else str(self.node_number)
        return f"B{self.branch_index}:N{number}:S{self.source_index}"

    @property
    def positive(self) -> bool:
        return self.node_number is not None and self.node_number > 0

    @property
    def semantic_type(self) -> str:
        if self.component_type == "BRAN" and self.connection_type == "TEE":
            return "TEE"
        return self.component_type

    @property
    def carries_engineering_semantics(self) -> bool:
        return bool(
            self.node_name
            or self.has_restraint
            or self.rigid not in {None, 0}
            or (self.weight is not None and abs(self.weight) > 1e-12)
            or self.semantic_type != "PIPE"
            or self.component_ref_no
        )


@dataclass(frozen=True)
class BranchRecord:
    index: int
    name: str
    nodes: tuple[NodeRecord, ...]


@dataclass(frozen=True)
class ComponentOccurrence:
    occurrence_id: str
    branch_index: int
    branch_name: str
    component_ref_no: str
    semantic_type: str
    records: tuple[NodeRecord, ...]

    @property
    def positive_node_numbers(self) -> tuple[int, ...]:
        return tuple(record.node_number for record in self.records if record.positive and record.node_number is not None)

    @property
    def endpoint_set(self) -> tuple[int, ...]:
        return tuple(sorted({record.endpoint for record in self.records if record.endpoint is not None}))


@dataclass(frozen=True)
class RouteSpan:
    span_id: str
    branch_index: int
    branch_name: str
    branch_order: int
    span_role: str
    occurrence_ids: tuple[str, ...]
    from_node: NodeRecord
    to_node: NodeRecord
    length_mm: float

    @property
    def semantic_types(self) -> tuple[str, str]:
        return self.from_node.semantic_type, self.to_node.semantic_type


@dataclass(frozen=True)
class Finding:
    finding_id: str
    code: str
    severity: str
    blocking: bool
    message: str
    branch_name: str = ""
    node_keys: tuple[str, ...] = ()
    node_numbers: tuple[int, ...] = ()
    component_ref_nos: tuple[str, ...] = ()
    span_ids: tuple[str, ...] = ()
    length_mm: float | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FixAction:
    action_id: str
    finding_ids: tuple[str, ...]
    disposition: str
    status: str
    confidence: float
    authority: str
    message: str
    branch_name: str = ""
    node_numbers: tuple[int, ...] = ()
    component_ref_nos: tuple[str, ...] = ()
    span_ids: tuple[str, ...] = ()
    owner_node_number: int | None = None
    absorbed_node_numbers: tuple[int, ...] = ()
    proposed_changes: tuple[dict[str, object], ...] = ()
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Psi116Document:
    source_path: str
    source_text: str
    source_sha256: str
    namespace: str
    branches: tuple[BranchRecord, ...]
    occurrences: tuple[ComponentOccurrence, ...]
    spans: tuple[RouteSpan, ...]


@dataclass(frozen=True)
class ResolutionResult:
    document: Psi116Document
    findings: tuple[Finding, ...]
    fix_actions: tuple[FixAction, ...]

    def findings_payload(self, config: ResolverConfig) -> dict[str, object]:
        counts = Counter(finding.code for finding in self.findings)
        blocking = sum(1 for finding in self.findings if finding.blocking)
        return {
            "schema": SCHEMA_FINDINGS,
            "source": {
                "path": self.document.source_path,
                "sha256": self.document.source_sha256,
                "namespace": self.document.namespace,
            },
            "config": asdict(config),
            "summary": {
                "branchCount": len(self.document.branches),
                "sourceNodeRecordCount": sum(len(branch.nodes) for branch in self.document.branches),
                "componentOccurrenceCount": len(self.document.occurrences),
                "positiveRouteSpanCount": len(self.document.spans),
                "findingCount": len(self.findings),
                "blockingFindingCount": blocking,
                "findingCountsByCode": dict(sorted(counts.items())),
            },
            "findings": [finding_to_dict(finding) for finding in self.findings],
        }

    def fix_plan_payload(self, config: ResolverConfig) -> dict[str, object]:
        counts = Counter(action.disposition for action in self.fix_actions)
        blocked = sum(1 for action in self.fix_actions if action.status == "BLOCKED")
        return {
            "schema": SCHEMA_FIX_PLAN,
            "source": {
                "path": self.document.source_path,
                "sha256": self.document.source_sha256,
                "namespace": self.document.namespace,
            },
            "config": asdict(config),
            "mutationPolicy": "DRY_RUN_ONLY",
            "sourceXmlMutated": False,
            "summary": {
                "actionCount": len(self.fix_actions),
                "blockedActionCount": blocked,
                "proposedActionCount": len(self.fix_actions) - blocked,
                "actionCountsByDisposition": dict(sorted(counts.items())),
            },
            "actions": [action_to_dict(action) for action in self.fix_actions],
        }


def finding_to_dict(finding: Finding) -> dict[str, object]:
    payload = asdict(finding)
    for key in ("node_keys", "node_numbers", "component_ref_nos", "span_ids"):
        payload[key] = list(payload[key])
    return payload


def action_to_dict(action: FixAction) -> dict[str, object]:
    payload = asdict(action)
    for key in (
        "finding_ids", "node_numbers", "component_ref_nos", "span_ids",
        "absorbed_node_numbers", "proposed_changes", "blockers",
    ):
        payload[key] = list(payload[key])
    return payload
