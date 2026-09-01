#!/usr/bin/env python3
"""Deterministic lookup for the bundled classical 39x39 TRIZ matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_DATA = Path(__file__).resolve().parent.parent / "references" / "contradiction-matrix.json"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


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


def lookup(data: dict[str, Any], improve: int, worsen: int) -> dict[str, Any]:
    if not 1 <= improve <= 39 or not 1 <= worsen <= 39:
        raise ValueError("Both parameter IDs must be integers from 1 through 39")

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
    print(
        "SELF_TEST_PASS "
        f"parameters=39 principles=40 rows=39 columns=39 "
        f"populated={data['audit']['populated_cells']} "
        f"golden_cells={len(known)} "
        f"matrix_sha256={data['audit']['matrix_payload_sha256']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Look up the bundled classical Altshuller contradiction matrix."
    )
    parser.add_argument("--improve", type=int, help="Improving-parameter ID, 1..39")
    parser.add_argument("--worsen", type=int, help="Worsening-parameter ID, 1..39")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--list-parameters", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        data = load_resource(args.data)
        if args.self_test:
            self_test(data)
            return 0
        if args.list_parameters:
            print(render_parameters(data))
            return 0
        if args.improve is None or args.worsen is None:
            parser.error("--improve and --worsen are required unless --self-test or --list-parameters is used")
        result = lookup(data, args.improve, args.worsen)
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_markdown(result))
        return 0
    except (OSError, ValueError, AssertionError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
