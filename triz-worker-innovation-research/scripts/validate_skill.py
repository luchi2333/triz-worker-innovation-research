#!/usr/bin/env python3
"""Self-contained structural and content validation for this Skill package.

用法：
    python scripts/validate_skill.py            常规校验（输出 JSON 报告）
    python scripts/validate_skill.py --strict   缺失运行时也判失败，用于发布门禁

退出码：0 通过；2 失败。

设计约束：
- 版本号从 SKILL.md frontmatter 读取，不在本文件里硬编码，避免版本升级被校验器拦住。
- 矩阵自检一律走子进程，不在包内 import，避免生成 `scripts/__pycache__`。
- 包内文件必须全部列入发布清单，未列入的文件（尤其内部案例文件）直接判失败。
- 内部案例词扫描让"具体项目内容回灌公开包"这类倒退被自动拦截。
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# 发布清单：必须存在
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

# 发布清单：允许存在但不强制
OPTIONAL = [
    "CHANGELOG.md",
]

# 禁止出现在包内的目录（构建产物 / 版本控制元数据）
FORBIDDEN_DIRS = {
    "__pycache__",
    ".git",
    ".github",
    ".venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

# 禁止出现在包内的文件后缀
FORBIDDEN_SUFFIXES = {".pyc", ".pyo", ".zip", ".tar", ".gz", ".bak", ".orig", ".tmp"}

TEXT_SUFFIXES = {".md", ".py", ".mjs", ".json", ".yaml"}

# 内部案例词扫描：命中即判失败，防止具体项目内容回灌公开包
CASE_SCAN_SKIP = {"scripts/validate_skill.py"}  # 本文件容纳词表，必须跳过
CASE_LEAK_PATTERNS: list[tuple[str, str]] = [
    (r"电缆", "具体项目对象（电缆）"),
    (r"接地尾段", "具体项目结构（接地尾段）"),
    (r"开剥", "具体项目工序（开剥）"),
    (r"线芯|铜网|护套", "具体项目结构（线芯/铜网/护套）"),
    (r"屏蔽形式|导电/屏蔽", "具体项目结构（屏蔽形式）"),
    (r"每端|min/端", "具体项目口径（每端）"),
    (r"case-example|案例格式示例", "内部案例文件引用"),
]

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")

SELF_TEST_TIMEOUT_SECONDS = 120


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def read_utf8(path: Path, errors: list[str]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        fail(errors, f"UTF-8 read failed: {path.relative_to(ROOT)}: {exc}")
        return ""


def check_manifest(errors: list[str], warnings: list[str]) -> list[str]:
    """校验包内文件清单：缺文件、多余文件、构建产物一律拦下。"""
    allowed = set(REQUIRED) | set(OPTIONAL)
    unexpected: list[str] = []

    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        parts = set(path.relative_to(ROOT).parts[:-1])
        if parts & FORBIDDEN_DIRS:
            fail(errors, f"Build artifact or VCS metadata inside package: {rel}")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            fail(errors, f"Forbidden file type inside package: {rel}")
            continue
        if rel not in allowed:
            unexpected.append(rel)

    for rel in unexpected:
        fail(errors, f"File not in release manifest: {rel}")

    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(errors, f"Missing required file: {rel}")

    for rel in OPTIONAL:
        if not (ROOT / rel).is_file():
            warnings.append(f"Optional file absent: {rel}")

    return unexpected


def check_frontmatter(text: str, errors: list[str]) -> str | None:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
    if not match:
        fail(errors, "SKILL.md lacks YAML frontmatter")
        return None
    frontmatter = match.group(1)
    if not re.search(r"^name:\s*triz-worker-innovation-research\s*$", frontmatter, flags=re.MULTILINE):
        fail(errors, "SKILL.md name is missing or incorrect")
    description = re.search(r"^description:\s*(.+)$", frontmatter, flags=re.MULTILINE)
    if not description or len(description.group(1).strip(" \"'")) < 80:
        fail(errors, "SKILL.md description is missing or not discriminating")

    # 允许缩进：`version:` 位于 frontmatter 的 `metadata:` 之下
    version_match = re.search(r'^[ \t]*version:[ \t]*"([^"]+)"', frontmatter, flags=re.MULTILINE)
    if not version_match:
        fail(errors, "SKILL.md metadata.version is missing or not quoted")
        return None
    version = version_match.group(1)
    if not SEMVER.match(version):
        fail(errors, f"SKILL.md metadata.version is not semver: {version}")
        return None
    if not re.search(r"^[ \t]*last_updated:[ \t]*\S", frontmatter, flags=re.MULTILINE):
        fail(errors, "SKILL.md metadata.last_updated is missing")
    return version


def check_changelog(version: str | None, files: dict[str, str], errors: list[str]) -> None:
    changelog = files.get("CHANGELOG.md")
    if changelog is None or version is None:
        return
    head = re.search(r"^##\s*\[?v?(\d+\.\d+\.\d+[^\]\s]*)\]?", changelog, flags=re.MULTILINE)
    if not head:
        fail(errors, "CHANGELOG.md has no version heading")
        return
    if head.group(1) != version:
        fail(errors, f"CHANGELOG.md top entry {head.group(1)} != SKILL.md version {version}")


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
        "G1.5",
        "沉默",
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
        "G2 深度研究",
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

    workflow = files.get("references/research-workflow.md", "")
    for required_phrase in [
        "G1.5",
        "唯一编号体系",
        "验证成熟度",
    ]:
        if required_phrase not in workflow:
            fail(errors, f"Research workflow missing: {required_phrase}")
    if re.search(r"\|\s*G[678]\s*\|", workflow):
        fail(errors, "Research workflow still uses retired G6/G7/G8 gates")

    audit = files.get("references/matrix-audit.md", "")
    if "golden_cells" not in audit:
        fail(errors, "Matrix audit missing golden_cells regression description")


def check_placeholders(files: dict[str, str], errors: list[str]) -> None:
    patterns = [r"\bTODO\b", r"\bTBD\b", r"\[PLACEHOLDER\]"]
    for rel, text in files.items():
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                fail(errors, f"Unfinished placeholder in {rel}: {pattern}")


def check_case_leaks(files: dict[str, str], errors: list[str]) -> int:
    hits = 0
    for rel, text in files.items():
        if rel in CASE_SCAN_SKIP:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, reason in CASE_LEAK_PATTERNS:
                if re.search(pattern, line):
                    fail(errors, f"Case-specific content leaked into public package: {rel}:{lineno} ({reason})")
                    hits += 1
    return hits


def run_self_test(
    command: list[str],
    label: str,
    errors: list[str],
    warnings: list[str],
    strict: bool,
) -> dict[str, object]:
    """以子进程运行自检；不使用 importlib，避免生成 `__pycache__`。"""
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=SELF_TEST_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        message = f"{label} runtime not found: {command[0]}"
        if strict:
            fail(errors, message)
        else:
            warnings.append(message + "（加 --strict 可使缺失运行时判失败）")
        return {"runtime": command[0], "status": "SKIPPED"}
    except subprocess.TimeoutExpired:
        fail(errors, f"{label} self-test timed out after {SELF_TEST_TIMEOUT_SECONDS}s")
        return {"runtime": command[0], "status": "TIMEOUT"}

    stdout = proc.stdout.strip()
    if proc.returncode != 0:
        fail(errors, f"{label} self-test exit {proc.returncode}: {stdout or proc.stderr.strip()}")
    elif "SELF_TEST_PASS" not in stdout:
        fail(errors, f"{label} self-test did not print SELF_TEST_PASS: {stdout!r}")
    return {
        "runtime": command[0],
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "stdout": stdout,
    }


def check_dual_runtime(errors: list[str], warnings: list[str], strict: bool) -> dict[str, object]:
    python_result = run_self_test(
        [sys.executable, "scripts/lookup_matrix.py", "--self-test"],
        "Python",
        errors,
        warnings,
        strict,
    )
    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        if strict:
            fail(errors, "Node runtime not found (--strict)")
        else:
            warnings.append("Node runtime not found（加 --strict 可使缺失运行时判失败）")
        node_result: dict[str, object] = {"runtime": "node", "status": "SKIPPED"}
    else:
        node_result = run_self_test(
            [node, "scripts/lookup_matrix.mjs", "--self-test"],
            "Node",
            errors,
            warnings,
            strict,
        )

    identical = False
    if python_result.get("status") == "PASS" and node_result.get("status") == "PASS":
        identical = python_result.get("stdout") == node_result.get("stdout")
        if not identical:
            fail(
                errors,
                "Python/Node SELF_TEST_PASS output drift: "
                f"python={python_result.get('stdout')!r} node={node_result.get('stdout')!r}",
            )

    return {
        "python": python_result,
        "node": node_result,
        "outputs_identical": identical,
    }


def load_matrix(errors: list[str]) -> dict | None:
    path = ROOT / "references" / "contradiction-matrix.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(errors, f"Cannot load contradiction-matrix.json: {exc}")
        return None


def main(argv: list[str]) -> int:
    strict = "--strict" in argv
    if "--help" in argv or "-h" in argv:
        print(__doc__.strip())
        return 0

    errors: list[str] = []
    warnings: list[str] = []

    check_manifest(errors, warnings)

    files: dict[str, str] = {}
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            rel = path.relative_to(ROOT).as_posix()
            files[rel] = read_utf8(path, errors)
            if path.suffix.lower() == ".md":
                check_links(path, files[rel], errors)

    version = check_frontmatter(files.get("SKILL.md", ""), errors)
    check_changelog(version, files, errors)
    check_required_content(files, errors)
    check_placeholders(files, errors)
    case_leak_hits = check_case_leaks(files, errors)
    runtimes = check_dual_runtime(errors, warnings, strict)
    data = load_matrix(errors)

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
        "version": version,
        "strict": strict,
        "files": len(inventory),
        "manifest": {
            "required": len(REQUIRED),
            "optional": len(OPTIONAL),
            "unexpected": sorted(
                set(path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file())
                - set(REQUIRED)
                - set(OPTIONAL)
            ),
        },
        "matrix": {
            "parameters": len(data["parameters"]) if data else None,
            "principles": len(data["principles"]) if data else None,
            "rows": len(data["matrix"]) if data else None,
            "populated_cells": data.get("audit", {}).get("populated_cells") if data else None,
            "sha256": data.get("audit", {}).get("matrix_payload_sha256") if data else None,
        },
        "runtimes": runtimes,
        "case_leak_hits": case_leak_hits,
        "warnings": warnings,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
