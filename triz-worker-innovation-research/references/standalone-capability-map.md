# 单技能独立能力覆盖与移植说明

本文件用于回答两个验收问题：

1. 不安装任何通用“深度研究”技能，本技能是否仍能独立完成职工创新研究？
2. 换到不同智能体、操作系统或工具平台后，能否复现相同的研究结构、证据纪律和交付质量？

结论边界：本技能完整覆盖**工程型职工创新研究**所需的课题界定、TRIZ 分析、系统检索、来源核验、跨来源综合、反证、方案生成、风险验证、效益测算和技术报告编制。它不是医学系统综述、统计元分析或人体研究伦理审查工具；遇到这类课题，应另行采用相应专业规范，但这不影响普通工器具、设备、检修和作业流程创新的独立运行。

## 一、能力覆盖矩阵

| 通用深度研究能力 | 本技能内置实现 | 强制产物 | 验收条件 |
|---|---|---|---|
| 研究问题澄清 | `research-workflow.md` 的 G0；`weak-model-playbook.md` 的事实分层 | F/M/S/H 事实表、目标、边界、禁区 | 事实、测量、推断、假设不混写 |
| 对象标识与接口冻结 | `engineering-claim-safety-checks.md` 的身份门 | 原始标识、候选解释、直接证据和阻断项 | 不静默纠错；身份未冻结不外推结构/适配 |
| 研究问题与方法架构 | `deep-research-protocol.md` 第 1—2 节 | 研究问题树、命题清单、检索计划 | 每个关键结论在检索前已形成待证命题 |
| TRIZ 问题建模 | `triz-analysis-output.md`、`matrix-usage.md`、`triz-extended-tools.md` | 工艺瓶颈、技术矛盾、物理矛盾、物—场模型 | 参数映射含因果句与备选参数；矩阵结果可复算 |
| 确定性矛盾矩阵检索 | `contradiction-matrix.json`、Python/Node 查询器、`matrix-rows/` 行分片 | 改善参数、恶化参数、矩阵单元格、推荐原理 | Python、Node 或行分片三选一，结果一致且反向单元交叉复核 |
| 发明原理工程化 | `inventive-principles.md`、`weak-model-playbook.md` | 原理到结构、动作、控制和验证的映射 | 不把原理名称直接当方案 |
| 物理矛盾、物—场、标准解、裁剪和演化 | `triz-extended-tools.md` | 分离条件、Su-Field 模型、标准解族、演化方向 | 标准解编号仅在内置表或经核验时使用 |
| 系统检索与书目发现 | `deep-research-protocol.md` 的七轨检索 | 标准、产品、专利、论文、跨行业、反证检索日志 | 每轨记录查询式、范围、结果和未命中项 |
| 来源身份核验 | `deep-research-protocol.md` 的 V/P/L/X 核验 | 来源核验卡 | 标题、作者/机构、日期、载体、定位和稳定链接可对应 |
| 来源质量与命题适配 | `deep-research-protocol.md`、`engineering-claim-safety-checks.md` | 权威性、直接性、独立性、时效性、适配分栏 | “已打开 V”不替代“权威/直接/适配”的判断 |
| 论证内容提取 | `deep-research-protocol.md` 的 WHY/HOW/WHAT/FIT/USE/EVIDENCE 卡 | 机制与应用证据卡 | 摘要性描述与原文直接证据分开 |
| 跨来源综合 | `deep-research-protocol.md` 的收敛、分歧、沉默框架 | 证据综合表和研究空白 | 不以单一来源代表共识；分歧原因被解释 |
| 论证与因果审查 | `deep-research-protocol.md` 的主张—证据—论证桥和最佳解释比较 | 限定词、替代解释、推翻条件 | 来源真实不等于推论成立；相关不写成因果 |
| 反方审查与可证伪性 | `deep-research-protocol.md` 的三次反对者检查 | 最强反对意见、推翻条件、反证检索 | 推荐路线包含停止条件和最小否证试验 |
| 失败路径恢复 | `deep-research-protocol.md`、`weak-model-playbook.md` | 失败记录、替代查询或降级结论 | 未命中不等于不存在；不可核验不写成事实 |
| 产品适配与类比迁移 | `engineering-claim-safety-checks.md` | 适配表、类比迁移卡、最小否证试验 | 标称范围不冒充适配；候选机理不冒充目标可行 |
| 候选方案生成 | `research-workflow.md`、`final-report-blueprint.md` | 成熟基准、低风险后备、高潜力探索、超系统替代 | 每条路线均回答“用什么方法解决什么难点” |
| 工程方案拆解 | `output-templates.md`、`final-report-blueprint.md` | 方法—难点—机理—来源—已有集成—候选创新—风险—试验卡 | 已有技术与候选创新逐项分栏，不混作原创 |
| 安全、质量和可实施性审查 | `research-workflow.md`、`engineering-claim-safety-checks.md` | 安全屏障真实性表、FMEA、验证一致性表 | 对象材料/手感/软件不冒充保护；安全先于效率评分 |
| 现场资料伦理与授权 | `deep-research-protocol.md` 的方法适配与现场数据伦理 | 授权、脱敏和试验许可边界 | 未授权访谈/录像/现场试验不写成已完成实证 |
| 社会与经济效益 | `final-report-blueprint.md`、`output-templates.md` | 参数表、公式、区间和敏感性分析 | 实测、现场报告、假设分别标记，不伪造基线 |
| 报告综合与编辑 | `final-report-blueprint.md` | 决策摘要、主报告、证据附件、来源/图表台账 | 摘要技术导向；正文完整；证据可追溯 |
| 视觉与文档质量 | `delivery-contract.md`、`engineering-figure-planning.md`、`final-report-blueprint.md` | Figure Plan、结构/运动/作用/安全图、SVG/PNG、DOCX 及交付清单 | 核心方案不是只有架构图；图号/标签/字体/图文一致性通过；文档逐页检查；成果校验通过 |
| 普通模型稳定执行 | `weak-model-playbook.md` | 进度卡、逐门检查、两轮最终复核 | 不跳阶段、不凭记忆查矩阵、不自动越过用户确认门 |

