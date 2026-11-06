# 可选的参数映射与主张支持审查

这是评估期功能，默认 `quality_review.policy=off`。未完成独立比较前，不把它宣传为已提高研究质量。原有证据、安全、矩阵和成熟度契约始终适用。G0 不加载本附录；G1 出现参数歧义、G3 出现决策关键强主张、G5 用户要求审查时再加载。

## 参数映射卡

先保留记录中的控制量、方向、收益、恶化、因果依据、反向核查和 eligibility。脚本只按内置参数指导中的现场词生成候选，不排序为“最优参数”，不自动查矩阵，不把控制量误当收益参数。无词命中时保留空候选并人工选择。记录 `selection_rationale` 与 `discriminating_observation`；`no_triz_contradiction`、`reframe_required`、`assumption_only` 继续合法，不为填满卡片强行查询。

## 主张审查

先从摘要、推荐结论选最多三条会改变决策的 claim ID，生成待填写草稿：

```bash
python scripts/research_review.py --record research-record.json --draft review-draft.json --claims CLM-001
```

`focused` 只覆盖所选主张；`complete` 覆盖所有 claims、矛盾卡和已有试验协议。草稿不是完成记录，将真实审查结果写回 `quality_review` 后校验。启用审查后，G5 **必须**完成其声明范围，并在报告源设置 `quality_review_surface=true` 输出证据附件。五层契约中的 conditional MUST 指本条件。

每条 claim_checks 的 id 等于 claim_id，以便使用稳定 ID 绑定报告。审查复用 claim/source/test ID；填写支持到哪一部分、不支持哪一部分、原文定位或数据位置、理由、处置、复核者、日期和复核方式。`supported` 只表示复核者记录的支持判断，脚本检查引用、覆盖与一致性，无法证明来源语义。`hypothesis` 用于保留条件清楚的 H 机理或算例，不把所有 H 删除。`partial/unsupported/unverifiable` 不得原样保留；修改措辞后针对最终 claim 和证据重新审查，或移出正文及审查范围，在运行日志保存删除理由。修改命题或支持/反对来源及试验记录会使哈希失效。原始数据文件仍由核心契约核验。

核对五类常见越界：来源子功能扩张成整机适配；专利摘要扩张成首创或 FTO；方案计划写成完成事实；H 推算写成 M 效益；产品保护规格扩张成目标工况安全。对明确来源支持的子功能、可复算 H 示例及带实测链的 M 正例保留正确证据等级。单模型顺序复核填 `serial`；真实独立复核才填 `independent`，字段本身不能证明独立性。

```bash
python scripts/research_review.py --record research-record.json --require-ready
python scripts/validate_research.py --record research-record.json
```

旧 1.0/1.1 记录不含本扩展时返回 `NOT_CHECKED`。迁移仅补默认关闭字段，保留既有证据与 ID，不自动生成通过结论。研究记录、报告源、DOCX 与图示哈希变化后按原有绑定流程重新生成和复核。

## 推荐语义

`assessments.selection.status` 支持 `not_assessed`、`selected`、`priority_for_validation`、`no_robust_winner`。后者只用于阶段稿：比较至少两条既有路线，说明无法稳健排名的原因和下一决定性试验，且不得同时声明主路线。完整交付仍须选择优先研究/验证路线；优先验证不等于性能、安全或准入已获证实。这里不豁免专利追踪、安全闸门、候选组合、逐路线图示或其他完成检查。

## 运行清单

用原有 research record、deliverables manifest 和 eval run-record 保存事实及运行元数据，不再维护第二套来源事实。记录实际 Skill 提交及文件哈希、工具、原始输出、确认交互、失败重试、计时范围和 token。宿主未提供的用量写 `unavailable`。独立效果评价由匿名评审包和冻结比较协议承担。
