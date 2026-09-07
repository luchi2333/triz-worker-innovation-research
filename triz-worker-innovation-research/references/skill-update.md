# GitHub 更新与回退

用户说“检查 TRIZ skill 更新”“下载最新版本”“更新这个 skill”时，进入维护模式，不启动课题研究。检查请求只检查；明确更新请求直接执行更新，已有授权不重复询问。不得在研究过程中静默升级。

在需要更新的已安装 skill 目录运行：

```sh
python scripts/update_skill.py --check
python scripts/update_skill.py --apply
python scripts/update_skill.py --rollback "检查更新输出中的 backup 目录"
```

也可从任意目录使用脚本绝对路径并加 `--target "已安装 skill 目录"`。只更新指定的一份；有多个客户端时分别执行并核对结果，不猜测安装目录。维护中的 Git 仓库禁止覆盖，请通过仓库正常版本管理维护。

上游固定为 [luchi2333/triz-worker-innovation-research](https://github.com/luchi2333/triz-worker-innovation-research)，读取 `main` 的最新提交，随后所有元数据与 ZIP 均固定到同一完整提交 SHA。这里的“最新”指 main，不是 GitHub Release 列表。无需 git、gh 或访问令牌；网络需要可访问 GitHub API、raw.githubusercontent.com、codeload.github.com。

- `UPDATE_AVAILABLE`：远端语义版本更高，可执行 apply。
- `UP_TO_DATE`：版本号相同，不覆盖；维护者应为新发布提升版本号。
- `LOCAL_AHEAD`：本机版本更高，保留本机版本，绝不降级。尚未推送的本机版本不会在 GitHub 自动出现。
- `UPDATED`：校验通过并完成替换，输出版本、提交和备份路径。
- `ERROR`：检查具体错误，不报告成功。网络失败、限流、压缩包异常或严格校验失败均不得强行安装。

运行依赖 Python 3.10+；下载包安装前运行其严格校验，当前校验还需要 Node.js。校验的是固定上游提供的代码，会执行其测试，因此只用于信任该上游的用户。严格校验通过不等于工程方案正确，也不是发布者数字签名。

更新前在安装目录旁建立 `.triz-worker-innovation-research-backups`，保留旧版全文件及哈希收据；更新期间检测到文件变化会停止。目录替换失败会尝试立即恢复旧目录。请避免同时运行研究生成或其他维护操作。锁冲突时先核实输出锁文件对应进程是否仍运行，仅在确认已退出后删除遗留锁。

回退要求旧备份与当前安装均未发生额外修改，避免覆盖用户新改动；成功后新版保留在备份中的 `replaced` 子目录。不要手改收据。若进程或系统在两个目录重命名之间中断，旧包仍在备份 `skill` 目录：保留所有目录，核对 receipt.json 的 target 与 before 哈希后恢复，不能删除备份强行重试。回退到没有更新器的旧版后，可用保留下来的 `replaced/scripts/update_skill.py` 指定 `--target` 再检查更新。

验收应分别记录离线回归、真实远端检查/下载、实际安装与回退结果；不能用模拟下载宣称 GitHub 联网成功。
