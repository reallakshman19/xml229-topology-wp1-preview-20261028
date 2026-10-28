#!/usr/bin/env python3
"""Portable master-customization primitives for the XML -> CII pipeline.

Design (mirrors the PcfStudio_Basic_Legacy service layer so behaviour matches,
but kept dependency-free so this file can be COPIED as-is into a standalone app
alongside xml_to_cii2019.py):

  * Pure functions only. No DOM, no localStorage, no file/network I/O, no
    globals. Masters, overrides and config are passed in by the caller, which
    owns persistence/UI at the edge.
  * Precedence everywhere: manual override > exact > fuzzy(contains) >
    fuzzy(token overlap) > none.
  * Fuzzy results carry a confidence and a `needs_review` flag so the host can
    raise an "approximate match" prompt instead of silently guessing.

Supported customizations:
  1. material      - map a master material *name* to a material *code* via a
                     Material Map, with fuzzy fallback and manual overrides.
  2. approximate   - resolve a derived piping class against the known class set
     class match     (exact -> startsWith -> fuzzy ratio), flagging approximate
                     hits for review.
  3. manual        - any field can be force-set via an overrides table keyed by
     overrides       (kind, key); checked first, always wins.
  4. fuzzy logic   - shared string-similarity helpers (normalize, contains,
     mapping         token Jaccard, ratio) used by the above and reusable for
                     other master lookups.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

# ---------------------------------------------------------------------------
# Configuration (all overridable by passing a dict; never read from globals).
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: dict[str, Any] = {
    # Fuzzy-name matching (material names, descriptions...).
    "contains_confidence": 0.90,      # one string contains the other
    "token_jaccard_threshold": 0.35,  # min token-set overlap to accept
    # Approximate piping-class matching.
    "class_startswith_confidence": 0.80,
    "class_fuzzy_threshold": 0.60,    # min SequenceMatcher ratio to accept
    # Any accepted match below this confidence is flagged needs_review.
    "review_below": 1.00,
}


def merged_config(overrides: Optional[dict] = None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg


# ---------------------------------------------------------------------------
# Fuzzy-logic primitives
# ---------------------------------------------------------------------------
def normalize(value: Any) -> str:
    """Lowercase, collapse non-alphanumerics to single spaces, trim."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _tokens(value: str) -> set[str]:
    return {t for t in normalize(value).split(" ") if t}


def token_jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def fuzzy_name_match(name: str, candidates: Iterable[Any], cfg: Optional[dict] = None,
                     key=lambda c: c) -> Optional[dict]:
    """Match `name` against candidates using exact -> contains -> token Jaccard.

    Returns {candidate, score, method} for the best acceptable match, or None.
    `key` extracts the comparable string from each candidate.
    """
    cfg = merged_config(cfg)
    n = normalize(name)
    if not n:
        return None
    cand = list(candidates)

    # 1) exact (normalized)
    for c in cand:
        if normalize(key(c)) == n:
            return {"candidate": c, "score": 1.0, "method": "exact"}

    # 2) contains (either direction)
    best = None
    for c in cand:
        ck = normalize(key(c))
        if ck and (ck in n or n in ck):
            score = cfg["contains_confidence"]
            if best is None or score > best["score"]:
                best = {"candidate": c, "score": score, "method": "contains"}
    if best:
        return best

    # 3) token Jaccard
    for c in cand:
        j = token_jaccard(n, key(c))
        if j >= cfg["token_jaccard_threshold"] and (best is None or j > best["score"]):
            best = {"candidate": c, "score": j, "method": "token-jaccard"}
    return best


# ---------------------------------------------------------------------------
# Manual overrides (highest precedence)
# ---------------------------------------------------------------------------
def override_for(overrides: Optional[dict], kind: str, key: Any) -> Optional[Any]:
    """Look up a manual override. `overrides` is { kind: { normKey: value } }.

    Matching is case/format-insensitive on the key. Returns the override value
    or None. This is checked before any automatic resolution.
    """
    if not overrides:
        return None
    bucket = overrides.get(kind) or {}
    if not isinstance(bucket, dict):
        return None
    nk = normalize(key)
    for k, v in bucket.items():
        if normalize(k) == nk:
            return v
    return None


