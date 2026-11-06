# M0 宿主运行协议

状态：候选协议，未冻结正式实验。基线 `19e20f4a2b4d2d9e0b46a214fd609146be0a7d7c`。本次只运行 S01/C0；单题通路校准不能替代完整 M0、A/B 比较或留出验证。

## 输入与隔离

`cases/*.json` 只存 id、input、constraints；`cases.json` 为兼容目录。题面保留原字句。`private/confirmations.json` 只在已记录 G1.5 请求后由运行器读取，`private/annotations.md` 是评审材料。`splits.json` 保存病例字节哈希、8 道开发题、3 道通路题和 4 个留出名额；不生成留出题或金标。

隔离依赖宿主：每题每组启动独立会话，实际加载清单、精确模型版本和工具权限写入 runtime 文件。目录名 private 不构成访问控制；被测模型不得拥有整库/评审目录的读权限。A/B 若已加载 TRIZ Skill，必须保留输出并标条件不符。库存不全、模型未知或上下文不隔离只能作校准。

## 工具使用

所有命令在仓库根运行。Python 3.10+ 标准库即可；C0 导出固定提交需 git。运行器不调用模型，不把封装/复制输出视作一次新的模型推理。

```bash
python evals/worker-bench/bench.py prepare --case S01 --arm C0 --runtime /path/runtime.json --output /path/new-run
# 宿主加载导出的 prompt.md；C0 参考资料仅使用 new-run/c0-skill/。
python evals/worker-bench/bench.py request --run /path/new-run --text /path/actual-direction.md
python evals/worker-bench/bench.py confirm --run /path/new-run --mode human --reply '用户实际原话'
# 若用户明确允许模拟，runtime 中记录 simulation_authorization 原话；之后可改用：
# python evals/worker-bench/bench.py confirm --run /path/new-run --mode simulated
python evals/worker-bench/bench.py finish --run /path/new-run --text /path/actual-final-output.md
python evals/worker-bench/bench.py telemetry --run /path/new-run --metadata /path/measured-usage.json
python evals/worker-bench/bench.py audit --run /path/new-run
```

runtime 最少提供 `loaded_skills` 数组。`model` 为精确可见版本，否则 unavailable；`skill_inventory_complete` 表示是否确认完整；`context_isolation` 为 isolated 或 not_isolated；`tool_permissions` 列出实际权限。`execution_kind=live_host` 只用于真实执行，历史输出回放写 artifact_replay，后者不进入正式评估。C0 已加载项须给真实 Skill 名及 commit，运行器只记录宿主陈述，不以导出资源代替已加载证据。

模拟答复以 `role=user_simulated`、`mode=simulated` 记录，并保留授权原话。它只确认研究方向，不生成现场事实、试验数据、M 证据或专业评审意见。模拟值在请求前不进入 prompt。实际用户修正优先；每次新方向变更保留在实际交互记录中。

运行状态为 prepared → awaiting_confirmation → confirmed → completed_smoke。A/B 不要求 G1.5，可由 prepared 直接收集输出。`completed_smoke` 仅表示采集链路完整；G0–G5 阶段、七轨深研、报告完整性和工程正确性单独标记。不得把收集 PASS 写成 G5 完成。

原始 prompt、方向稿、最终输出不可覆盖，绑定 SHA256；基线全部资源逐文件绑定 SHA256。重试必须使用新目录并同时提供 --retry-of 和 --retry-reason。错误尝试与输出保留，不能只留下成功样本。

## 预算、耗时和证据

通路阶段不凭空补正式预算。预算文件提供 seconds、search_calls、output_tokens；正式开发题前由三道通路测量后冻结。usage 未取得时填 unavailable，不能以字符串长度估算 token。时间戳使用带时区 ISO 时间，查询 date 单独使用 YYYY-MM-DD。记录实际执行片段，不把等待用户、复制历史产物或回放时间冒充模型推理耗时。

检索逐条保留原式、入口、日期、过滤、纳排、source ID 和实际尝试次数。audit 的 PASS 只检查可计算完整性及哈希，不审核语义真实性，不认证工具可用性。超预算输出保留并标记 over_budget；不伪造缺失 token。

## 人工评价与后续冻结

正式评价前冻结输入、提示包装、模型、资源、预算、预设答复与允许的用户改动规则。两名独立评审各自收到随机顺序和匿名编号；组别/模型/提交映射另存。保留原始分、原句、关键错误与分歧；模型预审标为 model_precheck，不能填写人工分数。

运行汇总使用 `summarize_results.py`。未知成本不按零参与完整总量；可报告已知小计与缺失运行数。回放的历史用量不重复计费。完整性 PASS、正式条件合格、G0–G5 阶段、技术内容复核和现场实测成熟度分别呈现，严格验收失败的原文必须保留。

M0 本次交付为工具与 S01 校准。未完成的其余通路、独立标注、正式预算和评审人选由状态清单明确保留，不据此升级 Skill 合同、版本号或发布。
