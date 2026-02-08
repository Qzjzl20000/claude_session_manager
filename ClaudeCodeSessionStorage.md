# Claude Code 会话存储机制详解

> 本文档详细说明了 Claude Code 的会话数据存储结构，用于理解会话文件的组织方式和相互关系。

## 目录

- [1. 概览](#1-概览)
- [2. 目录结构](#2-目录结构)
- [3. Session ID 的使用](#3-session-id-的使用)
- [4. 文件类型详解](#4-文件类型详解)
- [5. 索引机制](#5-索引机制)
- [6. 会话生命周期](#6-会话生命周期)
- [7. 残留文件分析](#7-残留文件分析)

---

## 1. 概览

Claude Code 采用**分布式存储策略**，将不同类型的会话数据存储在 `~/.claude` 目录的不同子目录中。

### 存储位置总览

| 目录 | 用途 | 文件格式 |
|------|------|----------|
| `~/.claude/debug/` | 实时对话日志 | `.txt` |
| `~/.claude/projects/` | 完整会话数据 | `.jsonl` |
| `~/.claude/file-history/` | 文件历史快照 | 目录 |
| `~/.claude/todos/` | TodoWrite 任务数据 | `.json` |
| `~/.claude/session-env/` | 会话环境配置 | 目录 |
| `~/.claude/history.jsonl` | 全局历史记录索引 | `.jsonl` |
| `~/.claude/paste-cache/` | 粘贴缓存 | 文件 |

---

## 2. 目录结构

```
~/.claude/
├── debug/                          # 实时对话日志
│   └── <sessionId>.txt            # 每个会话一个文件
│
├── projects/                       # 按项目分类的会话数据
│   └── <project-path>/            # 项目路径（编码后）
│       ├── <sessionId>.jsonl      # 完整会话数据
│       └── sessions-index.json    # 项目级会话索引
│
├── file-history/                   # 文件历史快照
│   └── <sessionId>/               # 每个会话一个目录
│       └── <timestamp>-<file>     # 文件快照
│
├── todos/                          # TodoWrite 任务数据
│   └── <sessionId>-agent-<subagentId>.json
│
├── session-env/                    # 会话环境目录
│   └── <sessionId>/               # 每个会话一个目录
│
├── history.jsonl                   # 全局历史记录索引
└── paste-cache/                    # 粘贴缓存
```

---

## 3. Session ID 的使用

Session ID（UUID 格式，如 `84a8a596-4e49-4482-ba3a-bbb9fb46a817`）是会话的唯一标识符，在多个位置被引用：

### 3.1 文件名中的引用

| 位置 | 格式 | 示例 |
|------|------|------|
| `debug/` | `<sessionId>.txt` | `84a8a596-4e49-4482-ba3a-bbb9fb46a817.txt` |
| `projects/` | `<sessionId>.jsonl` | `84a8a596-4e49-4482-ba3a-bbb9fb46a817.jsonl` |
| `file-history/` | `<sessionId>/` | 目录名 |
| `session-env/` | `<sessionId>/` | 目录名 |
| `todos/` | `<sessionId>-agent-<subagentId>.json` | `84a8a596-4e49-4482-ba3a-bbb9fb46a817-agent-a9df8fb.json` |

### 3.2 文件内容中的引用

| 文件 | 引用方式 |
|------|----------|
| `history.jsonl` | 每条记录包含 `sessionId` 字段 |
| `sessions-index.json` | 每个条目以 session ID 为键 |
| `.jsonl` 会话文件 | 每条消息包含 `sessionId` 字段 |

---

## 4. 文件类型详解

### 4.1 Debug 日志 (`~/.claude/debug/<sessionId>.txt`)

**用途**：存储实时对话的 DEBUG 级别日志

**内容**：
- API 请求/响应
- 工具调用详情
- 系统消息

**特点**：
- 每个会话一个文件
- 文件大小随对话增长
- 可用于调试和问题排查

### 4.2 完整会话数据 (`~/.claude/projects/<project>/<sessionId>.jsonl`)

**用途**：存储会话的完整消息历史

**格式**：JSON Lines（每行一个 JSON 对象）

**内容示例**：
```json
{"role": "user", "content": "帮我写一个函数", "timestamp": "..."}
{"role": "assistant", "content": "好的，我来帮你...", "timestamp": "..."}
```

**特点**：
- 按项目分组存储
- 可用于会话恢复
- 包含完整的上下文

### 4.3 文件历史 (`~/.claude/file-history/<sessionId>/`)

**用途**：存储会话过程中访问/修改的文件快照

**结构**：
```
<sessionId>/
├── 1738567890123-file1.py
├── 1738567890456-file2.py
└── ...
```

**特点**：
- 时间戳命名防止冲突
- 可能占用大量空间
- 删除会话时常被遗漏

### 4.4 Todo 数据 (`~/.claude/todos/<sessionId>-agent-<subagentId>.json`)

**用途**：存储 TodoWrite 创建的任务列表

**内容**：
```json
{
  "todos": [
    {"content": "...", "status": "completed", "activeForm": "..."},
    ...
  ]
}
```

### 4.5 索引文件

#### `~/.claude/history.jsonl`
全局历史记录，按时间顺序记录所有会话的基本信息。

#### `~/.claude/projects/<project>/sessions-index.json`
项目级索引，记录该项目的所有会话元数据：
- Session ID
- 文件路径
- 修改时间
- 首次提示
- 会话摘要
- 消息数量
- Git 分支信息

---

## 5. 索引机制

Claude Code 使用**多层次索引机制**：

### 5.1 全局索引

**文件**：`~/.claude/history.jsonl`

**用途**：按时间顺序记录所有会话

**更新时机**：每次创建/修改会话时

### 5.2 项目级索引

**文件**：`~/.claude/projects/<project>/sessions-index.json`

**用途**：记录特定项目的所有会话

**内容**：
```json
{
  "<sessionId>": {
    "filePath": "/path/to/session.jsonl",
    "mtime": 1738567890123,
    "firstPrompt": "用户的第一条消息",
    "summary": "会话摘要",
    "messageCount": 42,
    "createdAt": "2026-01-15T10:30:00Z",
    "gitBranch": "main",
    "projectPath": "/path/to/project"
  }
}
```

### 5.3 索引同步问题

⚠️ **重要**：索引文件可能不会自动更新，导致：
- 索引中记录的会话文件已被删除
- 实际存在的会话文件未被索引记录

---

## 6. 会话生命周期

### 6.1 创建会话

1. 生成新的 Session ID（UUID）
2. 创建 `~/.claude/debug/<sessionId>.txt`
3. 创建 `~/.claude/projects/<project>/<sessionId>.jsonl`
4. 创建 `~/.claude/file-history/<sessionId>/` 目录
5. 更新 `history.jsonl`
6. 更新 `sessions-index.json`

### 6.2 会话进行中

1. 每次交互追加到 `debug/<sessionId>.txt`
2. 每次交互追加到 `projects/<project>/<sessionId>.jsonl`
3. 访问文件时创建快照到 `file-history/<sessionId>/`
4. 使用 TodoWrite 时创建 `todos/<sessionId>-*.json`

### 6.3 删除会话（理想情况）

应该删除以下内容：
1. `~/.claude/debug/<sessionId>.txt`
2. `~/.claude/file-history/<sessionId>/`（整个目录）
3. `~/.claude/projects/<project>/<sessionId>.jsonl`
4. `~/.claude/todos/<sessionId>-*.json`
5. `~/.claude/session-env/<sessionId>/`
6. 从 `history.jsonl` 中删除对应记录
7. 从 `sessions-index.json` 中删除对应条目

---

## 7. 残留文件分析

### 7.1 常见残留位置

| 位置 | 原因 | 影响 |
|------|------|------|
| `~/.claude/file-history/<sessionId>/` | 删除逻辑未覆盖 | 占用磁盘空间 |
| `~/.claude/session-env/<sessionId>/` | 删除逻辑未覆盖 | 空目录残留 |
| `~/.claude/todos/<sessionId>-*.json` | 任务未完成时删除 | 任务数据残留 |
| `history.jsonl` 中的记录 | 索引未更新 | 索引与实际不同步 |
| `sessions-index.json` 中的条目 | 索引未更新 | 索引与实际不同步 |

### 7.2 残留原因分析

1. **删除逻辑不完整**
   - 原始删除命令可能只删除了部分位置
   - 某些目录（如 file-history）被忽略

2. **索引更新机制缺陷**
   - 删除会话后，索引文件可能未被同步更新
   - 导致"幽灵会话"（索引存在但文件已删除）

3. **并发操作**
   - 多个进程同时操作可能导致部分文件残留

4. **原子写入机制**
   - 使用临时文件写入后再重命名
   - 中断可能导致临时文件残留

---

## 8. 关键安全原则

### 8.1 禁止"反向删除"

❌ **危险操作**：删除"没有索引"的文件

**原因**：
- 索引可能不完整或过时
- 可能误删正在使用的 session
- 可能误删其他重要文件

### 8.2 正向删除

✅ **安全操作**：只删除明确指定的 session ID 相关的文件

**要求**：
- 必须由用户提供 session ID
- 通过精确匹配文件名中的 session ID
- 逐一验证每个文件是否匹配

### 8.3 索引同步

删除后必须更新索引文件，防止：
- 索引与实际文件不同步
- 后续操作基于错误数据

### 8.4 项目路径验证

删除前验证项目路径，防止误删其他项目的 session。

---

## 9. 总结

Claude Code 的会话存储机制具有以下特点：

| 优点 | 缺点 |
|------|------|
| 数据分类清晰 | 需要多文件同步删除 |
| 易于按类型管理 | 索引更新不及时 |
| 支持会话恢复 | 残留文件难以清理 |
| 按项目分组 | 删除逻辑复杂 |

**完整的会话清理需要同时操作多个位置**，这是设计安全删除脚本时必须考虑的核心问题。