# ---------------------------------------------------------------------------
# Material name -> code resolution
# ---------------------------------------------------------------------------
def resolve_material_code(material_name: str, material_map: Iterable[dict],
                          overrides: Optional[dict] = None,
                          cfg: Optional[dict] = None,
                          code_key: str = "code", desc_key: str = "material") -> dict:
    """Resolve a material *code* from a material *name* via the Material Map.

    material_map: iterable of {code, material/desc} rows.
    Returns {code, name, method, confidence, needs_review}.
    Precedence: manual override -> exact -> contains -> token Jaccard.
    """
    cfg = merged_config(cfg)
    ov = override_for(overrides, "material", material_name)
    if ov not in (None, ""):
        return {"code": str(ov), "name": material_name, "method": "override",
                "confidence": 1.0, "needs_review": False}

    rows = [r for r in (material_map or []) if r]
    hit = fuzzy_name_match(material_name, rows, cfg, key=lambda r: r.get(desc_key, ""))
    if not hit:
        return {"code": None, "name": material_name, "method": "none",
                "confidence": 0.0, "needs_review": True}
    row = hit["candidate"]
    return {
        "code": row.get(code_key),
        "name": row.get(desc_key, material_name),
        "method": hit["method"],
        "confidence": hit["score"],
        "needs_review": hit["score"] < cfg["review_below"],
    }


# ---------------------------------------------------------------------------
# Approximate piping-class match
# ---------------------------------------------------------------------------
def approximate_class_match(derived_class: str, known_classes: Iterable[str],
                            overrides: Optional[dict] = None,
                            cfg: Optional[dict] = None) -> dict:
    """Resolve a derived class against the known class set.

    Order: manual override -> exact -> startsWith -> fuzzy ratio.
    Returns {pipingClass, method, confidence, needs_review}. `needs_review` is
    the signal the host uses to show the 'approximate class match' prompt.
    """
    cfg = merged_config(cfg)
    ov = override_for(overrides, "pipingClass", derived_class)
    if ov not in (None, ""):
        return {"pipingClass": str(ov), "method": "override", "confidence": 1.0, "needs_review": False}

    d = normalize(derived_class)
    classes = [str(c) for c in (known_classes or []) if str(c).strip()]
    if not d or not classes:
        return {"pipingClass": None, "method": "none", "confidence": 0.0, "needs_review": True}

    # exact
    for c in classes:
        if normalize(c) == d:
            return {"pipingClass": c, "method": "exact", "confidence": 1.0, "needs_review": False}

    # startsWith (either direction) - the reference's primary fuzzy tier
    sw = [c for c in classes if normalize(c).startswith(d) or d.startswith(normalize(c))]
    if len(sw) == 1:
        conf = cfg["class_startswith_confidence"]
        return {"pipingClass": sw[0], "method": "startsWith", "confidence": conf,
                "needs_review": conf < cfg["review_below"]}
    if len(sw) > 1:
        return {"pipingClass": None, "method": "ambiguous", "confidence": cfg["class_startswith_confidence"],
                "needs_review": True, "candidates": sw}

    # fuzzy ratio
    best_c, best_s = None, 0.0
    for c in classes:
        s = ratio(d, c)
        if s > best_s:
            best_c, best_s = c, s
    if best_c is not None and best_s >= cfg["class_fuzzy_threshold"]:
        return {"pipingClass": best_c, "method": "fuzzy", "confidence": best_s,
                "needs_review": best_s < cfg["review_below"]}
    return {"pipingClass": None, "method": "none", "confidence": best_s, "needs_review": True}


# Helper utilities for dict keys
def mrow(row, *keys):
    if not isinstance(row, dict):
        return None
    for k in keys:
        if k in row and str(row[k]).strip() != "":
            return row[k]
    return None


def normalize_piping_class(val: Any) -> str:
    return str(val or "").strip().upper().replace(" ", "")


def normalize_component_type(val: Any) -> str:
    return str(val or "").strip().upper()


def normalize_rating(val: Any) -> str:
    return str(val or "").strip().upper().replace("#", "")


def normalize_schedule(val: Any) -> str:
    return str(val or "").strip().upper()


