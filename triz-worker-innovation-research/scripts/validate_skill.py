#!/usr/bin/env python3
"""Self-contained structural and content validation for this Skill package."""

from __future__ import annotations

import hashlib
import importlib.util
import contextlib
import io
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


REQUIRED = [
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/lookup_matrix.py",
    "scripts/lookup_matrix.mjs",
    "scripts/validate_skill.py",
    "references/contradiction-matrix.json",
    "references/matrix-usage.md",
    "references/matrix-audit.md",
    "references/inventive-principles.md",
    "references/triz-extended-tools.md",
    "references/research-workflow.md",
    "references/triz-analysis-output.md",
    "references/deep-research-protocol.md",
    "references/engineering-claim-safety-checks.md",
    "references/output-templates.md",
    "references/final-report-blueprint.md",
    "references/weak-model-playbook.md",
    "references/standalone-capability-map.md",
]


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def read_utf8(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        fail(errors, f"UTF-8 read failed: {path.relative_to(ROOT)}: {exc}")
        return ""


def check_frontmatter(text: str, errors: list[str]) -> None:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if not match:
        fail(errors, "SKILL.md lacks YAML frontmatter")
        return
    frontmatter = match.group(1)
    if not re.search(r"^name:\s*triz-worker-innovation-research\s*$", frontmatter, flags=re.MULTILINE):
        fail(errors, "SKILL.md name is missing or incorrect")
    description = re.search(r"^description:\s*(.+)$", frontmatter, flags=re.MULTILINE)
    if not description or len(description.group(1).strip(" \"'")) < 80:
        fail(errors, "SKILL.md description is missing or not discriminating")
    if "version: \"2.1.0\"" not in frontmatter:
        fail(errors, "Expected metadata version 2.1.0")


def check_links(path: Path, text: str, errors: list[str]) -> None:
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = target.strip().split("#", 1)[0]
        if not target or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith("mailto:"):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(ROOT.resolve())
        except ValueError:
            fail(errors, f"Link escapes Skill root: {path.relative_to(ROOT)} -> {target}")
            continue
        if not resolved.exists():
            fail(errors, f"Broken local link: {path.relative_to(ROOT)} -> {target}")


def check_required_content(files: dict[str, str], errors: list[str]) -> None:
    skill = files.get("SKILL.md", "")
    for required_phrase in [
        "用户方向确认",
        "lookup_matrix.mjs",
        "deep-research-protocol.md",
        "final-report-blueprint.md",
        "weak-model-playbook.md",
        "standalone-capability-map.md",
        "engineering-claim-safety-checks.md",
        "不得要求用户另装",
        "不得以相似名称静默纠错",
        "对象自身材料",
    ]:
        if required_phrase not in skill:
            fail(errors, f"SKILL.md missing required contract: {required_phrase}")

    report = files.get("references/final-report-blueprint.md", "")
    for required_phrase in [
        "采用的方法及解决的难点",
        "成熟已有技术",
        "候选创新部分",
        "社会效益",
        "经济效益",
        "逐页",
        "摘要中减少的内容",
        "检索日志未闭合",
        "验证一致性",
    ]:
        if required_phrase not in report:
            fail(errors, f"Final-report blueprint missing: {required_phrase}")

    deep = files.get("references/deep-research-protocol.md", "")
    for required_phrase in [
        "七轨检索",
        "来源身份",
        "WHY/HOW/WHAT",
        "命题级证据矩阵",
        "主张—证据—论证桥",
        "替代解释",
        "现场数据伦理",
        "三次反对者检查",
        "常见失败与恢复",
        "五维质量",
        "类比迁移卡",
    ]:
        if required_phrase not in deep:
            fail(errors, f"Deep-research protocol missing: {required_phrase}")

    weak = files.get("references/weak-model-playbook.md", "")
    for required_phrase in [
        "进度卡",
        "防幻觉",
        "技术矛盾判断树",
        "五角色串行法",
        "两轮最终复核",
        "标识不纠错",
        "七问",
    ]:
        if required_phrase not in weak:
            fail(errors, f"Weak-model playbook missing: {required_phrase}")

    gates = files.get("references/engineering-claim-safety-checks.md", "")
    for required_phrase in [
        "七道硬闸门",
        "对象与标识身份门",
        "来源五维核验",
        "缺失证据阶梯",
        "类比迁移卡",
        "安全屏障真实性检查",
        "专利与法律边界",
        "验证一致性门",
        "上游失败向下游传播",
        "普通模型终稿七问",
        "跨模型回归微测试",
    ]:
        if required_phrase not in gates:
            fail(errors, f"Engineering gate reference missing: {required_phrase}")


def check_placeholders(files: dict[str, str], errors: list[str]) -> None:
    patterns = [r"\bTODO\b", r"\bTBD\b", r"\[PLACEHOLDER\]"]
    for rel, text in files.items():
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                fail(errors, f"Unfinished placeholder in {rel}: {pattern}")


def load_python_lookup(errors: list[str]):
    path = ROOT / "scripts" / "lookup_matrix.py"
    spec = importlib.util.spec_from_file_location("triz_lookup", path)
    if spec is None or spec.loader is None:
        fail(errors, "Cannot import Python matrix lookup")
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
        data = module.load_resource(ROOT / "references" / "contradiction-matrix.json")
        with contextlib.redirect_stdout(io.StringIO()):
            module.self_test(data)
        result = module.lookup(data, 1, 28)
    except Exception as exc:  # noqa: BLE001 - validator must report all failures
        fail(errors, f"Python matrix validation failed: {exc}")
        return None
    actual = [item["id"] for item in result["principles"]]
    if actual != [28, 27, 35, 26]:
        fail(errors, f"R1C28 regression: {actual}")
    return data


def main() -> int:
    errors: list[str] = []
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(errors, f"Missing required file: {rel}")

    files: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".py", ".mjs", ".yaml", ".json"}:
            rel = path.relative_to(ROOT).as_posix()
            files[rel] = read_utf8(path, errors)
            if path.suffix.lower() == ".md":
                check_links(path, files[rel], errors)

    check_frontmatter(files.get("SKILL.md", ""), errors)
    check_required_content(files, errors)
    check_placeholders(files, errors)
    data = load_python_lookup(errors)

    inventory = []
    for path in sorted(ROOT.rglob("*")):
        if path.is_file():
            payload = path.read_bytes()
            inventory.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )

    report = {
        "skill": ROOT.name,
        "version": "2.1.0",
        "files": len(inventory),
        "matrix": {
            "parameters": len(data["parameters"]) if data else None,
            "principles": len(data["principles"]) if data else None,
            "rows": len(data["matrix"]) if data else None,
            "populated_cells": data.get("audit", {}).get("populated_cells") if data else None,
            "sha256": data.get("audit", {}).get("matrix_payload_sha256") if data else None,
        },
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

