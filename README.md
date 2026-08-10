# lifeforce

跨 AI 共用的个人项目经验库 skill。核心目标是“同一个坑不踩第二次”：先检索已验证经验，复用结论并只验证变化部分；解决后合并回同一主题，随着时间推移让同类问题越来越快。推荐把 OpenWiki personal 作为知识层，把 lifeforce 作为 Claude/Codex 的生命周期适配层：OpenWiki 负责个人知识图谱、Markdown 关系、外部来源和可视化，lifeforce 负责当前项目路由、隐私过滤、session 指针、任务级检索和经验闭环。旧版 Obsidian vault 仍可独立工作，也可以一次性迁移到 OpenWiki。

不管使用哪种后端，经验都保存为本地 Markdown。没有 OpenWiki 时，`reindex.py` 生成两级索引、`rg` 负责兜底检索；启用 OpenWiki 后，hook 只读检索 `~/.openwiki/wiki`，不会在每个 prompt 中启动模型或联网。Claude Code 和 Codex 安装后可以自动注入上下文、记录 session 指针；Gemini CLI、Grok 或网页端可显式调用同一套保存规则。

## 与 OpenWiki 集成

OpenWiki 的 `personal` 模式与 lifeforce 的职责边界如下：

| 层 | 负责什么 | 不负责什么 |
|---|---|---|
| lifeforce | Claude/Codex hook、当前项目匹配、任务级候选、session 指针、隐私/去重规则 | 外部来源摄取、知识图谱维护、模型推理 |
| OpenWiki personal | `~/.openwiki/wiki`、OKF frontmatter、跨主题链接、Notion/Gmail/Slack/X/Web Search 等连接器、可视化 | 识别哪个 AI session 值得保存、读取 Claude/Codex transcript |

安装 OpenWiki（当前版本要求 Node.js 22 或更高版本），初始化个人 wiki：

```bash
npm install -g openwiki
openwiki personal --init --language zh-CN
```

已有 lifeforce vault 时先预览，再执行一次非破坏迁移：

```bash
V="$(cat ~/.lifeforce-vault)"
python3 "$V/.lifeforce/migrate-openwiki.py" --dry-run
python3 "$V/.lifeforce/migrate-openwiki.py"
openwiki personal --update --print "整理刚导入的 lifeforce 经验：合并重复主题，保留项目归属、验证方式和陷阱；不要复制 session 原文。"
```

迁移器只读取 `projects/` 下已经由 lifeforce 过滤的 Markdown 叶子笔记，写到 `~/.openwiki/wiki/projects/<项目>/...`；目标文件存在时跳过，不覆盖 OpenWiki 修改。迁移后建议以 OpenWiki 为主，旧 vault 留作备份和 fallback。

常用操作：

```bash
openwiki personal -p "只基于本地 wiki 回答：<问题>"
openwiki ingest all --print
openwiki personal --update --print "<结构化经验>"
openwiki visualize "$HOME/.openwiki/wiki"
```

`save` 不应把完整 transcript 交给 OpenWiki，而应先由 AI 提炼项目、主题、可复用结论、环境、验证和陷阱，再让 `openwiki personal --update --print` 检索并合并到已有 canonical page；没有命中时才在 `projects/<项目>/<分类>/` 创建新叶子页。密码、token、cookie、个人查询、真实客户/员工结果和一次性探索过程不得进入 wiki。OpenWiki 未安装或 wiki 尚未初始化时，lifeforce 会自动回退到旧 vault。

## 安装

需要 Bash、Python 3。`rg` 用于全文兜底搜索，Claude hook 不需要 `jq`；如果启用 OpenWiki，还需要 Node.js 22+ 和 npm。

```bash
git clone git@github.com:dorabc/lifeforce.git
cd lifeforce
bash install.sh "/你的/Obsidian/vault"
```

不想维护 Obsidian vault、只使用 OpenWiki 时：

```bash
bash install.sh --openwiki-only
```

使用旧 vault 的模式需要由安装命令传入 vault 路径，安装器不会写死路径；`--openwiki-only` 模式会把运行时放到 `~/.lifeforce`。它会：

1. 旧 vault 模式把规范化后的路径写入 `~/.lifeforce-vault`；OpenWiki-only 模式写入 `~/.lifeforce-runtime`。
2. 安装 `.lifeforce/skill`、索引脚本、OpenWiki 桥接/迁移脚本、Claude/Codex lifecycle hook 和 Codex 历史 wiki 脚本。
3. 旧 vault 模式创建 `projects/` 并重建初始 `MAP.md`。
4. 把 skill 链接到 `~/.claude/skills/lifeforce`、`~/.codex/skills/lifeforce` 和 `~/.gemini/skills/lifeforce`。
5. 默认向 `~/.claude/settings.json` 和 `~/.codex/hooks.json` 幂等追加 SessionStart、UserPromptSubmit 和 Stop hook。

