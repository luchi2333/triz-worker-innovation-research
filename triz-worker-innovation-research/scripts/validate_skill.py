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
- 内容合规只保留通用规则（内部案例引用、本机绝对路径）；具体项目的案例词扫描
  属于项目工作区的私有发布前 QA，不进入公开包。
- 跨文件一致性：禁止第二套验证成熟度定义（全包只允许一套 V0—V3），禁止"只允许脚本"
  类措辞，检查清单文件必须显式给出 Python/Node/行分片三选一路径。
- 双运行时表驱动回归：成功与失败路径的 stdout、stderr、退出码必须逐字一致。
- README 首页示例（仓库根）必须与矩阵本体复算结果一致。
- G5 成果校验器与纯标准库 DOCX 生成器必须各自通过正向/负向自检。
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
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")


# 发布清单：必须存在
REQUIRED = [
    "SKILL.md",
    "agents/openai.yaml",
    "scripts/lookup_matrix.py",
    "scripts/lookup_matrix.mjs",
    "scripts/build_report.py",
    "scripts/validate_deliverables.py",
    "scripts/validate_skill.py",
    "assets/deliverables-manifest-template.json",
    "assets/report-source-template.json",
    "assets/figure-template.svg",
    "references/contradiction-matrix.json",
    "references/parameter-guidance.json",
    "references/matrix-usage.md",
    "references/matrix-audit.md",
    "references/intake-guide.md",
    "references/inventive-principles.md",
    "references/triz-extended-tools.md",
    "references/research-workflow.md",
    "references/triz-analysis-output.md",
    "references/deep-research-protocol.md",
    "references/engineering-claim-safety-checks.md",
    "references/output-templates.md",
    "references/final-report-blueprint.md",
    "references/engineering-figure-planning.md",
    "references/delivery-contract.md",
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

TEXT_SUFFIXES = {".md", ".py", ".mjs", ".json", ".yaml", ".svg"}

# 通用内容合规扫描（不含任何具体项目案例词）。
# 具体项目的案例特征词扫描属于项目工作区的私有发布前 QA，不进入公开包。
# 注意：模式串用拼接写法，避免本文件自身命中扫描（不再设跳过名单）。
GENERIC_LEAK_PATTERNS: list[tuple[str, str]] = [
    ("case" + "-example" + r"|案例格式" + "示例", "内部案例文件引用"),
    (r"[A-Za-z]:[\\/]+Users[\\/]", "本机绝对路径（Windows 用户目录）"),
    (r"/Users/[A-Za-z0-9._-]+/|/home/[A-Za-z0-9._-]+/", "本机绝对路径（Unix 用户目录）"),
]

# 禁止出现第二套验证成熟度定义：全包只允许一套 V0—V3（见 research-workflow.md）
FORBIDDEN_MATURITY_PATTERNS: list[tuple[str, str]] = [
    (r"\bV" + r"4\b", "出现第四级成熟度编号（全包只允许一套 V0—V3）"),
    ("V0[—–-]V" + "4", "出现四级成熟度区间表述"),
]

# 禁止“只允许脚本”措辞：确定性查询必须三选一（Python/Node/行分片）
FORBIDDEN_SCRIPT_ONLY_PATTERNS: list[tuple[str, str]] = [
    ("是否由" + "脚本执行", "检查清单只允许脚本执行"),
    ("单独执行" + "脚本", "检查清单只允许脚本执行"),
    ("脚本" + "查表", "通过条件限定脚本路径"),
    ("脚本或" + " JSON 人工读取", "未包含行分片路径"),
]

# 这些文件必须显式包含“三选一”确定性查询路径
TRI_PATH_REQUIRED_FILES = [
    "references/triz-analysis-output.md",
    "references/weak-model-playbook.md",
    "references/matrix-usage.md",
    "references/research-workflow.md",
    "references/standalone-capability-map.md",
]

# 矩阵行分片：references/matrix-rows/R01.md .. R39.md（生成产物，单独校验）
ROW_SHARD_PATTERN = re.compile(r"^references/matrix-rows/R(0[1-9]|[12][0-9]|3[0-9])\.md$")

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
        if rel not in allowed and not ROW_SHARD_PATTERN.match(rel):
            unexpected.append(rel)

    for rel in unexpected:
        fail(errors, f"File not in release manifest: {rel}")

    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            fail(errors, f"Missing required file: {rel}")

    for row in range(1, 40):
        shard = f"references/matrix-rows/R{row:02d}.md"
        if not (ROOT / shard).is_file():
            fail(errors, f"Missing matrix row shard: {shard}")

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
        "交付层级",
        "intake-guide.md",
        "沉默不算确认",
        "交付必须落地",
        "validate_deliverables.py",
        "build_report.py",
        "engineering-figure-planning.md",
        "Figure Plan",
        "核心原理图",
        "运动序列图",
        "安全边界图",
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
        "必要图示硬门槛",
        "deliverables-manifest.json",
        "替代文本",
        "Figure Plan",
        "F4 机理剖面",
        "F5 运动序列",
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
        "阶段播报",
        "暂停与恢复",
        "现场否决回灌",
        "能力探测",
        "成果校验器",
        "十种常见绘图失败",
        "首次阅读者",
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
        "物理属性与检测方法匹配",
        "实际证据成熟度",
    ]:
        if required_phrase not in gates:
            fail(errors, f"Engineering gate reference missing: {required_phrase}")

    workflow = files.get("references/research-workflow.md", "")
    for required_phrase in [
        "G1.5",
        "唯一编号体系",
        "验证成熟度",
        "白话确认卡",
        "intake-guide.md",
    ]:
        if required_phrase not in workflow:
            fail(errors, f"Research workflow missing: {required_phrase}")
    if re.search(r"\|\s*G[678]\s*\|", workflow):
        fail(errors, "Research workflow still uses retired G6/G7/G8 gates")

    delivery = files.get("references/delivery-contract.md", "")
    for required_phrase in [
        "先探测能力",
        "标准交付的强制成果",
        "必要图示硬门槛",
        "deliverables-manifest.json",
        "validate_deliverables.py",
        "build_report.py",
        "G5 交付回执",
        "不得把插图和 Word 留作",
        "Figure Plan",
        "架构图",
    ]:
        if required_phrase not in delivery:
            fail(errors, f"Delivery contract missing: {required_phrase}")

    audit = files.get("references/matrix-audit.md", "")
    if "golden_cells" not in audit:
        fail(errors, "Matrix audit missing golden_cells regression description")
    if "行分片" not in audit:
        fail(errors, "Matrix audit missing row-shard note")

    usage = files.get("references/matrix-usage.md", "")
    for required_phrase in [
        "--search",
        "--explain",
        "--batch",
        "--version",
        "行分片",
        "映射候选",
    ]:
        if required_phrase not in usage:
            fail(errors, f"Matrix usage missing: {required_phrase}")

    analysis = files.get("references/triz-analysis-output.md", "")
    for required_phrase in [
        "白话确认卡",
        "回复选项",
        "你看着办",
    ]:
        if required_phrase not in analysis:
            fail(errors, f"TRIZ analysis output missing: {required_phrase}")

    templates = files.get("references/output-templates.md", "")
    for required_phrase in [
        "一页纸成果速览",
        "会话检查点",
        "暂停点",
        "Figure Plan 表",
        "核心原理图描述卡",
    ]:
        if required_phrase not in templates:
            fail(errors, f"Output templates missing: {required_phrase}")

    figure_planning = files.get("references/engineering-figure-planning.md", "")
    for required_phrase in [
        "九类工程图",
        "F1-object-structure",
        "F4-mechanism-section",
        "F5-motion-sequence",
        "F7-safety-boundary",
        "decision_question",
        "main_message",
        "SVG",
        "PNG",
        "Figure Review",
        "3～6 帧",
        "架构图不能代替",
    ]:
        if required_phrase not in figure_planning:
            fail(errors, f"Engineering figure planning missing: {required_phrase}")

    try:
        manifest_template = json.loads(files.get("assets/deliverables-manifest-template.json", "{}"))
    except json.JSONDecodeError as exc:
        fail(errors, f"Deliverables manifest template is invalid JSON: {exc}")
        manifest_template = {}
    if manifest_template.get("schema_version") != "1.1":
        fail(errors, "Deliverables manifest template must use schema_version 1.1")
    for key in ["primary_routes", "concept_profile", "figure_plan_frozen", "figure_review"]:
        if key not in manifest_template:
            fail(errors, f"Deliverables manifest template missing: {key}")
    manifest_checks = manifest_template.get("checks", {})
    for key in ["figure_contract", "caption_numbering"]:
        if key not in manifest_checks:
            fail(errors, f"Deliverables manifest template checks missing: {key}")

    try:
        report_template = json.loads(files.get("assets/report-source-template.json", "{}"))
    except json.JSONDecodeError as exc:
        fail(errors, f"Report source template is invalid JSON: {exc}")
        report_template = {}
    if report_template.get("schema_version") != "1.1":
        fail(errors, "Report source template must use schema_version 1.1")
    figure_blocks = [
        block
        for section in report_template.get("sections", [])
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") == "figure"
    ]
    if not figure_blocks:
        fail(errors, "Report source template must include an engineering figure block")
    else:
        for key in ["figure_id", "figure_type", "design_status", "main_message", "claim_limit"]:
            if key not in figure_blocks[0]:
                fail(errors, f"Report source template figure missing: {key}")

    intake = files.get("references/intake-guide.md", "")
    for required_phrase in [
        "先抽取",
        "代理证据模式",
    ]:
        if required_phrase not in intake:
            fail(errors, f"Intake guide missing: {required_phrase}")


