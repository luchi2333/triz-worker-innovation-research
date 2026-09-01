# 参与贡献 / Contributing

感谢你帮助改进 TRIZ Worker Innovation Research。贡献不要求是 TRIZ 专家：安装反馈、矩阵核对、文档修正、平台兼容测试和公开教学问题都很有价值。

## 可以贡献什么

- 报告矩阵单元、参数解释、脚本或安装错误；
- 报告 Codex、Claude Code 或其他 Agent 平台的实际兼容结果；
- 改进中文或英文文档；
- 提交完全公开、虚构或已充分脱敏的工程测试问题；
- 增加可复现测试，但不要放入依赖私有服务或个人凭据的步骤。

## 不要提交什么

请勿在 Issue、Pull Request、示例或日志中上传：

- 企业内部文件、现场照片、未公开项目数据或内部规程；
- 真实型号清单、精确站点、客户名称、个人信息或访问凭据；
- 无权再分发的标准全文、论文全文、专利数据库批量内容或商业资料；
- 把模型推断包装成实测效果、专利性、FTO 或现场准入的结论。

如果不能确定某段材料能否公开，请只提交经过抽象的复现步骤。

## 提交 Issue

请使用最接近的模板：

- **Bug report**：矩阵、脚本、安装、链接或文档错误；
- **Compatibility report**：记录 Agent / 平台、版本、安装方法和结果；
- **Engineering example**：贡献公开、虚构或充分脱敏的教学问题。

一个好的 Issue 应包含最小复现步骤、期望结果、实际结果和非敏感日志。

## 提交 Pull Request

1. 从最新 `main` 创建分支；
2. 保持改动单一、可审查，不顺带重构核心 TRIZ 工作流；
3. 若修改 README 中的矩阵示例，必须与矩阵本体一致；
4. 运行：

   ```bash
   python triz-worker-innovation-research/scripts/validate_skill.py --strict
   node triz-worker-innovation-research/scripts/lookup_matrix.mjs --self-test
   ```

5. 在 PR 中说明修改目的、测试结果和兼容性影响。

核心 Skill 的 G0—G5、G1.5、F/M/S/H、矩阵方向、安全闸门和声称边界属于高影响契约。若认为其中有 Bug，请先提交可复现证据和最小修正建议。

---

## English summary

You do not need to be a TRIZ expert to contribute. Installation feedback, matrix corrections, documentation improvements, compatibility reports and fully fictional or safely de-identified engineering examples are welcome.

Do not submit confidential company material, site photographs, unpublished field data, internal procedures, real identifiers, credentials, copyrighted full-text sources, or unverified performance/patentability/FTO claims. Run the strict Python validator and Node self-test before opening a pull request.