不想让安装器修改 Claude 配置时：

```bash
bash install.sh "/你的/Obsidian/vault" --no-claude-hooks
```

只关闭 Codex hook：

```bash
bash install.sh "/你的/Obsidian/vault" --no-codex-hooks
```

已有同名目录或指向其他位置的软链接时，安装器会跳过并提示，不会覆盖它。重新运行安装命令可以更新运行文件和 skill。

## 使用

安装了 Claude/Codex hook 后，在任意项目目录开新 session 会自动注入 `MAP.md`、匹配到的项目 `_index.md`、OpenWiki quickstart/项目候选和待沉淀数量；每次提交任务时还会自动检索当前项目的相关叶子笔记与 OpenWiki 页面，不需要再手动执行无参数 `/lifeforce`。仍可显式调用：

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

自动检索会把高相关经验作为已知基线注入上下文，并优先标记为 `canonical` 的已验证页面；`watchlist` 历史页只用于定位原 session。启用 OpenWiki 时会同时检索本地 personal wiki 和旧 vault，不会在 hook 中启动 agent 或联网。对实时数据库只重新查询变化值，不会重复从零分析整套表关系。`find` 仍用于扩大检索范围。Claude/Codex 的 Stop hook 会自动追加 cwd、session id、transcript 路径等指针；这相当于自动收集待归档流水，但不会直接把整段对话写成笔记。完成有价值的工作后，AI 会在最终回复前按 skill 和项目规则自动判断并执行 `$lifeforce save`，把“症状 → 根因 → 修复 → 验证 → 陷阱”合并到项目分类下唯一的 canonical page，不需要用户额外输入 `save`；必要时仍可显式执行。这样可以避免把密码、token、个人查询或一次性过程写入经验库。

新开的 Codex/Claude Code session 会自动加载 hook，直接描述任务即可；安装前已经打开的 session 可以说“使用 lifeforce 查找 `<问题>` 的历史经验”，或执行 `$lifeforce find <关键词>`。Gemini CLI 与 Antigravity/agy 会安装 skill 链接，但没有统一的 lifecycle hook；新开 session 后明确说“使用 lifeforce，先查相似经验再处理”，完成后说“使用 lifeforce save 沉淀本次经验”。

### 归档跨 AI 历史会话

Codex 的本地 transcript 在 `~/.codex/sessions/`，与 Claude 的 `~/.claude/projects/` 不是同一种存储。新安装的 Codex session 会由 Stop hook 自动留下指针；已有历史会话不会重新触发 hook，批量处理它们时用只读脚本列出目标工作目录的 session 指针：

```bash
V="$(cat ~/.lifeforce-vault)"
python3 "$V/.lifeforce/codex-sessions.py" "/path/to/project"
```

要把普通和归档 Codex session 生成成 OpenWiki 的脱敏历史索引：

```bash
python3 "$R/codex-history-wiki.py" --include-archived --force
```

以 Codex 为主干，按同一个项目树融合 Claude Code、Gemini CLI 与 Antigravity/agy（不会删除或替换 Codex 页面）：

```bash
python3 "$R/ai-history-wiki.py" --include-archived --force
```

Codex 刚处理过时可加 `--skip-codex`，只增量重建其他 AI 的历史页；该参数不会删除已有 Codex wiki。Claude Code 排除 subagent 重复记录；Gemini 使用 `.project_root` 归项目；agy 的受保护 `.pb` 不解密，只索引同 ID 下可读的 task、plan、walkthrough 和 report 产物。无法可靠恢复项目路径的 agy session 会进入 `agy-未归类`，等待后续确认。

该命令只写入项目页、主题地图、全量 session 元数据索引和有限长度的需求/最终回答候选，不复制完整 transcript。页面默认标记为 `watchlist`；确认过的结论仍需按 `/lifeforce save` 提升为 canonical experience page。

脚本只输出时间、session id、cwd、来源和 transcript 路径，不打印会话正文。由 AI 按需读取相关 transcript，按 `/lifeforce save` 的规则提炼后优先交给 OpenWiki 合并；没有 OpenWiki 时再合并到现有笔记并运行 `reindex.py`。这条路径与 Claude/Codex 的自动 hook 落到同一个知识层。

## 在其他项目中使用

不需要把经验文件复制到业务代码仓库。安装一次后，在任意目录调用 skill，lifeforce 会按当前 cwd 匹配 `projects/` 下的项目：

