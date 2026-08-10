---
name: lifeforce
description: 跨 AI 的个人项目经验库。优先从 OpenWiki personal wiki 和当前项目索引加载可复用经验，按需检索和更新运维、排障、写作、编码知识；session 结束前自动判断并沉淀可复用结论。用户说 /lifeforce、"以前是怎么弄的"、"查一下历史经验"、"记一下这次"、"沉淀"、"归档"，或开始运维、排障、改配置、写代码前需要历史上下文时使用。
---

# lifeforce — 个人经验库

目标：同一个坑不踩第二次，并且同类问题随着经验累积越来越快。把一次 session 中发现的非显然事实、可复用命令和可靠结论沉淀为 OpenWiki personal wiki 中可检索、可链接的 canonical experience；下一次遇到相似问题时，先复用已验证结论，只重新验证会变化的部分，不从零重做分析。lifeforce 继续负责 Claude/Codex 的生命周期 hook、当前项目路由、隐私过滤和旧 vault 兼容。

## 运行时约定

安装时由用户指定 vault，安装器把绝对路径写入 `~/.lifeforce-vault`。每次使用前先执行：

```bash
V="$(cat ~/.lifeforce-vault 2>/dev/null || true)"
BACKEND="$(cat ~/.lifeforce-backend 2>/dev/null || true)"
if [ "$BACKEND" = "openwiki" ]; then V=""; fi
R="$(cat ~/.lifeforce-runtime 2>/dev/null || true)"
if [ -z "$R" ] && [ -n "$V" ]; then R="$V/.lifeforce"; fi
if [ -z "$R" ]; then R="$HOME/.lifeforce"; fi
```

- `V` 为空或目录不存在：说明旧 vault 未安装。若 `~/.openwiki/wiki` 存在，仍可使用 OpenWiki 模式；否则提示用户执行 `bash /path/to/lifeforce/install.sh /path/to/obsidian-vault` 或 `bash /path/to/lifeforce/install.sh --openwiki-only`，不要猜路径，也不要写死路径。
- 路径可能含空格和中文，所有 shell 变量都加双引号。
- OpenWiki 的知识根目录固定为 `W="$HOME/.openwiki/wiki"`。hook 只对它做本地只读检索，不在每个 prompt 中启动 OpenWiki agent、连接器或网络请求。
- 旧版经验写在 `$V`，session 指针写在 `$R`；不要把 session 原文、密码、token 或业务数据写入 `inbox.jsonl` 或 OpenWiki 页面。
- Claude Code 或 Codex 安装了 hook 时，session 启动会自动注入旧 vault 地图和 OpenWiki quickstart/项目候选，提交任务时会检索两边，session 结束会自动记录待归档指针；其他 AI 没有统一的本地 hook，仍按本文件的显式流程执行。

## 新 session 与当前 session

- **新 Codex/Claude Code session**：安装后重新打开一个 session，启动 hook 会自动加载项目入口；之后直接描述任务即可。每次任务提交还会自动检索相似经验，不需要先输入命令。
- **安装前已经打开的 Codex/Claude Code session**：进程可能还没有重新加载 skill/hook。直接说“使用 lifeforce 查找 `<问题>` 的历史经验”，或显式执行 `$lifeforce find <关键词>`；下一个新 session 起自动生效。
- **Gemini CLI 与 Antigravity/agy**：安装器会链接 skill，但不承诺 lifecycle hook。新开 session 后说“使用 lifeforce，先查相似经验再处理”，或执行其支持的 skill 调用；完成后说“使用 lifeforce save 沉淀本次经验”。
- **只想查看 wiki**：从 `W/quickstart.md` 进入，或在 `W` 下运行 `rg -i --type md "<关键词>"`。`history/` 只用于定位旧 session，真正复用时优先读取项目分类目录中的 canonical experience。

无论哪种 AI，普通使用顺序都是：先检索 → 复用 canonical → 只验证变化部分 → 解决后合并保存。不要要求用户记住复杂命令。

## OpenWiki 集成（推荐路径）

