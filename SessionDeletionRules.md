# Claude Code Session 删除规则

> 本文档定义了安全、完整地删除 Claude Code 会话的规则和流程。

## 目录

- [1. 核心原则](#1-核心原则)
- [2. 删除目标清单](#2-删除目标清单)
- [3. 删除流程](#3-删除流程)
- [4. 预览格式](#4-预览格式)
- [5. 验证与回滚](#5-验证与回滚)
- [6. 禁止的操作](#6-禁止的操作)

---

## 1. 核心原则

### 1.1 正向删除原则

✅ **只删除明确指定的 Session**

- 必须由用户提供准确的 Session ID
- 通过精确匹配文件名/路径中的 Session ID
- 禁止基于"是否在索引中"来判断是否删除

### 1.2 完整性原则

✅ **一次删除，全部清理**

删除一个 Session 必须同时清理所有相关位置，防止残留。

### 1.3 索引同步原则

✅ **删除后必须更新索引**

确保索引文件与实际文件状态保持一致。

### 1.4 安全验证原则

✅ **删除前必须验证**

- 验证 Session ID 格式
- 验证项目路径
- 验证文件是否存在
- 预览待删除文件列表

### 1.5 禁止反向删除

❌ **绝不删除"没有索引"的文件**

- 索引可能不完整或过时
- 可能误删正在使用的 Session
- 可能误删其他重要文件

---

## 2. 删除目标清单

### 2.1 必须删除的文件/目录

按删除优先级排序：

| 优先级 | 路径 | 说明 |
|--------|------|------|
| 1 | `~/.claude/debug/<sessionId>.txt` | 主对话日志 |
| 2 | `~/.claude/projects/<project>/<sessionId>.jsonl` | 完整会话数据 |
| 3 | `~/.claude/file-history/<sessionId>/` | 文件历史快照目录 |
| 4 | `~/.claude/todos/<sessionId>-*.json` | TodoWrite 任务数据 |
| 5 | `~/.claude/session-env/<sessionId>/` | 会话环境目录 |

### 2.2 必须更新的索引文件

| 索引文件 | 更新操作 |
|----------|----------|
| `~/.claude/history.jsonl` | 删除包含该 sessionId 的行 |
| `~/.claude/projects/<project>/sessions-index.json` | 删除该 sessionId 的条目 |

### 2.3 可选删除的文件

以下文件如果存在且**仅与该 Session 相关**，可以删除：

- `~/.claude/paste-cache/` 中与该 Session 相关的缓存文件

---

## 3. 删除流程

### 3.1 完整流程图

```
┌─────────────────────────────────────────────────────────────┐
│                      用户发起删除请求                          │
│                  提供 Session ID 和可选的项目路径               │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      阶段 1: 输入验证                          │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 1. 验证 Session ID 格式（UUID）                           │ │
│  │ 2. 如果提供了项目路径，验证其存在性                        │ │
│  │ 3. 如果未提供项目路径，尝试从索引中查找                    │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────┬───────────────────────────────┘
                               │
                    验证失败？  │  验证通过
                    ┌──────────┴──────────┐
                    ▼                     ▼
              ❌ 错误退出        ┌─────────────────────────────────┐
                                │        阶段 2: 文件发现              │
                                │  ┌──────────────────────────────┐ │
                                │  │ 扫描所有可能的位置：            │ │
                                │  │ - debug/                      │ │
                                │  │ - projects/                   │ │
                                │  │ - file-history/               │ │
                                │  │ - todos/                      │ │
                                │  │ - session-env/                │ │
                                │  └──────────────────────────────┘ │
                                └─────────────────────────────────┘
                                               │
                                               ▼
                                ┌─────────────────────────────────┐
                                │        阶段 3: 危险检测            │
                                │  ┌──────────────────────────────┐ │
                                │  │ 检查是否在 Obsidian vault 内   │ │
                                │  │ 检查是否有 .obsidian 目录      │ │
                                │  │ 检查是否有用户文件             │ │
                                │  └──────────────────────────────┘ │
                                └─────────────────────────────────┘
                                               │
                                               ▼
                                ┌─────────────────────────────────┐
                                │        阶段 4: 预览展示            │
                                │  ┌──────────────────────────────┐ │
                                │  │ 分类显示待删除文件：            │ │
                                │  │ ✅ Claude 会话文件             │ │
                                │  │ ⚠️ 需要确认的文件               │ │
                                │  │ 🚫 禁止删除的文件               │ │
                                │  └──────────────────────────────┘ │
                                └─────────────────────────────────┘
                                               │
                                               ▼
                                ┌─────────────────────────────────┐
                                │        阶段 5: 用户确认            │
                                │  显示完整文件路径和统计信息        │ │
                                │  请求用户确认                     │
                                └─────────────────────────────────┘
                                               │
                                    用户拒绝？  │  用户确认
                                    ┌──────────┴──────────┐
                                    ▼                     ▼
                              ❌ 取消退出        ┌─────────────────────────────────┐
                                                │        阶段 6: 执行删除            │
                                                │  ┌──────────────────────────────┐ │
                                                │  │ 1. 备份索引文件（用于回滚）     │ │
                                                │  │ 2. 删除文件和目录              │ │
                                                │  │ 3. 更新索引文件                │ │
                                                │  └──────────────────────────────┘ │
                                                └─────────────────────────────────┘
                                                               │
                                                               ▼
                                                ┌─────────────────────────────────┐
                                                │        阶段 7: 验证与日志          │
                                                │  ┌──────────────────────────────┐ │
                                                │  │ 验证所有文件已删除              │ │
                                                │  │ 验证索引已更新                 │ │
                                                │  │ 记录操作日志                   │ │
                                                │  └──────────────────────────────┘ │
                                                └─────────────────────────────────┘
                                                               │
                                                               ▼
                                                        ✅ 完成
```

### 3.2 详细步骤

#### 阶段 1: 输入验证

```bash
# 验证 Session ID 格式
if [[ ! "$sessionId" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
    echo "错误: 无效的 Session ID 格式"
    exit 1
fi

# 验证项目路径（如果提供）
if [[ -n "$projectPath" && ! -d "$projectPath" ]]; then
    echo "错误: 项目路径不存在: $projectPath"
    exit 1
fi
```

#### 阶段 2: 文件发现

```bash
# 定义要搜索的基础目录
BASE_DIR="$HOME/.claude"

# 收集所有相关文件
declare -a FILES_TO_DELETE
declare -a DIRS_TO_DELETE

# 1. Debug 日志
if [[ -f "$BASE_DIR/debug/$sessionId.txt" ]]; then
    FILES_TO_DELETE+=("$BASE_DIR/debug/$sessionId.txt")
fi

# 2. 项目会话文件（需要确定项目路径）
if [[ -n "$projectPath" ]]; then
    # 编码项目路径（与 Claude Code 相同的方式）
    encodedPath=$(echo "$projectPath" | sed 's/\//%2F/g')
    if [[ -f "$BASE_DIR/projects/$encodedPath/$sessionId.jsonl" ]]; then
        FILES_TO_DELETE+=("$BASE_DIR/projects/$encodedPath/$sessionId.jsonl")
    fi
fi

# 3. 文件历史目录
if [[ -d "$BASE_DIR/file-history/$sessionId" ]]; then
    DIRS_TO_DELETE+=("$BASE_DIR/file-history/$sessionId")
fi

# 4. Todo 文件
for todoFile in "$BASE_DIR/todos/$sessionId"-*.json; do
    if [[ -f "$todoFile" ]]; then
        FILES_TO_DELETE+=("$todoFile")
    fi
done

# 5. Session 环境目录
if [[ -d "$BASE_DIR/session-env/$sessionId" ]]; then
    DIRS_TO_DELETE+=("$BASE_DIR/session-env/$sessionId")
fi
```

#### 阶段 3: 危险检测

```bash
# 检查是否在 Obsidian vault 内
check_obsidian_danger() {
    local file="$1"
    local dir=$(dirname "$file")

    # 检查父目录中是否有 .obsidian 目录
    while [[ "$dir" != "/" && "$dir" != "." ]]; do
        if [[ -d "$dir/.obsidian" ]]; then
            return 0  # 在 Obsidian vault 内
        fi
        dir=$(dirname "$dir")
    done
    return 1  # 不在 Obsidian vault 内
}

# 检查所有待删除文件
for file in "${FILES_TO_DELETE[@]}" "${DIRS_TO_DELETE[@]}"; do
    if check_obsidian_danger "$file"; then
        echo "警告: 检测到 Obsidian vault 相关文件"
        echo "文件: $file"
        # 标记为需要额外确认
    fi
done
```

#### 阶段 4-5: 预览与确认

详见下一节"预览格式"。

#### 阶段 6: 执行删除

```bash
# 备份索引文件
backup_index() {
    local indexFile="$1"
    if [[ -f "$indexFile" ]]; then
        cp "$indexFile" "${indexFile}.backup.$(date +%Y%m%d%H%M%S)"
    fi
}

# 更新 history.jsonl
update_history_index() {
    local historyFile="$BASE_DIR/history.jsonl"
    backup_index "$historyFile"

    # 删除包含该 sessionId 的行
    local tempFile=$(mktemp)
    grep -v "\"sessionId\":\"$sessionId\"" "$historyFile" > "$tempFile"
    mv "$tempFile" "$historyFile"
}

# 更新 sessions-index.json
update_sessions_index() {
    local indexFile="$BASE_DIR/projects/$encodedPath/sessions-index.json"
    backup_index "$indexFile"

    # 使用 jq 删除该 sessionId 的条目
    if command -v jq &> /dev/null; then
        jq "del(.\"$sessionId\")" "$indexFile" > "${indexFile}.tmp"
        mv "${indexFile}.tmp" "$indexFile"
    fi
}
```

---

## 4. 预览格式

### 4.1 预览输出模板

```
═══════════════════════════════════════════════════════════════
                    Claude Code Session 删除预览
═══════════════════════════════════════════════════════════════

Session ID:    84a8a596-4e49-4482-ba3a-bbb9fb46a817
项目路径:      /Users/username/Projects/MyProject

───────────────────────────────────────────────────────────────────
                        将要删除的文件
───────────────────────────────────────────────────────────────────

📁 Claude 会话文件 (5 项):

  1. ~/.claude/debug/84a8a596-4e49-4482-ba3a-bbb9fb46a817.txt
     └─ 大小: 1.2 MB

  2. ~/.claude/projects/Users%2Fusername%2FProjects%2FMyProject/84a8a596-4e49-4482-ba3a-bbb9fb46a817.jsonl
     └─ 大小: 2.4 MB

  3. ~/.claude/file-history/84a8a596-4e49-4482-ba3a-bbb9fb46a817/
     └─ 包含 12 个文件快照

  4. ~/.claude/todos/84a8a596-4e49-4482-ba3a-bbb9fb46a817-agent-a9df8fb.json
     └─ 大小: 456 B

  5. ~/.claude/session-env/84a8a596-4e49-4482-ba3a-bbb9fb46a817/
     └─ 空目录

───────────────────────────────────────────────────────────────────

📊 统计信息:
  • 文件数量: 3
  • 目录数量: 2
  • 预计释放空间: ~3.6 MB

───────────────────────────────────────────────────────────────────

⚠️  注意事项:
  • 此操作将永久删除上述文件和目录
  • 删除后无法恢复（除非有备份）
  • 将更新相关索引文件

───────────────────────────────────────────────────────────────────

确认删除? [yes/No]: _
```

### 4.2 详细目录内容预览

对于包含多个文件的目录（如 file-history），可以选择显示详细内容：

```
📂 ~/.claude/file-history/84a8a596-4e49-4482-ba3a-bbb9fb46a817/
   ├── 1738567890123-src%2Fmain.py
   ├── 1738567901245-src%2Futils.py
   ├── 1738567912346-src%2Fconfig.json
   └── ... (共 12 个文件)
```

---

## 5. 验证与回滚

### 5.1 删除后验证

```bash
verify_deletion() {
    local sessionId="$1"
    local failed=0

    echo "验证删除结果..."

    # 检查文件是否已删除
    for file in "${FILES_TO_DELETE[@]}"; do
        if [[ -e "$file" ]]; then
            echo "❌ 文件仍然存在: $file"
            failed=1
        fi
    done

    for dir in "${DIRS_TO_DELETE[@]}"; do
        if [[ -d "$dir" ]]; then
            echo "❌ 目录仍然存在: $dir"
            failed=1
        fi
    done

    # 检查索引是否已更新
    if grep -q "\"sessionId\":\"$sessionId\"" "$BASE_DIR/history.jsonl" 2>/dev/null; then
        echo "⚠️  history.jsonl 中仍存在该 session 的记录"
        failed=1
    fi

    if [[ $failed -eq 0 ]]; then
        echo "✅ 删除成功，所有文件和索引已清理"
    else
        echo "❌ 删除未完全成功，请检查上述错误"
        return 1
    fi
}
```

### 5.2 回滚机制

```bash
rollback_index() {
    local indexFile="$1"
    local backupFile="${indexFile}.backup.*"

    # 查找最新的备份
    local latestBackup=$(ls -t $backupFile 2>/dev/null | head -1)

    if [[ -n "$latestBackup" && -f "$latestBackup" ]]; then
        echo "正在回滚索引文件: $indexFile"
        cp "$latestBackup" "$indexFile"
        echo "✅ 索引文件已回滚"
    else
        echo "❌ 未找到备份文件，无法回滚"
        return 1
    fi
}
```

---

## 6. 禁止的操作

### 6.1 绝对禁止

❌ **禁止删除"没有索引"的文件**

这是最危险的操作，原因：
- 索引可能不完整或过时
- 可能误删正在使用的 Session
- 可能误删用户的正常文件

❌ **禁止使用通配符批量删除**

```bash
# 危险！不要这样做
rm -rf ~/.claude/debug/*
rm -rf ~/.claude/file-history/*
```

❌ **禁止删除整个 `.claude` 目录**

```bash
# 危险！不要这样做
rm -rf ~/.claude
```

### 6.2 需要额外确认的操作

⚠️ **删除属于 Obsidian vault 的文件**

如果检测到待删除文件在 Obsidian vault 内，必须：
1. 明确警告用户
2. 要求用户额外确认
3. 记录到操作日志

⚠️ **删除非预期的文件**

如果发现了未预期的文件（不在标准位置），必须：
1. 显示文件详细信息
2. 要求用户明确确认
3. 提供"跳过"选项

---

## 7. 使用示例

### 7.1 基本用法

```bash
# 删除指定 Session
./claude-session-delete.sh 84a8a596-4e49-4482-ba3a-bbb9fb46a817

# 删除指定项目的 Session
./claude-session-delete.sh 84a8a596-4e49-4482-ba3a-bbb9fb46a817 \
    --project /Users/username/Projects/MyProject

# 预览模式（不实际删除）
./claude-session-delete.sh 84a8a596-4e49-4482-ba3a-bbb9fb46a817 \
    --preview-only

# 强制删除（跳过确认，谨慎使用）
./claude-session-delete.sh 84a8a596-4e49-4482-ba3a-bbb9fb46a817 \
    --yes
```

### 7.2 获取 Session ID

```bash
# 列出所有 Session
./claude-session-delete.sh --list

# 搜索特定项目的 Session
./claude-session-delete.sh --list --project /path/to/project

# 按日期搜索
./claude-session-delete.sh --list --since "2026-01-01"
```

---

## 8. 配置文件

### 8.1 配置文件位置

`~/.claude-delete-rules.conf`

### 8.2 配置示例

```bash
# Claude 删除规则配置

# 默认项目路径（可选）
DEFAULT_PROJECT_PATH="/Users/username/Projects"

# 是否在删除前自动创建备份
AUTO_BACKUP=true

# 备份保留天数
BACKUP_RETENTION_DAYS=7

# 是否记录详细日志
VERBOSE_LOGGING=true

# 日志文件路径
LOG_FILE="$HOME/.claude-deletion.log"

# 额外的保护路径（这些路径下的文件不会被删除）
PROTECTED_PATHS=(
    "$HOME/ObsidianVault"
    "$HOME/Documents"
)
```

---

## 9. 总结

| 要点 | 说明 |
|------|------|
| **核心原则** | 正向删除，只删除明确指定的 Session |
| **完整性** | 必须删除所有相关位置的文件 |
| **安全性** | 预览、确认、验证、回滚 |
| **禁止** | 绝不删除"没有索引"的文件 |
| **索引同步** | 删除后必须更新索引文件 |

遵循这些规则，可以安全、完整地删除 Claude Code Session，避免残留文件和误删问题。
