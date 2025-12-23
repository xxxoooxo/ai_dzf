# Git 分支隔离 + 选择性提交 + 打标签 + 安全清理（面试版流程）

适用场景：不想把当前改动推到主分支（`main`），但希望把一份“可运行的代码快照”单独保存，并用标签标记版本（如 `version1`），同时清理本地缓存/生成物且不影响虚拟环境与业务数据。

> 环境假设：Windows + PowerShell；命令中的路径建议用双引号包裹；尽量使用 `/` 作为分隔符（Windows 也支持）。

---

## 0. 核心原则（面试可讲）

- **隔离**：任何实验性改动先建分支，避免污染 `main`。
- **可控**：只提交“能运行所需的代码”，不提交构建缓存/依赖目录/运行数据。
- **可回退**：所有危险操作先预演（preview），再执行（apply）。
- **可定位**：用 tag 把关键节点（版本）固定到具体 commit。
- **安全**：避免把 `api_key`/token 写入提交历史（除非明确允许且仅本地保存）。

---

## 1. 看清当前状态（只读）

```powershell
git branch --show-current
git status -sb
git diff --name-only
```

目标：确认当前在哪个分支、有哪些未提交改动、改动规模是否包含大量生成物（例如 `ui/.next/`、`node_modules/`、`.idea/`、运行缓存目录等）。

---

## 2. 创建并切换到独立分支（隔离改动）

分支名建议语义化、短、可读（例如 `no-rag-read-file`）。

```powershell
git switch -c "no-rag-read-file"
```

说明：此操作只在本地创建分支并切换，不会影响远端，也不会改动 `main` 的提交历史。

---

## 3. 选择性提交（只提交“必要代码”，排除缓存）

### 3.1 先决定“提交策略”

- **推荐（选择性提交）**：只提交源码/脚本/配置；不提交 `node_modules/`、`.next/`、运行缓存、日志、临时文件。
- **不推荐（快照式全提交）**：把所有变更（含缓存/依赖）都提交，提交体积会膨胀、后续维护困难。

### 3.2 暂存你要保存的文件（示例）

用 `git add -- <paths...>` 精确选择，避免 `git add .` 把缓存一锅端。

```powershell
git add -- "main1.py" "src/start_server.py" "src/tools.py" "src/run.bat"
git add -- "src/file_rag/main.py" "src/file_rag/core/llms.py"
git add -- "graphs_examples/document_call.py"
```

### 3.3 检查暂存区（非常重要）

```powershell
git diff --cached --name-status
git diff --cached --stat
```

面试可强调：**在 commit 前必须 review 暂存区**，避免把大文件/秘钥/缓存带进去。

---

## 4. 提交（commit）

```powershell
git commit -m "version1: no-rag-read-file"
```

提交信息建议包含：目的 + 版本点 + 关键变更摘要。

---

## 5. 打标签（tag 固化版本）

```powershell
git tag "version1"
```

检查分支与 tag 是否指向同一个提交：

```powershell
git show-ref --heads --tags | findstr /i "no-rag-read-file refs/tags/version1"
```

---

## 6. 安全清理工作区（保留 `.venv/` 和 `storage/`）

目标：把“未提交改动”与“无关生成物”清掉，保持工作区干净；同时保留虚拟环境与业务数据目录。

### 6.1 先预演（只看不删）

```powershell
git status -sb
git clean -nd -e ".venv/" -e "storage/"
```

### 6.2 丢弃未提交改动 + 删除未跟踪文件（执行）

```powershell
git restore --source=HEAD --staged --worktree -- .
git clean -fd -e ".venv/" -e "storage/"
```

结果：代码回到当前分支 `HEAD` 的状态；未跟踪文件被清掉（但 `.venv/`、`storage/` 保留）。

> 注意：如果某些缓存目录已被 Git 跟踪（tracked），`git clean` 无法清理它们；这类问题需要通过 `.gitignore` 或调整仓库结构解决。

---

## 7. 常用回退/排错命令（面试加分点）

### 7.1 查看提交与标签

```powershell
git log --oneline --decorate -n 20
git show "version1"
```

### 7.2 切回主分支（不合并、不推送）

```powershell
git switch "main"
```

