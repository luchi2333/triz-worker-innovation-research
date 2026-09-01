#!/usr/bin/env python3
"""Deterministic lookup for the bundled classical 39x39 TRIZ matrix.

用法：
    python scripts/lookup_matrix.py --improve 1 --worsen 28            # 单查（markdown）
    python scripts/lookup_matrix.py --batch "1x28,39x30"               # 批量查询
    python scripts/lookup_matrix.py --search "看不清"                   # 现场说法 → 参数候选
    python scripts/lookup_matrix.py --explain 30                       # 参数定义与易混判据
    python scripts/lookup_matrix.py --list-parameters                  # 39 参数表
    python scripts/lookup_matrix.py --version                          # 版本信息
    python scripts/lookup_matrix.py --self-test                        # 黄金回归自检
    python scripts/lookup_matrix.py --emit-rows [目录]                 # 重新生成行分片
    python scripts/lookup_matrix.py --verify-rows                      # 校验行分片与矩阵一致

退出码：0 成功；2 失败（错误信息格式：问题 | 给定 | 修复建议）。
与 lookup_matrix.mjs 的同名子命令输出保持一致。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "references" / "contradiction-matrix.json"
DEFAULT_GUIDANCE = ROOT / "references" / "parameter-guidance.json"
DEFAULT_ROWS_DIR = ROOT / "references" / "matrix-rows"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")


class UsageError(ValueError):
    """统一格式的用户可见错误：问题 | 给定 | 修复建议。"""


class UnifiedArgumentParser(argparse.ArgumentParser):
    """argparse 层错误同样输出统一格式，与 lookup_matrix.mjs 的错误逐字一致。"""

    def error(self, message: str) -> None:
        raise UsageError(translate_argparse_error(message))


def translate_argparse_error(message: str) -> str:
    match = re.match(r"unrecognized arguments: (.+)", message)
    if match:
        return f"未知参数 | 给定: {match.group(1).strip()} | 修复建议: 运行 --help 查看支持的参数"
    match = re.match(r"argument (--\S+): invalid int value: '(.*)'", message)
    if match:
        return (
            f"参数编号无效 | 给定: {match.group(1)} {match.group(2)} | "
            "修复建议: 使用 1..39 的整数；运行 --list-parameters 查看参数表"
        )
    match = re.match(r"argument (--\S+): invalid choice: '(.*?)'", message)
    if match:
        return (
            f"参数值无效 | 给定: {match.group(1)} {match.group(2)} | "
            "修复建议: --format 只接受 markdown 或 json"
        )
    match = re.match(r"argument (--\S+): expected one argument", message)
    if match:
        return f"缺少参数值 | 给定: {match.group(1)} | 修复建议: 在 {match.group(1)} 后提供一个值"
    return f"命令行参数错误 | 给定: {message} | 修复建议: 运行 --help 查看用法"


def fail(problem: str, given: str, fix: str) -> None:
    raise UsageError(f"{problem} | 给定: {given} | 修复建议: {fix}")


def load_resource(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    validate_resource(data)
    return data


def validate_resource(data: dict[str, Any]) -> None:
    parameters = data.get("parameters")
    principles = data.get("principles")
    matrix = data.get("matrix")
    if not isinstance(parameters, list) or len(parameters) != 39:
        raise ValueError("Expected exactly 39 engineering parameters")
    if not isinstance(principles, list) or len(principles) != 40:
        raise ValueError("Expected exactly 40 inventive principles")
    if not isinstance(matrix, list) or len(matrix) != 39:
        raise ValueError("Expected exactly 39 matrix rows")
    if any(not isinstance(row, list) or len(row) != 39 for row in matrix):
        raise ValueError("Every matrix row must contain 39 columns")
    if [item.get("id") for item in parameters] != list(range(1, 40)):
        raise ValueError("Parameter IDs must be consecutive from 1 through 39")
    if [item.get("id") for item in principles] != list(range(1, 41)):
        raise ValueError("Principle IDs must be consecutive from 1 through 40")

    populated = 0
    for row_index, row in enumerate(matrix):
        for col_index, cell in enumerate(row):
            if row_index == col_index:
                if cell is not None:
                    raise ValueError(f"Diagonal R{row_index + 1}C{col_index + 1} must be null")
                continue
            if not isinstance(cell, list):
                raise ValueError(f"Off-diagonal R{row_index + 1}C{col_index + 1} must be an array")
            if any(not isinstance(item, int) or not 1 <= item <= 40 for item in cell):
                raise ValueError(f"Invalid principle ID at R{row_index + 1}C{col_index + 1}")
            if len(cell) != len(set(cell)):
                raise ValueError(f"Repeated principle ID at R{row_index + 1}C{col_index + 1}")
            if cell:
                populated += 1

    expected_count = data.get("audit", {}).get("populated_cells")
    if populated != expected_count:
        raise ValueError(f"Populated-cell count mismatch: {populated} != {expected_count}")

    payload = json.dumps(matrix, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    actual_hash = hashlib.sha256(payload).hexdigest()
    expected_hash = data.get("audit", {}).get("matrix_payload_sha256")
    if actual_hash != expected_hash:
        raise ValueError(f"Matrix hash mismatch: {actual_hash} != {expected_hash}")


def load_guidance(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        guidance = json.load(stream)
    entries = guidance.get("parameters")
    if not isinstance(entries, list) or len(entries) != 39:
        raise ValueError("parameter-guidance.json must contain exactly 39 entries")
    if [item.get("id") for item in entries] != list(range(1, 40)):
        raise ValueError("Guidance entry IDs must be consecutive from 1 through 39")
    for item in entries:
        if not item.get("field_terms"):
            raise ValueError(f"Guidance entry #{item.get('id')} lacks field_terms")
    return guidance


def read_skill_version() -> str:
    skill = ROOT / "SKILL.md"
    match = re.search(r'version:\s*"([^"]+)"', skill.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("SKILL.md frontmatter version not found")
    return match.group(1)


def lookup(data: dict[str, Any], improve: int, worsen: int) -> dict[str, Any]:
    if not 1 <= improve <= 39 or not 1 <= worsen <= 39:
        fail(
            "参数编号超出范围",
            f"--improve {improve} --worsen {worsen}",
            "使用 1..39 的整数；运行 --list-parameters 查看参数表",
        )

    improve_parameter = data["parameters"][improve - 1]
    worsen_parameter = data["parameters"][worsen - 1]
    cell = data["matrix"][improve - 1][worsen - 1]

    if cell is None:
        status = "physical_contradiction"
        guidance = "同一参数的相反要求不查矩阵对角线；转用时间、空间、条件或系统层级分离。"
        principle_items: list[dict[str, Any]] = []
    elif not cell:
        status = "no_preferred_principle"
        guidance = "经典矩阵该单元没有优选原理；不得编造。复核参数映射，或转用全部 40 原理、物理矛盾、物—场分析。"
        principle_items = []
    else:
        status = "ok"
        guidance = "按单元原顺序用于构思；矩阵不证明方案可行，仍须现场化解释、查新和验证。"
        principle_items = [data["principles"][item_id - 1] for item_id in cell]

    return {
        "status": status,
        "improving_parameter": improve_parameter,
        "worsening_parameter": worsen_parameter,
        "direction": f"R{improve} x C{worsen}",
        "principles": principle_items,
        "guidance_zh": guidance,
        "matrix_version": data["matrix_version"],
    }


def render_markdown(result: dict[str, Any]) -> str:
    improve = result["improving_parameter"]
    worsen = result["worsening_parameter"]
    lines = [
        f"- 欲改善参数：#{improve['id']} {improve['zh']} ({improve['en']})",
        f"- 随之恶化参数：#{worsen['id']} {worsen['zh']} ({worsen['en']})",
        f"- 查表方向：{result['direction']}",
        f"- 状态：{result['status']}",
    ]
    if result["principles"]:
        joined = "；".join(
            f"#{item['id']} {item['zh']} ({item['en']})" for item in result["principles"]
        )
        lines.append(f"- 推荐发明原理：{joined}")
    else:
        lines.append("- 推荐发明原理：无")
    lines.append(f"- 使用提示：{result['guidance_zh']}")
    return "\n".join(lines)


def render_parameters(data: dict[str, Any]) -> str:
    lines = ["| 编号 | 中文参数 | English parameter |", "|---:|---|---|"]
    lines.extend(f"| {item['id']} | {item['zh']} | {item['en']} |" for item in data["parameters"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 参数指导：--search / --explain
# ---------------------------------------------------------------------------

def search_parameters(guidance: dict[str, Any], query: str) -> str:
    query_lower = query.strip().lower()
    rows: list[str] = []
    for entry in guidance["parameters"]:
        hit = None
        for term in entry["field_terms"]:
            if query_lower in term.lower():
                hit = f"现场说法：{term}"
                break
        if hit is None and query_lower in entry["zh"].lower():
            hit = "参数名（中文）"
        if hit is None and query_lower in entry["en"].lower():
            hit = "参数名（英文）"
        if hit is None and query_lower in entry["definition_zh"].lower():
            hit = "定义"
        if hit is not None:
            rows.append(f"| {entry['id']} | {entry['zh']} ({entry['en']}) | {hit} |")
    if not rows:
        return (
            f"没有找到匹配“{query}”的参数候选。\n"
            "可换一个现场说法重试，或运行 --list-parameters 查看全部 39 个参数。"
        )
    return "\n".join(
        [
            f"参数映射候选（只是候选，不能自动替代工程判断）：搜索词“{query}”",
            "| 编号 | 参数 | 命中 |",
            "|---:|---|---|",
            *rows,
            "提示：候选之间易混时，运行 --explain <编号> 查看定义和区分判据。",
        ]
    )


def explain_parameter(guidance: dict[str, Any], parameter_id: int) -> str:
    if not 1 <= parameter_id <= 39:
        fail(
            "参数编号超出范围",
            f"--explain {parameter_id}",
            "使用 1..39 的整数；运行 --list-parameters 查看参数表",
        )
    entry = guidance["parameters"][parameter_id - 1]
    lines = [
        f"参数 #{entry['id']}：{entry['zh']} ({entry['en']})",
        f"- 定义：{entry['definition_zh']}",
        f"- 现场常见说法：{'、'.join(entry['field_terms'])}",
        f"- 可测量：{entry['measurable_zh']}",
        "- 易混参数：",
    ]
    for item in entry.get("confusable", []):
        lines.append(f"  - #{item['id']} {guidance['parameters'][item['id'] - 1]['zh']}：{item['how']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 行分片：--emit-rows / --verify-rows
# ---------------------------------------------------------------------------

def render_row_shard(data: dict[str, Any], row: int) -> str:
    row_parameter = data["parameters"][row - 1]
    lines = [
        f"# 矩阵行分片 R{row:02d}（行 = 欲改善参数）",
        "",
        f"- 矩阵版本：{data['matrix_version']}",
        f"- 行参数：#{row_parameter['id']} {row_parameter['zh']} ({row_parameter['en']})",
        f"- 矩阵载荷 SHA-256：{data['audit']['matrix_payload_sha256']}",
        "- 本文件由 contradiction-matrix.json 自动生成，禁止手改；矩阵更新后必须重新生成全部 39 个行分片。",
        "",
        "用法：改善参数为该行时读本文件，定位“恶化参数”所在列，按原顺序取原理编号。",
        "`null` 表示对角线（同一参数，转物理矛盾）；`空` 表示经典矩阵该单元无优选原理，不得补造。",
        "",
        "| 恶化参数 | 推荐原理（原顺序） |",
        "|---|---|",
    ]
    for col in range(1, 40):
        col_parameter = data["parameters"][col - 1]
        cell = data["matrix"][row - 1][col - 1]
        if cell is None:
            value = "null（对角线：转物理矛盾）"
        elif not cell:
            value = "空（无优选原理）"
        else:
            names = "；".join(f"#{pid} {data['principles'][pid - 1]['zh']}" for pid in cell)
            value = f"{','.join(str(pid) for pid in cell)}（{names}）"
        lines.append(f"| C{col} #{col_parameter['id']} {col_parameter['zh']} | {value} |")
    lines.append("")
    return "\n".join(lines)


def emit_rows(data: dict[str, Any], directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    for row in range(1, 40):
        (directory / f"R{row:02d}.md").write_text(
            render_row_shard(data, row), encoding="utf-8", newline="\n"
        )
    print(f"ROWS_EMIT_PASS files=39 directory={directory.as_posix()}")
    return 0


def verify_rows(data: dict[str, Any], directory: Path) -> int:
    problems: list[str] = []
    found = sorted(path.name for path in directory.glob("R*.md")) if directory.is_dir() else []
    expected = [f"R{row:02d}.md" for row in range(1, 40)]
    if found != expected:
        problems.append(f"row-shard file set mismatch: {found} != {expected}")
    for row in range(1, 40):
        path = directory / f"R{row:02d}.md"
        if not path.is_file():
            continue
        actual = path.read_text(encoding="utf-8")
        expected_text = render_row_shard(data, row)
        if actual != expected_text:
            problems.append(f"row shard drift: {path.name} does not match matrix JSON")
    if problems:
        for problem in problems:
            print(f"ERROR: 行分片校验失败 | 给定: {problem} | 修复建议: 运行 --emit-rows 重新生成", file=sys.stderr)
        return 2
    print(
        f"ROWS_VERIFY_PASS files=39 matrix_sha256={data['audit']['matrix_payload_sha256']}"
    )
    return 0


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

def self_test(data: dict[str, Any]) -> None:
    known: dict[tuple[int, int], list[int]] = {
        (1, 28): [28, 27, 35, 26],
        (7, 28): [25, 26, 28],
        (15, 25): [20, 10, 28, 18],
        (15, 31): [21, 39, 16, 22],
        (18, 35): [15, 1, 19],
        (19, 9): [8, 35],
        (1, 38): [26, 35, 18, 19],
        (8, 25): [35, 16, 32, 18],
        (33, 10): [28, 13, 35],
        (34, 1): [2, 27, 35, 11],
        (1, 39): [35, 3, 24, 37],
        (39, 1): [35, 26, 24, 37],
        (39, 30): [22, 35, 13, 24],
        (39, 31): [35, 22, 18, 39],
        (25, 27): [10, 30, 4],
        (35, 36): [15, 29, 37, 28],
    }
    for (improve, worsen), expected in known.items():
        actual = [item["id"] for item in lookup(data, improve, worsen)["principles"]]
        if actual != expected:
            raise AssertionError(f"R{improve}C{worsen}: {actual} != {expected}")
    if data["parameters"][29]["zh"] != "作用于物体的有害因素":
        raise AssertionError("Parameter #30 translation drifted")
    if data["parameters"][30]["zh"] != "物体产生的有害因素":
        raise AssertionError("Parameter #31 translation drifted")
    if lookup(data, 30, 30)["status"] != "physical_contradiction":
        raise AssertionError("Diagonal lookup must route to physical contradiction")
    if lookup(data, 1, 2)["status"] != "no_preferred_principle":
        raise AssertionError("Empty cell must report no_preferred_principle")
    if lookup(data, 1, 39)["principles"] == lookup(data, 39, 1)["principles"]:
        raise AssertionError("Directional lookup regression")
    guidance = load_guidance(DEFAULT_GUIDANCE)
    if guidance["matrix_version"] != data["matrix_version"]:
        raise AssertionError("Guidance matrix_version drifted from matrix")
    print(
        "SELF_TEST_PASS "
        f"parameters=39 principles=40 rows=39 columns=39 "
        f"populated={data['audit']['populated_cells']} "
        f"golden_cells={len(known)} "
        f"matrix_sha256={data['audit']['matrix_payload_sha256']}"
    )


# ---------------------------------------------------------------------------
# 批量查询
# ---------------------------------------------------------------------------

BATCH_SPLIT = re.compile(r"[,，;；\s]+")
PAIR_PATTERN = re.compile(r"^(\d+)[xX×:：](\d+)$")


def parse_batch(spec: str) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for token in BATCH_SPLIT.split(spec.strip()):
        if not token:
            continue
        match = PAIR_PATTERN.match(token)
        if not match:
            fail(
                "批量查询格式无效",
                f"“{token}”",
                '每对写成 改善x恶化 并用逗号分隔，如 --batch "1x28,39x30"',
            )
        pairs.append((int(match.group(1)), int(match.group(2))))
    if not pairs:
        fail("批量查询为空", f"“{spec}”", '至少一对，如 --batch "1x28"')
    return pairs


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main() -> int:
    parser = UnifiedArgumentParser(
        description="Look up the bundled classical Altshuller contradiction matrix."
    )
    parser.add_argument("--improve", type=int, help="Improving-parameter ID, 1..39")
    parser.add_argument("--worsen", type=int, help="Worsening-parameter ID, 1..39")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--list-parameters", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="store_true", help="Print skill/matrix/guidance versions")
    parser.add_argument("--search", metavar="TEXT", help="Field term -> parameter candidates")
    parser.add_argument("--explain", type=int, metavar="ID", help="Parameter definition and confusables")
    parser.add_argument("--batch", metavar="SPEC", help='Batch lookup, e.g. "1x28,39x30"')
    parser.add_argument("--emit-rows", nargs="?", const=DEFAULT_ROWS_DIR, type=Path, metavar="DIR")
    parser.add_argument("--verify-rows", action="store_true")
    try:
        args = parser.parse_args()

        if args.version:
            guidance = load_guidance(DEFAULT_GUIDANCE)
            data = load_resource(args.data)
            print(
                f"lookup-matrix skill={read_skill_version()} "
                f"matrix={data['matrix_version']} guidance={guidance['guidance_version']}"
            )
            return 0

        if args.search is not None:
            query = args.search.strip()
            if not query:
                fail("搜索词为空", '--search ""', "提供一个现场说法，如 --search \"看不清\"")
            guidance = load_guidance(DEFAULT_GUIDANCE)
            print(search_parameters(guidance, query))
            return 0

        if args.explain is not None:
            guidance = load_guidance(DEFAULT_GUIDANCE)
            print(explain_parameter(guidance, args.explain))
            return 0

        data = load_resource(args.data)

        if args.self_test:
            self_test(data)
            return 0
        if args.list_parameters:
            print(render_parameters(data))
            return 0
        if args.emit_rows is not None:
            return emit_rows(data, args.emit_rows)
        if args.verify_rows:
            return verify_rows(data, DEFAULT_ROWS_DIR)
        if args.batch is not None:
            pairs = parse_batch(args.batch)
            results = [lookup(data, improve, worsen) for improve, worsen in pairs]
            if args.format == "json":
                print(json.dumps(results, ensure_ascii=False, indent=2))
            else:
                blocks = [f"## 批量查询：{len(results)} 对"]
                for result in results:
                    blocks.append(f"### {result['direction']}")
                    blocks.append(render_markdown(result))
                print("\n\n".join(blocks))
            return 0
        if args.improve is None or args.worsen is None:
            fail(
                "缺少查询参数",
                "无 --improve/--worsen",
                "使用 --improve N --worsen N，或 --batch/--search/--explain/--list-parameters/--self-test",
            )
        result = lookup(data, args.improve, args.worsen)
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_markdown(result))
        return 0
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
