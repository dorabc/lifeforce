# lifeforce

跨 AI 共用的个人项目经验库 skill。它把可复用的运维、排障、写作和编码结论保存到 Obsidian vault，并用两级索引实现懒加载：session 开始只看地图和当前项目摘要，真正需要时再打开具体笔记。

它不依赖向量数据库或在线服务：Markdown 保存内容，`reindex.py` 生成导航，`rg` 负责兜底检索。Claude Code 可以自动注入上下文和记录 session 指针；Codex、Gemini CLI、Grok 或网页端可以共用同一份 vault，但没有统一的 session hook 时应显式调用。

## 安装

需要 Bash、Python 3。`rg` 用于全文兜底搜索，Claude hook 不需要 `jq`。

```bash
git clone git@github.com:dorabc/lifeforce.git
cd lifeforce
bash install.sh "/你的/Obsidian/vault"
```

vault 路径必须由安装命令传入，安装器不会写死路径。它会：

1. 把规范化后的 vault 绝对路径写入 `~/.lifeforce-vault`。
2. 安装 `.lifeforce/skill`、`reindex.py`、`session-start.sh`、`capture.sh` 和 Codex 历史指针脚本。
3. 创建 `projects/` 并重建初始 `MAP.md`。
4. 把 skill 链接到 `~/.claude/skills/lifeforce`、`~/.codex/skills/lifeforce` 和 `~/.gemini/skills/lifeforce`。
5. 默认向 `~/.claude/settings.json` 幂等追加 SessionStart 和 Stop hook。

不想让安装器修改 Claude 配置时：

```bash
bash install.sh "/你的/Obsidian/vault" --no-claude-hooks
```

已有同名目录或指向其他位置的软链接时，安装器会跳过并提示，不会覆盖它。重新运行安装命令可以更新 vault 中的运行文件和 skill。

## 使用

在任意项目目录中开始工作前，显式调用：

```text
/lifeforce
```

或者直接说“使用 lifeforce 查一下这个项目以前的经验”。常用动作：

```text
/lifeforce                  # 加载地图和当前项目索引
/lifeforce find 证书更新    # 查找并按需打开相关笔记
/lifeforce save             # 把本次 session 的可复用结论沉淀下来
/lifeforce daily            # 处理之前积压的 session 流水
```

安装了 Claude hooks 后，SessionStart 会自动输出 `MAP.md`、匹配到的项目 `_index.md` 和待沉淀数量；Stop hook 只追加 cwd、session id、transcript 路径等指针，不会自动生成低价值笔记。完成有价值的工作后仍建议显式执行 `/lifeforce save`。

### 归档 Codex 历史会话

Codex 的本地 transcript 在 `~/.codex/sessions/`，与 Claude 的 `~/.claude/projects/` 不是同一种存储。当前版本没有给 Codex 自动追加 Stop hook，因此批量处理历史会话时先用只读脚本列出目标工作目录的 session 指针：

```bash
V="$(cat ~/.lifeforce-vault)"
python3 "$V/.lifeforce/codex-sessions.py" "/path/to/project"
```

脚本只输出时间、session id、cwd、来源和 transcript 路径，不打印会话正文。由 AI 按需读取相关 transcript，按 `/lifeforce save` 的规则合并到现有笔记，排除密码、token、cookie、个人查询和一次性业务数据，最后运行 `reindex.py`。这条路径与 Claude 的自动 hook 是两种入口，但落到同一个 vault。

## 在其他项目中使用

不需要把经验文件复制到业务代码仓库。安装一次后，在任意目录调用 skill，lifeforce 会按当前 cwd 匹配 `projects/` 下的项目：

- `/work/oa-backend` 默认匹配项目 `oa`（项目名是路径片段即可）。
- 没有匹配时使用当前 Git 根目录名作为新项目名，并在 vault 中创建对应目录。
- 有多个项目名可能命中，或目录名与经验项目完全不同，可以在 `$V/.lifeforce/projects.json` 写明确映射：

  ```json
  {
    "oa": ["/work/oa-backend", "oa-backend"],
    "写作": ["/Users/me/notes/writing"]
  }
  ```

如果希望 Codex 或 Gemini 每次都自动执行入口，在各自项目的 `AGENTS.md` 或 `GEMINI.md` 加：

```markdown
开始任务前使用 `$lifeforce` 加载当前项目的相关经验；完成后按需使用 `$lifeforce save` 沉淀可复用结论。
```

Grok 和网页端没有统一的本地 skill/hook 机制。把 `skill/SKILL.md` 的内容提供给它，或让它按本 README 中的动作操作，仍然可以读写同一个 vault。

## 数据结构

```text
vault/
├── MAP.md                         # L0：项目地图，脚本生成
├── projects/
│   └── oa/
│       ├── _index.md              # L1：分类和一行摘要，脚本生成
│       ├── database/
│       │   └── 查询员工信息.md     # L2：完整结论
│       └── server/
└── .lifeforce/
    ├── skill/SKILL.md
    ├── reindex.py
    ├── session-start.sh
    ├── capture.sh
    ├── codex-sessions.py
    └── inbox.jsonl                # append-only session 指针
```

经验笔记是普通 Markdown，推荐使用以下 frontmatter：

```yaml
---
id: oa/database/查询员工信息
project: oa
tags: [sql, oracle, hr]
summary: 一行说明这条经验能解决什么问题
created: 2026-08-08
updated: 2026-08-08
hits: 0
---
```

同一主题再次遇到时，更新原笔记的「结论」，在「历史」中追加一行，而不是新建重复笔记。`summary` 用于索引，`hits` 让高频经验靠前；完整命令、环境、验证方式和陷阱放在正文。

修改或新增笔记后重建索引：

```bash
V="$(cat ~/.lifeforce-vault)"
python3 "$V/.lifeforce/reindex.py"
```

每个分类默认最多进入索引 12 条，其余经验仍保留在文件系统中，用 `rg -i --type md "关键词" "$V/projects"` 查找，因此 vault 增长不会让每个 session 都加载全部历史。

## 仓库结构

```text
skill/SKILL.md                    # 实际给 AI 读取的 skill
skill/agents/openai.yaml          # Codex UI 元数据
scripts/reindex.py                # vault 运行时脚本
scripts/session-start.sh          # Claude SessionStart hook
scripts/capture.sh                # Claude Stop hook
scripts/codex-sessions.py         # 列出 Codex 历史 session 指针
scripts/configure_claude_hooks.py # 幂等合并 settings.json
install.sh                        # 安装入口
```

`skill/` 是可复制/链接的 skill 包；README、安装器和运行脚本是仓库级发布内容。安装器会把运行脚本复制到用户指定 vault，因此运行时不依赖仓库路径。

## 验证

```bash
python3 -m py_compile scripts/*.py
bash -n install.sh scripts/*.sh
python3 /path/to/skill-creator/scripts/quick_validate.py skill
```

安装器只会修改用户明确指定的 vault、`~/.lifeforce-vault`、三个 AI skill 链接和 Claude settings（可用 `--no-claude-hooks` 禁止最后一项）。session transcript 不会被复制到 vault，`inbox.jsonl` 只保存定位它所需的元数据。