def check_placeholders(files: dict[str, str], errors: list[str]) -> None:
    patterns = [r"\bTODO\b", r"\bTBD\b", r"\[PLACEHOLDER\]"]
    for rel, text in files.items():
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                fail(errors, f"Unfinished placeholder in {rel}: {pattern}")


def check_generic_leaks(files: dict[str, str], errors: list[str]) -> int:
    """通用合规扫描：不含具体项目词表；项目案例词由私有 QA 在工作区执行。"""
    hits = 0
    for rel, text in files.items():
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, reason in GENERIC_LEAK_PATTERNS:
                if re.search(pattern, line):
                    fail(errors, f"Non-generic content in public package: {rel}:{lineno} ({reason})")
                    hits += 1
    return hits


def check_consistency(files: dict[str, str], errors: list[str]) -> None:
    """跨文件语义一致性：唯一成熟度定义、唯一确定性查询路径。"""
    for rel, text in files.items():
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern, reason in FORBIDDEN_MATURITY_PATTERNS:
                if re.search(pattern, line):
                    fail(errors, f"Conflicting maturity definition: {rel}:{lineno} ({reason})")
            for pattern, reason in FORBIDDEN_SCRIPT_ONLY_PATTERNS:
                if re.search(pattern, line):
                    fail(errors, f"Script-only wording: {rel}:{lineno} ({reason})")
    for rel in TRI_PATH_REQUIRED_FILES:
        text = files.get(rel, "")
        if "三选一" not in text:
            fail(errors, f"{rel} does not state the tri-path (Python/Node/行分片) deterministic lookup")