OpenWiki 的 `personal` 模式负责个人知识图谱、Markdown 关系、OKF frontmatter、可视化和外部来源摄取；lifeforce 负责“什么时候读取”“当前项目是什么”“哪些 session 值得沉淀”以及“优先复用哪条经验”。两者不是二选一：OpenWiki 是知识层，lifeforce 是 AI 生命周期适配层。

先安装并初始化 OpenWiki（Node.js 需满足 OpenWiki 当前要求）：

```bash
npm install -g openwiki
openwiki personal --init --language zh-CN
bash /path/to/lifeforce/install.sh --openwiki-only
```

已有 lifeforce vault 时，只做一次非破坏迁移：

```bash
V="$(cat ~/.lifeforce-vault)"
python3 "$V/.lifeforce/migrate-openwiki.py" --dry-run
python3 "$V/.lifeforce/migrate-openwiki.py"
openwiki personal --update --print "整理刚导入的 lifeforce 经验：合并重复主题，保留项目归属、验证方式和陷阱；不要复制 session 原文。"
```

迁移脚本只复制已经经过 lifeforce 规则过滤的叶子笔记，写入 `~/.openwiki/wiki/projects/<项目>/...`，目标页面已存在时跳过，不会覆盖 OpenWiki 中的修改。迁移后以 OpenWiki 为主；旧 vault 保留作备份和无 OpenWiki 环境的 fallback。

常用 OpenWiki 操作：

- 查找：先让 hook 注入候选；需要扩大范围时，在 `~/.openwiki/wiki` 做只读 `rg`，或运行 `openwiki personal -p "只基于本地 wiki 回答：<问题>"`。
- 沉淀：先在当前 session 中提炼结论，再运行 `openwiki personal --update --print "<结构化经验>"`。要求 OpenWiki 先查找同主题页面，更新唯一 canonical page，不要为同一主题重复建文。
- 外部来源：按需运行 `openwiki ingest all --print`，再让 `openwiki personal --update --print` 合并；不要在 lifeforce hook 中自动联网摄取。
- 可视化：运行 `openwiki visualize "$HOME/.openwiki/wiki"` 查看知识节点图。

沉淀给 OpenWiki 的消息至少包含：项目、主题、可直接复用结论、环境、验证方式、陷阱和来源 session。不要把密码、token、cookie、个人查询、真实客户/员工结果、完整 transcript 或一次性探索过程传进去。OpenWiki 页面使用 OKF `type/title/description/tags`；项目经验必须放在 `projects/<项目>/<分类>/<经验>.md` 这类树形路径中，`projects/<项目>/_index.md` 只做入口，`history/` 只存待复核的历史线索，不能代替经验页；跨项目规律应提升到 `themes.md` 或其他 canonical 页面，并用 Markdown 链接表达关系。

如果 OpenWiki 未安装或 `~/.openwiki/wiki` 尚未初始化，所有动作自动回退到下面的旧 vault 流程，不要为了查经验临时安装或联网。

## 存储结构与懒加载

```text
$V/
├── MAP.md                         # L0：每个项目一行
├── projects/
│   └── oa/
│       ├── _index.md              # L1：分类和一行摘要
│       ├── database/
│       │   └── 查询员工信息.md     # L2：完整经验
│       └── server/
└── .lifeforce/
    ├── skill/SKILL.md
    ├── reindex.py                  # 从叶子笔记重建索引
    ├── session-start.sh            # 生成共享的 SessionStart 上下文
    ├── prompt-context.py           # 按当前用户任务检索经验候选
    ├── prompt-context.sh           # Claude UserPromptSubmit 包装器
    ├── openwiki-context.py         # OpenWiki 本地只读检索桥
    ├── migrate-openwiki.py         # 旧经验到 OpenWiki 的一次性迁移器
    ├── capture.sh                  # Claude/Codex Stop 指针脚本
    ├── codex-session-start.sh      # Codex SessionStart JSON 包装器
    ├── codex-prompt-submit.sh      # Codex UserPromptSubmit JSON 包装器
    ├── codex-stop.sh               # Codex Stop 包装器
    ├── codex-sessions.py           # Codex 历史 session 指针脚本
    ├── codex-history-wiki.py       # 全量 Codex 历史到 OpenWiki 的脱敏索引器
    ├── ai-history-wiki.py          # Claude/Gemini/agy + Codex 的统一历史入口
    └── inbox.jsonl                  # 只存 session 指针，append-only
```

