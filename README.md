# TRIZ 职工创新研究技能

![TRIZ 职工创新研究：从现场问题、矛盾矩阵与实证研究到方案创新、工程验证和技术报告的赛博科技流程图](assets/triz-worker-innovation-research-hero-v2.png)

这是一个面向一线职工创新课题、可独立安装的 TRIZ 深度研究技能。它将工具、设备、检修和作业流程中的现场问题转化为带证据标记的问题模型，完成经典阿奇舒勒矛盾矩阵检索、物理矛盾与物—场分析、系统查新、候选方案构建、工程验证设计、效益测算和技术报告编制。

## 特点

- 内置经典 39×39 矛盾矩阵、39 个参数、40 条发明原理；
- 内置七轨检索、来源核验、命题级证据矩阵、跨来源综合和三次反证检查；
- 包含适合普通模型执行的状态机、判断树、填空模板和复核闸门；
- 最终报告明确区分成熟已有技术、场景集成和候选创新。


## 仓库结构

```text
triz-worker-innovation-research/
├── SKILL.md
├── agents/
├── references/
└── scripts/
```

## 安装

### Codex

可直接告诉 Codex：

```text
请使用 skill-installer 从以下地址安装技能：
https://github.com/luchi2333/triz-worker-innovation-research/tree/main/triz-worker-innovation-research
```

或运行 Codex 内置安装脚本：

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo luchi2333/triz-worker-innovation-research \
  --path triz-worker-innovation-research
```

Windows PowerShell 可将 `~` 换成用户目录下的 `.codex` 路径。

### 其他智能体平台

将仓库中的 `triz-worker-innovation-research` 整个目录复制到平台的 skills 目录，并确保平台能把 `SKILL.md` 作为技能入口读取。若平台没有 skills 机制，可在任务开始时加载 `SKILL.md`，再按其中的资源路由按需加载 `references/`。

完成实时深度研究仍需要平台自身具备联网检索能力；没有 Python/Node 时可直接读取内置 JSON 矩阵，不影响确定性查询。

## 验证

```bash
python triz-worker-innovation-research/scripts/validate_skill.py
node triz-worker-innovation-research/scripts/lookup_matrix.mjs --self-test
```

完整性检查包括：39 个参数、40 条原理、39×39 矩阵、1248 个非空单元、固定哈希、已知单元和行列方向。

## 使用

安装后直接描述现场问题，或显式调用：

```text
请使用 $triz-worker-innovation-research 研究这个职工创新问题：……
```

技能会先形成完整 TRIZ 方向稿并请求确认；用户确认后，才进入产品、标准、专利、论文、跨行业类比和反对证据的系统研究。

## 许可与归属

本项目原创代码、工作流、模板和说明采用 MIT License。经典 TRIZ 方法、参数、发明原理和矩阵归其原始作者及相关权利人；数据来源与再分发说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 参与贡献

欢迎提交问题、修正来源、改进跨平台兼容性，或贡献不含企业秘密和个人信息的通用测试问题。请勿提交真实项目照片、型号清单、现场数据、内部规程或未获授权的完整案例。
