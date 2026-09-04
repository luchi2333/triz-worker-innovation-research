#!/usr/bin/env python3
"""Validate one TRIZ research delivery package against the G5 contract.

Usage:
    python scripts/validate_deliverables.py --root <output-dir> \
        --manifest <output-dir>/deliverables-manifest.json --strict
    python scripts/validate_deliverables.py --self-test

Exit codes: 0 PASS; 2 FAIL. This validates generated case artifacts, while
validate_skill.py validates the reusable Skill package itself.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


CAPABILITY_STATES = {"available", "unavailable", "not-checked"}
SCHEMA_VERSION = "1.1"
DELIVERY_LEVELS = {"direction", "standard", "engineering"}
DELIVERY_STATUS = {"complete", "degraded", "blocked"}
MATURITY_RANK = {"V0": 0, "V1": 1, "V2": 2, "V3": 3}
SCORE_VALUES = {0, 1, 3, 5}
REQUIRED_ROLES = {"decision-summary", "main-report", "evidence-appendix", "source-figure-ledger"}
BASE_FIGURE_TYPES = {
    "object-structure",
    "problem-process",
    "triz-trace",
    "solution-mechanism",
    "system-architecture",
    "validation-gates",
}
CHECK_NAMES = {
    "cross_file_consistency",
    "scoring_consistency",
    "measurement_method_match",
    "patent_citation_tracking",
    "stage_boundary",
    "claim_boundary",
    "figure_contract",
    "caption_numbering",
}
FIGURE_REVIEW_NAMES = {
    "engineer_view",
    "first_time_reader_view",
    "figure_text_consistency",
    "black_white_legibility",
}
FIGURE_TYPES = {
    "F1-object-structure",
    "F2-problem-failure",
    "F3-system-architecture",
    "F4-mechanism-section",
    "F5-motion-sequence",
    "F6-force-energy-material-path",
    "F7-safety-boundary",
    "F8-process-operation",
    "F9-validation-decision",
}
FIGURE_LIST_FIELDS = {
    "confirmed_elements",
    "hypothetical_elements",
    "unknown_elements",
    "motions",
    "forces",
    "energy_flows",
    "protected_objects",
    "hazards",
    "safety_barriers",
    "labels_required",
    "evidence_ids",
    "routes",
    "embedded_in",
}
MECHANICAL_FIGURE_TYPES = {
    "F4-mechanism-section",
    "F5-motion-sequence",
    "F7-safety-boundary",
}
SKILL_ROOT = Path(__file__).resolve().parent.parent
CLAIM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"确认(?:技术|市场|产品|专利)?空白"), "绝对空白结论"),
    (re.compile(r"市场(?:上)?不存在"), "市场不存在结论"),
    (re.compile(r"国内.{0,8}(?:专利)?申请空间"), "专利申请空间结论"),
    (re.compile(r"可自由实施|FTO\s*通过|无专利障碍", re.IGNORECASE), "法律实施结论"),
    (re.compile(r"已失效.{0,20}(?:可)?自由(?:参考|使用|实施)"), "失效等于自由使用"),
    (re.compile(r"全部型号适配|适配所有型号|直径范围已覆盖目标"), "未限定适配结论"),
    (re.compile(r"绝对安全|零损伤|零风险"), "绝对安全或性能结论"),
]
NEGATION_MARKERS = ("不得", "不能", "不等于", "不支持", "禁止", "不构成", "不可声称", "未证实")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")


def _fail(errors: list[str], message: str) -> None:
    errors.append(message)


def _safe_path(root: Path, value: object, errors: list[str], label: str) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        _fail(errors, f"{label}: missing path")
        return None
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        _fail(errors, f"{label}: path escapes output root: {value}")
        return None
    if not candidate.is_file():
        _fail(errors, f"{label}: file not found: {value}")
        return None
    if candidate.stat().st_size == 0:
        _fail(errors, f"{label}: empty file: {value}")
    return candidate


def _extract_text(path: Path) -> list[str]:
    if path.suffix.lower() in {".md", ".txt", ".csv"}:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as package:
            xml = package.read("word/document.xml")
        root = ET.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []
        for para in root.findall(".//w:p", namespace):
            text = "".join(node.text or "" for node in para.findall(".//w:t", namespace))
            if text:
                paragraphs.append(text)
        return paragraphs
    return []


def _check_claims(path: Path, errors: list[str]) -> int:
    hits = 0
    try:
        lines = _extract_text(path)
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        _fail(errors, f"claim scan failed for {path.name}: {exc}")
        return hits
    for line_no, line in enumerate(lines, start=1):
        if any(marker in line for marker in NEGATION_MARKERS):
            continue
        for pattern, reason in CLAIM_PATTERNS:
            if pattern.search(line):
                _fail(errors, f"unsupported claim in {path.name}:{line_no} ({reason})")
                hits += 1
    return hits


def _check_docx(path: Path, expected_figures: int, require_external_links: bool, errors: list[str]) -> dict[str, int | str]:
    result: dict[str, int | str] = {"path": path.name, "media": 0, "alt_text": 0, "external_links": 0}
    try:
        with zipfile.ZipFile(path) as package:
            corrupt = package.testzip()
            if corrupt:
                _fail(errors, f"DOCX corrupt member in {path.name}: {corrupt}")
            names = set(package.namelist())
            if "word/document.xml" not in names:
                _fail(errors, f"DOCX missing word/document.xml: {path.name}")
                return result
            document = ET.fromstring(package.read("word/document.xml"))
            result["media"] = sum(1 for name in names if name.startswith("word/media/") and not name.endswith("/"))
            ns = {"wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"}
            doc_prs = document.findall(".//wp:docPr", ns)
            result["alt_text"] = sum(1 for node in doc_prs if (node.attrib.get("descr") or "").strip())
            if doc_prs and int(result["alt_text"]) != len(doc_prs):
                _fail(errors, f"DOCX figures missing alt text in {path.name}: {result['alt_text']}/{len(doc_prs)}")
            rel_name = "word/_rels/document.xml.rels"
            if rel_name in names:
                rel_root = ET.fromstring(package.read(rel_name))
                result["external_links"] = sum(1 for node in rel_root if node.attrib.get("TargetMode") == "External")
    except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        _fail(errors, f"DOCX validation failed for {path.name}: {exc}")
        return result
    if int(result["media"]) < expected_figures:
        _fail(errors, f"DOCX media count below manifest figures in {path.name}: {result['media']} < {expected_figures}")
    if require_external_links and int(result["external_links"]) < 1:
        _fail(errors, f"DOCX has no external source hyperlink: {path.name}")
    return result


def _svg_number(value: str) -> float | None:
    match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", value)
    return float(match.group(1)) if match else None


def _check_svg(path: Path, item: dict, errors: list[str], warnings: list[str]) -> dict[str, object]:
    figure_id = str(item.get("id", ""))
    result: dict[str, object] = {"id": figure_id, "path": path.name, "labels": 0, "min_font_size": None}
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        _fail(errors, f"SVG parse failed for {figure_id}: {exc}")
        return result

    for attribute in ["width", "height", "viewBox"]:
        if not str(root.attrib.get(attribute, "")).strip():
            _fail(errors, f"SVG missing {attribute}: {figure_id}")

    local_names = [node.tag.rsplit("}", 1)[-1] for node in root.iter()]
    if "title" not in local_names or "desc" not in local_names:
        _fail(errors, f"SVG requires title and desc: {figure_id}")
    text_values = ["".join(node.itertext()).strip() for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "text"]
    combined_text = "\n".join(text_values)
    result["labels"] = len([value for value in text_values if value])

    for label in item.get("labels_required", []):
        if str(label).strip() and str(label).strip() not in combined_text:
            _fail(errors, f"required SVG label missing for {figure_id}: {label}")

    font_sizes: list[float] = []
    for node in root.iter():
        direct = _svg_number(str(node.attrib.get("font-size", "")))
        if direct is not None:
            font_sizes.append(direct)
        style = str(node.attrib.get("style", ""))
        style_match = re.search(r"font-size\s*:\s*([0-9]+(?:\.[0-9]+)?)", style)
        if style_match:
            font_sizes.append(float(style_match.group(1)))
    if font_sizes:
        minimum = min(font_sizes)
        result["min_font_size"] = minimum
        if minimum < 6:
            _fail(errors, f"SVG font-size below 6 for {figure_id}: {minimum}")
        elif minimum < 8:
            warnings.append(f"SVG font-size below 8 for {figure_id}: {minimum}")

    if item.get("figure_type") in MECHANICAL_FIGURE_TYPES:
        structural_shapes = {"path", "circle", "ellipse", "polygon", "polyline"}
        if not structural_shapes.intersection(local_names):
            warnings.append(f"mechanical figure may be a box-only diagram: {figure_id}")

    if item.get("figure_type") == "F5-motion-sequence":
        frame_count = item.get("frame_count")
        if not isinstance(frame_count, int) or not 3 <= frame_count <= 6:
            _fail(errors, f"motion sequence frame_count must be 3-6: {figure_id}")

    return result


def _check_figure_numbering(figures: list[dict], errors: list[str]) -> None:
    previous_chapter = -1
    previous_index = 0
    seen: set[str] = set()
    for position, item in enumerate(figures):
        number = str(item.get("number", "")).strip()
        chapter = item.get("chapter")
        match = re.fullmatch(r"(\d+)-(\d+)", number)
        if not match or not isinstance(chapter, int):
            _fail(errors, f"figure[{position}] requires numeric chapter and number like 6-1")
            continue
        number_chapter, number_index = int(match.group(1)), int(match.group(2))
        if number_chapter != chapter:
            _fail(errors, f"figure number does not match chapter: {number} vs chapter {chapter}")
        if number in seen:
            _fail(errors, f"duplicated figure number: {number}")
        seen.add(number)
        if chapter < previous_chapter or (chapter == previous_chapter and number_index <= previous_index):
            _fail(errors, f"figure numbers are not increasing at: {number}")
        previous_index = number_index if chapter == previous_chapter else number_index
        previous_chapter = chapter


def validate(root: Path, manifest: dict, strict: bool = False) -> dict[str, object]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    checked_files: list[str] = []
    docx_results: list[dict[str, int | str]] = []

    if manifest.get("schema_version") != SCHEMA_VERSION:
        _fail(errors, f"schema_version must be {SCHEMA_VERSION}")
    level = manifest.get("delivery_level")
    if level not in DELIVERY_LEVELS:
        _fail(errors, f"invalid delivery_level: {level}")
    status = manifest.get("status")
    if status not in DELIVERY_STATUS:
        _fail(errors, f"invalid status: {status}")
    maturity = manifest.get("maturity")
    if maturity not in MATURITY_RANK:
        _fail(errors, f"invalid maturity: {maturity}")

    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        _fail(errors, "capabilities must be an object")
        capabilities = {}
    capability_values: dict[str, str] = {}
    for name in ["file_write", "diagram", "docx", "render"]:
        item = capabilities.get(name)
        if not isinstance(item, dict):
            _fail(errors, f"capability missing: {name}")
            continue
        state = item.get("status")
        capability_values[name] = str(state)
        if state not in CAPABILITY_STATES:
            _fail(errors, f"invalid capability state for {name}: {state}")
        if state == "not-checked":
            _fail(errors, f"capability was not tested: {name}")
        evidence = str(item.get("evidence", "")).strip()
        if len(evidence) < 4:
            _fail(errors, f"capability evidence missing: {name}")

    if level in {"standard", "engineering"} and status == "complete":
        for name in ["file_write", "diagram", "docx", "render"]:
            if capability_values.get(name) != "available":
                _fail(errors, f"complete delivery requires available capability: {name}")
    if level in {"standard", "engineering"} and any(
        capability_values.get(name) == "unavailable" for name in ["diagram", "docx", "render"]
    ) and status != "degraded":
        _fail(errors, "missing diagram/DOCX/render capability requires status=degraded")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        _fail(errors, "artifacts must be an array")
        artifacts = []
    roles: dict[str, list[tuple[dict, Path]]] = {}
    public_paths: list[Path] = []
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            _fail(errors, f"artifact[{index}] must be an object")
            continue
        role = str(item.get("role", ""))
        path = _safe_path(root, item.get("path"), errors, f"artifact[{index}]")
        if path is None:
            continue
        checked_files.append(str(path.relative_to(root)))
        roles.setdefault(role, []).append((item, path))
        if role in {"decision-summary", "main-report"}:
            public_paths.append(path)
        if item.get("required", False) and item.get("opened") is not True:
            _fail(errors, f"required artifact not opened: {item.get('path')}")
        if capability_values.get("render") == "available" and path.suffix.lower() in {".docx", ".pdf"}:
            if item.get("rendered") is not True:
                _fail(errors, f"document not rendered: {item.get('path')}")

    if level in {"standard", "engineering"}:
        for role in sorted(REQUIRED_ROLES):
            if role not in roles:
                _fail(errors, f"missing required artifact role: {role}")
    if capability_values.get("docx") == "available":
        main_docx = [path for _, path in roles.get("main-report", []) if path.suffix.lower() == ".docx"]
        if not main_docx:
            _fail(errors, "DOCX capability is available but main-report has no DOCX")

    profile = manifest.get("concept_profile")
    if not isinstance(profile, dict):
        _fail(errors, "concept_profile must be an object")
        profile = {}
    for name in [
        "primary_engineering_concept",
        "physical_structure",
        "relative_motion",
        "force_energy_transfer",
        "material_deformation",
        "safety_risk",
        "multi_step_operation",
    ]:
        if not isinstance(profile.get(name), bool):
            _fail(errors, f"concept_profile.{name} must be boolean")
    if manifest.get("figure_plan_frozen") is not True:
        _fail(errors, "Figure Plan is not frozen")

    figures = manifest.get("figures")
    if not isinstance(figures, list):
        _fail(errors, "figures must be an array")
        figures = []
    figure_types: set[str] = set()
    engineering_types: set[str] = set()
    figure_ids: set[str] = set()
    route_coverage: set[str] = set()
    route_engineering_types: dict[str, set[str]] = {}
    svg_results: list[dict[str, object]] = []
    for index, item in enumerate(figures):
        if not isinstance(item, dict):
            _fail(errors, f"figure[{index}] must be an object")
            continue
        figure_id = str(item.get("id", "")).strip()
        if not figure_id or figure_id in figure_ids:
            _fail(errors, f"figure[{index}] id missing or duplicated: {figure_id}")
        figure_ids.add(figure_id)
        figure_type = str(item.get("type", "")).strip()
        figure_types.add(figure_type)
        engineering_type = str(item.get("figure_type", "")).strip()
        if engineering_type not in FIGURE_TYPES:
            _fail(errors, f"figure[{index}] invalid figure_type: {engineering_type}")
        engineering_types.add(engineering_type)
        for field in ["title", "decision_question", "main_message", "subject", "claim_limit"]:
            minimum = 4 if field == "title" else 8
            if len(str(item.get(field, "")).strip()) < minimum:
                _fail(errors, f"figure[{index}] missing meaningful {field}: {figure_id}")
        design_status = item.get("design_status")
        if design_status not in MATURITY_RANK:
            _fail(errors, f"figure[{index}] design_status must be V0-V3: {figure_id}")
        for field in sorted(FIGURE_LIST_FIELDS):
            if not isinstance(item.get(field), list):
                _fail(errors, f"figure[{index}] {field} must be an array: {figure_id}")
        if item.get("required") is not True:
            _fail(errors, f"manifest figures must explicitly declare required=true: {figure_id}")
        path = _safe_path(root, item.get("path"), errors, f"figure[{index}]")
        if path is not None:
            checked_files.append(str(path.relative_to(root)))
        svg_path = _safe_path(root, item.get("source_svg"), errors, f"figure[{index}].source_svg")
        png_path = _safe_path(root, item.get("render_png"), errors, f"figure[{index}].render_png")
        if svg_path is not None:
            checked_files.append(str(svg_path.relative_to(root)))
            if svg_path.suffix.lower() != ".svg":
                _fail(errors, f"figure source_svg is not SVG: {figure_id}")
            else:
                svg_results.append(_check_svg(svg_path, item, errors, warnings))
        if png_path is not None:
            checked_files.append(str(png_path.relative_to(root)))
            if png_path.suffix.lower() != ".png":
                _fail(errors, f"figure render_png is not PNG: {figure_id}")
        if len(str(item.get("alt", "")).strip()) < 8:
            _fail(errors, f"figure alt text missing: {figure_id}")
        if item.get("ledgered") is not True:
            _fail(errors, f"figure not recorded in ledger: {figure_id}")
        embedded = item.get("embedded_in", [])
        if capability_values.get("docx") == "available" and "main-report" not in embedded:
            _fail(errors, f"figure not embedded in main-report: {figure_id}")
        if figure_type == "solution-mechanism":
            route_coverage.update(str(route) for route in item.get("routes", []))
        for route in item.get("routes", []):
            route_engineering_types.setdefault(str(route), set()).add(engineering_type)

    _check_figure_numbering([item for item in figures if isinstance(item, dict)], errors)

    exemptions = manifest.get("figure_exemptions", [])
    exemption_types: set[str] = set()
    if not isinstance(exemptions, list):
        _fail(errors, "figure_exemptions must be an array")
        exemptions = []
    for item in exemptions:
        if not isinstance(item, dict):
            _fail(errors, "figure exemption must be an object")
            continue
        kind = str(item.get("type", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if not kind or len(reason) < 8:
            _fail(errors, f"figure exemption lacks technical reason: {kind}")
        exemption_types.add(kind)

    if capability_values.get("diagram") == "available" and level in {"standard", "engineering"}:
        required_figures = set(BASE_FIGURE_TYPES)
        if manifest.get("numeric_benefits") is True:
            required_figures.add("benefit-sensitivity")
        for figure_type in sorted(required_figures - exemption_types):
            if figure_type not in figure_types:
                _fail(errors, f"missing required figure type: {figure_type}")
        for route in manifest.get("shortlisted_routes", []):
            if str(route) not in route_coverage:
                _fail(errors, f"shortlisted route lacks mechanism figure: {route}")

        primary_routes = manifest.get("primary_routes", [])
        if not isinstance(primary_routes, list) or not primary_routes:
            _fail(errors, "primary_routes must identify at least one recommended route")
            primary_routes = []
        if profile.get("primary_engineering_concept") is True and any(
            profile.get(name) is True
            for name in ["physical_structure", "relative_motion", "force_energy_transfer", "material_deformation"]
        ):
            for required_type in ["F4-mechanism-section", "F5-motion-sequence"]:
                if required_type not in engineering_types:
                    _fail(errors, f"primary engineering concept missing {required_type}")
            for route in primary_routes:
                present = route_engineering_types.get(str(route), set())
                for required_type in ["F4-mechanism-section", "F5-motion-sequence"]:
                    if required_type not in present:
                        _fail(errors, f"primary route {route} missing {required_type}")
        if profile.get("safety_risk") is True:
            if "F7-safety-boundary" not in engineering_types:
                _fail(errors, "safety risk declared but F7-safety-boundary is missing")
            for route in primary_routes:
                if "F7-safety-boundary" not in route_engineering_types.get(str(route), set()):
                    _fail(errors, f"primary route {route} missing F7-safety-boundary")
        if profile.get("multi_step_operation") is True and "F8-process-operation" not in engineering_types:
            _fail(errors, "multi-step operation declared but F8-process-operation is missing")

    review = manifest.get("figure_review")
    if not isinstance(review, dict):
        _fail(errors, "figure_review must be an object")
        review = {}
    expected_review_status = "pass" if capability_values.get("diagram") == "available" else "not-applicable"
    for name in sorted(FIGURE_REVIEW_NAMES):
        item = review.get(name)
        if not isinstance(item, dict) or item.get("status") != expected_review_status:
            _fail(errors, f"figure review status must be {expected_review_status}: {name}")
            continue
        if len(str(item.get("evidence", "")).strip()) < 8:
            _fail(errors, f"figure review evidence missing: {name}")

    research_log = manifest.get("research_log")
    if not isinstance(research_log, dict):
        _fail(errors, "research_log must be an object")
    else:
        log_path = _safe_path(root, research_log.get("path"), errors, "research_log")
        if log_path is not None:
            checked_files.append(str(log_path.relative_to(root)))
        claimed = research_log.get("claimed_queries")
        logged = research_log.get("logged_queries")
        if not isinstance(claimed, int) or not isinstance(logged, int) or claimed < 0 or logged < 0:
            _fail(errors, "research_log counts must be non-negative integers")
        elif claimed != logged:
            _fail(errors, f"claimed query count differs from logged rows: {claimed} != {logged}")
        elif status == "complete" and level in {"standard", "engineering"} and logged == 0:
            _fail(errors, "complete standard/engineering delivery has no reproducible query row")

    sources = manifest.get("sources")
    if not isinstance(sources, dict):
        _fail(errors, "sources must be an object")
        sources = {}
    cards = sources.get("cards", 0)
    stable = sources.get("with_stable_identifier", 0)
    critical = sources.get("critical", 0)
    with_url = sources.get("with_url", 0)
    if not all(isinstance(value, int) and value >= 0 for value in [cards, stable, critical, with_url]):
        _fail(errors, "source counts must be non-negative integers")
    else:
        if stable > cards or critical > cards or with_url > cards:
            _fail(errors, "source counts cannot exceed source cards")
        if stable < critical:
            _fail(errors, "every critical source requires a stable identifier")

    for index, row in enumerate(manifest.get("score_rows", [])):
        if not isinstance(row, dict):
            _fail(errors, f"score_rows[{index}] must be an object")
            continue
        unknown = row.get("unknown") is True
        not_applicable = row.get("not_applicable") is True
        score = row.get("score")
        if unknown or not_applicable:
            if score is not None:
                _fail(errors, f"unknown/N/A score must be null: score_rows[{index}]")
            continue
        if score not in SCORE_VALUES:
            _fail(errors, f"score must be 0/1/3/5: score_rows[{index}]")
        if not str(row.get("evidence_id", "")).strip():
            _fail(errors, f"score lacks evidence_id: score_rows[{index}]")
        evidence_level = row.get("evidence_maturity")
        anchor_level = row.get("anchor_maturity")
        if evidence_level not in MATURITY_RANK or anchor_level not in MATURITY_RANK:
            _fail(errors, f"score maturity must be V0-V3: score_rows[{index}]")
        elif MATURITY_RANK[evidence_level] < MATURITY_RANK[anchor_level]:
            _fail(errors, f"score exceeds evidence maturity anchor: score_rows[{index}] {evidence_level} < {anchor_level}")

    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        _fail(errors, "checks must be an object")
        checks = {}
    for name in sorted(CHECK_NAMES):
        if checks.get(name) != "pass":
            _fail(errors, f"manual/structured check not passed: {name}")

    render = manifest.get("render_summary")
    if not isinstance(render, dict):
        _fail(errors, "render_summary must be an object")
    elif capability_values.get("render") == "available":
        pages = render.get("pages")
        checked_pages = render.get("checked_pages")
        if not isinstance(pages, int) or pages < 1:
            _fail(errors, "render_summary.pages must be positive")
        if checked_pages != pages:
            _fail(errors, f"not all pages visually checked: {checked_pages}/{pages}")
        page_checks = render.get("page_checks")
        if not isinstance(page_checks, list) or len(page_checks) != pages:
            _fail(errors, f"page_checks must contain one row per rendered page: {len(page_checks) if isinstance(page_checks, list) else 0}/{pages}")
        else:
            seen_pages: set[int] = set()
            for item in page_checks:
                if not isinstance(item, dict):
                    _fail(errors, "page_checks entries must be objects")
                    continue
                page = item.get("page")
                if not isinstance(page, int) or page < 1 or page > pages or page in seen_pages:
                    _fail(errors, f"invalid or duplicate page check: {page}")
                seen_pages.add(page)
                if item.get("status") != "pass":
                    _fail(errors, f"rendered page not passed: {page}")
                if len(str(item.get("evidence", "")).strip()) < 4:
                    _fail(errors, f"page check evidence missing: {page}")
        if render.get("blank_pages"):
            _fail(errors, f"blank pages remain: {render.get('blank_pages')}")
        if render.get("unresolved_visual_issues"):
            _fail(errors, f"visual issues remain: {render.get('unresolved_visual_issues')}")

    claim_hits = 0
    for path in dict.fromkeys(public_paths):
        claim_hits += _check_claims(path, errors)

    report_text = "\n".join(
        line
        for _, path in roles.get("main-report", [])
        for line in _extract_text(path)
    )
    for item in figures:
        if not isinstance(item, dict) or "main-report" not in item.get("embedded_in", []):
            continue
        number = str(item.get("number", "")).strip()
        title = str(item.get("title", "")).strip()
        if f"图{number}" not in report_text and f"图 {number}" not in report_text:
            _fail(errors, f"main report lacks caption number for {item.get('id')}: {number}")
        if title and title not in report_text:
            _fail(errors, f"main report lacks figure title for {item.get('id')}: {title}")

    expected_docx_figures = len(figures) if capability_values.get("docx") == "available" else 0
    require_links = isinstance(with_url, int) and with_url > 0
    for _, path in roles.get("main-report", []):
        if path.suffix.lower() == ".docx":
            docx_results.append(_check_docx(path, expected_docx_figures, require_links, errors))

    if strict and manifest.get("validator_runtime") != "available":
        _fail(errors, "strict validation requires validator_runtime=available")

    return {
        "schema_version": manifest.get("schema_version"),
        "delivery_level": level,
        "declared_status": status,
        "checked_files": sorted(set(checked_files)),
        "figures": len(figures),
        "engineering_figure_types": sorted(engineering_types),
        "svg": svg_results,
        "claim_scan_hits": claim_hits,
        "docx": docx_results,
        "warnings": warnings,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="triz-delivery-") as tmp:
        root = Path(tmp)
        for name in ["01-summary.md", "02-report.md", "03-evidence.md", "04-ledger.md"]:
            (root / name).write_text(f"# {name}\n可复核内容。\n", encoding="utf-8")
        figure_specs = [
            ("object-structure", "F1-object-structure", ["R0", "R1"]),
            ("problem-process", "F2-problem-failure", ["R0", "R1"]),
            ("triz-trace", "F6-force-energy-material-path", ["R1"]),
            ("solution-mechanism", "F4-mechanism-section", ["R0", "R1"]),
            ("solution-mechanism", "F5-motion-sequence", ["R1"]),
            ("solution-mechanism", "F7-safety-boundary", ["R1"]),
            ("system-architecture", "F3-system-architecture", ["R1"]),
            ("validation-gates", "F9-validation-decision", ["R1"]),
            ("problem-process", "F8-process-operation", ["R1"]),
        ]
        figures = []
        png_payload = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        for index, (role, engineering_type, routes) in enumerate(figure_specs, start=1):
            svg_path = root / f"figure-{index}.svg"
            png_path = root / f"figure-{index}.png"
            svg_path.write_text(
                (
                    '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">'
                    f'<title>图6-{index} 技术说明</title><desc>工具对目标层施加受控作用并保护下层对象。</desc>'
                    '<rect width="800" height="450" fill="#eef6f8"/>'
                    '<path d="M80 230 C210 90 430 90 590 230" fill="none" stroke="#176B87" stroke-width="8"/>'
                    '<polygon points="590,215 630,230 590,245" fill="#176B87"/>'
                    '<text x="100" y="320" font-size="18">工具</text><text x="300" y="320" font-size="18">目标层</text>'
                    '<text x="500" y="320" font-size="18">被保护区域</text></svg>'
                ),
                encoding="utf-8",
            )
            png_path.write_bytes(png_payload)
            figures.append(
                {
                    "id": f"FIG-{index:02d}",
                    "number": f"6-{index}",
                    "chapter": 6,
                    "type": role,
                    "figure_type": engineering_type,
                    "title": f"图型{index}技术说明",
                    "decision_question": "工具如何对目标层施加作用并保护下层对象？",
                    "main_message": "受控工具界面把输入作用传给目标层并隔离被保护对象。",
                    "subject": "通用分层对象处理方案",
                    "confirmed_elements": ["目标层"],
                    "hypothetical_elements": ["工具界面"],
                    "unknown_elements": ["具体尺寸"],
                    "motions": ["受控接近", "作用", "退出"],
                    "forces": ["输入作用力"],
                    "energy_flows": [],
                    "protected_objects": ["被保护区域"],
                    "hazards": ["工具越界"],
                    "safety_barriers": ["候选机械止挡"],
                    "labels_required": ["工具", "目标层", "被保护区域"],
                    "evidence_ids": ["H-01"],
                    "claim_limit": "V0 概念机理，具体尺寸和安全能力尚未验证。",
                    "design_status": "V0",
                    "source_svg": svg_path.name,
                    "render_png": png_path.name,
                    "path": png_path.name,
                    "alt": f"图型{index}显示工具、目标层、运动方向和被保护区域。",
                    "ledgered": True,
                    "embedded_in": [],
                    "routes": routes,
                    "required": True,
                    "frame_count": 4 if engineering_type == "F5-motion-sequence" else None,
                }
            )
        degraded_manifest = {
            "schema_version": "1.1",
            "delivery_level": "standard",
            "status": "degraded",
            "maturity": "V0",
            "validator_runtime": "available",
            "capabilities": {
                "file_write": {"status": "available", "evidence": "已写入并读回测试文件"},
                "diagram": {"status": "available", "evidence": "已生成并读取 SVG"},
                "docx": {"status": "unavailable", "evidence": "测试环境刻意禁用文档生成"},
                "render": {"status": "unavailable", "evidence": "测试环境刻意禁用渲染"},
            },
            "artifacts": [
                {"role": "decision-summary", "path": "01-summary.md", "required": True, "opened": True, "rendered": False},
                {"role": "main-report", "path": "02-report.md", "required": True, "opened": True, "rendered": False},
                {"role": "evidence-appendix", "path": "03-evidence.md", "required": True, "opened": True, "rendered": False},
                {"role": "source-figure-ledger", "path": "04-ledger.md", "required": True, "opened": True, "rendered": False},
            ],
            "shortlisted_routes": ["R0", "R1"],
            "primary_routes": ["R1"],
            "concept_profile": {
                "primary_engineering_concept": True,
                "physical_structure": True,
                "relative_motion": True,
                "force_energy_transfer": True,
                "material_deformation": True,
                "safety_risk": True,
                "multi_step_operation": True,
            },
            "figure_plan_frozen": True,
            "figures": figures,
            "figure_exemptions": [],
            "figure_review": {
                name: {"status": "pass", "evidence": f"{name} 已用自检图组完成复核"}
                for name in FIGURE_REVIEW_NAMES
            },
            "numeric_benefits": False,
            "research_log": {"path": "03-evidence.md", "claimed_queries": 1, "logged_queries": 1},
            "sources": {"cards": 1, "with_stable_identifier": 1, "critical": 1, "with_url": 0},
            "score_rows": [
                {"route": "R0", "dimension": "安全", "score": 3, "unknown": False, "evidence_id": "S-01", "evidence_maturity": "V1", "anchor_maturity": "V1"},
                {"route": "R1", "dimension": "效率", "score": None, "unknown": True, "evidence_id": "", "evidence_maturity": "V0", "anchor_maturity": "V2"},
            ],
            "checks": {name: "pass" for name in CHECK_NAMES},
            "render_summary": {
                "pages": 0,
                "checked_pages": 0,
                "page_checks": [],
                "blank_pages": [],
                "unresolved_visual_issues": [],
            },
        }
        degraded = validate(root, degraded_manifest, strict=True)
        assert degraded["status"] == "PASS", degraded["errors"]

        no_diagram_manifest = json.loads(json.dumps(degraded_manifest))
        no_diagram_manifest["capabilities"]["diagram"] = {
            "status": "unavailable",
            "evidence": "当前平台没有可调用的图示生成与渲染能力",
        }
        no_diagram_manifest["figures"] = []
        no_diagram_manifest["figure_review"] = {
            name: {"status": "not-applicable", "evidence": "未生成图示，已在交付说明中标记降级原因"}
            for name in FIGURE_REVIEW_NAMES
        }
        no_diagram = validate(root, no_diagram_manifest, strict=True)
        assert no_diagram["status"] == "PASS", no_diagram["errors"]

        report_source = root / "report-source.json"
        report_source.write_text(
            json.dumps(
                {
                    "schema_version": "1.1",
                    "title": "成果校验自检报告",
                    "status": "V0 概念研究",
                    "sections": [
                        {
                            "title": "1. 技术内容",
                            "level": 1,
                            "blocks": [
                                *[
                                    {
                                        "type": "figure",
                                        "path": item["path"],
                                        "figure_id": item["id"],
                                        "figure_type": item["figure_type"],
                                        "design_status": item["design_status"],
                                        "caption": f"图{item['number']} {item['title']}",
                                        "alt": item["alt"],
                                        "main_message": item["main_message"],
                                        "claim_limit": item["claim_limit"],
                                    }
                                    for item in figures
                                ]
                            ],
                        }
                    ],
                    "sources": [
                        {"id": "SRC-01", "title": "自检来源", "url": "https://example.com/source", "claim": "支持校验结构"}
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        report_docx = root / "02-report.docx"
        build = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "build_report.py"), "--input", str(report_source), "--output", str(report_docx)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        assert build.returncode == 0, build.stderr
        complete_manifest = json.loads(json.dumps(degraded_manifest))
        complete_manifest["status"] = "complete"
        complete_manifest["capabilities"] = {
            "file_write": {"status": "available", "evidence": "已写入并读回测试文件"},
            "diagram": {"status": "available", "evidence": "已生成并读取六张 SVG"},
            "docx": {"status": "available", "evidence": "内置生成器已生成并重新打开 DOCX"},
            "render": {"status": "available", "evidence": "自检清单模拟两页均已逐页检查"},
        }
        complete_manifest["artifacts"][1] = {
            "role": "main-report",
            "path": "02-report.docx",
            "required": True,
            "opened": True,
            "rendered": True,
        }
        for item in complete_manifest["figures"]:
            item["embedded_in"] = ["main-report"]
        complete_manifest["sources"]["with_url"] = 1
        complete_manifest["render_summary"] = {
            "pages": 2,
            "checked_pages": 2,
            "page_checks": [
                {"page": 1, "status": "pass", "evidence": "封面与首个技术图已检查"},
                {"page": 2, "status": "pass", "evidence": "其余图题与来源已检查"},
            ],
            "blank_pages": [],
            "unresolved_visual_issues": [],
        }
        complete = validate(root, complete_manifest, strict=True)
        assert complete["status"] == "PASS", complete["errors"]

        architecture_only = json.loads(json.dumps(complete_manifest))
        architecture_only["figures"] = [
            item for item in architecture_only["figures"] if item["figure_type"] == "F3-system-architecture"
        ]
        negative_architecture = validate(root, architecture_only, strict=True)
        assert negative_architecture["status"] == "FAIL"
        assert any("missing F4-mechanism-section" in item for item in negative_architecture["errors"])

        motion_broken = json.loads(json.dumps(complete_manifest))
        motion_broken["figures"] = [
            item for item in motion_broken["figures"] if item["figure_type"] != "F5-motion-sequence"
        ]
        negative_motion = validate(root, motion_broken, strict=True)
        assert negative_motion["status"] == "FAIL"
        assert any("missing F5-motion-sequence" in item for item in negative_motion["errors"])

        safety_broken = json.loads(json.dumps(complete_manifest))
        safety_broken["figures"] = [
            item for item in safety_broken["figures"] if item["figure_type"] != "F7-safety-boundary"
        ]
        negative_safety = validate(root, safety_broken, strict=True)
        assert negative_safety["status"] == "FAIL"
        assert any("F7-safety-boundary" in item for item in negative_safety["errors"])

        label_broken = json.loads(json.dumps(complete_manifest))
        label_broken["figures"][0]["labels_required"].append("不存在的必需标签")
        negative_label = validate(root, label_broken, strict=True)
        assert negative_label["status"] == "FAIL"
        assert any("required SVG label missing" in item for item in negative_label["errors"])

        number_broken = json.loads(json.dumps(complete_manifest))
        number_broken["figures"][1]["number"] = "6-0"
        negative_number = validate(root, number_broken, strict=True)
        assert negative_number["status"] == "FAIL"
        assert any("not increasing" in item for item in negative_number["errors"])

        tiny_svg = root / complete_manifest["figures"][0]["source_svg"]
        clean_svg = tiny_svg.read_text(encoding="utf-8")
        tiny_svg.write_text(clean_svg.replace('font-size="18"', 'font-size="5"', 1), encoding="utf-8")
        negative_font = validate(root, complete_manifest, strict=True)
        assert negative_font["status"] == "FAIL"
        assert any("font-size below 6" in item for item in negative_font["errors"])
        tiny_svg.write_text(clean_svg, encoding="utf-8")

        capability_broken = json.loads(json.dumps(complete_manifest))
        capability_broken["capabilities"]["docx"]["status"] = "unavailable"
        negative_capability = validate(root, capability_broken, strict=True)
        assert negative_capability["status"] == "FAIL"
        assert any("complete delivery requires" in item for item in negative_capability["errors"])

        score_broken = json.loads(json.dumps(complete_manifest))
        score_broken["score_rows"][0]["evidence_maturity"] = "V0"
        score_broken["score_rows"][0]["anchor_maturity"] = "V2"
        negative_score = validate(root, score_broken, strict=True)
        assert negative_score["status"] == "FAIL"
        assert any("score exceeds evidence maturity" in item for item in negative_score["errors"])

        summary = root / "01-summary.md"
        clean_summary = summary.read_text(encoding="utf-8")
        summary.write_text(clean_summary + "\n已确认市场空白。\n", encoding="utf-8")
        negative_claim = validate(root, complete_manifest, strict=True)
        assert negative_claim["status"] == "FAIL"
        assert any("unsupported claim" in item for item in negative_claim["errors"])
    print("DELIVERABLE_SELF_TEST_PASS")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="research output directory")
    parser.add_argument("--manifest", type=Path, help="deliverables-manifest.json")
    parser.add_argument("--strict", action="store_true", help="enforce validator runtime declaration")
    parser.add_argument("--self-test", action="store_true", help="run positive and negative built-in tests")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.root is None or args.manifest is None:
        print("error: --root and --manifest are required", file=sys.stderr)
        return 2
    root = args.root.resolve()
    manifest_path = args.manifest.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result = validate(root, manifest, strict=args.strict)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
