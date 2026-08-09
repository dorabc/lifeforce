---
name: lifeforce
description: 跨 AI 的个人项目经验库。按当前工作目录加载 Obsidian vault 中的项目索引，按需检索和更新运维、排障、写作、编码经验，并在 session 结束后把可复用结论沉淀为结构化笔记。用户说 /lifeforce、"以前是怎么弄的"、"查一下历史经验"、"记一下这次"、"沉淀"、"归档"，或开始运维、排障、改配置、写代码前需要历史上下文时使用。
---

# lifeforce — 个人经验库

目标：同一个坑不踩第二次。把一次 session 中发现的非显然事实、可复用命令和可靠结论，保存到 Obsidian vault；下次只加载当前项目的导航，需要时再打开具体笔记。

## 运行时约定

安装时由用户指定 vault，安装器把绝对路径写入 `~/.lifeforce-vault`。每次使用前先执行：

```bash
V="$(cat ~/.lifeforce-vault 2>/dev/null || true)"
```

- `V` 为空或目录不存在：说明未安装。提示用户执行 `bash /path/to/lifeforce/install.sh /path/to/obsidian-vault`，不要猜路径，也不要写死路径。
- 路径可能含空格和中文，所有 shell 变量都加双引号。
- 只在 `$V` 下读写经验；不要把 session 原文、密码、token 或业务数据写入 `inbox.jsonl`。
- Claude Code 安装了 hook 时，session 启动会自动注入地图和当前项目索引；其他 AI 没有统一的本地 hook，仍按本文件的显式流程执行。

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
    ├── session-start.sh            # Claude SessionStart hook
    ├── capture.sh                  # Claude Stop hook
    ├── codex-sessions.py           # Codex 历史 session 指针脚本
    └── inbox.jsonl                  # 只存 session 指针，append-only
```

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

## 四个动作

### `/lifeforce`（无参数）：加载上下文

1. 读取 `$V/MAP.md`。
2. 按上面的规则确定项目；存在时读取 `$V/projects/<项目>/_index.md` 的索引内容，不要递归读取所有叶子笔记。
3. 检查 `$V/.lifeforce/inbox.jsonl` 中与当前项目或 cwd 相关的 `done:false` 条目，报告未沉淀数量；只在需要判断时读取对应的 transcript 指针。
4. 向用户简短说明找到的分类和可能相关的经验；不要因为索引命中就自动把所有笔记全文塞进上下文。

### `/lifeforce find <关键词>`：检索经验

1. 先查当前项目 `_index.md` 的摘要；命中后打开对应叶子笔记。
2. 未命中时执行 `rg -i --type md "关键词" "$V/projects"`，再按命中文件判断相关性；不要假设索引完整。
3. 真正采用一篇经验后，把它的 frontmatter `hits` 加 1，并更新 `updated`；只看索引摘要不增加 `hits`。
4. 先复述可直接复用的结论，再说明适用环境和陷阱；历史区是审计记录，不是当前操作指令；不确定的内容标明不确定性。

### `/lifeforce save`：沉淀本次 session

1. 先用关键词在 `$V/projects` 搜索同主题笔记；同一主题只维护一篇，不要重复建文。
2. 找到已有笔记时：更新「结论」区为当前可靠口径；「历史」区只追加一行 `- YYYY-MM-DD · <ai> · <本次补充>`；更新 `updated`，保留 `id`、`created` 和已有历史。
   - 如果本次 session 包含用户对旧做法的明确纠正，后来的纠正视为当前权威：从「结论」中移除旧做法，必要时在「陷阱」标为已废弃；旧做法只能留在「历史」作为审计记录，不能和新做法并列成两个可选方案。
   - 如果新旧做法只在不同前提下分别成立，必须把适用条件写清；如果条件不明，不要擅自保留旧做法，先标记不确定并请求确认。
3. 找不到时按下面模板新建。目录不存在就创建，项目目录用解析出的项目名。
4. 只记录非显然事实、可复用命令/SQL/配置、根因、验证方式和陷阱；不要记录一次性探索、读代码即可知道的内容或秘密。
5. 执行 `python3 "$V/.lifeforce/reindex.py"`。
6. 将本次对应的 `inbox.jsonl` 条目更新为 `done:true`。不要重写其他条目；处理并发时保持 JSONL 一行一条。

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

读取 `inbox.jsonl` 中 `done:false` 的条目，按项目逐条判断是否值得沉淀。需要上下文时才打开 `transcript` 指向的记录，不要一次性加载全部 session；不值得沉淀的条目标记 `done:true` 并写 `skip` 原因。

## 触发与跨 AI 使用

- **Claude Code**：安装器会把 skill 链接到 `~/.claude/skills/lifeforce`，并默认追加 SessionStart/Stop hook。可直接说 `/lifeforce`、`/lifeforce find 关键词`、`/lifeforce save` 或 `/lifeforce daily`。
- **Codex**：安装器链接到 `~/.codex/skills/lifeforce`。可显式说“使用 lifeforce 查一下历史经验”或调用 `$lifeforce`；需要自动入口时，在项目的 `AGENTS.md` 加一行“开始任务前使用 `$lifeforce` 加载相关经验，完成后按需 `$lifeforce save`”。
- **Codex 历史会话**：Codex transcript 通常在 `~/.codex/sessions/`，不是 Claude 的项目目录。批量处理某个项目时先运行 `python3 "$V/.lifeforce/codex-sessions.py" "/path/to/project"`；它只列出 session 指针，不打印正文。按需读取相关 transcript，去重后执行 `/lifeforce save`，不要把原始 transcript 复制到 vault。
- **Gemini CLI**：安装器链接到 `~/.gemini/skills/lifeforce`；在 `GEMINI.md` 加同样的入口说明即可。没有 hook 的环境不能承诺 session 自动执行。
- **Grok 或网页端**：没有统一的本地 skill/hook 目录，复制本文件内容或让其按 README 的动作流程操作；仍然可以共用同一个 vault。

只有 Claude Code 的 hook 能做到真正的 session 自动注入和结束流水记录；其他 AI 的显式调用是可靠路径。hook 只记录 cwd、session id 和 transcript 路径，不自动生成低价值笔记。
