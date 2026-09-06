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
import hashlib
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
CURRENT_SCHEMA_VERSION = "1.2"
RESEARCH_RECORD_SCHEMA = "1.0"
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
    (re.compile(r"(?:可)?立即落地|直接落地"), "未限定的立即实施结论"),
    (re.compile(r"实现.{0,12}(?:不误报|不漏报)"), "无条件识别性能结论"),
    (re.compile(r"(?:风险|故障|事故|误报|漏报).{0,8}归零"), "无条件归零结论"),
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
    result: dict[str, object] = {
        "id": figure_id,
        "path": path.name,
        "labels": 0,
        "min_font_size": None,
        "effective_min_font_pt": None,
    }
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
        effective = minimum
        view_box = str(root.attrib.get("viewBox", "")).split()
        display_width = item.get("display_width_pt")
        if len(view_box) == 4 and isinstance(display_width, (int, float)) and display_width > 0:
            try:
                view_width = float(view_box[2])
                if view_width > 0:
                    effective = minimum * float(display_width) / view_width
            except ValueError:
                pass
        elif item.get("display_width_pt") is not None:
            _fail(errors, f"invalid display_width_pt/viewBox for {figure_id}")
        result["effective_min_font_pt"] = round(effective, 3)
        if effective < 6:
            _fail(errors, f"effective SVG font-size below 6pt for {figure_id}: {effective:.2f}pt")
        elif effective < 8:
            warnings.append(f"effective SVG font-size below 8pt for {figure_id}: {effective:.2f}pt")

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


def _validate_v11(root: Path, manifest: dict, strict: bool = False) -> dict[str, object]:
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_ids(items: object, section: str, errors: list[str]) -> tuple[list[dict], set[str]]:
    if not isinstance(items, list):
        _fail(errors, f"research_record.{section} must be an array")
        return [], set()
    rows: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            _fail(errors, f"research_record.{section}[{index}] must be an object")
            continue
        item_id = str(item.get("id", "")).strip()
        if not item_id or item_id in seen:
            _fail(errors, f"research_record.{section}[{index}] id missing or duplicated: {item_id}")
        seen.add(item_id)
        rows.append(item)
    return rows, seen


def _check_reference_ids(
    values: object,
    allowed: set[str],
    label: str,
    errors: list[str],
    allow_empty: bool = True,
) -> None:
    if not isinstance(values, list):
        _fail(errors, f"{label} must be an array")
        return
    if not values and not allow_empty:
        _fail(errors, f"{label} must contain at least one resolvable ID")
    for value in values:
        ref = str(value).strip()
        if not ref or ref not in allowed:
            _fail(errors, f"{label} contains unresolved ID: {ref}")


