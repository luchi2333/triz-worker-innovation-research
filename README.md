# TRIZ 职工创新研究技能

![TRIZ 职工创新研究：从现场问题、矛盾矩阵与实证研究到方案创新、工程验证和技术报告的赛博科技流程图](assets/triz-worker-innovation-research-hero-v2.png)

这是一个面向一线职工创新课题、可独立安装的 TRIZ 深度研究技能。它将工具、设备、检修和作业流程中的现场问题转化为带证据标记的问题模型，完成经典阿奇舒勒矛盾矩阵检索、物理矛盾与物—场分析、系统查新、候选方案构建、工程验证设计、效益测算和技术报告编制。

## 特点

- 内置经典 39×39 矛盾矩阵、39 个参数、40 条发明原理；
- 内置七轨检索、来源核验、命题级证据矩阵、跨来源综合和三次反证检查；
- 包含适合普通模型执行的状态机、判断树、填空模板和复核闸门；
- 最终报告明确区分成熟已有技术、场景集成和候选创新。

## 5 分钟上手

以一个**完全虚构**的示例走一遍流程（不含任何真实企业信息）：

> 虚构场景：某教学车间用台虎钳夹持薄壁铜管进行锯切，经常把管子夹瘪，锯完还要校圆，费时且报废率高。

1. **直接描述问题**。安装后对智能体说：

   ```text
   请使用 $triz-worker-innovation-research 研究这个职工创新问题：
   我们用台虎钳夹薄壁铜管锯切，管子经常被夹瘪，锯完要校圆，
   有时直接报废。希望不买新设备，先把报废率降下来。
   ```

2. **技能先抽取、再补问**（G0→G1）。它会从你的描述里先提取已有信息，最多追问 1～3 个关键问题，例如管径范围、钳口是平的还是 V 形、报废率大概多少。

3. **确认方向**（G1.5）。技能用大白话复述矛盾，并给出编号方向表让你选，例如“既要夹得稳，又不能夹变形”。你回复 A/B/C/D 或提出修正，沉默不会被视为同意。

4. **矩阵查询**。技能将矛盾映射为工程参数（本例：欲改善 `#10 力（强度）`、随之恶化 `#12 形状`，即 `10×12`），用确定性查询查出推荐原理（#10 预先作用、#35 参数变化、#40 复合材料、#34 抛弃与再生），并把每条原理翻译成现场可用的方案雏形——例如“钳口加开槽软衬块”。

5. **获得交付**。默认交付标准研究（含查新、候选路线决策表、验证设计和效益测算）；只有你明确只要快速讨论时才给方向稿。每条结论都带证据标记：`F` 现场报告 / `M` 受控实测 / `S` 可追溯来源 / `H` 工程假设。

整个过程你只需要回答问题和做决策，方法推导由技能按固定状态机推进。

## 仓库结构

```text
triz-worker-innovation-research/          # 仓库根
├── README.md
├── LICENSE / THIRD_PARTY_NOTICES.md
├── assets/                               # 仓库宣传图
└── triz-worker-innovation-research/      # 发布源（Skill 目录本体）
    ├── SKILL.md                          # 技能入口与顶层契约
    ├── CHANGELOG.md
    ├── agents/openai.yaml                # OpenAI 平台配置入口
    ├── references/                       # 工作流、模板、矩阵行分片等 40+ 文档
    └── scripts/                          # lookup_matrix.py / .mjs、validate_skill.py
```

## 安装

### Codex

可直接告诉 Codex：

```text
请使用 skill-installer 从以下地址安装技能：
https://github.com/luchi2333/triz-worker-innovation-research/tree/main/triz-worker-innovation-research
```

或运行 Codex 内置安装脚本（Bash）：

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo luchi2333/triz-worker-innovation-research \
  --path triz-worker-innovation-research