- `/work/oa-backend` 默认匹配项目 `oa`（项目名是路径片段即可）。
- 没有匹配时使用当前 Git 根目录名作为新项目名，并在 vault 中创建对应目录。
- 有多个项目名可能命中，或目录名与经验项目完全不同，可以在 `$V/.lifeforce/projects.json` 写明确映射：

  ```json
  {
    "oa": ["/work/oa-backend", "oa-backend"],
    "写作": ["/work/notes/writing"]
  }
  ```

如果关闭了 Codex hook，或使用没有 lifecycle hook 的 Gemini，在各自项目的 `AGENTS.md` 或 `GEMINI.md` 加：

```markdown
开始任务前使用 `$lifeforce` 加载当前项目的相关经验；完成后按需使用 `$lifeforce save` 沉淀可复用结论。
```

Grok 和网页端没有统一的本地 skill/hook 机制。把 `skill/SKILL.md` 的内容提供给它，或让它按本 README 中的动作操作；有本地 OpenWiki CLI 时使用 OpenWiki personal，没有时仍可读写同一个 vault。

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
    ├── prompt-context.py
    ├── prompt-context.sh
    ├── openwiki-context.py
    ├── migrate-openwiki.py
    ├── capture.sh
    ├── codex-session-start.sh
    ├── codex-prompt-submit.sh
    ├── codex-stop.sh
    ├── codex-sessions.py
    ├── codex-history-wiki.py
    ├── ai-history-wiki.py
    └── inbox.jsonl                # append-only session 指针
```

OpenWiki-only 模式的知识树位于 `~/.openwiki/wiki`：

```text
wiki/
├── quickstart.md                 # L0：知识库入口
├── themes.md                     # L1：跨项目主题入口
├── projects/
│   └── <项目>/
│       ├── _index.md             # L1：项目入口
│       ├── <分类>/
│       │   └── <经验>.md          # L2：可复用 canonical experience
│       └── history/               # 历史候选，不是最终经验
│           ├── demand-signals.md
│           └── answer-candidates.md
└── sources/                       # session 审计索引
```

`projects/` 根目录只放项目子目录；同一主题只维护一篇 canonical experience。解决新问题后把症状、根因、修复、验证和陷阱合并回原页面，下一次优先读取该页面。

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

OpenWiki 的已验证页面使用 `confidence: canonical`；历史候选使用 `confidence: watchlist`，检索时只把后者当作定位原 session 的线索。

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
scripts/session-start.sh          # 生成共享的 SessionStart 上下文
scripts/prompt-context.py         # 按当前用户任务检索经验候选
scripts/prompt-context.sh         # Claude UserPromptSubmit 包装器
scripts/openwiki-context.py       # OpenWiki 本地只读检索桥
scripts/migrate-openwiki.py       # 旧经验到 OpenWiki 的一次性迁移器
scripts/codex-session-start.sh    # Codex SessionStart JSON 包装器
scripts/codex-prompt-submit.sh    # Codex UserPromptSubmit JSON 包装器
scripts/codex-stop.sh             # Codex Stop hook 包装器
scripts/capture.sh                # Claude/Codex Stop 指针采集
scripts/codex-sessions.py         # 列出 Codex 历史 session 指针
scripts/codex-history-wiki.py     # 生成脱敏的 OpenWiki 历史索引
scripts/ai-history-wiki.py        # 统一导入 Claude/Gemini/agy，并可先刷新 Codex
scripts/configure_claude_hooks.py # 幂等合并 settings.json
scripts/configure_codex_hooks.py  # 幂等合并 Codex hooks.json
install.sh                        # 安装入口
```

`skill/` 是可复制/链接的 skill 包；README、安装器和运行脚本是仓库级发布内容。安装器会把运行脚本复制到用户指定 vault，因此运行时不依赖仓库路径。

## 验证

```bash
python3 -m py_compile scripts/*.py
bash -n install.sh scripts/*.sh
python3 /path/to/skill-creator/scripts/quick_validate.py skill
```

安装器只会修改用户明确指定的 vault（或 OpenWiki-only 模式的 `~/.lifeforce`）、`~/.lifeforce-vault`/`~/.lifeforce-runtime`/`~/.lifeforce-backend`、三个 AI skill 链接、Claude settings 和 Codex hooks（可分别用 `--no-claude-hooks`、`--no-codex-hooks` 禁止）。session transcript 不会被复制到 vault 或 OpenWiki，`inbox.jsonl` 只保存定位它所需的元数据；OpenWiki 的安装、初始化和迁移由用户显式执行。