def _validate_record(
    record: dict,
    manifest: dict,
    public_text: str,
    errors: list[str],
    warnings: list[str],
) -> tuple[dict[str, int], list[dict], str]:
    if record.get("schema_version") != RESEARCH_RECORD_SCHEMA:
        _fail(errors, f"research_record schema_version must be {RESEARCH_RECORD_SCHEMA}")

    variables, variable_ids = _unique_ids(record.get("variables"), "variables", errors)
    for index, variable in enumerate(variables):
        for field in ["object", "quantity", "unit", "preferred_direction", "evidence_status"]:
            if not str(variable.get(field, "")).strip():
                _fail(errors, f"variables[{index}] missing {field}")
        if variable.get("preferred_direction") not in {"increase", "decrease", "range"}:
            _fail(errors, f"variables[{index}] preferred_direction must be increase/decrease/range")
        rule = variable.get("decision_rule")
        if isinstance(rule, dict) and rule.get("enabled") is True:
            comparison = rule.get("comparison")
            change = rule.get("earlier_warning_change")
            expected = "increase" if comparison == "below" else "decrease" if comparison == "above" else None
            if expected is None:
                _fail(errors, f"variables[{index}] decision_rule.comparison must be below/above")
            elif change != expected:
                _fail(errors, f"variables[{index}] threshold polarity conflict: {comparison} requires {expected}")

    contradictions, _ = _unique_ids(record.get("contradictions", []), "contradictions", errors)
    for index, item in enumerate(contradictions):
        if str(item.get("control_variable_id", "")) not in variable_ids:
            _fail(errors, f"contradictions[{index}] control_variable_id is unresolved")
        eligibility = item.get("eligibility")
        if eligibility not in {
            "matrix_eligible",
            "separation_eligible",
            "assumption_only",
            "reframe_required",
            "no_triz_contradiction",
        }:
            _fail(errors, f"contradictions[{index}] invalid eligibility: {eligibility}")
        for field in ["change_direction", "useful_result", "worsened_result", "causality_basis", "ec2_reverse_case"]:
            if len(str(item.get(field, "")).strip()) < 4:
                _fail(errors, f"contradictions[{index}] missing meaningful {field}")
        mapping = item.get("matrix_mapping", {})
        if eligibility == "matrix_eligible":
            if not isinstance(mapping, dict):
                _fail(errors, f"contradictions[{index}] matrix_mapping must be an object")
                continue
            improve = mapping.get("improving_parameter")
            worsen = mapping.get("worsening_parameter")
            if not isinstance(improve, int) or not 1 <= improve <= 39:
                _fail(errors, f"contradictions[{index}] invalid improving_parameter")
            if not isinstance(worsen, int) or not 1 <= worsen <= 39:
                _fail(errors, f"contradictions[{index}] invalid worsening_parameter")
            expected_cell = f"R{improve:02d}xC{worsen:02d}" if isinstance(improve, int) and isinstance(worsen, int) else ""
            if str(mapping.get("matrix_cell", "")).replace("×", "x") != expected_cell:
                _fail(errors, f"contradictions[{index}] matrix_cell does not match parameter direction")
            if not isinstance(mapping.get("principles"), list):
                _fail(errors, f"contradictions[{index}] principles must be an array")
            elif isinstance(improve, int) and isinstance(worsen, int) and 1 <= improve <= 39 and 1 <= worsen <= 39:
                try:
                    matrix_payload = json.loads((SKILL_ROOT / "references" / "contradiction-matrix.json").read_text(encoding="utf-8"))
                    expected_principles = matrix_payload["matrix"][improve - 1][worsen - 1]
                    if mapping.get("principles") != expected_principles:
                        _fail(errors, f"contradictions[{index}] principles differ from deterministic matrix cell")
                except (OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
                    _fail(errors, f"cannot verify contradictions[{index}] matrix cell: {exc}")

    queries, _ = _unique_ids(record.get("queries"), "queries", errors)
    aggregate_query = re.compile(r"(?:×|\bx\s*)\d+|多次|若干次|……|\.\.\.", re.IGNORECASE)
    valid_queries = 0
    failed_queries = 0
    for index, item in enumerate(queries):
        query = str(item.get("query", "")).strip()
        if len(query) < 3:
            _fail(errors, f"queries[{index}] lacks a reproducible query string")
        elif aggregate_query.search(query):
            _fail(errors, f"queries[{index}] merges multiple attempts instead of recording one query")
        else:
            valid_queries += 1
        if not str(item.get("date", "")).strip() or not str(item.get("entry", "")).strip():
            _fail(errors, f"queries[{index}] requires date and entry")
        if item.get("status") not in {"completed", "failed", "no-result"}:
            _fail(errors, f"queries[{index}] invalid status")
        if item.get("status") in {"failed", "no-result"}:
            failed_queries += 1

    sources, source_ids = _unique_ids(record.get("sources"), "sources", errors)
    stable_sources = 0
    critical_sources = 0
    target_kinds = {"field_baseline", "proxy_benchmark", "source_component", "proposed_system"}
    for index, item in enumerate(sources):
        if len(str(item.get("title", "")).strip()) < 3:
            _fail(errors, f"sources[{index}] missing title")
        if item.get("target_kind") not in target_kinds:
            _fail(errors, f"sources[{index}] invalid target_kind")
        for field in ["creator", "date_or_version", "authority", "directness", "independence", "currency", "scope_match"]:
            if not str(item.get(field, "")).strip():
                _fail(errors, f"sources[{index}] missing five-dimensional evidence field: {field}")
        stable = bool(str(item.get("stable_identifier", "")).strip() or str(item.get("url", "")).strip())
        if stable:
            stable_sources += 1
        if item.get("critical") is True:
            critical_sources += 1
            for field in ["locator", "supporting_excerpt_or_fact", "limitations"]:
                if len(str(item.get(field, "")).strip()) < 4:
                    _fail(errors, f"critical sources[{index}] missing {field}")
            if not stable:
                _fail(errors, f"critical sources[{index}] lacks stable identifier or URL")

    claims, claim_ids = _unique_ids(record.get("claims"), "claims", errors)
    for index, item in enumerate(claims):
        if item.get("target_kind") not in target_kinds:
            _fail(errors, f"claims[{index}] invalid target_kind")
        _check_reference_ids(item.get("supporting_source_ids", []), source_ids, f"claims[{index}].supporting_source_ids", errors)
        _check_reference_ids(item.get("opposing_source_ids", []), source_ids, f"claims[{index}].opposing_source_ids", errors)
        if item.get("evidence_status") in {"unknown", "H", None}:
            if len(str(item.get("allowed_wording", "")).strip()) < 6:
                _fail(errors, f"claims[{index}] unknown/H claim lacks allowed_wording")
            if len(str(item.get("next_validation", "")).strip()) < 4:
                _fail(errors, f"claims[{index}] unknown/H claim lacks next_validation")

    allowed_evidence_ids = source_ids | claim_ids
    for index, variable in enumerate(variables):
        _check_reference_ids(variable.get("evidence_ids", []), allowed_evidence_ids, f"variables[{index}].evidence_ids", errors)
    for index, item in enumerate(contradictions):
        _check_reference_ids(item.get("evidence_ids", []), allowed_evidence_ids, f"contradictions[{index}].evidence_ids", errors)
    for index, item in enumerate(queries):
        _check_reference_ids(item.get("included_source_ids", []), source_ids, f"queries[{index}].included_source_ids", errors)
    routes, route_ids = _unique_ids(record.get("routes"), "routes", errors)
    primary_routes = {str(value) for value in manifest.get("primary_routes", [])}
    shortlisted_routes = {str(value) for value in manifest.get("shortlisted_routes", [])}
    for route in routes:
        route_id = str(route.get("id", ""))
        if route.get("maturity") not in MATURITY_RANK:
            _fail(errors, f"route {route_id} maturity must be V0-V3")
        components = route.get("components")
        if not isinstance(components, list) or not components:
            _fail(errors, f"route {route_id} requires components")
            components = []
        for index, component in enumerate(components):
            if not isinstance(component, dict):
                _fail(errors, f"route {route_id} component[{index}] must be an object")
                continue
            if component.get("target_kind") not in target_kinds:
                _fail(errors, f"route {route_id} component[{index}] invalid target_kind")
            _check_reference_ids(component.get("evidence_ids", []), allowed_evidence_ids, f"route {route_id} component[{index}].evidence_ids", errors)
        steps = route.get("steps")
        if not isinstance(steps, list) or not steps:
            _fail(errors, f"route {route_id} requires an end-to-end step chain")
            steps = []
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                _fail(errors, f"route {route_id} step[{index}] must be an object")
                continue
            for field in ["action", "input_range", "output_range", "handoff_status"]:
                if len(str(step.get(field, "")).strip()) < 3:
                    _fail(errors, f"route {route_id} step[{index}] missing {field}")
            if step.get("handoff_status") not in {"compatible", "conditional", "gap"}:
                _fail(errors, f"route {route_id} step[{index}] invalid handoff_status")
            if route_id in primary_routes and step.get("handoff_status") == "gap":
                _fail(errors, f"primary route {route_id} has end-to-end capability gap at step[{index}]")
            if step.get("handoff_status") == "conditional":
                warnings.append(f"route {route_id} has conditional handoff at step[{index}]")
            _check_reference_ids(step.get("evidence_ids", []), allowed_evidence_ids, f"route {route_id} step[{index}].evidence_ids", errors)
        for index in range(len(steps) - 1):
            upstream = steps[index] if isinstance(steps[index], dict) else {}
            downstream = steps[index + 1] if isinstance(steps[index + 1], dict) else {}
            output_range = upstream.get("output_numeric_range")
            input_range = downstream.get("input_numeric_range")
            if isinstance(output_range, dict) and isinstance(input_range, dict):
                try:
                    if output_range.get("unit") != input_range.get("unit"):
                        _fail(errors, f"route {route_id} numeric handoff unit mismatch at steps {index}/{index + 1}")
                    elif float(output_range["min"]) < float(input_range["min"]) or float(output_range["max"]) > float(input_range["max"]):
                        _fail(errors, f"route {route_id} numeric handoff gap at steps {index}/{index + 1}")
                except (KeyError, TypeError, ValueError):
                    _fail(errors, f"route {route_id} invalid numeric handoff range at steps {index}/{index + 1}")
        effects = [item for item in route.get("active_effects", []) if isinstance(item, dict)]
        active_ids = {str(item.get("id", "")) for item in effects if item.get("type") not in {"read", "passive", "information_read"}}
        interactions = route.get("interactions", [])
        if len(active_ids) > 1:
            covered: set[str] = set()
            if isinstance(interactions, list):
                for interaction in interactions:
                    if not isinstance(interaction, dict) or interaction.get("status") not in {"compatible", "conditional", "conflict", "unknown"}:
                        continue
                    covered.update(str(value) for value in interaction.get("effect_ids", []))
            if not active_ids.issubset(covered):
                _fail(errors, f"route {route_id} has multiple active effects without coexistence/interference review")
        if len(str(route.get("failure_fallback", "")).strip()) < 4:
            _fail(errors, f"route {route_id} lacks failure fallback")
        _check_reference_ids(route.get("claim_ids", []), claim_ids, f"route {route_id}.claim_ids", errors, allow_empty=False)
        mechanism = route.get("mechanism_kind")
        if mechanism in {"electrical_measurement", "measurement", "diagnosis"}:
            card = route.get("identifiability")
            required_fields = ["excitation", "observations", "unknowns", "reference", "relationship", "confounders", "decision_uncertainty"]
            if not isinstance(card, dict):
                _fail(errors, f"measurement route {route_id} requires identifiability card")
            else:
                for field in required_fields:
                    value = card.get(field)
                    if value is None or value == "" or value == []:
                        _fail(errors, f"measurement route {route_id} identifiability.{field} is missing")
        if MATURITY_RANK.get(str(route.get("maturity")), 0) > 0:
            supporting_system_claim = any(
                claim.get("target_kind") == "proposed_system"
                and str(claim.get("target_id", "")) == route_id
                and claim.get("evidence_status") in {"M", "measured", "verified"}
                for claim in claims
            )
            if not supporting_system_claim:
                _fail(errors, f"route {route_id} maturity cannot exceed V0 using component/proxy evidence only")

    for route_id in primary_routes | shortlisted_routes:
        if route_id not in route_ids:
            _fail(errors, f"manifest route is missing from research_record.routes: {route_id}")

    assessments = record.get("assessments")
    if not isinstance(assessments, dict):
        _fail(errors, "research_record.assessments must be an object")
        assessments = {}
    gates = assessments.get("gates", [])
    if not isinstance(gates, list):
        _fail(errors, "assessments.gates must be an array")
    else:
        for index, gate in enumerate(gates):
            if not isinstance(gate, dict):
                _fail(errors, f"assessments.gates[{index}] must be an object")
                continue
            _check_reference_ids(gate.get("evidence_ids", []), allowed_evidence_ids, f"assessments.gates[{index}].evidence_ids", errors)
            if gate.get("status") == "pass" and not gate.get("evidence_ids"):
                _fail(errors, f"assessments.gates[{index}] cannot pass without evidence")
    scorecard = assessments.get("scorecard", {})
    legacy_score_rows: list[dict] = []
    score_rows_count = 0
    if not isinstance(scorecard, dict):
        _fail(errors, "assessments.scorecard must be an object")
    else:
        dimensions, dimension_ids = _unique_ids(scorecard.get("dimensions", []), "assessments.scorecard.dimensions", errors)
        dimension_map = {str(item.get("id")): item for item in dimensions}
        rows = scorecard.get("rows", [])
        if not isinstance(rows, list):
            _fail(errors, "assessments.scorecard.rows must be an array")
            rows = []
        score_rows_count = len(rows)
        if scorecard.get("used") is True:
            expected_pairs = {(route_id, dimension_id) for route_id in shortlisted_routes for dimension_id in dimension_ids}
            actual_pairs: set[tuple[str, str]] = set()
            for index, row in enumerate(rows):
                if not isinstance(row, dict):
                    _fail(errors, f"scorecard.rows[{index}] must be an object")
                    continue
                route_id = str(row.get("route_id", ""))
                dimension_id = str(row.get("dimension_id", ""))
                pair = (route_id, dimension_id)
                if pair in actual_pairs:
                    _fail(errors, f"duplicated score row: {route_id}/{dimension_id}")
                actual_pairs.add(pair)
                dimension = dimension_map.get(dimension_id, {})
                anchors = dimension.get("anchors", {}) if isinstance(dimension, dict) else {}
                unknown = row.get("unknown") is True
                not_applicable = row.get("not_applicable") is True
                score = row.get("score")
                evidence_ids = row.get("evidence_ids", [])
                if unknown or not_applicable:
                    if score is not None:
                        _fail(errors, f"unknown/N/A score must be null: scorecard.rows[{index}]")
                    legacy_score_rows.append({"score": None, "unknown": unknown, "not_applicable": not_applicable})
                    continue
                if score not in SCORE_VALUES:
                    _fail(errors, f"score must be 0/1/3/5: scorecard.rows[{index}]")
                    continue
                anchor = anchors.get(str(score)) if isinstance(anchors, dict) else None
                if not isinstance(anchor, dict):
                    _fail(errors, f"scorecard dimension {dimension_id} lacks frozen anchor {score}")
                    anchor = {}
                anchor_maturity = anchor.get("required_maturity")
                evidence_maturity = row.get("evidence_maturity")
                _check_reference_ids(evidence_ids, allowed_evidence_ids, f"scorecard.rows[{index}].evidence_ids", errors, allow_empty=False)
                if row.get("target_kind") != "proposed_system":
                    _fail(errors, f"scorecard.rows[{index}] must evaluate proposed_system, not a source component")
                if anchor_maturity not in MATURITY_RANK or evidence_maturity not in MATURITY_RANK:
                    _fail(errors, f"scorecard.rows[{index}] maturity must be V0-V3")
                elif MATURITY_RANK[evidence_maturity] < MATURITY_RANK[anchor_maturity]:
                    _fail(errors, f"score exceeds frozen evidence maturity anchor: scorecard.rows[{index}]")
                legacy_score_rows.append(
                    {
                        "route": route_id,
                        "dimension": dimension_id,
                        "score": score,
                        "unknown": False,
                        "not_applicable": False,
                        "evidence_id": str(evidence_ids[0]) if evidence_ids else "",
                        "evidence_maturity": evidence_maturity,
                        "anchor_maturity": anchor_maturity,
                    }
                )
            if actual_pairs != expected_pairs:
                missing = sorted(expected_pairs - actual_pairs)
                extra = sorted(actual_pairs - expected_pairs)
                _fail(errors, f"scorecard route×dimension coverage mismatch; missing={missing}, extra={extra}")
        elif rows:
            _fail(errors, "scorecard.used=false but score rows are present")
        elif re.search(r"加权评分|可行性\s*/?\s*价值分", public_text):
            _fail(errors, "report contains a scoring table but structured scorecard is unused/empty")

    models = record.get("models_and_tests")
    if not isinstance(models, dict):
        _fail(errors, "research_record.models_and_tests must be an object")
        models = {}
    benefit_scenarios = models.get("benefit_scenarios", [])
    if not isinstance(benefit_scenarios, list):
        _fail(errors, "models_and_tests.benefit_scenarios must be an array")
        benefit_scenarios = []
    for index, model in enumerate(benefit_scenarios):
        if not isinstance(model, dict):
            _fail(errors, f"benefit_scenarios[{index}] must be an object")
            continue
        if model.get("formula_type") == "linear_difference_rate":
            inputs = model.get("inputs", {})
            try:
                calculated = (
                    (float(inputs["baseline"]) - float(inputs["candidate"]))
                    * float(inputs.get("quantity", 1))
                    * float(inputs.get("unit_rate", 1))
                )
                expected = float(model["expected_result"])
                if abs(calculated - expected) > max(1e-9, abs(expected) * 1e-9):
                    _fail(errors, f"benefit_scenarios[{index}] arithmetic mismatch: {calculated} != {expected}")
            except (KeyError, TypeError, ValueError):
                _fail(errors, f"benefit_scenarios[{index}] has invalid linear_difference_rate inputs")
        outputs = model.get("outputs", [])
        if isinstance(outputs, list) and outputs:
            expected_value = model.get("expected_result")
            expected_unit = model.get("unit")
            for output in outputs:
                if not isinstance(output, dict) or output.get("value") != expected_value or output.get("unit") != expected_unit:
                    _fail(errors, f"benefit_scenarios[{index}] output value/unit differs across artifacts")

    tests = models.get("tests", [])
    if not isinstance(tests, list):
        _fail(errors, "models_and_tests.tests must be an array")
        tests = []
    for index, test in enumerate(tests):
        if not isinstance(test, dict) or test.get("claim_scope") != "full_range":
            continue
        target = test.get("target_range", {})
        tested = test.get("tested_range", {})
        try:
            if float(tested["min"]) > float(target["min"]) or float(tested["max"]) < float(target["max"]):
                _fail(errors, f"tests[{index}] does not cover the claimed full range")
        except (KeyError, TypeError, ValueError):
            _fail(errors, f"tests[{index}] full_range claim requires numeric target_range/tested_range")

    absence = record.get("absence_assessments", [])
    if not isinstance(absence, list):
        _fail(errors, "research_record.absence_assessments must be an array")
        absence = []
    for index, item in enumerate(absence):
        if not isinstance(item, dict):
            _fail(errors, f"absence_assessments[{index}] must be an object")
            continue
        level = item.get("level")
        required = []
        if level in {"N2", "N3"}:
            required = ["databases", "queries", "classifications", "exclusions", "uncovered_scope"]
        if level == "N3":
            required += ["citation_tracking", "saturation_evidence"]
        for field in required:
            value = item.get(field)
            if value is None or value == "" or value is False or value == []:
                _fail(errors, f"absence_assessments[{index}] {level} lacks {field}")

    engineering_review = assessments.get("engineering_review", {})
    engineering_status = str(engineering_review.get("status", "pending")) if isinstance(engineering_review, dict) else "pending"
    if engineering_status not in {"pending", "issues-found", "reviewed"}:
        _fail(errors, "assessments.engineering_review.status must be pending/issues-found/reviewed")
    if engineering_status == "reviewed" and not str(engineering_review.get("reviewed_artifact_sha256", "")).strip():
        _fail(errors, "reviewed engineering content requires reviewed_artifact_sha256")
    if engineering_status == "issues-found" and manifest.get("status") == "complete":
        _fail(errors, "complete delivery cannot retain unresolved engineering review issues")

    stats = {
        "query_records": valid_queries,
        "failed_queries": failed_queries,
        "source_records": len(sources),
        "stable_sources": stable_sources,
        "critical_sources": critical_sources,
        "score_rows": score_rows_count,
        "benefit_scenarios": len(benefit_scenarios),
    }
    expected = manifest.get("expected_counts")
    if not isinstance(expected, dict):
        _fail(errors, "expected_counts must be an object")
    else:
        for name in ["query_records", "source_records", "critical_sources", "score_rows", "benefit_scenarios"]:
            if expected.get(name) != stats[name]:
                _fail(errors, f"expected_counts.{name} differs from research record: {expected.get(name)} != {stats[name]}")
    return stats, legacy_score_rows, engineering_status


def _check_bound_review(root: Path, review: object, diagram_available: bool, errors: list[str]) -> set[str]:
    bound_paths: set[str] = set()
    if not isinstance(review, dict):
        _fail(errors, "figure_review must be an object")
        return bound_paths
    expected_status = "pass" if diagram_available else "not-applicable"
    for name in sorted(FIGURE_REVIEW_NAMES):
        item = review.get(name)
        if not isinstance(item, dict) or item.get("status") != expected_status:
            _fail(errors, f"figure review status must be {expected_status}: {name}")
            continue
        if not diagram_available:
            if not item.get("findings"):
                _fail(errors, f"degraded figure review requires a concrete reason: {name}")
            continue
        findings = item.get("findings")
        if not isinstance(findings, list) or not findings or any(len(str(value).strip()) < 4 for value in findings):
            _fail(errors, f"figure review requires concrete findings: {name}")
        checked = item.get("checked_files")
        if not isinstance(checked, list) or not checked:
            _fail(errors, f"figure review requires hash-bound checked_files: {name}")
            continue
        for index, binding in enumerate(checked):
            if not isinstance(binding, dict):
                _fail(errors, f"figure review {name}.checked_files[{index}] must be an object")
                continue
            path = _safe_path(root, binding.get("path"), errors, f"figure review {name}.checked_files[{index}]")
            if path is not None and str(binding.get("sha256", "")).lower() != _sha256(path):
                _fail(errors, f"figure review hash mismatch: {name}/{path.name}")
            if path is not None:
                bound_paths.add(str(path.relative_to(root)))
        if name == "engineer_view" and len(str(item.get("dangerous_misreading_checked", "")).strip()) < 6:
            _fail(errors, "engineer_view requires the most dangerous misreading and its disposition")
        if name == "first_time_reader_view" and len(str(item.get("mechanism_restatement", "")).strip()) < 12:
            _fail(errors, "first_time_reader_view requires a 2-3 sentence mechanism restatement")
    return bound_paths


def _check_actual_figure_order(root: Path, manifest: dict, errors: list[str]) -> None:
    order = manifest.get("report_figure_order")
    if not isinstance(order, dict):
        _fail(errors, "report_figure_order must be an object")
        return
    expected = [str(value) for value in order.get("ordered_numbers", [])]
    if not expected:
        return
    main_paths = []
    for artifact in manifest.get("artifacts", []):
        if isinstance(artifact, dict) and artifact.get("role") == "main-report":
            candidate = _safe_path(root, artifact.get("path"), errors, "report_figure_order.main-report")
            if candidate is not None and candidate.suffix.lower() == ".docx":
                main_paths.append(candidate)
    if not main_paths:
        return
    paragraphs = _extract_text(main_paths[0])
    marker = str(order.get("body_start_marker", "")).strip()
    start = 0
    marker_found = not marker
    if marker:
        for index, paragraph in enumerate(paragraphs):
            if marker in paragraph:
                start = index
                marker_found = True
                break
    if not marker_found:
        _fail(errors, f"DOCX body_start_marker not found: {marker}")
        return
    preview_allowed = {str(value) for value in order.get("summary_preview_numbers", [])}
    preview_found: set[str] = set()
    for paragraph in paragraphs[:start]:
        for number in re.findall(r"图\s*(\d+\s*[-－]\s*\d+)", paragraph):
            preview_found.add(re.sub(r"\s", "", number).replace("－", "-"))
    unexpected_preview = sorted(preview_found - preview_allowed)
    if unexpected_preview:
        _fail(errors, f"DOCX summary contains undeclared figure previews: {unexpected_preview}")
    found: list[str] = []
    for paragraph in paragraphs[start:]:
        for number in re.findall(r"图\s*(\d+\s*[-－]\s*\d+)", paragraph):
            normalized = re.sub(r"\s", "", number).replace("－", "-")
            if normalized not in found:
                found.append(normalized)
    filtered = [number for number in found if number in set(expected)]
    if filtered != expected:
        _fail(errors, f"DOCX actual body figure order differs: {filtered} != {expected}")


def _validate_v12(root: Path, manifest: dict, strict: bool = False) -> dict[str, object]:
    root = root.resolve()
    v12_errors: list[str] = []
    v12_warnings: list[str] = []
    record_info = manifest.get("research_record")
    record: dict = {}
    record_path: Path | None = None
    if not isinstance(record_info, dict):
        _fail(v12_errors, "research_record must be an object")
    else:
        record_path = _safe_path(root, record_info.get("path"), v12_errors, "research_record")
        if record_info.get("schema_version") != RESEARCH_RECORD_SCHEMA:
            _fail(v12_errors, f"manifest research_record.schema_version must be {RESEARCH_RECORD_SCHEMA}")
        if record_path is not None:
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                _fail(v12_errors, f"research_record JSON invalid: {exc}")

    public_text = "\n".join(
        line
        for artifact in manifest.get("artifacts", [])
        if isinstance(artifact, dict) and artifact.get("role") in {"decision-summary", "main-report"}
        for path in [_safe_path(root, artifact.get("path"), v12_errors, f"public artifact {artifact.get('role')}")]
        if path is not None
        for line in _extract_text(path)
    )
    stats, score_rows, engineering_status = _validate_record(
        record, manifest, public_text, v12_errors, v12_warnings
    ) if record else ({"query_records": 0, "source_records": 0, "critical_sources": 0, "score_rows": 0, "benefit_scenarios": 0}, [], "pending")

    legacy = json.loads(json.dumps(manifest))
    legacy["schema_version"] = SCHEMA_VERSION
    legacy["research_log"] = {
        "path": record_info.get("path") if isinstance(record_info, dict) else "",
        "claimed_queries": stats.get("query_records", 0),
        "logged_queries": stats.get("query_records", 0),
    }
    sources = record.get("sources", []) if isinstance(record, dict) else []
    legacy["sources"] = {
        "cards": stats.get("source_records", 0),
        "with_stable_identifier": sum(
            1 for item in sources if isinstance(item, dict) and (item.get("stable_identifier") or item.get("url"))
        ),
        "critical": stats.get("critical_sources", 0),
        "with_url": sum(1 for item in sources if isinstance(item, dict) and item.get("url")),
    }
    legacy["score_rows"] = score_rows
    new_review = manifest.get("figure_review", {})
    legacy["figure_review"] = {
        name: {
            "status": (new_review.get(name, {}) if isinstance(new_review, dict) else {}).get("status"),
            "evidence": "; ".join(
                str(value) for value in (new_review.get(name, {}) if isinstance(new_review, dict) else {}).get("findings", [])
            ),
        }
        for name in FIGURE_REVIEW_NAMES
    }
    domain = str(manifest.get("concept_profile", {}).get("domain", "mechanical"))
    if domain not in {"mechanical", "electrical", "measurement", "control", "software", "thermal", "fluid", "process", "work"}:
        _fail(v12_errors, f"invalid concept_profile.domain: {domain}")
    if domain != "mechanical":
        legacy_profile = legacy.get("concept_profile", {})
        for name in ["physical_structure", "relative_motion", "force_energy_transfer", "material_deformation"]:
            legacy_profile[name] = False

    base = _validate_v11(root, legacy, strict=strict)
    diagram_available = manifest.get("capabilities", {}).get("diagram", {}).get("status") == "available"
    review_paths = _check_bound_review(root, manifest.get("figure_review"), diagram_available, v12_errors)
    if diagram_available:
        required_review_paths = {
            str(item.get("source_svg", ""))
            for item in manifest.get("figures", [])
            if isinstance(item, dict) and item.get("required") is True
        }
        missing_review_bindings = sorted(required_review_paths - review_paths)
        if missing_review_bindings:
            _fail(v12_errors, f"required figures lack hash-bound review evidence: {missing_review_bindings}")
    _check_actual_figure_order(root, manifest, v12_errors)

    render = manifest.get("render_summary", {})
    if manifest.get("capabilities", {}).get("render", {}).get("status") == "available" and isinstance(render, dict):
        document_path = _safe_path(root, render.get("document_path"), v12_errors, "render_summary.document_path")
        declared_hash = str(render.get("document_sha256", "")).lower()
        if document_path is not None:
            actual_hash = _sha256(document_path)
            if declared_hash != actual_hash:
                _fail(v12_errors, "render_summary.document_sha256 does not match the checked document")
            for index, item in enumerate(render.get("page_checks", [])):
                if isinstance(item, dict) and str(item.get("artifact_sha256", "")).lower() != actual_hash:
                    _fail(v12_errors, f"page_checks[{index}] is not bound to the rendered document hash")

    errors = list(base.get("errors", [])) + v12_errors
    warnings = list(base.get("warnings", [])) + v12_warnings
    base.update(
        {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "research_record_stats": stats,
            "quality_status": {
                "structural": "PASS" if not base.get("errors") else "FAIL",
                "computational_consistency": "PASS" if not v12_errors else "FAIL",
                "engineering_review": engineering_status,
            },
            "warnings": warnings,
            "errors": errors,
            "status": "PASS" if not errors else "FAIL",
        }
    )
    return base


def validate(root: Path, manifest: dict, strict: bool = False) -> dict[str, object]:
    schema = manifest.get("schema_version")
    if schema == CURRENT_SCHEMA_VERSION:
        return _validate_v12(root, manifest, strict=strict)
    result = _validate_v11(root, manifest, strict=strict)
    result["quality_status"] = {
        "structural": result.get("status"),
        "computational_consistency": "LEGACY_UNCHECKED",
        "engineering_review": "LEGACY_UNCHECKED",
    }
    warning = f"legacy schema {schema} read; v2.5 research-record checks were not executed"
    result.setdefault("warnings", []).append(warning)
    if strict:
        result.setdefault("errors", []).append("legacy schema cannot pass v2.5 strict validation")
        result["status"] = "FAIL"
    return result


def _self_test_v12() -> None:
    with tempfile.TemporaryDirectory(prefix="triz-delivery-v12-") as tmp:
        root = Path(tmp)
        for name in ["01-summary.md", "02-report.md", "03-evidence.md", "04-ledger.md"]:
            (root / name).write_text(f"# {name}\n可复核的通用技术内容。\n", encoding="utf-8")
        specs = [
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
        png_payload = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        figures: list[dict] = []
        for index, (role, figure_type, routes) in enumerate(specs, start=1):
            svg = root / f"figure-{index}.svg"
            png = root / f"figure-{index}.png"
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450">'
                f'<title>图6-{index} 通用工程图</title><desc>输入通过候选界面作用于目标对象。</desc>'
                '<rect width="800" height="450" fill="#eef6f8"/>'
                '<path d="M80 230 C210 90 430 90 590 230" fill="none" stroke="#176B87" stroke-width="8"/>'
                '<polygon points="590,215 630,230 590,245" fill="#176B87"/>'
                '<text x="100" y="320" font-size="18">工具</text>'
                '<text x="300" y="320" font-size="18">目标层</text>'
                '<text x="500" y="320" font-size="18">被保护区域</text></svg>',
                encoding="utf-8",
            )
            png.write_bytes(png_payload)
            figures.append(
                {
                    "id": f"FIG-{index:02d}",
                    "number": f"6-{index}",
                    "chapter": 6,
                    "type": role,
                    "figure_type": figure_type,
                    "title": f"通用工程图{index}",
                    "decision_question": "输入怎样通过候选界面形成目标输出？",
                    "main_message": "受控作用路径把输入传给目标对象并保留安全退出。",
                    "subject": "通用工程对象与候选作用界面",
                    "confirmed_elements": ["目标层"],
                    "hypothetical_elements": ["工具"],
                    "unknown_elements": ["尺寸"],
                    "motions": ["输入", "作用", "退出"],
                    "forces": ["受控作用"],
                    "energy_flows": [],
                    "protected_objects": ["被保护区域"],
                    "hazards": ["越界"],
                    "safety_barriers": ["候选止挡"],
                    "labels_required": ["工具", "目标层", "被保护区域"],
                    "evidence_ids": ["CLM-001"],
                    "claim_limit": "V0 概念机理，具体尺寸和安全能力待验证。",
                    "design_status": "V0",
                    "source_svg": svg.name,
                    "render_png": png.name,
                    "path": png.name,
                    "display_width_pt": 432,
                    "alt": "图中显示工具、目标层、主作用方向和被保护区域。",
                    "ledgered": True,
                    "embedded_in": [],
                    "routes": routes,
                    "required": True,
                    "frame_count": 4 if figure_type == "F5-motion-sequence" else None,
                }
            )

        record = {
            "schema_version": "1.0",
            "project": {"title": "通用工程课题", "record_status": "working", "maturity": "V0", "last_updated": "2026-09-06"},
            "variables": [
                {
                    "id": "VAR-01", "object": "目标对象", "quantity": "控制量", "unit": "1",
                    "preferred_direction": "range", "evidence_status": "H", "evidence_ids": [],
                    "decision_rule": {"enabled": False, "comparison": "below", "threshold_variable": False, "earlier_warning_change": "increase"},
                }
            ],
            "contradictions": [
                {
                    "id": "CON-01", "control_variable_id": "VAR-01", "change_direction": "increase",
                    "useful_result": "目标作用增强", "worsened_result": "副作用增加",
                    "causality_basis": "当前仅为待验证假设", "ec2_reverse_case": "反向改变时目标作用下降且副作用减小",
                    "eligibility": "assumption_only", "matrix_mapping": {"improving_parameter": None, "worsening_parameter": None, "matrix_cell": None, "principles": []},
                }
            ],
            "queries": [
                {"id": "Q-001", "date": "2026-09-06", "entry": "通用检索入口", "query": "generic engineering mechanism", "filters": "none", "status": "completed", "included_source_ids": ["SRC-001"], "excluded": []}
            ],
            "sources": [
                {
                    "id": "SRC-001", "title": "通用来源", "creator": "机构", "date_or_version": "2026",
                    "stable_identifier": "DOC-001", "url": "https://example.com/source", "locator": "section 1",
                    "supporting_excerpt_or_fact": "支持候选子功能存在", "target_kind": "source_component",
                    "authority": "medium", "directness": "direct", "independence": "primary", "currency": "current",
                    "scope_match": "partial", "critical": True, "limitations": "未验证目标系统适配",
                }
            ],
            "claims": [
                {
                    "id": "CLM-001", "text": "候选系统机理待验证", "target_kind": "proposed_system", "target_id": "R1",
                    "conditions": "仅限概念阶段", "evidence_status": "H", "supporting_source_ids": ["SRC-001"],
                    "opposing_source_ids": [], "unknowns": ["目标适配"], "allowed_wording": "候选机理可进入短样否证",
                    "next_validation": "代表性短样试验",
                },
                {
                    "id": "CLM-000", "text": "成熟基准仅作对照", "target_kind": "proposed_system", "target_id": "R0",
                    "conditions": "当前工况", "evidence_status": "H", "supporting_source_ids": ["SRC-001"],
                    "opposing_source_ids": [], "unknowns": ["现场完整节拍"], "allowed_wording": "作为基准候选",
                    "next_validation": "完整节拍对照",
                },
            ],
            "routes": [],
            "assessments": {
                "scorecard": {"used": False, "dimensions": [], "rows": []},
                "gates": [],
                "engineering_review": {"status": "pending", "reviewer_role": "待指定", "reviewed_artifact_sha256": None, "findings": ["待专业复核"]},
            },
            "models_and_tests": {"models": [], "tests": [], "benefit_scenarios": []},
            "absence_assessments": [],
        }
        for route_id, claim_id in [("R0", "CLM-000"), ("R1", "CLM-001")]:
            record["routes"].append(
                {
                    "id": route_id, "role": "primary" if route_id == "R1" else "baseline", "maturity": "V0",
                    "mechanism_kind": "mechanical", "evidence_status": "H",
                    "components": [{"id": f"M-{route_id}", "name": "候选模块", "target_kind": "proposed_system", "maturity": "V0", "evidence_ids": [claim_id]}],
                    "steps": [{"id": "STEP-01", "action": "完成目标作用", "input_range": "代表对象", "output_range": "目标状态", "handoff_to": None, "handoff_status": "compatible", "evidence_ids": [claim_id]}],
                    "active_effects": [{"id": "ACT-01", "type": "mechanical", "source": f"M-{route_id}", "target": "目标对象"}],
                    "interactions": [], "interfaces": [{"from": "操作者", "to": f"M-{route_id}", "kind": "control", "status": "defined"}],
                    "capability_range": {"input": "代表对象", "output": "目标状态", "environment": "受控", "known_gaps": []},
                    "failure_fallback": "停止并回到基准方法", "identifiability": None, "claim_ids": [claim_id],
                }
            )
        record_path = root / "research-record.json"
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        review_bindings = [
            {"path": item["source_svg"], "sha256": _sha256(root / item["source_svg"])}
            for item in figures
        ]
        manifest = {
            "schema_version": "1.2", "delivery_level": "standard", "status": "degraded", "maturity": "V0",
            "validator_runtime": "available",
            "capabilities": {
                "file_write": {"status": "available", "evidence": "已写入并读回测试文件"},
                "diagram": {"status": "available", "evidence": "已生成并读取 SVG 与 PNG"},
                "docx": {"status": "unavailable", "evidence": "此正例刻意测试降级交付"},
                "render": {"status": "unavailable", "evidence": "此正例刻意测试降级交付"},
            },
            "artifacts": [
                {"role": "decision-summary", "path": "01-summary.md", "required": True, "opened": True, "rendered": False},
                {"role": "main-report", "path": "02-report.md", "required": True, "opened": True, "rendered": False},
                {"role": "evidence-appendix", "path": "03-evidence.md", "required": True, "opened": True, "rendered": False},
                {"role": "source-figure-ledger", "path": "04-ledger.md", "required": True, "opened": True, "rendered": False},
                {"role": "research-record", "path": "research-record.json", "required": True, "opened": True, "rendered": False},
            ],
            "research_record": {"path": "research-record.json", "schema_version": "1.0"},
            "expected_counts": {"query_records": 1, "source_records": 1, "critical_sources": 1, "score_rows": 0, "benefit_scenarios": 0},
            "shortlisted_routes": ["R0", "R1"], "primary_routes": ["R1"],
            "concept_profile": {
                "primary_engineering_concept": True, "domain": "mechanical", "mechanism_kind": "mechanical",
                "physical_structure": True, "relative_motion": True, "force_energy_transfer": True,
                "material_deformation": True, "safety_risk": True, "multi_step_operation": True,
            },
            "figure_plan_frozen": True, "figures": figures, "figure_exemptions": [],
            "figure_review": {
                "engineer_view": {"status": "pass", "checked_files": review_bindings, "findings": ["主作用箭头从工具指向目标层，候选边界已标出"], "dangerous_misreading_checked": "已排除候选止挡被误读为验证完成"},
                "first_time_reader_view": {"status": "pass", "checked_files": review_bindings, "findings": ["首次读者仍需从图题确认具体对象"], "mechanism_restatement": "工具先接近目标层，再施加受控作用，异常时退出并保护下层对象。"},
                "figure_text_consistency": {"status": "pass", "checked_files": review_bindings, "findings": ["图中对象、路线和 V0 边界与正文一致"]},
                "black_white_legibility": {"status": "pass", "checked_files": review_bindings, "findings": ["线型与文字标签在低饱和条件下仍可区分"]},
            },
            "numeric_benefits": False, "checks": {name: "pass" for name in CHECK_NAMES},
            "report_figure_order": {"body_start_marker": "1.", "ordered_numbers": [], "summary_preview_numbers": []},
            "render_summary": {"document_path": "02-report.md", "document_sha256": "", "pages": 0, "checked_pages": 0, "page_checks": [], "blank_pages": [], "unresolved_visual_issues": []},
            "quality_status": {"structural": "not-checked", "computational_consistency": "not-checked", "engineering_review": "pending"},
        }

        positive = validate(root, manifest, strict=True)
        assert positive["status"] == "PASS", positive["errors"]

        tests = 0
        def expect_fail(mutator, needle: str) -> None:
            nonlocal tests
            tests += 1
            mutated_manifest = json.loads(json.dumps(manifest))
            mutated_record = json.loads(json.dumps(record))
            mutator(mutated_manifest, mutated_record)
            record_path.write_text(json.dumps(mutated_record, ensure_ascii=False), encoding="utf-8")
            result = validate(root, mutated_manifest, strict=True)
            assert result["status"] == "FAIL", f"negative test {tests} unexpectedly passed"
            assert any(needle in message for message in result["errors"]), (needle, result["errors"])
            record_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

        expect_fail(lambda m, r: m["expected_counts"].update(query_records=999), "expected_counts.query_records")
        expect_fail(lambda m, r: m["expected_counts"].update(source_records=999), "expected_counts.source_records")

        clean_report = (root / "02-report.md").read_text(encoding="utf-8")
        (root / "02-report.md").write_text(clean_report + "\n## 加权评分\n", encoding="utf-8")
        result = validate(root, manifest, strict=True)
        tests += 1
        assert result["status"] == "FAIL" and any("scorecard" in message for message in result["errors"])
        (root / "02-report.md").write_text(clean_report, encoding="utf-8")

        def bad_score(m, r):
            r["assessments"]["scorecard"] = {
                "used": True,
                "dimensions": [{"id": "D1", "name": "安全", "weight": 1, "anchors": {str(v): {"required_maturity": "V0"} for v in [0, 1, 3, 5]}}],
                "rows": [
                    {"route_id": route, "dimension_id": "D1", "score": 3, "unknown": False, "not_applicable": False, "evidence_ids": ["NO-SUCH-ID"], "evidence_maturity": "V0", "target_kind": "proposed_system"}
                    for route in ["R0", "R1"]
                ],
            }
            m["expected_counts"]["score_rows"] = 2
        expect_fail(bad_score, "unresolved ID")
        expect_fail(lambda m, r: r["routes"][1].update(maturity="V1"), "maturity cannot exceed V0")
        expect_fail(lambda m, r: r["variables"][0].update(decision_rule={"enabled": True, "comparison": "below", "threshold_variable": True, "earlier_warning_change": "decrease"}), "threshold polarity conflict")

        summary_path = root / "01-summary.md"
        clean_summary = summary_path.read_text(encoding="utf-8")
        summary_path.write_text(clean_summary + "\n该方案实现不误报。\n", encoding="utf-8")
        result = validate(root, manifest, strict=True)
        tests += 1
        assert result["status"] == "FAIL" and any("unsupported claim" in message for message in result["errors"])
        summary_path.write_text(clean_summary, encoding="utf-8")

        def numeric_range_gap(m, r):
            first = r["routes"][1]["steps"][0]
            first["handoff_to"] = "STEP-02"
            first["output_numeric_range"] = {"min": 1, "max": 10, "unit": "mm"}
            r["routes"][1]["steps"].append(
                {"id": "STEP-02", "action": "完成下游判断", "input_range": "受限对象", "output_range": "判断结果", "input_numeric_range": {"min": 1, "max": 3, "unit": "mm"}, "handoff_to": None, "handoff_status": "compatible", "evidence_ids": ["CLM-001"]}
            )
        expect_fail(numeric_range_gap, "numeric handoff gap")
        def missing_interaction(m, r):
            r["routes"][1]["active_effects"].append({"id": "ACT-02", "type": "electrical", "source": "M-R1", "target": "目标对象"})
        expect_fail(missing_interaction, "multiple active effects")
        def missing_identifiability(m, r):
            r["routes"][1]["mechanism_kind"] = "electrical_measurement"
            r["routes"][1]["identifiability"] = None
        expect_fail(missing_identifiability, "identifiability card")
        expect_fail(lambda m, r: m["figures"][0].update(display_width_pt=200), "effective SVG font-size below 6pt")

        # T12: Word 内的实际图题顺序与清单相反，即使清单自身有序也必须失败。
        report_source = root / "report-source-v12.json"
        reversed_figures = list(reversed(figures))
        report_source.write_text(
            json.dumps(
                {
                    "schema_version": "1.2", "research_record_path": "research-record.json",
                    "research_record_sha256": _sha256(record_path),
                    "title": "实际图序负例", "status": "V0 概念研究",
                    "sections": [{"title": "1. 技术内容", "level": 1, "blocks": [
                        {"type": "figure", "path": item["path"], "figure_id": item["id"], "figure_type": item["figure_type"], "design_status": "V0", "caption": f"图{item['number']} {item['title']}", "alt": item["alt"], "main_message": item["main_message"], "claim_limit": item["claim_limit"]}
                        for item in reversed_figures
                    ]}],
                    "sources": [{"id": "SRC-001", "title": "通用来源", "url": "https://example.com/source", "claim": "支持候选子功能"}],
                }, ensure_ascii=False), encoding="utf-8")
        report_docx = root / "02-report.docx"
        build = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "build_report.py"), "--input", str(report_source), "--output", str(report_docx)],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        assert build.returncode == 0, build.stderr
        order_manifest = json.loads(json.dumps(manifest))
        order_manifest["capabilities"]["docx"] = {"status": "available", "evidence": "已生成并打开 DOCX"}
        order_manifest["artifacts"][1] = {"role": "main-report", "path": "02-report.docx", "required": True, "opened": True, "rendered": False}
        order_manifest["report_figure_order"]["ordered_numbers"] = [item["number"] for item in figures]
        for item in order_manifest["figures"]:
            item["embedded_in"] = ["main-report"]
        result = validate(root, order_manifest, strict=True)
        tests += 1
        assert result["status"] == "FAIL" and any("actual body figure order" in message for message in result["errors"]), result["errors"]

        def inconsistent_benefit(m, r):
            r["models_and_tests"]["benefit_scenarios"] = [{"id": "BEN-01", "formula_type": "linear_difference_rate", "inputs": {"baseline": 10, "candidate": 5, "quantity": 2, "unit_rate": 3}, "expected_result": 30, "unit": "元", "outputs": [{"artifact": "summary", "value": 30, "unit": "元"}, {"artifact": "report", "value": 31, "unit": "元"}]}]
            m["expected_counts"]["benefit_scenarios"] = 1
        expect_fail(inconsistent_benefit, "output value/unit differs")
        def insufficient_range(m, r):
            r["models_and_tests"]["tests"] = [{"id": "T-01", "claim_scope": "full_range", "target_range": {"min": 1, "max": 60}, "tested_range": {"min": 1, "max": 10}}]
        expect_fail(insufficient_range, "does not cover the claimed full range")
        def false_absence_level(m, r):
            r["absence_assessments"] = [{"id": "N-01", "level": "N2", "databases": ["db"], "queries": ["q"]}]
        expect_fail(false_absence_level, "N2 lacks")
        assert tests == 15, tests
    print("DELIVERABLE_SELF_TEST_PASS tests=15")


def self_test() -> None:
    _self_test_v12()
    return
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
