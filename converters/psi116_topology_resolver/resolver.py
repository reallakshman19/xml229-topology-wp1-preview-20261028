from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .analysis import (
    _analyze_coincident_nodes,
    _analyze_occurrences,
    _analyze_rigids,
    _analyze_spans,
    _finding_factory,
)
from .geometry_analysis import _analyze_overlaps, _analyze_pipe_carriers
from .models import Finding, Psi116Document, ResolutionResult, ResolverConfig
from .parser import read_psi116_xml
from .planner import _build_fix_actions


def analyze_document(document: Psi116Document, config: ResolverConfig | None = None) -> ResolutionResult:
    config = config or ResolverConfig()
    config.validate()
    findings, add = _finding_factory()
    _analyze_occurrences(document, add)
    _analyze_coincident_nodes(document, config, add)
    _analyze_spans(document, config, add)
    _analyze_rigids(document, add)
    _analyze_pipe_carriers(document, config, add)
    _analyze_overlaps(document, config, add)
    findings.sort(key=lambda item: (item.branch_name, item.node_numbers, item.code, item.finding_id))
    normalized = tuple(
        Finding(
            finding_id=f"FND-{index + 1:06d}",
            code=finding.code,
            severity=finding.severity,
            blocking=finding.blocking,
            message=finding.message,
            branch_name=finding.branch_name,
            node_keys=finding.node_keys,
            node_numbers=finding.node_numbers,
            component_ref_nos=finding.component_ref_nos,
            span_ids=finding.span_ids,
            length_mm=finding.length_mm,
            details=finding.details,
        )
        for index, finding in enumerate(findings)
    )
    return ResolutionResult(
        document=document,
        findings=normalized,
        fix_actions=_build_fix_actions(document, normalized),
    )


def resolve_psi116(
    source: str | Path,
    config: ResolverConfig | None = None,
    *,
    source_name: str | None = None,
) -> ResolutionResult:
    return analyze_document(read_psi116_xml(source, source_name=source_name), config)


def write_sidecars(
    result: ResolutionResult,
    output_dir: str | Path,
    config: ResolverConfig | None = None,
    *,
    stem: str | None = None,
) -> tuple[Path, Path]:
    config = config or ResolverConfig()
    config.validate()
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    resolved_stem = stem or Path(result.document.source_path).stem or "psi116"
    findings_path = directory / f"{resolved_stem}.topology-findings.json"
    plan_path = directory / f"{resolved_stem}.topology-fix-plan.json"
    findings_path.write_text(
        json.dumps(result.findings_payload(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(result.fix_plan_payload(config), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return findings_path, plan_path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze PSI116 topology and emit non-mutating sidecar findings/fix plans."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--stem")
    parser.add_argument("--short-span-mm", type=float, default=ResolverConfig.short_span_threshold_mm)
    parser.add_argument("--connection-mm", type=float, default=ResolverConfig.connection_tolerance_mm)
    parser.add_argument("--coincidence-mm", type=float, default=ResolverConfig.exact_coincidence_tolerance_mm)
    parser.add_argument(
        "--fail-on-blocking",
        action="store_true",
        help="Return exit code 2 when blocking findings exist.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = ResolverConfig(
        short_span_threshold_mm=args.short_span_mm,
        connection_tolerance_mm=args.connection_mm,
        exact_coincidence_tolerance_mm=args.coincidence_mm,
    )
    result = resolve_psi116(args.input, config)
    findings_path, plan_path = write_sidecars(result, args.output_dir, config, stem=args.stem)
    summary = result.findings_payload(config)["summary"]
    print(
        f"PSI116 topology analysis: {summary['findingCount']} findings, "
        f"{summary['blockingFindingCount']} blocking"
    )
    print(findings_path)
    print(plan_path)
    return 2 if args.fail_on_blocking and int(summary["blockingFindingCount"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