```

Windows PowerShell：

```powershell
python "$env:USERPROFILE\.codex\skills\.system\skill-installer\scripts\install-skill-from-github.py" `
  --repo luchi2333/triz-worker-innovation-research `
  --path triz-worker-innovation-research
```

### Claude / Claude Code

将仓库中的 `triz-worker-innovation-research` 整个目录复制到个人技能目录（如 `~/.claude/skills/`），确保 `SKILL.md` 位于技能目录根部。

### 其他智能体平台

通用做法：把 `triz-worker-innovation-research` 整个目录复制到平台的 skills 目录，并确保平台能把 `SKILL.md` 作为技能入口读取。若平台没有 skills 机制：

1. 在任务开始时把 `SKILL.md` 全文加载给智能体；
2. 按 `SKILL.md` 中的资源路由表按需加载 `references/` 下的文档；
3. 无脚本平台让智能体直接读取 `references/matrix-rows/R01.md`～`R39.md` 行分片查矩阵，不需要 Python/Node。

完成实时深度研究仍需要平台自身具备联网检索能力；没有 Python/Node 时可直接读取内置 JSON 矩阵与行分片，不影响确定性查询。

## 验证

```bash
python triz-worker-innovation-research/scripts/validate_skill.py
node triz-worker-innovation-research/scripts/lookup_matrix.mjs --self-test
```

完整性检查包括：39 个参数、40 条原理、39×39 矩阵、1248 个非空单元、固定哈希、16 个黄金回归锚点、行分片一致性和双运行时（Python/Node）输出逐字一致。

## FAQ

**Q：必须联网才能用吗？**
不是。矛盾矩阵检索、参数映射、物理矛盾分析、方案模板都不需要联网。只有“深度查新”（产品、标准、专利、论文检索）需要平台具备联网检索能力；无联网时技能会明确标注“检索日志未闭合”，不会假装查过。

**Q：没有 Python 或 Node 能用吗？**
能。矩阵数据内置为 JSON，并预生成了 39 个行分片（`references/matrix-rows/`），智能体可直接读文件查表。脚本只是提供更快、可校验的查询方式。

**Q：我的项目数据会被上传或内置到技能里吗？**
技能本身不含任何真实案例，也不会主动把你的项目信息写入技能文件或本仓库。但对话数据的传输、保留和训练政策取决于你使用的平台及所在单位的规定，本技能无法替平台承诺；请勿把真实项目照片、型号清单或内部规程提交到本仓库。

**Q：我不回复确认，技能会继续往下做吗？**
不会。方向确认门（G1.5）要求显式回复；沉默不视为授权。这是顶层契约的一部分。

**Q：和直接问大模型“帮我用 TRIZ 分析一下”有什么区别？**
直接问模型会得到不可复现的自由发挥。本技能提供固定状态机、判断树和填空模板，矩阵结果来自带哈希校验的本地数据，每个结论带证据分层和来源追溯，普通模型也能稳定执行同一套流程。

**Q：矩阵数据可靠吗？**
经典 39×39 矩阵来自阿奇舒勒原著转译版本，与常见英文版存在个别历史转录差异。本仓库固定了一个版本并给出 SHA-256 哈希与 16 个黄金回归锚点，任何改动都会被自检发现；差异清单记录在 `references/matrix-audit.md`。

**Q：怎么确认安装完整？**
运行上面的验证命令，看到 `SELF_TEST_PASS` 和校验器 `status: PASS` 即可。校验器同时检查发布清单完整性和双运行时一致性。

## 许可与归属

本项目原创代码、工作流、模板和说明采用 MIT License。经典 TRIZ 方法、参数、发明原理和矩阵归其原始作者及相关权利人；数据来源与再分发说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 参与贡献

欢迎提交问题、修正来源、改进跨平台兼容性，或贡献不含企业秘密和个人信息的通用测试问题。请勿提交真实项目照片、型号清单、现场数据、内部规程或未获授权的完整案例。