def _check_readme_text(text: str, data: dict | None, errors: list[str]) -> None:
    """对 README 文本执行黄金示例检查；所有问题写入 errors。"""
    # 示例参数名称必须正确：#10 力（强度）、#12 形状；查询方向 10×12
    for phrase in ["#10 力（强度）", "#12 形状", "10×12"]:
        if phrase not in text:
            fail(errors, f"README quickstart example missing or incorrect: {phrase}")

    # 用矩阵本体复算示例单元：R10×C12 必须返回 README 展示的原理序列
    if data is not None:
        cell = data["matrix"][9][11]
        expected = [10, 35, 40, 34]
        if cell != expected:
            fail(errors, f"Matrix R10xC12 drifted from README example: {cell} != {expected}")
        for principle_no in ["#10 预先作用", "#35 参数变化", "#40 复合材料", "#34 抛弃与再生"]:
            if principle_no not in text:
                fail(errors, f"README quickstart example missing principle: {principle_no}")


def check_readme_golden(data: dict | None, errors: list[str], warnings: list[str]) -> dict[str, object]:
    """README 首页示例必须与实际矩阵数据一致（README 位于仓库根，即包外上一级）。"""
    readme_path = ROOT.parent / "README.md"
    result: dict[str, object] = {"path": str(readme_path), "status": "SKIPPED"}
    if not readme_path.is_file():
        warnings.append("Repo README.md not found next to package; README golden test skipped")
        return result

    try:
        text = readme_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        fail(errors, f"UTF-8 read failed: {readme_path.name}: {exc}")
        result["status"] = "FAIL"
        return result

    # 子状态取决于本子检查是否新增错误，不得无条件 PASS
    errors_before = len(errors)
    _check_readme_text(text, data, errors)
    result["status"] = "PASS" if len(errors) == errors_before else "FAIL"
    return result


