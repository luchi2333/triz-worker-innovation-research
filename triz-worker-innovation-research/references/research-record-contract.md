# 研究记录与图文生成契约

v2.9 的比较协议、单位换算与完整正文要求见 [engineering-correctness-contract.md](engineering-correctness-contract.md)；领域图元见 [engineering-diagram-authoring.md](engineering-diagram-authoring.md)。下文 v2.6 接口继续读取，新版交付同时执行新增要求。

本文件维护 v2.6 的新增数据与脚本接口。G0 开始读取；G3 建机制、G5 生成图文时按需回到对应小节。阶段仍为 G0—G5，技术成熟度仍为 V0—V3。

## 1. 从现场输入开始

先从现有材料提取，保存原话、位置与证据等级。只补问会改变当前判断的缺口。多个痛点分别建卡，按影响、可验证性与约束排序，保留未选问题。

`inputs` 保存原始信息的 `id/text/locator/evidence_status`；`problems.input_ids` 指向原始信息；`requirements.problem_ids` 指向问题，`criterion` 写可观察的成功条件。未知量明确记录为未知，不以模板中的教学尺寸替代。

按当前任务分流：原因不明，先比较竞争解释并设计区分观察；成熟方法足以满足要求，允许常规改进；存在真实冲突，再选技术矛盾、物理矛盾、功能/资源等方法。方法不适用时说明依据，不强行补出一组矩阵参数。

G0 的 `context` 使用 `object_identity/operating_boundary/measurement_basis/proxy_scenarios` 记录对象身份、工况边界、统计口径与代理情景。未知保持 null 或明确待确认。没有候选方案时，在 `project.maturity_note` 说明尚未评定机理；兼容字段 V0 不是对不存在方案的可行性结论。

`workflow` 记录 `current_stage/completed_stage/next_actions/pending_questions`。`completed_stage=null` 表示尚未完成任何阶段，不等于失败。阶段检查只读取记录，不会替用户确认方向或批准现场动作。

```bash
python scripts/validate_research.py --record research-record.json
python scripts/validate_research.py --record research-record.json --complete-stage G0
```

`check_scope` 报告实际检查的查询、已完成试验与效益模型数量。PASS 仅表示未发现已记录的一致性错误；模型数量为零时没有执行效益计算。

普通检查允许工作中记录；`--complete-stage` 要求该阶段应具备的输入。没有联网记录可保存分析与待执行计划，但不能宣布 G2 查新完成。旧 1.0 记录可读取；迁移复制到新文件，保留原始内容，不自动补事实或授权：

```bash
python scripts/validate_research.py --record old-record.json --migrate research-record.json
```

## 2. 方向确认与既有授权

没有明确授权时，保留白话方向确认卡并等待；沉默不是确认。用户已选定方向，或明确委托“按你的判断推进研究”，则记录 `decisions` 中的原话、日期、范围和所选路线，继续授权范围内的研究，不再次索要同一确认。

方向决定使用 `kind=direction_confirmation` 或 `delegated_direction`，`status=confirmed`，保留 `user_text/scope/route_ids`。用户明确要求先看方向再继续时必须等待。研究授权不扩展到真实现场实施；现场动作的批准单独记录为 `field_authorization`。

### 2.1 G2 七轨覆盖必须结构化

G2 不是“有过搜索”即可完成。每条 `queries[]` 增加 `track`，只能取以下七类之一：

`standards_process / object_structure_material / mature_products_processes / patents / literature_mechanism / cross_industry_analogy / opposition_supersystem`

同时用根级 `research_tracks[]` 对七类逐项结案。每项包含 `track/status/query_ids/rationale`；`status=covered` 时必须绑定本轨道真实查询，`not_applicable` 时不得挂查询且必须解释为何对当前问题不适用。G2 完成前七类都必须被显式评估，不能用一条普通网页搜索代替多轨研究。

## 3. 原理怎样形成机制

每个推荐路线的 `mechanisms` 必须指向 `requirement_ids` 和 `route_ids`，写清 `method/input/action_path/output/conditions/falsification`。按需要记录 `component_ids/interface_ids/claim_ids/evidence_ids`。作用路径描述实际接触、力/能量/信号或工序变化；不要停在“智能化”“动态化”等词。

机制卡应回答：用什么资源、在哪个界面作用、哪个量怎样改变、需要什么工况、什么现象能否定它。科学效应检索只是寻找线索；引用外部效应或跨行业方案时，补原始来源、量级与适配差异，不能把库中的简述当成目标系统实测。

已有作用冲突、接口缺口或硬门槛失败必须回写路线状态。失败路线可以保留研究记录，改为 `rejected/exploratory` 等真实角色；不能继续标成主推荐路线。多个主动作用检查每一对共存关系，不能用几个 ID 出现在表里冒充所有组合已经复核。

进入最终比较或主推荐的每条 `routes[]` 必须填写 `innovation_attribution`，把“技术本身已经存在”与“本项目做了什么”分开记录：