def to_finite_number(val: Any) -> Optional[float]:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def score_piping_class_row(
    row: dict,
    piping_class: str,
    bore_mm: Optional[float],
    component_type: Optional[str],
    rating: Optional[str],
    schedule: Optional[str] = None,
    config: Optional[dict] = None
) -> tuple[float, list[str]]:
    cfg = {
        "boreToleranceMm": 1.0,
        "classExactWeight": 1000,
        "boreExactWeight": 300,
        "boreNearWeight": 220,
        "componentExactWeight": 180,
        "pipeRigidWeight": 120,
        "ratingExactWeight": 80,
        "scheduleExactWeight": 60,
    }
    if config and "pipingClassMatch" in config:
        cfg.update(config["pipingClassMatch"])

    score = 0.0
    reasons = []

    # Get row class
    row_class = normalize_piping_class(
        row.get("pipingClass") or row.get("Piping Class") or row.get("Class") or row.get("SPEC")
    )
    req_class = normalize_piping_class(piping_class)
    if row_class == req_class:
        score += cfg["classExactWeight"]
        reasons.append("class-exact")
    else:
        return -float("inf"), ["class-mismatch"]

    # Get row bore
    row_bore = to_finite_number(
        row.get("convertedBore") or row.get("Converted Bore") or row.get("boreMm") or row.get("sizeMm") or row.get("Size") or row.get("size")
    )
    req_bore = to_finite_number(bore_mm)

    if req_bore is not None and row_bore is not None:
        diff = abs(row_bore - req_bore)
        if diff <= 0.001:
            score += cfg["boreExactWeight"]
            reasons.append("bore-exact")
        elif diff <= cfg["boreToleranceMm"]:
            score += cfg["boreNearWeight"]
            reasons.append(f"bore-near:{diff:.3f}mm")
        else:
            score -= 300
            reasons.append(f"bore-mismatch:{diff:.3f}mm")
    else:
        reasons.append("bore-missing")

    # Component type matching
    row_comp = normalize_component_type(
        row.get("componentType") or row.get("Component Type") or row.get("type") or row.get("itemType")
    )
    req_comp = normalize_component_type(component_type)
    if row_comp and req_comp and row_comp == req_comp:
        score += cfg["componentExactWeight"]
        reasons.append("component-exact")
    elif row_comp == "PIPE" and req_comp in ("RIGID", "PIPE"):
        score += cfg["pipeRigidWeight"]
        reasons.append("pipe-rigid-compatible")

    # Rating matching
    row_rating = normalize_rating(
        row.get("rating") or row.get("Rating") or row.get("class")
    )
    req_rating = normalize_rating(rating)
    if row_rating and req_rating and row_rating == req_rating:
        score += cfg["ratingExactWeight"]
        reasons.append("rating-exact")

    # Schedule matching
    row_sched = normalize_schedule(
        row.get("schedule") or row.get("Schedule") or row.get("SCH")
    )
    req_sched = normalize_schedule(schedule)
    if row_sched and req_sched and row_sched == req_sched:
        score += cfg["scheduleExactWeight"]
        reasons.append("schedule-exact")

    return score, reasons


def find_best_piping_class_row(
    piping_class: str,
    bore_mm: Optional[float],
    component_type: Optional[str],
    rating: Optional[str],
    schedule: Optional[str] = None,
    piping_class_rows: Optional[list[dict]] = None,
    config: Optional[dict] = None
) -> dict:
    cfg = {
        "ambiguousScoreDelta": 50,
        "minAcceptScore": 1000,
        "classExactWeight": 1000,
        "boreExactWeight": 300,
        "componentExactWeight": 180,
        "ratingExactWeight": 80,
    }
    if config and "pipingClassMatch" in config:
        cfg.update(config["pipingClassMatch"])

    rows = piping_class_rows or []
    cls = normalize_piping_class(piping_class)

    # Filter to only matching class rows
    matching_rows = []
    for r in rows:
        row_cls = normalize_piping_class(
            r.get("pipingClass") or r.get("Piping Class") or r.get("Class") or r.get("SPEC")
        )
        if row_cls == cls:
            matching_rows.append(r)

    scored = []
    for r in matching_rows:
        score, reasons = score_piping_class_row(
            r, cls, bore_mm, component_type, rating, schedule, config
        )
        if score > -float("inf"):
            scored.append({"row": r, "score": score, "reasons": reasons})

    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)

    best = scored[0] if scored else None
    second = scored[1] if len(scored) > 1 else None

    if not best or best["score"] < cfg["minAcceptScore"]:
        return {
            "row": None,
            "method": "none",
            "confidence": 0.0,
            "needsReview": True,
            "score": best["score"] if best else 0.0,
            "reasons": best["reasons"] if best else [],
            "candidates": scored[:5]
        }

    ambiguous = second and abs(best["score"] - second["score"]) <= cfg["ambiguousScoreDelta"]
    needs_review = ambiguous or ("bore-missing" in best["reasons"])

    max_possible = cfg["classExactWeight"] + cfg["boreExactWeight"] + cfg["componentExactWeight"] + cfg["ratingExactWeight"]
    confidence = min(1.0, best["score"] / max_possible)

    return {
        "row": best["row"],
        "method": "ambiguous-best-score" if ambiguous else "best-score",
        "confidence": confidence,
        "needsReview": needs_review,
        "score": best["score"],
        "reasons": best["reasons"],
        "candidates": scored[:5]
    }