def check_readme_golden_negative(data: dict | None, errors: list[str]) -> None:
    """负向自检：把 README 示例改错后，黄金检查必须拒绝；否则说明该检查机制失效。"""
    readme_path = ROOT.parent / "README.md"
    if not readme_path.is_file() or data is None:
        return
    try:
        text = readme_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return

    # 正向未通过时，负向自检无意义（总状态已经 FAIL）
    clean: list[str] = []
    _check_readme_text(text, data, clean)
    if clean:
        return

    corrupted = text.replace("#12 形状", "#11 形状", 1)
    if corrupted == text:
        fail(errors, "README golden negative self-check cannot run: marker phrase not found")
        return
    scratch: list[str] = []
    _check_readme_text(corrupted, data, scratch)
    if not scratch:
        fail(errors, "README golden negative self-check broken: corrupted example was not rejected")


def run_self_test(
    command: list[str],
    label: str,
    errors: list[str],
    warnings: list[str],
    strict: bool,
    marker: str = "SELF_TEST_PASS",
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
    elif marker not in stdout:
        fail(errors, f"{label} self-test did not print {marker}: {stdout!r}")
    return {
        "runtime": command[0],
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "stdout": stdout,
    }


def check_row_shards(errors: list[str], warnings: list[str], strict: bool) -> dict[str, object]:
    """子进程运行行分片校验：分片内容必须与矩阵 JSON 完全一致。"""
    result = run_self_test(
        [sys.executable, "scripts/lookup_matrix.py", "--verify-rows"],
        "RowShards",
        errors,
        warnings,
        strict,
        marker="ROWS_VERIFY_PASS",
    )
    if result.get("status") == "PASS" and "ROWS_VERIFY_PASS" not in str(result.get("stdout", "")):
        fail(errors, "Row-shard verification did not print ROWS_VERIFY_PASS")
        result["status"] = "FAIL"
    return result


# 双运行时表驱动回归：成功与失败路径的 stdout、stderr、退出码必须逐字一致。
DUAL_RUNTIME_CASES: list[list[str]] = [
    ["--improve", "10", "--worsen", "12"],
    ["--improve", "10", "--worsen", "12", "--format", "json"],
    ["--improve", "10", "--worsen", "10"],
    ["--improve", "1", "--worsen", "2"],
    ["--batch", "1x28,39x30"],
    ["--batch", "1x28,39x30", "--format", "json"],
    ["--search", "划伤"],
    ["--search", "不存在的词xyz"],
    ["--explain", "30"],
    ["--list-parameters"],
    ["--version"],
    ["--self-test"],
    ["--explain", "abc"],
    ["--format", "xml", "--improve", "1", "--worsen", "2"],
    ["--bogus"],
    ["--improve"],
    ["--improve", "0", "--worsen", "2"],
    ["--batch", "1x"],
]


def run_command(command: list[str], env: dict[str, str] | None = None) -> tuple[int, str, str]:
    import os

    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=SELF_TEST_TIMEOUT_SECONDS,
        env=merged_env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def check_dual_runtime(errors: list[str], warnings: list[str], strict: bool) -> dict[str, object]:
    node = shutil.which("node") or shutil.which("node.exe")
    node_missing = node is None
    if node_missing:
        message = "Node runtime not found"
        if strict:
            fail(errors, message + " (--strict)")
        else:
            warnings.append(message + "（加 --strict 可使缺失运行时判失败）")

    python_result = run_self_test(
        [sys.executable, "scripts/lookup_matrix.py", "--self-test"],
        "Python",
        errors,
        warnings,
        strict,
    )
    if node_missing:
        node_result: dict[str, object] = {"runtime": "node", "status": "SKIPPED"}
    else:
        node_result = run_self_test(
            [node, "scripts/lookup_matrix.mjs", "--self-test"],
            "Node",
            errors,
            warnings,
            strict,
        )

    # 表驱动一致性：逐用例比较 stdout、stderr 和退出码。
    # NODE_OPTIONS=--no-warnings 屏蔽托管运行时自身的实验特性警告，与脚本输出无关。
    parity: list[dict[str, object]] = []
    if node_missing:
        parity_status = "SKIPPED"
    else:
        parity_status = "PASS"
        for case in DUAL_RUNTIME_CASES:
            try:
                py_rc, py_out, py_err = run_command([sys.executable, "scripts/lookup_matrix.py", *case])
                nd_rc, nd_out, nd_err = run_command(
                    [node, "scripts/lookup_matrix.mjs", *case],
                    env={"NODE_OPTIONS": "--no-warnings"},
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                fail(errors, f"Dual-runtime case {case} failed to execute: {exc}")
                parity_status = "FAIL"
                continue
            same = py_rc == nd_rc and py_out == nd_out and py_err == nd_err
            parity.append({"args": case, "rc": py_rc, "identical": same})
            if not same:
                parity_status = "FAIL"
                fail(
                    errors,
                    f"Python/Node output drift on {case}: "
                    f"rc {py_rc}/{nd_rc}; py_out={py_out!r}; nd_out={nd_out!r}; "
                    f"py_err={py_err!r}; nd_err={nd_err!r}",
                )

    identical = (
        python_result.get("status") == "PASS"
        and node_result.get("status") == "PASS"
        and parity_status == "PASS"
    )

    return {
        "python": python_result,
        "node": node_result,
        "parity_cases": len(parity),
        "parity_status": parity_status,
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

    unexpected = check_manifest(errors, warnings)

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
    check_consistency(files, errors)
    leak_hits = check_generic_leaks(files, errors)
    runtimes = check_dual_runtime(errors, warnings, strict)
    row_shards = check_row_shards(errors, warnings, strict)
    report_builder = run_self_test(
        [sys.executable, "scripts/build_report.py", "--self-test"],
        "ReportBuilder",
        errors,
        warnings,
        strict,
        marker="REPORT_SELF_TEST_PASS",
    )
    deliverable_validator = run_self_test(
        [sys.executable, "scripts/validate_deliverables.py", "--self-test"],
        "Deliverables",
        errors,
        warnings,
        strict,
        marker="DELIVERABLE_SELF_TEST_PASS",
    )
    data = load_matrix(errors)
    readme_golden = check_readme_golden(data, errors, warnings)
    check_readme_golden_negative(data, errors)

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

    generated_row_shards = sum(
        1
        for path in ROOT.rglob("*")
        if path.is_file() and ROW_SHARD_PATTERN.match(path.relative_to(ROOT).as_posix())
    )

    report = {
        "skill": ROOT.name,
        "version": version,
        "strict": strict,
        "files": len(inventory),
        "manifest": {
            "required": len(REQUIRED),
            "optional": len(OPTIONAL),
            "generated_row_shards": generated_row_shards,
            "unexpected": unexpected,
        },
        "matrix": {
            "parameters": len(data["parameters"]) if data else None,
            "principles": len(data["principles"]) if data else None,
            "rows": len(data["matrix"]) if data else None,
            "populated_cells": data.get("audit", {}).get("populated_cells") if data else None,
            "sha256": data.get("audit", {}).get("matrix_payload_sha256") if data else None,
        },
        "runtimes": runtimes,
        "row_shards": row_shards,
        "report_builder": report_builder,
        "deliverable_validator": deliverable_validator,
        "readme_golden": readme_golden,
        "generic_leak_hits": leak_hits,
        "warnings": warnings,
        "errors": errors,
        "status": "PASS" if not errors else "FAIL",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
