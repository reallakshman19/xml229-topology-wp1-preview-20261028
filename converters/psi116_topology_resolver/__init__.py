"""PSI116 topology analysis, dry-run planning, and explicit transactional sidecar correction."""

from .models import ResolverConfig, ResolutionResult
from .parser import read_psi116_xml
from .resolver import analyze_document, resolve_psi116, write_sidecars
from .lineage import (
    TopoFixLineageError,
    build_topofix_source_lineage,
    verify_topofix_pre_final,
)
from .transaction import (
    TopoFixTransactionResult,
    TransactionPolicy,
    apply_topofix_transaction,
    write_topofix_outputs,
)

__all__ = [
    "ResolverConfig",
    "ResolutionResult",
    "TopoFixTransactionResult",
    "TransactionPolicy",
    "analyze_document",
    "apply_topofix_transaction",
    "read_psi116_xml",
    "resolve_psi116",
    "write_sidecars",
    "write_topofix_outputs",
    "TopoFixLineageError",
    "build_topofix_source_lineage",
    "verify_topofix_pre_final",
]