OpenWiki 模式使用同样的懒加载原则，但根目录是 `$W="$HOME/.openwiki/wiki"`：

```text
$W/
├── quickstart.md                 # L0：知识库入口
├── themes.md                     # L1：跨项目主题入口
├── projects/
│   └── <项目>/
│       ├── _index.md             # L1：项目入口，不放完整结论
│       ├── <分类>/
│       │   └── <经验>.md          # L2：canonical experience，未来优先复用
│       └── history/               # 只放历史 session 候选/审计线索
│           ├── demand-signals.md
│           └── answer-candidates.md
└── sources/
    ├── codex-history.md
    └── codex-sessions.md
```

不要把所有项目经验直接放进 `projects/` 根目录，也不要把历史 session 候选误当成已经验证的经验。分类目录按需创建；没有内容时不要创建空目录。

旧 vault 模式的运行文件位于 `$V/.lifeforce`；`--openwiki-only` 模式位于 `$R`（通常是 `~/.lifeforce`），经验不落到 vault。

索引是派生数据，不能手改。笔记改完后执行：

```bash
python3 "$V/.lifeforce/reindex.py"
```

`MAP.md` 只回答“有哪些项目”；项目 `_index.md` 只回答“有哪些分类和经验摘要”；完整结论只在叶子笔记里。索引每个分类默认最多列 12 条，其余用 `rg` 找，避免 vault 变大后每次加载全部内容。

叶子笔记必须有以下 frontmatter 字段：

```yaml
---
id: oa/database/查询员工信息
project: oa
tags: [sql, oracle, hr]
summary: 员工表和状态字段的可复用查询口径
created: 2026-08-08
updated: 2026-08-08
hits: 0
---
```

`summary` 必填且一行不超过 40 字；`hits` 只增不减，用于让高频经验在索引中优先显示。分类目录按需创建，允许无限层级；不要预先建立空分类。

## 项目解析

优先读取可选的 `$V/.lifeforce/projects.json`。格式如下，键是项目名，值是能出现在 cwd 中的路径片段：

```json
{
  "oa": ["/work/oa-backend", "oa-backend"],
  "写作": ["/notes/writing"]
}
```

没有映射时，用当前 cwd 的目录名和 `projects/` 下的项目名做大小写不敏感匹配；优先完整路径段，其次最长子串。仍然匹配不上时，把当前 Git 根目录名作为新项目名；有歧义时再向用户确认。

## 任务复用优先

这是 lifeforce 的核心闭环。对查询数据、跨表分析、排障、改配置、部署等非显然任务，先复用历史结论，再补验证：

1. SessionStart 提供当前项目索引和 OpenWiki quickstart/项目候选；UserPromptSubmit 会按用户任务自动检索两边，并把少量高相关候选注入上下文。
2. 先找 `canonical`/已验证项目经验，再看 `watchlist` 历史线索。命中 canonical 后，先读取并采用其中的「结论」「可直接复用结果」「验证」和「陷阱」，不要把同一套表关系或排障路径从零重做。
3. 只重新验证会变化的部分：实时数值、当前服务状态、版本、权限和外部依赖必须复核；若历史前提仍成立，不要重复做整套探索。若与用户明确纠正、`AGENTS.md` 或当前实测冲突，以后者为准，并更新旧经验。
4. 没有命中或验证失败时才完整分析；解决后必须把“症状 → 根因 → 修复 → 验证 → 陷阱”整理为一篇 canonical experience，合并到同主题旧页，而不是只留下 session 指针。
5. 每次复用或更新经验都保留来源 session 和适用环境。这样历史不是静态归档，而是下一次排障的已知基线；高频主题通过更新同一 canonical page 逐步变快。

## 四个动作

### `/lifeforce`（无参数）：加载上下文

