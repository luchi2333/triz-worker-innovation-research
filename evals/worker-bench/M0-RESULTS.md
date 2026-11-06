# M0 / S01 本轮优化结果

日期：2026-11-06。范围：本轮只运行 S01/C0，按已提交实施计划完善 M0 评估资产；未运行其他病例的模型评估，未修改主 Skill。

## 已完成的工程改动

| 运行暴露的问题 | 本轮实现 | 验证 |
|---|---|---|
| 原始病例同时保存题面与预设回复，README 混有评审标签 | 分离 `cases/`、`private/confirmations.json`、`private/annotations.md`；运行器只封装白名单题面 | 原始 11 个病例的 input/constraints 逐字保持；8 开发/3 通路/4 留出名额不变 |
| C0 容易使用未固定版本，A/B 可能误载 Skill | C0 仅从完整基线提交导出 97 个文件并逐文件绑定 SHA256；记录实际加载清单；A/B 不导出 Skill | 基线篡改可被发现；A/B 误载会被标条件不符并保留原始输出 |
| G1.5 依赖人工反复推动，模拟与真实答复易混 | 有限状态采集；先保存请求再释放回复；授权模拟单独记录 role/mode/授权原话 | 请求前释放、缺授权模拟、预设回复变更均被拒绝 |
| 记录依赖手填、重复覆盖与未知元数据 | prompt/input/output 哈希，原始输出不可覆盖，重试关联，时间与 token 缺失写 unavailable | 文件改写、路径越界、覆盖原尝试均被拒绝；预算超限仍保留输出 |
| 结果身份可能泄漏给评审，或自动给出人工分 | 两套独立随机顺序的匿名材料；映射单独保存；评分表保持空白 | 模拟/不合条件运行不能进入正式评审包；只能显式导出校准包 |

实现文件：`bench.py`、`prepare_review.py`、`test_bench.py`、`protocol.md`、`prompts/`、`splits.json`，以及上述分离后的题面与评审资料。

## S01 输出与通路判断

实际宿主运行的原始方向稿、用户原话“比较限力和改接触面”、有限比较、三条实际检索式、原始返回、计时及工具清单保留在：

`results/S01-C0-20261106T061340Z/`

用户随后授权“由你自行模拟用户的选择，我只要优化的结果”。本轮用已经取得的真实输出回放新采集工具，模拟预设选择“比较限力和改接触面。”，没有伪称第二次独立模型运行、真实现场回复或新实测。

回放结果在 `results/S01-C0-authorized-simulation/`：

- 题面封装 → 方向稿收集 → 授权模拟确认 → 最终输出收集 → 文件校验 → 匿名校准导出：**跑通**。
- `audit.integrity=PASS`、`status=completed_smoke`、`formal_eligible=false`；“采集跑通”和“正式条件合格”分开。
- 完整 C0 的 G2 七轨深研与 G3–G5 完成尚未证实，不能把这次回放计为完整研究链路通过。
- 原真实运行只有部分活动片段合计 360 秒；完整端到端耗时和 token unavailable。回放不重复计入模型成本。
- 原始输出和运行清单仍在本地；`results/.gitignore` 防止将第三方网页返回、宿主工具清单、评审映射等原始材料随代码自动发布。

S01 的技术结论仍是待验证判断：先确认原接触面是否存在“不滑且压痕合格”的力值窗口；有窗口时研究限力，无窗口时优先改接触面；使用两力值×两接触面的试验分离作用。没有实测改善数字，不宣称创新效果、新颖性或现场适用。

## 实际检查结果

```text
python -m unittest discover -s evals/worker-bench -p 'test_*.py' -v
15 tests — OK

python triz-worker-innovation-research/scripts/validate_skill.py --strict
PASS

node triz-worker-innovation-research/scripts/lookup_matrix.mjs --self-test
SELF_TEST_PASS

git diff --check
PASS
```

Skill 目录相对基线 `19e20f4a2b4d2d9e0b46a214fd609146be0a7d7c` 无变更。确定性回归通过与创新效果评价相互独立。

## 本轮结论与未完成项

本轮交付了可执行的 M0 采集、隔离与校验工具，并完成 S01 的确认/采集/匿名导出校准。没有足够跨题证据支持修改主 Skill 提示或增加强制合同，因此按实施计划保留 C0。

完整 M0 仍需其余通路成本校准、独立题目标注、正式模型/工具/预算及协议冻结、两名独立评审安排；这些未完成项不会通过“模拟用户”被自动补成已完成。当前材料可直接用于继续 M0，不代表 M1–M4、A/B 收益或完整 DOCX 交付已经通过。