def resolve_material_code_from_line_material(
    line_row: Optional[dict],
    material_map: Optional[list[dict]],
    piping_class_row: Optional[dict],
    overrides: Optional[dict] = None,
    xml_node: Optional[dict] = None,
    xml_branch: Optional[dict] = None
) -> dict:
    # 1. Explicit user override
    overrides = overrides or {}
    override_code = normalize(overrides.get("materialCode"))
    if override_code:
        return {
            "material": normalize(mrow(line_row, "material") or mrow(piping_class_row, "materialName", "Material_Name", "Material", "material") or ""),
            "materialCode": override_code,
            "source": "override"
        }

    # 2. Line-list Material -> Material Map -> Code
    line_material = normalize(mrow(line_row, "material") or "")
    if line_material and material_map:
        for r in material_map:
            desc = normalize(mrow(r, "material", "Material", "materialName", "Material_Name", "description", "Description", "name", "Name") or "")
            if desc == line_material:
                return {
                    "material": line_material,
                    "materialCode": normalize(r.get("code") or ""),
                    "source": "line-list-material-map",
                    "matchedRow": r
                }

    # 3. Piping Class master Material_Name -> Material Map -> Code
    class_material = normalize(
        mrow(piping_class_row, "materialName", "Material_Name", "Material", "material") or ""
    )
    if class_material and material_map:
        for r in material_map:
            desc = normalize(mrow(r, "material", "Material", "materialName", "Material_Name", "description", "Description", "name", "Name") or "")
            if desc == class_material:
                return {
                    "material": class_material,
                    "materialCode": normalize(r.get("code") or ""),
                    "source": "piping-class-material-map",
                    "matchedRow": r
                }

    # 4. XML fallback
    xml_material = normalize(mrow(xml_node, "material") or mrow(xml_branch, "material") or "")

    # 5. Blank
    return {
        "material": line_material or class_material or xml_material,
        "materialCode": "",
        "source": "xml-fallback" if xml_material else "blank",
        "matchedRow": None
    }


def resolve_corrosion_from_piping_class(
    line_row: Optional[dict],
    bore_mm: Optional[float],
    component_type: Optional[str],
    rating: Optional[str],
    piping_class_rows: Optional[list[dict]],
    overrides: Optional[dict] = None,
    xml_node: Optional[dict] = None,
    xml_branch: Optional[dict] = None,
    config: Optional[dict] = None
) -> dict:
    # 1. Explicit user override
    overrides = overrides or {}
    override_corrosion = to_finite_number(overrides.get("corrosionAllowanceMm"))
    if override_corrosion is not None:
        return {
            "corrosionAllowanceMm": override_corrosion,
            "source": "override",
            "matchedRow": None
        }

    # 2. Piping Class + Bore/Size -> Piping Class master Corrosion
    piping_class = mrow(line_row, "pipingClass") or ""
    class_match = find_best_piping_class_row(
        piping_class,
        bore_mm,
        component_type,
        rating,
        piping_class_rows=piping_class_rows,
        config=config
    )
    class_row = class_match.get("row")
    from_class = to_finite_number(
        mrow(class_row, "corrosion", "Corrosion", "corrosionAllowance", "CORROSION_ALLOWANCE", "CA")
    ) if class_row else None

    if from_class is not None:
        return {
            "corrosionAllowanceMm": from_class,
            "source": "piping-class-master",
            "matchedPipingClass": piping_class,
            "matchedRow": class_row,
            "matchMethod": class_match.get("method"),
            "matchScore": class_match.get("score"),
            "matchReasons": class_match.get("reasons"),
            "needsReview": class_match.get("needsReview"),
            "candidates": class_match.get("candidates")
        }

    # 3. XML CorrosionAllowance fallback
    from_xml = to_finite_number(
        mrow(xml_node, "corrosionAllowance", "CorrosionAllowance") or mrow(xml_branch, "corrosionAllowance")
    )
    if from_xml is not None:
        return {
            "corrosionAllowanceMm": from_xml,
            "source": "xml-fallback",
            "matchedPipingClass": piping_class,
            "matchedRow": class_row,
            "matchMethod": class_match.get("method") or "none",
            "matchScore": class_match.get("score") or 0,
            "matchReasons": class_match.get("reasons") or [],
            "needsReview": class_match.get("needsReview") if class_match else True,
            "candidates": class_match.get("candidates") or []
        }

    # 4. Config default / 5. 0
    config = config or {}
    from_config = to_finite_number(config.get("defaultCorrosionAllowance"))
    return {
        "corrosionAllowanceMm": from_config if from_config is not None else 0.0,
        "source": "config-default" if from_config is not None else "default-zero",
        "matchedPipingClass": piping_class,
        "matchedRow": class_row,
        "matchMethod": class_match.get("method") or "none",
        "matchScore": class_match.get("score") or 0,
        "matchReasons": class_match.get("reasons") or [],
        "needsReview": class_match.get("needsReview") if class_match else True,
        "candidates": class_match.get("candidates") or []
    }


