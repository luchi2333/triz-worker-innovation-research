# 核心要求覆盖矩阵

本表防止版本迭代把早期核心要求保留在说明文档里，却从事实源、主报告或硬校验中弱化。标记为 MUST 的要求，完整 `standard/engineering` 交付必须同时具备：规范来源、结构化事实、主报告出口、机器校验和回归测试。

| Requirement ID | 核心要求 | 规范来源 | research-record | 主报告出口 | 机器校验 | 回归 |
|---|---|---|---|---|---|---|
| CR-01 | 七轨深研覆盖 | deep-research-protocol §3 | `research_tracks[]` + `queries[].track` | 第4章 | `research_contract.py` | `test_complete_requires_all_deep_research_tracks` |
| CR-02 | 候选组合包含成熟基准、工程后备、高潜力探索，超系统显式判适用性 | research-workflow / SKILL | `routes[].portfolio_roles` + `assessments.route_portfolio` | 第5章 | `research_contract.py` | `test_complete_requires_distinct_portfolio_roles` |
| CR-03 | 成熟技术、场景化集成、候选创新与创新边界分离 | final-report-blueprint §6 | `routes[].innovation_attribution` | 第6章 | `validate_deliverables.py` | deliverables negative tests |
| CR-04 | 每条活跃路线有进一步提升状态 | final-report-blueprint §6 | `routes[].improvement_outlook` | 第6章 | `research_contract.py` | `test_complete_requires_further_improvement_outlook` |
| CR-05 | 每条活跃路线有 FMEA/危险链与验证协议 | research-workflow §11 | `hazards[]` + protocols | 第8章 | `research_contract.py` | `test_complete_requires_fmea_per_active_route` |
| CR-06 | 经济效益有模型或待数据公式/情景计划 | final-report-blueprint §9 | `models_and_tests.benefit_assessment.economic` + `benefit_scenarios` | 第9章 | `research_contract.py` | core contract positive/negative tests |
| CR-07 | 社会效益用可测指标表达 | final-report-blueprint §9 | `models_and_tests.benefit_assessment.social.metrics` | 第9章 | `research_contract.py` | `test_complete_requires_social_benefit_metric` |
| CR-08 | 最强反对意见、退出条件与移除最强证据后的稳健性 | final-report-blueprint §7 / deep-research §3.7 | `assessments.robustness_review` | 第7章 | `research_contract.py` | `test_complete_requires_strong_counterevidence_review` |
| CR-09 | 实施路径包含决定性试验、阶段闸门、采购/退出条件、边界和未知 | final-report-blueprint §10 | `implementation_plan` | 第10章 | `research_contract.py` | `test_complete_requires_implementation_plan` |
| CR-10 | 完整主报告实际呈现研究全链条 | final-report-blueprint §3 | `report-quality-review.json.report_sections` | 第1—10章 | `report_quality.py` | `test_each_complete_report_section_cannot_be_omitted` |

## 维护规则

1. 新增或修改 MUST 要求时，同一 PR 内更新本表。
2. 若某要求有意降级为 SHOULD，必须在 CHANGELOG 说明原因；不能通过删除 validator 或模板字段实现静默降级。
3. 任一 MUST 行缺少“事实源 / 报告出口 / 校验 / 回归”之一，发布评审视为覆盖缺口。
4. `not_applicable / unknown / pending-data` 是合法状态，但必须显式记录理由或下一验证；不得用空白冒充原创、完成或不适用。
5. 教学样例和 degraded/blocked 阶段稿可不满足完整交付门槛，但不得被标记为 complete。
