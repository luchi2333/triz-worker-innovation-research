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
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


CAPABILITY_STATES = {"available", "unavailable", "not-checked"}
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


def validate(root: Path, manifest: dict, strict: bool = False) -> dict[str, object]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    checked_files: list[str] = []
    docx_results: list[dict[str, int | str]] = []

    if manifest.get("schema_version") != "1.0":
        _fail(errors, "schema_version must be 1.0")
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

    figures = manifest.get("figures")
    if not isinstance(figures, list):
        _fail(errors, "figures must be an array")
        figures = []
    figure_types: set[str] = set()
    figure_ids: set[str] = set()
    route_coverage: set[str] = set()
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
        path = _safe_path(root, item.get("path"), errors, f"figure[{index}]")
        if path is not None:
            checked_files.append(str(path.relative_to(root)))
        if len(str(item.get("alt", "")).strip()) < 8:
            _fail(errors, f"figure alt text missing: {figure_id}")
        if item.get("ledgered") is not True:
            _fail(errors, f"figure not recorded in ledger: {figure_id}")
        embedded = item.get("embedded_in", [])
        if capability_values.get("docx") == "available" and "main-report" not in embedded:
            _fail(errors, f"figure not embedded in main-report: {figure_id}")
        if figure_type == "solution-mechanism":
            route_coverage.update(str(route) for route in item.get("routes", []))

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
        if render.get("blank_pages"):
            _fail(errors, f"blank pages remain: {render.get('blank_pages')}")
        if render.get("unresolved_visual_issues"):
            _fail(errors, f"visual issues remain: {render.get('unresolved_visual_issues')}")

    claim_hits = 0
    for path in dict.fromkeys(public_paths):
        claim_hits += _check_claims(path, errors)

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
        figure_types = sorted(BASE_FIGURE_TYPES)
        figures = []
        for index, figure_type in enumerate(figure_types, start=1):
            path = root / f"figure-{index}.svg"
            path.write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450"><title>{figure_type}</title><rect width="800" height="450" fill="#eef6f8"/></svg>',
                encoding="utf-8",
            )
            figures.append(
                {
                    "id": f"FIG-{index:02d}",
                    "type": figure_type,
                    "path": path.name,
                    "alt": f"{figure_type} 的技术关系示意图",
                    "ledgered": True,
                    "embedded_in": [],
                    "routes": ["R0", "R1"] if figure_type == "solution-mechanism" else [],
                }
            )
        degraded_manifest = {
            "schema_version": "1.0",
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
            "figures": figures,
            "figure_exemptions": [],
            "numeric_benefits": False,
            "research_log": {"path": "03-evidence.md", "claimed_queries": 1, "logged_queries": 1},
            "sources": {"cards": 1, "with_stable_identifier": 1, "critical": 1, "with_url": 0},
            "score_rows": [
                {"route": "R0", "dimension": "安全", "score": 3, "unknown": False, "evidence_id": "S-01", "evidence_maturity": "V1", "anchor_maturity": "V1"},
                {"route": "R1", "dimension": "效率", "score": None, "unknown": True, "evidence_id": "", "evidence_maturity": "V0", "anchor_maturity": "V2"},
            ],
            "checks": {name: "pass" for name in CHECK_NAMES},
            "render_summary": {"pages": 0, "checked_pages": 0, "blank_pages": [], "unresolved_visual_issues": []},
        }
        degraded = validate(root, degraded_manifest, strict=True)
        assert degraded["status"] == "PASS", degraded["errors"]

        report_source = root / "report-source.json"
        report_source.write_text(
            json.dumps(
                {
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
                                        "caption": f"{item['id']} {item['type']}",
                                        "alt": item["alt"],
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
            "blank_pages": [],
            "unresolved_visual_issues": [],
        }
        complete = validate(root, complete_manifest, strict=True)
        assert complete["status"] == "PASS", complete["errors"]

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
