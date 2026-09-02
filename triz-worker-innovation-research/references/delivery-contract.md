# G5 成果生成与交付闸门

本文件用于阻止智能体在只完成 Markdown 草稿、未生成图示、未形成正式文档或未做视觉检查时宣布 G5 完成。它适用于 `standard` 和 `engineering` 交付；`direction` 仅在用户明确只要方向稿时例外。

## 1. 先探测能力，再决定交付路径

进入 G5 后先建立能力表，不能凭感觉写“平台不支持”：

| 能力 | 状态 | 最小探测动作 | 结果证据 |
|---|---|---|---|
| 文件写入 | available / unavailable | 在项目输出目录创建并重新读取一个 UTF-8 小文件 | 路径、读取结果或错误原文 |
| 图示生成 | available / unavailable | 生成一个含中文、箭头和图题的 SVG 或平台原生图形 | 文件路径或工具结果 |
| DOCX 生成 | available / unavailable | 优先探测平台文档工具；否则运行 `scripts/build_report.py --self-test` | 工具结果或自检输出 |
| 打开/渲染 | available / unavailable | 打开或渲染一页测试文档 | 预览、页图路径或错误原文 |

规则：

1. `not-checked` 不等于 unavailable；未探测时不得走降级路径。
2. 能力 available 时必须使用，不得因为 Markdown 已完成而省略图示或 DOCX。
3. 能力 unavailable 时保留错误原文，交付完整 Markdown/CSV/SVG 或 PNG，并把状态写为 `degraded`，不得写 `complete`。
4. 用户明确只要某一种格式时可合并文件，但四类内容角色仍须在交付清单中逐项映射。

## 2. 标准交付的强制成果

`standard` / `engineering` 默认至少包含：

1. `decision-summary`：技术导向决策摘要；
2. `main-report`：最终技术方案报告；
3. `evidence-appendix`：逐条检索日志、来源卡、证据矩阵、评分、FMEA 和验证协议；
4. `source-figure-ledger`：来源与图示台账；
5. `deliverables-manifest.json`：机器可检查的交付清单。

若文档能力 available，`main-report` 必须包含 DOCX；源 Markdown 同时保留，便于复核与后续修改。不得等用户再次提出“做成 Word”。

## 3. 必要图示硬门槛

除非某图确实不适用并在 manifest 的 `figure_exemptions` 中给出技术理由，至少生成：

- `object-structure`：对象/典型结构图；
- `problem-process`：完整工序和瓶颈图；
- `triz-trace`：现场矛盾—参数—矩阵原理—作用机制追溯图；
- `solution-mechanism`：每个入选路线至少一张机理图；
- `system-architecture`：推荐系统及模块接口图；
- `validation-gates`：V0—V3 验证闸门图；
- `benefit-sensitivity`：报告存在数值效益情景时生成。

每张图必须有图号、题名、替代文本、文件路径、生成/来源说明、概念图边界和所覆盖的路线编号。缺任一入选路线机理图时，G5 不通过。

## 4. 交付清单

复制并填写 `assets/deliverables-manifest-template.json`。关键字段：

- `delivery_level`：direction / standard / engineering；
- `status`：complete / degraded / blocked；
- `capabilities`：四项能力探测结果和证据；
- `artifacts`：角色、路径、是否必需、是否打开、是否渲染；
- `shortlisted_routes`：进入最终比较的路线编号；
- `figures`：类型、路线覆盖、替代文本和台账状态；
- `research_log`：宣称检索数与实际逐条日志数；
- `sources`：来源卡数、稳定标识数和关键来源数；
- `score_rows`：每个分数的锚点成熟度与实际证据成熟度；
- `checks`：跨文件一致性、评分、检测方法、专利引用追踪、阶段边界和声称边界；
- `render_summary`：页数、已检查页数、空白页和未解决版式问题。

不得手工把失败项写成 pass。manifest 是对实际文件的索引，不是计划表。

## 5. G5 自动校验

交付前运行：

```bash
python scripts/validate_deliverables.py --root <项目输出目录> --manifest <交付清单路径> --strict
```

没有 Python 时按本文件第 7 节人工逐项检查，但必须在 manifest 中标记 `validator_runtime: unavailable`，交付状态只能是 `degraded`。

校验器检查：

- 四类成果与文件路径是否存在；
- 能力 available 时是否真的生成 DOCX/图示并打开或渲染；
- 必要图示、路线覆盖、替代文本和图示台账；
- 检索数量是否等于逐条日志数；
- 关键来源是否具有 URL、DOI、标准号、专利号或其他稳定标识；
- 评分证据成熟度是否达到该分值锚点，未知项是否被违规赋分；
- 主报告和摘要是否出现无证据的绝对适配、市场空白或法律结论；
- DOCX 包完整性、内嵌媒体、替代文本与外部超链接；
- 页数、逐页检查、空白页和未解决视觉问题。

`validate_skill.py` 只证明 Skill 包结构正确；`validate_deliverables.py` 才检查一次研究任务的产物。两者不可互相替代。

## 6. Word 生成路径

优先使用平台原生文档工具，并按其要求渲染检查。若平台能运行 Python 但没有文档库，可使用内置纯标准库生成器：

```bash
python scripts/build_report.py \
  --input <复制并填写的 report-source.json> \
  --output <最终技术方案报告.docx>
```

输入结构见 `assets/report-source-template.json`。生成器支持标题、状态行、段落、列表、表格、PNG/JPEG/SVG 插图、替代文本和外部来源链接。它是跨平台兜底，不替代平台具备的高质量原生排版工具。

生成后仍必须打开或渲染；仅有一个可解压的 DOCX 不等于视觉验收通过。

## 7. 人工完成回执

校验器不可运行时，在最终回复中逐项给出：

```text
G5 交付回执
- 状态：complete / degraded / blocked
- 决策摘要：路径；已打开/渲染：是/否
- 主报告：路径与格式；页数；已检查页数
- 证据附件：路径；逐条日志数/宣称检索数
- 来源与图示台账：路径；稳定来源数/关键来源数
- 图示：实际张数；必要类型；入选路线覆盖
- DOCX：生成方式；内嵌图数；外部来源链接数
- 未解决问题：无 / 列表
- 能力阻断：无 / 错误原文和替代交付
```

只有必需项全部通过且 `status=complete` 时，才能播报“G5 完成”。降级交付可以结束当前任务，但必须明确其不是完整格式验收通过。

## 8. 普通模型固定动作序列

普通模型在 G5 不自行改序：

1. 修正正文中的冲突和旧结论；
2. 生成所有必要图示；
3. 生成四类成果内容；
4. 生成 DOCX 或记录真实能力阻断；
5. 建立 `deliverables-manifest.json`；
6. 打开/渲染并逐页检查；
7. 修复后重新生成与复查；
8. 运行成果校验器；
9. 输出 G5 交付回执。

任何一步失败均回到对应步骤修复，不得把插图和 Word 留作“后续扩展”。