## 二、与通用深度研究流程的等效角色

平台支持多个智能体时可以分工；平台只有一个普通模型时，必须按照以下顺序串行切换角色。角色是检查视角，不要求真实多智能体：

1. **问题架构员**：锁定研究问题、子问题、范围、命题和检索轨道。
2. **检索与来源核验员**：发现来源并完成身份、质量和命题适配核验。
3. **证据综合员**：提取 WHY/HOW/WHAT，比较收敛、分歧、沉默和研究空白。
4. **反对者**：主动寻找失败案例、替代解释、实施障碍、专利拥挤和推翻条件。
5. **技术总编**：只依据证据台账组装方案、验证计划、效益测算和最终报告。

每次角色切换前保存阶段产物；后一角色不得悄悄修改前一角色确认过的现场事实。若发现错误，应建立修订记录并重新通过对应闸门。

## 三、没有专用工具时的等效执行

| 能力 | 首选 | 无该工具时的等效办法 | 不允许的降级 |
|---|---|---|---|
| 网页检索 | 搜索引擎、专利库、标准库、厂商站点 | 使用平台任意联网检索能力，逐条保存查询式和 URL | 用模型记忆冒充当前检索结果 |
| PDF/网页读取 | 原文解析或浏览器 | 下载后文本提取；无法读取时只记录题录并标“未核全文” | 根据标题猜测结论 |
| 矩阵查询 | Python 或 Node 脚本 | 只读取 `references/matrix-rows/R{改善}.md` 行分片定位目标列，并交叉复核反向单元 | 凭记忆或二手网页返回原理 |
| 数据计算 | 表格或脚本 | 写出公式后手工复算关键数字 | 只给收益结论而无参数和公式 |
| 原理图 | CAD/绘图/图像生成工具 | 先按 `engineering-figure-planning.md` 写 Figure Plan；流程/因果图可用 Mermaid，机理/几何图用 SVG 或原生可编辑图形；动态动作拆成 3～6 帧 | 把架构图当原理图；把概念图标为制造图；用 Mermaid 表达复杂机械空间结构 |
| DOCX/PDF | 平台原生文档工具；或 `scripts/build_report.py` 标准库兜底 | 实测两种路径均不可用后，交付完整 Markdown 与独立图表文件并标 `degraded` | 未探测能力就省略 Word；因无文档工具删减内容或证据 |
| 多智能体 | 并行角色 | 单模型按五角色串行执行 | 删除反对者或来源核验环节 |