```json
{
  "mature_technology_status": "identified | none_identified | unknown",
  "mature_existing_technology": "可直接复用的成熟产品、工艺、机构、算法或标准做法；若没有或未知则明确写明",
  "existing_technology_source_ids": ["SRC-..."],
  "scenario_integration": "为目标现场做的接口、空间、工序、人员或参数适配与组合",
  "candidate_innovation": "相对已检得现有技术新增或改变的作用链、接口或协同关系；没有则明确写无新增创新主张",
  "innovation_boundary": "明确哪些成熟模块、通用原理和已有做法不属于本项目创新",
  "validation_needed": "验证候选创新成立或推翻所需的最低成本证据"
}
```

当 `mature_technology_status=identified` 时，`existing_technology_source_ids` 必须非空并解析到真实来源；`none_identified` 或 `unknown` 可以为空，但正文必须保留这一判定，不能把空白误读成原创。不能用“优化、改进、智能化、集成化”等口号代替 `candidate_innovation`。成熟模块本身不因被组合进方案就自动成为本项目创新，场景化集成也应与候选创新分别陈述。该归属卡进入主报告正文，不只留在研究记录或附件。

### 3.1 候选组合、进一步提升与强反证

`role` 继续表示当前决策状态；新增 `portfolio_role` 表示路线在候选组合中的技术角色，二者不要混用。G3 至少要有：

- `mature_baseline`：成熟/现行最佳基准；
- `engineering_backup`：低风险、可回退工程后备；
- `high_potential_exploratory`：高潜力探索路线；
- `supersystem_alternative`：采购、预制、工序前移等超系统替代；若确实不适用，在 `assessments.candidate_portfolio` 明确 `supersystem_status=not_applicable` 和理由。

非成熟基准路线填写 `further_improvements[]`，记录在质量、安全、稳定性、标准化、维护或资源方面还能继续提升什么，不能只写“进一步优化”。

主推荐路线填写 `challenge_review`：`strongest_objection/exit_condition/strongest_support_evidence_id/without_strongest_support/opposition_search_status/opposition_evidence_ids/rationale`。这样“最强反对意见”和“去掉最强支持证据后结论是否仍成立”成为事实记录，不只是一段报告文案。

## 4. 实测、试验与成熟度

计划放在 `models_and_tests.protocols`，结果放在 `tests`。协议包含 `id/route_ids/scope/sampling_plan/metrics/stop_rule`；`metrics` 每项有 `id/unit/criterion`，判据为 `{operator: <= 或 >= 或 ==, value: 数值}`。脚本只支持这类明确数值判据；复杂判据需扩展实现并加回归，不使用任意表达式执行。

完成试验记录包含 `id/route_id/protocol_id/target_kind=proposed_system/status=completed/maturity/date/conditions/sample_count/claim_ids/results/raw_artifacts`。每条结果为 `metric_id/value/unit`，原始文件为 `path/sha256`。M 命题通过 `test_ids` 连接实际试验，试验通过 `claim_ids` 反向连接命题。

V1 协议范围为 `short_sample`；V2 为 `full_process` 并记录基准比较；V3 为 `controlled_field`，另有现场批准决定和风险、工艺、IP、效益审查依据。不要用改标签替代这些证据。真实不利结果仍是研究证据，但不能支持通过判据的成熟度。

算法检查记录、单位、判据、引用和文件是否一致，不证明测量真实或工程安全。专业复核与现实动作授权仍需单独记录。

效益支持 `linear_difference_rate` 与 `net_benefit`。前者提供各输入单位；后者按同一结果单位分别列收益与成本。未知公式返回 `NOT_CHECKED`，完整交付不能把未检查计算写成通过。节省工时与现金节约需分开解释，计入新增实施/维护成本，避免重复计算收益。

G4 增加两组不可省略的事实记录：

1. 根级 `hazards[]`：每个活动路线至少覆盖一个危险链，字段包括 `id/route_ids/event/cause/consequence/controls/residual_risk/validation_protocol_id/stop_condition`。F7 安全边界图只能辅助解释，不能替代 FMEA。
2. `models_and_tests.benefit_assessment`：经济效益可为 `modeled / insufficient_data / not_applicable`。没有数据时必须留下 `economic_formula_plan` 和 `missing_economic_inputs`，不能用虚构数字补齐；社会效益用 `social_status=defined` + `social_metrics[]` 记录指标、测量方法和解释边界，不写宣传口号。确实不适用时保留理由。

## 5. 参数与工程图

`parameters` 每项有 `id/symbol/name/value/unit/evidence_status/evidence_ids`，`symbol` 为独一的字母数字下划线名称。未知值用 null，不能参与数值绘图。

`figure_specs` 每项有 `id/title/figure_type/purpose/design_status/main_message/claim_limit/route_ids/parameter_ids`。`purpose` 为 `explanation/initial_design/detailed_design`，仅表示绘图用途，不另建成熟度。图型沿用现有 F1—F9。