1. 如果 `$V` 存在，读取 `$V/MAP.md`；如果 `W` 存在，读取 `W/quickstart.md` 或由 hook 提供的 OpenWiki 启动上下文。
2. 按上面的规则确定项目；旧 vault 存在时读取 `$V/projects/<项目>/_index.md`，不要递归读取所有叶子笔记；OpenWiki 页面按需打开 `W/projects/<项目>/...`，优先项目分类下的 canonical experience。
3. 如果 `$R/inbox.jsonl` 存在，检查其中与当前项目或 cwd 相关的 `done:false` 条目，报告未沉淀数量；只在需要判断时读取对应的 transcript 指针。
4. 向用户简短说明找到的分类和可能相关的经验；不要因为索引命中就自动把所有笔记全文塞进上下文。

### `/lifeforce find <关键词>`：检索经验

1. 先查当前项目 `_index.md` 和 OpenWiki quickstart/主题摘要；优先打开该项目分类目录中的 canonical experience，再查看 `history/` 候选。
2. 未命中时分别执行 `rg -i --type md "关键词" "$V/projects"` 和 `rg -i --type md "关键词" "$W"`（只对存在的根目录执行），再按命中文件判断相关性；不要假设索引完整。
3. 真正采用旧 vault 经验后，把它的 frontmatter `hits` 加 1 并更新 `updated`；OpenWiki 页面不要手工伪造 hits，按其页面与来源规则更新。
4. 先复述可直接复用的结论，再说明适用环境和陷阱；`history/` 和 `sources/` 是审计证据，不是当前操作指令；不确定的内容标明不确定性。

### `/lifeforce save`：沉淀本次 session

1. 先用关键词在 `W` 搜索同主题 OpenWiki 页面；若没有 OpenWiki，再在 `$V/projects` 搜索；同一主题只维护一篇，不要重复建文。
2. 找到已有笔记时：更新「结论」区为当前可靠口径；「历史」区只追加一行 `- YYYY-MM-DD · <ai> · <本次补充>`；更新 `updated`，保留 `id`、`created` 和已有历史。
   - 如果本次 session 包含用户对旧做法的明确纠正，后来的纠正视为当前权威：从「结论」中移除旧做法，必要时在「陷阱」标为已废弃；旧做法只能留在「历史」作为审计记录，不能和新做法并列成两个可选方案。
   - 如果新旧做法只在不同前提下分别成立，必须把适用条件写清；如果条件不明，不要擅自保留旧做法，先标记不确定并请求确认。
3. 找不到时按下面模板新建。目录不存在就创建，项目目录用解析出的项目名，主题归入合适的分类子目录；不要在 `projects/` 根目录直接创建经验页。
4. 只记录非显然事实、可复用命令/SQL/配置、根因、验证方式和陷阱；不要记录一次性探索、读代码即可知道的内容或秘密。
   - 如果本次产出了跨表分析、最终查询结果或报告口径，必须保存可复用的表关系、SQL、筛选条件、结论和验证时间。
   - 对员工、客户等敏感数据，只保存查询方法和字段语义，不保存姓名、工号、邮箱、真实结果行或其他个人数据。
5. 如果 `~/.openwiki/wiki` 存在，优先把整理后的结构化经验交给 OpenWiki：

   ```bash
   openwiki personal --update --print "项目：<项目>；主题：<主题>；结论：<结论>；环境：<环境>；验证：<验证>；陷阱：<陷阱>。请先合并同主题页面，只保存可复用知识，不保存 session 原文或秘密。"
   ```

   要求它先检索并更新现有同主题 canonical page；没有命中时才在 `projects/<项目>/<分类>/` 下创建新叶子页，并补充来源和关系链接。不要让 OpenWiki 读取或复制完整 transcript。OpenWiki 调用失败时，按下面的旧 vault 模板保存。
6. 旧 vault fallback 路径：执行 `python3 "$R/reindex.py"`。
7. 将本次对应的 `$R/inbox.jsonl` 条目更新为 `done:true`。不要重写其他条目；处理并发时保持 JSONL 一行一条。

笔记模板：

```markdown
---
id: oa/database/查询员工信息
project: oa
tags: [sql, oracle, hr]
summary: 一行说明这条经验能解决什么问题
created: 2026-08-08
updated: 2026-08-08
hits: 0
---

# 查询员工信息

## 可直接复用结果
<下次同类任务可以直接采用的最终结论或报告口径；实时数据只保存查询定义，不保存个人结果行>

## 结论（可直接复用）
<命令、SQL、配置或操作步骤>

## 环境
<版本、库、服务器或账号别名；没有就删除本节>

## 验证
<如何确认结论有效；没有就删除本节>

## 陷阱
- <容易误判或重复踩坑的地方>

## 历史
- 2026-08-08 · claude-code · 首次整理
```

