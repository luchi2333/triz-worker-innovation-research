# GitHub 更新与回退

用户说“检查 TRIZ skill 更新”“下载最新版本”“更新这个 skill”时，进入维护模式，不启动课题研究。检查请求只检查；明确更新请求直接执行更新，已有授权不重复询问。不得在研究过程中静默升级。

在需要更新的已安装 skill 目录运行：

```sh
python scripts/update_skill.py --check
python scripts/update_skill.py --apply
python scripts/update_skill.py --rollback "检查更新输出中的 backup 目录"
python scripts/update_skill.py --recover "中断安装的 backup 目录" --target "原安装目录"
python scripts/update_skill.py --check --channel main
```

也可从任意目录使用脚本绝对路径并加 `--target "已安装 skill 目录"`。只更新指定的一份；有多个客户端时分别执行并核对结果，不猜测安装目录。维护中的 Git 仓库禁止覆盖，请通过仓库正常版本管理维护。

上游固定为 [luchi2333/triz-worker-innovation-research](https://github.com/luchi2333/triz-worker-innovation-research)，默认读取最新非草稿、非预发布的稳定 Release，再解析 tag 到完整提交。发布包必须有 release-manifest.json，安装前核对 archive_sha256、版本、提交及逐文件哈希，再执行严格校验。只有明确指定 `--channel main` 才直接下载开发分支固定提交；稳定 Release 缺包不会自动改用 main。无需 git、gh 或令牌，需访问 GitHub API、原始文件及下载域名。

- `UPDATE_AVAILABLE`：远端语义版本更高，可执行 apply。
- `UP_TO_DATE`：版本号相同，不覆盖；维护者应为新发布提升版本号。
- `LOCAL_AHEAD`：本机版本更高，保留本机版本，绝不降级。尚未推送的本机版本不会在 GitHub 自动出现。
- `UPDATED`：校验通过并完成替换，输出版本、提交和备份路径。release_ready=false 表示旧 Release 缺少新版更新器要求的发布资产。
- `ERROR`：检查具体错误，不报告成功。网络失败、限流、压缩包异常或严格校验失败均不得强行安装。

运行依赖 Python 3.10+；下载包严格校验还需 Node.js。检查代码会执行固定上游的测试，只适用于信任该上游的用户。同一 GitHub 来源的校验清单检查一致性，不能代替独立数字签名，也不能单独防止账号被入侵。严格校验不证明工程方案正确。

更新前在安装目录旁建立 `.triz-worker-innovation-research-backups`，保留旧版全文件及哈希收据；更新期间检测到文件变化会停止。目录替换失败会尝试立即恢复旧目录。请避免同时运行研究生成或其他维护操作。锁冲突时先核实输出锁文件对应进程是否仍运行，仅在确认已退出后删除遗留锁。

回退要求旧备份与当前安装未发生额外修改，成功后新版保留在 replaced。若系统在两个目录重命名之间中断，使用可用副本中的更新器加 `--recover`、`--target`：它核对 prepared 日志和哈希，仅在目标缺失时恢复旧目录；新版已经完整安装时补全收据；其他情况不覆盖文件。锁冲突会给出路径和 PID，确认进程已退出后才处理遗留锁，不靠超时推定旧进程死亡。回退到无更新器的旧版后，可使用 replaced/scripts/update_skill.py 指定原 target。

## 维护者发布

打标签不等于创建 Release。[GitHub Release API](https://docs.github.com/en/rest/releases/releases) 独立管理发布资产。维护者先验证待发布提交与版本匹配，再运行 `scripts/package_release.py --output <新目录> --commit <完整SHA>`，生成确定性 ZIP 和逐文件清单。包内只含 skill，不含现场报告、测试输出或备份。

仓库的 Publish validated stable release 工作流通过手动指定已有 tag 启动：严格校验、生成实际图文样例、LibreOffice 渲染、打包全部完成后创建带资产的 Release。发布需用户授权；这个文档不是自动对外发布指令。发布后读回 tag/commit/资产并运行 stable 检查。旧版本没有新打包脚本时应使用维护端打包工具验证旧 tag 内容，不在旧标签下替换新版文件。

验收应分别记录离线回归、真实远端检查/下载、实际安装与回退结果；不能用模拟下载宣称 GitHub 联网成功。