def resolve_wall_thickness_from_piping_class(
    piping_class_row: Optional[dict],
    xml_node: Optional[dict] = None,
    xml_branch: Optional[dict] = None,
    config: Optional[dict] = None
) -> dict:
    from_class = to_finite_number(
        mrow(piping_class_row, "wallThickness", "WallThickness", "WT")
    ) if piping_class_row else None
    if from_class is not None:
        return {"valueMm": from_class, "source": "piping-class-master"}
    from_xml = to_finite_number(
        mrow(xml_node, "wallThickness", "WallThickness") or mrow(xml_branch, "wallThickness")
    )
    if from_xml is not None:
        return {"valueMm": from_xml, "source": "xml-fallback"}
    return {"valueMm": 0.0, "source": "default-zero"}


def resolve_branch_process_data(
    branch_name: str,
    line_key: str,
    line_row: Optional[dict],
    bore_mm: Optional[float],
    component_type: str,
    rating: Optional[str],
    material_map: Optional[list[dict]],
    piping_class_rows: Optional[list[dict]],
    overrides: Optional[dict] = None,
    xml_node: Optional[dict] = None,
    xml_branch: Optional[dict] = None,
    config: Optional[dict] = None
) -> dict:
    piping_class = mrow(line_row, "pipingClass") or ""
    class_match = find_best_piping_class_row(
        piping_class,
        bore_mm,
        component_type,
        rating or mrow(line_row, "rating"),
        piping_class_rows=piping_class_rows,
        config=config
    )
    piping_class_row = class_match.get("row")

    material = resolve_material_code_from_line_material(
        line_row,
        material_map,
        piping_class_row,
        overrides,
        xml_node,
        xml_branch
    )

    corrosion = resolve_corrosion_from_piping_class(
        line_row,
        bore_mm,
        component_type,
        rating or mrow(line_row, "rating"),
        piping_class_rows=piping_class_rows,
        overrides=overrides,
        xml_node=xml_node,
        xml_branch=xml_branch,
        config=config
    )

    wall_thickness = resolve_wall_thickness_from_piping_class(
        piping_class_row,
        xml_node,
        xml_branch,
        config
    )

    return {
        "branchName": branch_name,
        "lineKey": line_key,
        "pipingClass": piping_class,
        "material": material["material"],
        "materialCode": material["materialCode"],
        "materialSource": material["source"],
        "corrosionAllowanceMm": corrosion["corrosionAllowanceMm"],
        "corrosionSource": corrosion["source"],
        "wallThicknessMm": wall_thickness["valueMm"],
        "wallThicknessSource": wall_thickness["source"],
        "pipingClassMatchedRow": piping_class_row,
        "pipingClassMatchMethod": class_match["method"],
        "pipingClassRowScore": class_match["score"],
        "pipingClassRowReasons": class_match["reasons"],
        "pipingClassNeedsReview": class_match["needsReview"],
        "pipingClassCandidates": class_match["candidates"],
        "pipingClassConfidence": class_match["confidence"]
    }
