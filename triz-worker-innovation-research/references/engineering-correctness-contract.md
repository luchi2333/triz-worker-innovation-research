# v2.9 工程一致性与迁移

保留研究记录 1.1、报告源 1.3、清单 1.2 的读取。旧成果缺少新证据时须补齐、重新生成和复核，不能自动填通过。

## V2/V3 基准比较

baseline_test_id 须指向原始数据哈希有效、不同基准路线的 `target_kind=baseline_system` 试验。基准不能再引用基准；其结果即使未满足候选通过判据，也可用于比较，但不给候选虚增成熟度。

双方协议填写相同 comparison_basis，包含 object_population、metric_definition、reference_points、instrument_chain；scope、sampling_plan、指标 ID 与单位也须可比。不能以空对象或“可比较=true”代替。不同设备可通过事前定义且有校准依据的等效仪器链比较，未能建立等效时不升级。

保留原始 conditions，再填 comparison_conditions 的同名工况，如 temperature_C、load_N、batch。值须相等，或在双方事前 condition_tolerances 范围内。comparison_rationale 说明配对/抽样依据、允许变化和限制。归一化另附复算记录，不能只写“已归一化”跳过差异。

示例：同批对象、同测点、同仪器链、同抽样和全工序口径，temperature_C 容差为 1；20 与 20.5 可通过数值检查，20 与 40 不通过。脚本不证明记录真实。

## 单位与口径

input_units 与输出 unit 支持显式乘除表达式：s/min/h、m/mm、A/mA、V/kV、J/kWh、CNY、count、person、year；支持元、次、件、端、人、年等别名。year 表示统计口径，不自动与秒换算；币种不自动兑换。

`(60 min/count − 0.5 h/count) × 100 count/year × 20 CNY/h = 1000 CNY/year`。检查同时转换倍率和推导量纲，CNY 与 CNY/year、时间与金额不能混写。未知单位为未检查，不能完成交付。净收益目前要求各项同一结果单位。扩展单位须增加有依据的换算和回归。

## 关键事实绑定

新报告源设 critical_facts_policy=bound，完整 DOCX 必须启用。性能、尺寸、成本、阈值、成熟度、安全声明和推荐结论在 claims/parameters/decisions 中维护，整句用 claim_ref，参数表用 table_ref；自由 text 只作解释。模板插值之外的文字仍须审阅，不能绑定无关数值后声称整句可信。

规则筛查常见数值和关键表述，并核对声明的 fact_role。这是启发式筛查，不能保证覆盖所有同义表达。生成器对全篇段落存文本指纹，手改自由正文也须重生成并复核。哈希不证明内容正确；读者仍须逐段核对关键事实是否遗漏绑定。

绘图见 [engineering-diagram-authoring.md](engineering-diagram-authoring.md)，更新与发布见 [skill-update.md](skill-update.md)。新增 CI 必须在实际提交运行后才能声称远端通过。标签不等于 GitHub Release。