### `/lifeforce daily`：处理积压

读取 `$R/inbox.jsonl` 中 `done:false` 的条目，按项目逐条判断是否值得沉淀。需要上下文时才打开 `transcript` 指向的记录，不要一次性加载全部 session；不值得沉淀的条目标记 `done:true` 并写 `skip` 原因。

Stop hook 自动记录的只是定位 session 的元数据，不等于自动生成经验笔记。历史索引中的 `watchlist` 页面只是检索线索，不能直接当作可执行经验。是否值得沉淀、如何合并旧结论、哪些内容必须排除，必须经过 `/lifeforce save` 或 `/lifeforce daily` 的语义判断；不得因为 hook 自动触发就把整段 transcript 复制进 vault。

如果本次 session 已经产生非显然、可复用的结论，或用户明确纠正了旧做法，AI 不要等待用户输入 `save`；在最终回复前主动执行 `$lifeforce save`，并把结论合并到项目分类下唯一的 canonical page。如果没有可复用结论，不创建空笔记；由 Stop hook 留下指针，后续 `daily` 再标记为 `skip` 即可。

## 触发与跨 AI 使用

- **Claude Code**：安装器会把 skill 链接到 `~/.claude/skills/lifeforce`，并默认追加 SessionStart/UserPromptSubmit/Stop hook。启动自动加载旧 vault 索引和 OpenWiki 候选，任务提交时自动检索两边；仍可直接说 `/lifeforce find 关键词` 做更宽的检索。
- **Codex**：安装器链接到 `~/.codex/skills/lifeforce`，并默认把 SessionStart/UserPromptSubmit/Stop hook 幂等写入 `~/.codex/hooks.json`。新 session 自动加载旧 vault 索引和 OpenWiki 候选，每个用户任务自动检索两边，Stop 自动留下 session 指针；不需要手动调用无参数 `$lifeforce`。需要查具体主题时调用 `$lifeforce` 做更宽的检索；完成有价值的工作后按需 `$lifeforce save`，优先用 `openwiki personal --update --print` 保存。若用 `--no-codex-hooks`，再在项目 `AGENTS.md` 中补充启动和保存约定。
- **跨 AI 历史会话**：运行 `python3 "$R/ai-history-wiki.py" --include-archived --force`，以 Codex 历史为主干，按同一个项目树融合 Claude Code、Gemini CLI 与 Antigravity/agy；这不会删除或替换 Codex 页面。Codex 来源是 `~/.codex/sessions`/`archived_sessions`；Claude 来源是 `~/.claude/projects`（排除 subagent）；Gemini 来源是 `~/.gemini/tmp/*/chats`；agy 来源是 `~/.gemini/antigravity-ide/conversations` 和 `brain`。脚本只写入脱敏后的项目/session 索引和有限长度候选，不复制 transcript；受保护的 agy `.pb` 不解密，只索引对应的 user-facing brain 产物。Codex 已更新时可加 `--skip-codex`，含义仅是本次不重复扫描 Codex，已有 Codex wiki 保持不变。按需复核原 session 后执行 `/lifeforce save`，把结论提升为 canonical page。
- **Gemini CLI**：安装器链接到 `~/.gemini/skills/lifeforce`；在 `GEMINI.md` 加同样的入口说明即可。没有 hook 的环境不能承诺 session 自动执行。
- **Grok 或网页端**：没有统一的本地 skill/hook 目录，复制本文件内容或让其按 README 的动作流程操作；有本地 OpenWiki CLI 时使用 personal wiki，没有时仍然共用旧 vault。

Claude Code 和 Codex 的 hook 能做到 session 自动注入和结束流水记录；其他 AI 的显式调用是可靠路径。hook 只记录 cwd、session id 和 transcript 路径，不自动生成低价值笔记，也不会自动联网调用 OpenWiki 连接器。