## 四、普通模型的分阶段上下文装载

不要一次加载全部参考文件。按当前阶段只读取最少集合；长文件允许只读当前 G 阶段对应小节，进入新阶段再读下一段：

1. **G0 立项**：`SKILL.md` + `research-workflow.md` 的 G0 小节 + `intake-guide.md`；需要冻结对象身份时加读 `engineering-claim-safety-checks.md` 的身份门一节。
2. **G1 建模**：`triz-analysis-output.md` + `matrix-usage.md` + `inventive-principles.md`（需要扩展工具时加 `triz-extended-tools.md`）；收尾对照 `weak-model-playbook.md` 的 G1 检查清单。
3. **G1.5 确认**：只保留方向稿与确认卡所需内容，等待用户回复。
4. **G2/G3 深研与选型**：`deep-research-protocol.md` + `output-templates.md`，并执行 `engineering-claim-safety-checks.md` 全文闸门。
5. **G4 验证**：`research-workflow.md` 的 G4 与 V0—V3 小节 + `engineering-claim-safety-checks.md` 的验证一致性门。
6. **G5 报告**：先读 `delivery-contract.md` 做能力探测，再读 `engineering-figure-planning.md` 冻结 Figure Plan，最后按 `final-report-blueprint.md` 组装成果；文档能力可用时无需用户追问，主动生成 SVG/PNG、DOCX 和必要图示。
7. **交付前**：复制 `assets/deliverables-manifest-template.json` 填写实际结果，运行 `scripts/validate_deliverables.py --strict`；`validate_skill.py` 只验证技能包，不能替代成果校验。

模型每完成一个阶段，只保留“进度卡 + 已确认事实 + 决策 + 证据台账索引”进入下一阶段，避免把大段搜索材料直接塞进最终写作上下文。

## 五、可复现性不变量

跨平台迁移时，工具名称、文件格式和是否并行可以变化，但以下项目不得变化：

- G0—G5 阶段顺序与用户确认门；
- F/M/S/H 事实分层；
- 原始标识冻结、适配/类比检查和 I/E/A/T/S/P/V 七道闸门；
- 39×39 矩阵数据和确定性查询；
- 七轨逐条检索日志、来源五维核验和命题级证据矩阵；
- G5 能力探测、Figure Plan、核心 F4/F5/F7/F8 图契约、SVG/PNG、DOCX、交付清单和成果校验；
- 三次反对者检查与推翻条件；
- 已有技术、场景集成、候选创新三者分栏；
- 安全/质量硬门槛优先；
- 效益公式、参数来源、区间和敏感性分析；
- 技术导向摘要、完整主报告和可审计证据附件；
- 最终两轮复核及文档视觉检查。

如果某个平台无法维持这些不变量，应明确指出缺失能力和受影响产物，不得宣称已等效完成。

## 六、独立安装验收

仅复制本技能目录后，执行以下检查即可判定安装是否完整：

1. 确认 `SKILL.md`、`references/`、`scripts/`、`agents/` 均存在。
2. 有 Python 时运行：`python scripts/validate_skill.py`。
3. 有 Node.js 时运行：`node scripts/lookup_matrix.mjs --self-test`。
4. 两种运行时均无时，读取 `references/matrix-rows/R39.md`，确认 `C30` 行的原理为 22、35、13、24；再抽查 `R01.md` 的 `C1` 为 null（对角线）。
5. 用一个小型工程问题做纸面演练，确认模型在首次完整 TRIZ 输出后暂停，等待用户确认，而不是自行进入深研。

通过以上检查后，普通工程型职工创新研究不需要再安装外部深度研究技能、矩阵插件或多智能体框架。