图形由实际机制决定。`primitives` 支持 `rect/circle/line/arrow/polyline/text`，实体可绑定 `component_id`，坐标可写数字或 `{"expr":"L/2 - BL/2"}`。表达式只允许已知参数与加减乘除；没有脚本执行、函数调用或自动联网。文字用 `text_template` 与 `{{/parameters/P-L/value}}` 引用取值，也可用 `${L}` 显示当前帧参数。

动态机制使用 `frames`：每帧有 `id/label/description/primitives`，可用 `parameter_overrides` 明确该帧的状态；所有覆盖值仍是研究记录的一部分。`width/height` 表示单帧画布，`columns` 决定静态排列。具体可运行结构见教学记录，不把教学机构当成默认现场方案。

```bash
python scripts/build_figures.py --record research-record.json --output figures
python scripts/build_figures.py --record research-record.json --output figures --png-browser <本机Chromium浏览器可执行文件>
```

输出 SVG、`figure-manifest.json` 和单文件 `report-explainer.html`；显式提供浏览器时生成同源 PNG。没有浏览器时如实标记 `not-rendered`，再用平台图像工具渲染，不强制安装绘图框架。机械复杂几何可接参数化 CAD、电气可接专用回路绘图，但仍需同一部件与参数引用；本版不自动生成 STEP 或制造详图。

HTML 可切换图和动作，静态打印保留完整图组与分步说明；参数更改后由记录重新生成。`figure-manifest` 绑定记录和 SVG/PNG 散列。生成成功仍为 `visual_review=pending`，需按最终嵌入宽度查看字体、接触关系、箭头和每个动作帧。

## 6. 从记录生成并核验实际报告

v2.7.1：`text_template` 可以使用 `[[triz_parameter:28]]` 确定性输出标准参数编号和名称，使用 `[[evidence_legend]]` 输出统一 F/M/S/H 定义；不得手工重定义。表格缺字段、空单元格或列数错配须修复，未知值写明依据/原因。协议及来源关键限定语不得按字符数截断，见 [model-and-output-audit.md](model-and-output-audit.md)。

报告源使用 schema 1.3，`research_record_path/research_record_sha256/figure_manifest_path` 指向当前记录与同版本图组。原有 schema 1.2 可读取，但正文绑定检查为 `LEGACY_UNCHECKED`。

| 内容 | 报告源写法 |
|---|---|
| 关键文字/数值 | `text_template`，其中引用如 `{{/parameters/P-X/value}}` |
| 命题 | `claim_ref: /claims/CLM-001`，H/unknown 自动取 `allowed_wording` |
| 参数或结果表 | `table_ref: /parameters`，`columns` 列出 `header/field` |
| 工程图 | `figure_ref: FIG-MECH`，从图组清单取当前文件与元信息 |
| 图号引用 | `[[figure:FIG-MECH]]`，按报告中首次出现顺序编号 |

新报告默认连续图号 1、2……；交付清单 `figures[].number` 和 `report_figure_order.ordered_numbers` 同步使用该序列，旧章内编号仍可读但不混用。图组清单只记录生成图的散列，不替代交付清单的领域图组与实际复核记录。

数组引用按稳定 ID 解析，不用容易随排序变化的数组下标。跨页新章节用 section 的 `page_break_before=true`，避免把分页块放在标题后。

说明性段落仍可使用普通 `text`；脚本报告未绑定段落数，需要人工内容复核，不能声称所有自然语言已由机器证明。

```bash
python scripts/build_report.py --input report-source.json --output report.docx
python scripts/build_report.py --input report-source.json --output report.docx --verify-bindings
```

绑定块写入 DOCX 内容控件；核验从当前研究记录重新生成期望值，读取实际 DOCX 的对应文字及嵌入图片散列。篡改正文、替换图、缺失绑定或使用旧图清单会被发现。G5 清单的 DOCX artifact 增加 `report_source_path`，让总校验器执行同样检查。

最终报告按“问题与推荐 → 机理与动作 → 初步设计 → 证据与比较 → 验证、风险、效益与实施”组织。详细推导与查询日志保留在附件。初设按领域给必要视图、接口、尺寸和部件表；缺少载荷、材料、公差或验证时，保留待定项，不自动升级为加工/现场实施图。

## 7. 变更与可恢复工作

```bash
python scripts/validate_research.py --record research-record.json --previous previous-record.json
```

报告输出变化 ID、通过显式引用传播的待复核 ID。保留旧记录作为检查点，重新生成受影响的图、正文与计算；未记录的物理影响仍须工程判断。已有用户确认在范围有效时继续沿用，范围改变时处理新增决定。

## 8. 可独立运行的教学链路

```bash
python scripts/run_tutorial.py --output <新的空目录>
```

可加 `--png-browser <可执行文件>` 检查 SVG→PNG→DOCX。教学记录全部是 H，不含现场试验，输出回执明确未开展工程/视觉复核。此命令用于了解字段和生成链路，不作为真实研究成绩。