### 7.3 撤销暂存（未 commit 前）

```powershell
git restore --staged -- .
```

### 7.4 丢弃单文件改动（未 commit 前）

```powershell
git restore -- "src/start_server.py"
```

---

## 8. 面试表达模板（30 秒）

> 我会先用 `git switch -c <branch>` 从 `main` 分出实验分支；然后用 `git add -- <paths>` 做选择性暂存，`git diff --cached` 审核暂存区，确保不把缓存/依赖/秘钥提交进去；提交后用 `git tag <version>` 固化版本点。最后用 `git restore ...` + `git clean` 清理工作区，同时通过 `-e` 排除 `.venv/` 和业务数据目录，保证不影响可运行环境和数据。

---

## 9. 实战：VSCode 推送失败（Connection reset/443 连接失败）怎么排查与修复

### 9.1 现象

- VSCode 内 `git push` 报错：`Recv failure: Connection was reset`、`Failed to connect to github.com port 443` 等。

### 9.2 排查顺序（由快到慢）

1. 确认远端地址和协议是否正确：

```powershell
git remote -v
```

2. 查看 Git 代理配置（global 和 repo-local 都要看）：

```powershell
git config --global --get http.proxy
git config --global --get https.proxy
git config --local --get http.proxy
git config --local --get https.proxy
```

3. 打开网络细节日志定位卡点（DNS / 443 连接 / TLS / 认证）：

```powershell
$env:GIT_CURL_VERBOSE=1; git ls-remote https://github.com/<owner>/<repo>.git
```

如果日志显示 DNS 正常但卡在 `Trying <ip>:443...` 或频繁 reset，通常是直连被阻断/不稳定，需要走代理。

### 9.3 修复：给 Git 配代理（优先 repo-local，避免污染全局）

示例（HTTP CONNECT 代理）：

```powershell
git config --local http.proxy http://127.0.0.1:7897
git config --local https.proxy http://127.0.0.1:7897
```

然后重试推送：

```powershell
git push -u origin <branch>
```

补充：
- 如果你的代理是 SOCKS5（而非 HTTP CONNECT），把代理地址改成：`socks5h://127.0.0.1:<port>`。
- 只对当前仓库生效的回滚方式：

```powershell
git config --local --unset http.proxy
git config --local --unset https.proxy
```

---

## 10. 实战：误把 `ui/node_modules` / `ui/.next` 提交进仓库（如何治理）

### 10.1 典型症状

- `git status`/`git diff` 变得极慢，动辄上万文件变更。
- 运行一次 `next dev` 就产生大量 `.next` 变更；安装依赖会产生大量 `node_modules` 变更。
- 即使 `.gitignore` 里写了忽略规则，`git status` 仍然显示这些目录的改动（原因：**它们已经被 Git 跟踪 tracked 了**）。

### 10.2 诊断（确认是否被跟踪）

1. 确认 `.gitignore` 是否已有忽略规则（示例）：

```powershell
rg -n "(^|/)ui/(\\.next|node_modules)" ".gitignore"
```

2. 统计当前被 Git 跟踪的数量（Windows PowerShell）：

```powershell
git ls-files "ui/.next" | Measure-Object | Select-Object -ExpandProperty Count
git ls-files "ui/node_modules" | Measure-Object | Select-Object -ExpandProperty Count
```

### 10.3 修复（从索引移除，但保留本地文件）

关键点：用 `--cached` 只影响 Git 索引，不会删除你本地的文件夹。

```powershell
git rm -r --cached -- "ui/node_modules" "ui/.next"
git commit -m "chore(ui): 停止跟踪构建产物与依赖目录"
git push
```

### 10.4 之后如何“只提交 UI 源码”

```powershell
git add -- "ui/src" "ui/next-env.d.ts"
git diff --cached --name-status
git commit -m "feat(ui): 更新交互与渲染"
git push
```

说明：
- `.gitignore` 负责“忽略未跟踪文件”；对已跟踪文件无效，必须配合 `git rm --cached`。
- 仓库变更较大时建议在分支上做，并在 PR 里明确说明：依赖与构建产物已从版本库移除，拉取后需要自行 `install`/`build`。
