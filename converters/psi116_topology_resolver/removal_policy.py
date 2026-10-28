"""Source-record vetoes shared by planning and the authoritative mutation guard."""
from .models import NodeRecord, ResolverConfig


def _compatible_number(left: float | None, right: float | None, tolerance: float = 1e-9) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(left - right) <= tolerance


def can_remove_plain_pipe(record: NodeRecord, owner: NodeRecord, config: ResolverConfig) -> tuple[bool, str]:
    if record.semantic_type != "PIPE":
        return False, "ABSORBED_NODE_NOT_PIPE"
    if record.has_restraint:
        return False, "ABSORBED_PIPE_HAS_RESTRAINT"
    if record.rigid not in {None, 0}:
        return False, "ABSORBED_PIPE_HAS_RIGID_EVIDENCE"
    if record.weight is not None and abs(record.weight) > 1e-12:
        return False, "ABSORBED_PIPE_HAS_WEIGHT"
    if record.node_name:
        return False, "ABSORBED_PIPE_HAS_NODE_NAME"
    if record.position is None or owner.position is None or record.position.distance_to(owner.position) > config.connection_tolerance_mm:
        return False, "ABSORBED_PIPE_NOT_COINCIDENT_WITH_OWNER"
    if not _compatible_number(record.outside_diameter, owner.outside_diameter):
        return False, "ABSORBED_PIPE_DIAMETER_DIFFERS"
    if not _compatible_number(record.wall_thickness, owner.wall_thickness):
        return False, "ABSORBED_PIPE_WALL_DIFFERS"
    if record.component_ref_no:
        return False, "ABSORBED_PIPE_HAS_COMPONENT_REF_NO"
    return True, "PLAIN_PIPE_WITHOUT_ENGINEERING_SEMANTICS"
