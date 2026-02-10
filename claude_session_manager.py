#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude 会话管理器 v2.4
用于管理 Claude Code 的历史对话记录
"""

import json
import shutil
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# ============ 数据模型 ============


class SessionData:
    """会话数据模型"""

    def __init__(self):
        self.claude_dir = Path.home() / '.claude'
        self.history_file = self.claude_dir / 'history.jsonl'
        self.projects_dir = self.claude_dir / 'projects'
        self.debug_dir = self.claude_dir / 'debug'
        self.session_env_dir = self.claude_dir / 'session-env'
        self.file_history_dir = self.claude_dir / 'file-history'
        self.todos_dir = self.claude_dir / 'todos'
        self.shell_snapshots_dir = self.claude_dir / 'shell-snapshots'
        self.sessions = []
        self.active_session_ids = set()

    def load_sessions(self):
        """加载所有会话记录"""
        self.sessions = []

        if not self.history_file.exists():
            return self.sessions

        with open(self.history_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        session = json.loads(line)
                        self.sessions.append(session)
                    except json.JSONDecodeError:
                        continue

        return self.sessions

    def get_active_sessions(self, minutes: int = 10) -> set:
        """获取最近 N 分钟内活跃的 Session ID"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=minutes)
        cutoff_ts = cutoff.timestamp()

        active = set()

        # 方法1: 检查 debug 文件修改时间
        if self.debug_dir.exists():
            for debug_file in self.debug_dir.glob("*.txt"):
                try:
                    mtime = debug_file.stat().st_mtime
                    if mtime > cutoff_ts:
                        sid = debug_file.stem
                        active.add(sid)
                except:
                    pass

        # 方法2: 检查对话文件最后消息时间
        if self.projects_dir.exists():
            for project_dir in self.projects_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                for conv_file in project_dir.glob("*.jsonl"):
                    try:
                        last_ts = 0
                        with open(conv_file, 'r') as f:
                            for line in f:
                                if line.strip():
                                    try:
                                        msg = json.loads(line)
                                        ts_str = msg.get('timestamp', '')
                                        if ts_str:
                                            dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                            ts = dt.timestamp()
                                            if ts > last_ts:
                                                last_ts = ts
                                    except:
                                        pass

                        if last_ts > cutoff_ts:
                            sid = conv_file.stem
                            active.add(sid)
                    except:
                        pass

        self.active_session_ids = active
        return active

    def get_all_session_ids(self) -> set:
        """从 history.jsonl 获取所有有效的 sessionId"""
        session_ids = set()
        for session in self.sessions:
            sid = session.get('sessionId')
            if sid:
                session_ids.add(sid)
        return session_ids

    def get_conversation_file(self, session_id: str,
                              project_path: str) -> Path:
        """获取对话文件路径"""
        # Claude 的目录命名规则：将 / 替换为 -
        encoded_project = project_path.replace('/', '-')
        project_dir = self.projects_dir / encoded_project
        return project_dir / f"{session_id}.jsonl"

    def get_conversation_file_size(self, session_id: str,
                                   project_path: str) -> int:
        """获取对话文件大小"""
        conv_file = self.get_conversation_file(session_id, project_path)
        if conv_file.exists():
            return conv_file.stat().st_size
        return 0

    def load_conversation(self, session_id: str, project_path: str) -> list:
        """加载对话内容"""
        conv_file = self.get_conversation_file(session_id, project_path)
        if not conv_file.exists():
            return []

        messages = []
        with open(conv_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        continue
        return messages

    def get_session_title(self, session_id: str, project_path: str) -> str:
        """获取会话名称（优先 customTitle，否则第一条用户消息）"""
        conv_file = self.get_conversation_file(session_id, project_path)
        if not conv_file.exists():
            return None

        custom_title = None
        first_user_message = None

        try:
            with open(conv_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            msg = json.loads(line)
                            # 查找 customTitle 字段
                            if msg.get('customTitle'):
                                custom_title = msg.get('customTitle')
                                return custom_title
                            # 查找第一条用户消息
                            if first_user_message is None:
                                if msg.get('type') == 'user' and msg.get(
                                        'userType') == 'external':
                                    message_obj = msg.get('message', {})
                                    if message_obj:
                                        content = message_obj.get(
                                            'content', '')
                                        if isinstance(content,
                                                      str) and content.strip():
                                            first_user_message = content.strip(
                                            )
                        except json.JSONDecodeError:
                            continue
        except Exception:
            pass

        # 如果没有 customTitle，返回第一条用户消息
        if first_user_message:
            return first_user_message

        return None

    def format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def format_timestamp(self, ts: int) -> str:
        """格式化时间戳"""
        return datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d %H:%M:%S')

    def delete_session(self, session_id: str, project_path: str) -> dict:
        """删除会话的所有相关文件"""
        result = {
            'conversation_file': False,
            'debug_file': False,
            'session_env': False,
            'file_history': False,
            'todos': False,
            'history_entries': 0,
            'success': False
        }

        try:
            # 1. 删除对话文件
            conv_file = self.get_conversation_file(session_id, project_path)
            if conv_file.exists():
                conv_file.unlink()
                result['conversation_file'] = True

            # 2. 删除 debug 文件
            debug_file = self.debug_dir / f"{session_id}.txt"
            if debug_file.exists():
                debug_file.unlink()
                result['debug_file'] = True

            # 3. 删除 session-env 目录
            session_env = self.session_env_dir / session_id
            if session_env.exists() and session_env.is_dir():
                shutil.rmtree(session_env)
                result['session_env'] = True

            # 4. 删除 file-history 目录
            file_hist = self.file_history_dir / session_id
            if file_hist.exists() and file_hist.is_dir():
                shutil.rmtree(file_hist)
                result['file_history'] = True

            # 5. 删除 todos 文件
            if self.todos_dir.exists():
                todo_files = list(self.todos_dir.glob(f"{session_id}-*.json"))
                if todo_files:
                    for f in todo_files:
                        f.unlink()
                    result['todos'] = len(todo_files)

            # 6. 从 history.jsonl 中删除条目
            with open(self.history_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            new_lines = []
            removed_count = 0
            for line in lines:
                if session_id not in line:
                    new_lines.append(line)
                else:
                    removed_count += 1

            with open(self.history_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)

            result['history_entries'] = removed_count
            result['success'] = True

        except Exception as e:
            result['error'] = str(e)

        return result

    def cleanup_orphaned_files(self) -> dict:
        """清理无索引指向的文件"""
        valid_session_ids = self.get_all_session_ids()

        result = {
            'debug_files': 0,
            'session_envs': 0,
            'conversation_files': 0,
            'file_histories': 0,
            'todos': 0,
            'total_size_freed': 0,
            'details': []
        }

        try:
            # 1. 清理 debug 文件
            for f in self.debug_dir.glob("*.txt"):
                sid = f.stem
                if sid not in valid_session_ids:
                    size = f.stat().st_size
                    f.unlink()
                    result['debug_files'] += 1
                    result['total_size_freed'] += size
                    result['details'].append(
                        f"debug: {sid[:8]}... ({self.format_size(size)})")

            # 2. 清理 session-env 目录
            for d in self.session_env_dir.iterdir():
                if d.is_dir():
                    sid = d.name
                    if sid not in valid_session_ids:
                        shutil.rmtree(d)
                        result['session_envs'] += 1
                        result['details'].append(f"session-env: {sid[:8]}...")

            # 3. 清理 projects 目录下的对话文件
            for project_dir in self.projects_dir.iterdir():
                if project_dir.is_dir():
                    for f in project_dir.glob("*.jsonl"):
                        sid = f.stem
                        if sid not in valid_session_ids:
                            size = f.stat().st_size
                            f.unlink()
                            result['conversation_files'] += 1
                            result['total_size_freed'] += size
                            result['details'].append(
                                f"conversation: {sid[:8]}... ({self.format_size(size)})"
                            )

                    # 如果项目目录为空，删除它
                    try:
                        if project_dir.exists() and not list(
                                project_dir.iterdir()):
                            project_dir.rmdir()
                            result['details'].append(
                                f"空项目目录已删除: {project_dir.name}")
                    except:
                        pass

            # 4. 清理 file-history 目录
            for d in self.file_history_dir.iterdir():
                if d.is_dir():
                    sid = d.name
                    if sid not in valid_session_ids:
                        shutil.rmtree(d)
                        result['file_histories'] += 1
                        result['details'].append(f"file-history: {sid[:8]}...")

            # 5. 清理 todos 文件
            if self.todos_dir.exists():
                for f in self.todos_dir.glob("*-*.json"):
                    # 文件名格式: <sessionId>-agent-<sessionId>.json 或类似
                    parts = f.stem.split('-')
                    if parts:
                        sid = parts[0]
                        if sid not in valid_session_ids:
                            f.unlink()
                            result['todos'] += 1
                            result['details'].append(f"todo: {sid[:8]}...")

        except Exception as e:
            result['error'] = str(e)

        return result

    def get_unique_sessions(self) -> list:
        """获取去重后的会话列表（按 sessionId，取最新的记录）"""
        # 先按时间戳排序（最新的在前）
        sorted_sessions = sorted(self.sessions,
                                 key=lambda x: x.get('timestamp', 0),
                                 reverse=True)

        # 按 sessionId 去重，保留每个 sessionId 的第一条（由于已排序，所以是最新的）
        seen = set()
        unique = []
        for session in sorted_sessions:
            sid = session.get('sessionId')
            if sid and sid not in seen:
                seen.add(sid)
                unique.append(session)

        # 计算每个会话是否有对话文件，用于排序
        session_with_file_info = []
        for session in unique:
            sid = session.get('sessionId')
            project = session.get('project', 'N/A')
            has_file = self.get_conversation_file_size(sid, project) > 0
            timestamp = session.get('timestamp', 0)
            # 判断是否是本地命令
            display = session.get('display', '')
            is_local_cmd = display.startswith('/') if display else False

            session_with_file_info.append({
                'session': session,
                'has_file': has_file,
                'timestamp': timestamp,
                'is_local_cmd': is_local_cmd
            })

        # 排序：
        # 1. 有数据文件的优先（has_file=True 排前面）
        # 2. 本地命令放后面
        # 3. 时间倒序（最新的在上面）
        session_with_file_info.sort(key=lambda x: (
            not x['has_file'],  # 有文件的优先
            x['is_local_cmd'],  # 本地命令放后面
            -x['timestamp']  # 时间倒序（负号，大的在前）
        ))

        return [s['session'] for s in session_with_file_info]


# ============ GUI 界面 ============


class SessionManagerApp:
    """会话管理器主窗口"""

    def __init__(self,
                 root,
                 app_title="Claude 会话管理器",
                 window_geometry="1200x700",
                 developer="Qzjzl20000",
                 version="v1.0.0",
                 footer_hint="💡 双击对话可查看详情"):
        self.root = root
        self.app_title = app_title
        self.window_geometry = window_geometry
        self.developer = developer
        self.version = version
        self.footer_hint = footer_hint

        self.root.title(self.app_title)
        self.root.geometry(self.window_geometry)

        self.data = SessionData()
        self.current_sessions = []
        self.checked_sessions = {}  # {item_id: session_id}
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search)

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        """设置界面"""
        # 顶部工具栏
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill=tk.X)

        # 标题
        title_label = ttk.Label(toolbar,
                                text=self.app_title,
                                font=("", 16, "bold"))
        title_label.pack(side=tk.LEFT, padx=5)

        # 搜索框
        search_frame = ttk.Frame(toolbar)
        search_frame.pack(side=tk.RIGHT, padx=5)

        ttk.Label(search_frame, text="🔍 搜索:").pack(side=tk.LEFT, padx=5)
        search_entry = ttk.Entry(search_frame,
                                 textvariable=self.search_var,
                                 width=30)
        search_entry.pack(side=tk.LEFT)

        # 刷新按钮
        refresh_btn = ttk.Button(toolbar, text="🔄 刷新", command=self.load_data)
        refresh_btn.pack(side=tk.RIGHT, padx=5)

        # 统计信息栏
        self.stats_label = ttk.Label(self.root, text="", padding=(10, 5))
        self.stats_label.pack(fill=tk.X)

        # 操作栏（全选、删除等）
        action_bar = ttk.Frame(self.root, padding=(10, 5))
        action_bar.pack(fill=tk.X)

        self.select_all_btn = ttk.Button(action_bar,
                                         text="☑️ 全选",
                                         command=self.select_all)
        self.select_all_btn.pack(side=tk.LEFT, padx=5)

        self.deselect_all_btn = ttk.Button(action_bar,
                                           text="☐ 取消全选",
                                           command=self.deselect_all)
        self.deselect_all_btn.pack(side=tk.LEFT, padx=5)

        self.delete_selected_btn = ttk.Button(action_bar,
                                              text="🗑️ 删除选中的会话",
                                              command=self.delete_selected,
                                              state="disabled")
        self.delete_selected_btn.pack(side=tk.LEFT, padx=5)

        self.selected_count_label = ttk.Label(action_bar, text="已选: 0")
        self.selected_count_label.pack(side=tk.LEFT, padx=15)

        ttk.Separator(action_bar, orient=tk.VERTICAL).pack(side=tk.LEFT,
                                                           fill=tk.Y,
                                                           padx=10)

        ttk.Button(action_bar, text="🧹 清理无索引数据",
                   command=self.cleanup_orphaned).pack(side=tk.LEFT, padx=5)

        # 页脚（需要在主内容之前 pack，以固定在底部）
        footer_frame = ttk.Frame(self.root)
        footer_frame.pack(side=tk.BOTTOM, fill=tk.X)

        ttk.Label(footer_frame,
                  text=self.footer_hint,
                  font=("", 12),
                  foreground="#666666").pack(side=tk.LEFT, padx=10, pady=5)

        ttk.Label(footer_frame,
                  text=f"{self.developer} {self.version}",
                  font=("", 12),
                  foreground="#999999").pack(side=tk.RIGHT, padx=10, pady=5)

        # 主内容区域（使用 PanedWindow 分割）
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 左侧：会话列表
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=3)

        # 表格
        columns = ("check", "row_id", "status", "display", "file_type", "time",
                   "filesize", "project", "session_id")
        self.tree = ttk.Treeview(left_frame,
                                 columns=columns,
                                 show="headings",
                                 selectmode="browse")

        # 设置列
        self.tree.heading("check", text="✓")
        self.tree.heading("row_id", text="行号")
        self.tree.heading("status", text="状态")
        self.tree.heading("display", text="对话")
        self.tree.heading("file_type", text="文件类型")
        self.tree.heading("time", text="时间")
        self.tree.heading("filesize", text="文件大小")
        self.tree.heading("project", text="项目路径")
        self.tree.heading("session_id", text="Session ID")

        self.tree.column("check", width=40, anchor="center")
        self.tree.column("row_id", width=50, anchor="center")
        self.tree.column("status", width=90, anchor="center")
        self.tree.column("display", width=230)
        self.tree.column("file_type", width=90, anchor="center")
        self.tree.column("time", width=140)
        self.tree.column("filesize", width=90, anchor="center")
        self.tree.column("project", width=180)
        self.tree.column("session_id", width=150)

        # 滚动条
        scrollbar_y = ttk.Scrollbar(left_frame,
                                    orient=tk.VERTICAL,
                                    command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(left_frame,
                                    orient=tk.HORIZONTAL,
                                    command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set,
                            xscrollcommand=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # 绑定事件
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-1>", self.on_click)

        # 右键菜单
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="查看对话",
                                      command=self.view_conversation)
        self.context_menu.add_command(label="切换选中", command=self.toggle_check)
        self.tree.bind("<Button-2>", self.show_context_menu)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # 右侧：预览和统计面板
        right_frame = ttk.Frame(paned, padding=10)
        paned.add(right_frame, weight=1)

        # 上半部分：对话预览
        preview_group = ttk.LabelFrame(right_frame, text="对话预览", padding=10)
        preview_group.pack(fill=tk.BOTH, expand=True, pady=5)

        self.info_text = scrolledtext.ScrolledText(preview_group,
                                                   font=("", 12),
                                                   wrap=tk.WORD,
                                                   padx=5,
                                                   pady=5)
        self.info_text.pack(fill=tk.BOTH, expand=True)

        # 配置预览标签样式
        self.info_text.tag_config("user_msg",
                                  foreground="#0066cc",
                                  font=("", 12, "bold"))
        self.info_text.tag_config("assistant_msg",
                                  foreground="#008800",
                                  font=("", 11))
        self.info_text.tag_config("system_msg",
                                  foreground="#666666",
                                  font=("", 10))
        self.info_text.tag_config("tool_msg",
                                  foreground="#aa6600",
                                  font=("", 10))
        self.info_text.tag_config("placeholder",
                                  foreground="#999999",
                                  font=("", 10))
        self.info_text.tag_config("error", foreground="#cc0000", font=("", 11))

        # 下半部分：文件大小统计
        stats_group = ttk.LabelFrame(right_frame, text="文件大小分布", padding=10)
        stats_group.pack(fill=tk.X, pady=5)

        self.stats_text = scrolledtext.ScrolledText(stats_group,
                                                    font=("Courier", 11),
                                                    wrap=tk.WORD,
                                                    padx=10,
                                                    pady=10,
                                                    height=12)
        self.stats_text.pack(fill=tk.BOTH, expand=True)

        # 配置统计标签样式
        self.stats_text.tag_config("title",
                                   foreground="#333333",
                                   font=("", 12, "bold"))
        self.stats_text.tag_config("label",
                                   foreground="#666666",
                                   font=("", 10))
        self.stats_text.tag_config("value",
                                   foreground="#0066cc",
                                   font=("Courier", 11, "bold"))
        self.stats_text.tag_config("total",
                                   foreground="#008800",
                                   font=("Courier", 12, "bold"))
        self.stats_text.tag_config("separator", foreground="#cccccc")
        self.stats_text.tag_config("placeholder",
                                   foreground="#999999",
                                   font=("", 10))

    def load_data(self):
        """加载数据"""
        self.data.load_sessions()
        # 检测活跃的 Session
        self.active_sessions = self.data.get_active_sessions(minutes=10)
        self.update_session_list()
        self.update_stats()

    def update_session_list(self, filter_text=""):
        """更新会话列表"""
        # 保存当前选中状态
        saved_checks = self.checked_sessions.copy()

        # 清空列表
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 获取去重后的会话
        sessions = self.data.get_unique_sessions()

        # 过滤
        if filter_text:
            filter_text = filter_text.lower()
            sessions = [
                s for s in sessions
                if filter_text in s.get('display', '').lower()
                or filter_text in s.get('project', '').lower()
                or filter_text in s.get('sessionId', '').lower()
            ]

        self.current_sessions = sessions

        # 插入数据
        for idx, session in enumerate(sessions, start=1):
            session_id = session.get('sessionId', '')
            display = session.get('display', 'N/A')
            timestamp = session.get('timestamp', 0)
            project_full = session.get('project', 'N/A')  # 完整路径用于计算文件大小

            # 检查是否是活跃会话
            is_active = session_id in self.active_sessions

            # 优先显示会话名称（customTitle），如果没有则使用 display
            session_title = self.data.get_session_title(
                session_id, project_full)
            if session_title:
                display = session_title
            else:
                # 简化显示
                if len(display) > 40:
                    display = display[:37] + "..."
            project_display = project_full
            if len(project_display) > 30:
                project_display = "..." + project_display[-27:]

            # 使用完整路径计算文件大小
            file_size = self.data.get_conversation_file_size(
                session_id, project_full)

            # 检查是否是本地命令
            is_local_command = self.is_local_command(display)

            # 状态列显示
            if is_active:
                status = "🟢 运行中"
            else:
                status = ""

            # 文件类型和文件大小显示
            if is_local_command:
                file_type = "本地命令"
                size_str = "-"
                tags = ("local_command", )
            elif file_size > 0:
                file_type = "对话文件"
                size_str = self.data.format_size(file_size)
                tags = ("has_data", )
            else:
                file_type = "对话文件"
                size_str = "-"
                tags = ("no_data", )

            # 活跃会话使用特殊标签
            if is_active:
                tags = ("active_session", )

            item_id = self.tree.insert(
                "",
                tk.END,
                values=("🚫" if is_active else "☐", idx, status, display, file_type,
                        self.data.format_timestamp(timestamp), size_str,
                        project_display, session_id),
                tags=tags)

            # 恢复选中状态（仅非活跃会话）
            if session_id in saved_checks.values() and not is_active:
                self.tree.set(item_id, "check", "☑")
                self.checked_sessions[item_id] = session_id

        # 设置标签颜色
        self.tree.tag_configure("has_data", foreground="black")
        self.tree.tag_configure("no_data", foreground="#999")
        self.tree.tag_configure("local_command", foreground="#228B22")  # 绿色
        self.tree.tag_configure("active_session", foreground="#0066cc",
                                background="#e6f3ff")  # 蓝色文字，浅蓝背景

        self.update_selected_count()

    def update_stats(self):
        """更新统计信息"""
        total = len(self.data.sessions)
        unique = len(self.data.get_unique_sessions())

        # 统计所有相关文件
        debug_files = list(self.data.debug_dir.glob("*.txt"))
        debug_count = len(debug_files)
        debug_size = sum(f.stat().st_size for f in debug_files)

        total_conv_size = 0
        conv_count = 0
        for session in self.data.get_unique_sessions():
            sid = session.get('sessionId')
            project = session.get('project', 'N/A')  # 使用完整路径
            size = self.data.get_conversation_file_size(sid, project)
            if size > 0:
                conv_count += 1
                total_conv_size += size

        history_size = self.data.history_file.stat(
        ).st_size if self.data.history_file.exists() else 0
        total_size = history_size + debug_size + total_conv_size

        text = (
            f"📊 会话记录: {total} 条 | 🎯 独立会话: {unique} 个 | "
            f"💬 对话文件: {conv_count} 个 ({self.data.format_size(total_conv_size)}) | "
            f"🐛 Debug: {debug_count} 个 ({self.data.format_size(debug_size)}) | "
            f"💾 总存储: {self.data.format_size(total_size)}")
        self.stats_label.config(text=text)

    def update_selected_count(self):
        """更新选中计数"""
        count = len(self.checked_sessions)
        self.selected_count_label.config(text=f"已选: {count}")
        self.delete_selected_btn.config(
            state="normal" if count > 0 else "disabled")

    def update_file_size_distribution(self, session):
        """更新右侧文件大小分布面板（针对选中会话）"""
        self.stats_text.config(state="normal")
        self.stats_text.delete(1.0, tk.END)

        session_id = session.get('sessionId', '')
        project = session.get('project', 'N/A')

        # 统计该会话的文件大小
        conv_file = self.data.get_conversation_file(session_id, project)
        conv_size = conv_file.stat().st_size if conv_file.exists() else 0

        debug_file = self.data.debug_dir / f"{session_id}.txt"
        debug_size = debug_file.stat().st_size if debug_file.exists() else 0

        # Session-env 目录
        session_env_dir = self.data.session_env_dir / session_id
        session_env_size = 0
        if session_env_dir.exists():
            for f in session_env_dir.rglob('*'):
                if f.is_file():
                    session_env_size += f.stat().st_size

        # File-history 目录
        file_hist_dir = self.data.file_history_dir / session_id
        file_hist_size = 0
        if file_hist_dir.exists():
            for f in file_hist_dir.rglob('*'):
                if f.is_file():
                    file_hist_size += f.stat().st_size

        # Todos 文件
        todo_size = 0
        todo_count = 0
        if self.data.todos_dir.exists():
            for f in self.data.todos_dir.glob(f"{session_id}-*.json"):
                todo_size += f.stat().st_size
                todo_count += 1

        # 总计
        total = conv_size + debug_size + session_env_size + file_hist_size + todo_size

        # 显示统计
        self.stats_text.insert(tk.END, f"📁 会话文件分布\n\n", "title")
        self.stats_text.insert(tk.END, f"Session ID: {session_id[:12]}...\n\n",
                               "label")

        # 对话文件
        if conv_size > 0:
            self.stats_text.insert(tk.END, "💬 对话文件\n", "label")
            self.stats_text.insert(
                tk.END, f"  大小: {self.data.format_size(conv_size)}\n", "value")
            pct = (conv_size / total * 100) if total > 0 else 0
            self.stats_text.insert(tk.END, f"  占比: {pct:.1f}%\n\n", "value")
        else:
            self.stats_text.insert(tk.END, "💬 对话文件\n", "label")
            self.stats_text.insert(tk.END, "  (无文件)\n\n", "placeholder")

        # Debug 文件
        if debug_size > 0:
            self.stats_text.insert(tk.END, "🐛 Debug 日志\n", "label")
            self.stats_text.insert(
                tk.END, f"  大小: {self.data.format_size(debug_size)}\n",
                "value")
            pct = (debug_size / total * 100) if total > 0 else 0
            self.stats_text.insert(tk.END, f"  占比: {pct:.1f}%\n\n", "value")
        else:
            self.stats_text.insert(tk.END, "🐛 Debug 日志\n", "label")
            self.stats_text.insert(tk.END, "  (无文件)\n\n", "placeholder")

        # Session-env
        if session_env_size > 0:
            self.stats_text.insert(tk.END, "📦 Session 环境\n", "label")
            self.stats_text.insert(
                tk.END, f"  大小: {self.data.format_size(session_env_size)}\n",
                "value")
            pct = (session_env_size / total * 100) if total > 0 else 0
            self.stats_text.insert(tk.END, f"  占比: {pct:.1f}%\n\n", "value")

        # File-history
        if file_hist_size > 0:
            self.stats_text.insert(tk.END, "📜 文件历史\n", "label")
            self.stats_text.insert(
                tk.END, f"  大小: {self.data.format_size(file_hist_size)}\n",
                "value")
            pct = (file_hist_size / total * 100) if total > 0 else 0
            self.stats_text.insert(tk.END, f"  占比: {pct:.1f}%\n\n", "value")

        # Todos
        if todo_count > 0:
            self.stats_text.insert(tk.END, "📝 Todo 记录\n", "label")
            self.stats_text.insert(tk.END, f"  数量: {todo_count} 个\n", "label")
            self.stats_text.insert(
                tk.END, f"  大小: {self.data.format_size(todo_size)}\n", "value")
            pct = (todo_size / total * 100) if total > 0 else 0
            self.stats_text.insert(tk.END, f"  占比: {pct:.1f}%\n\n", "value")

        # 分隔线
        self.stats_text.insert(tk.END, "─" * 25 + "\n\n", "separator")

        # 总计
        self.stats_text.insert(tk.END, "💾 该会话总大小\n", "label")
        self.stats_text.insert(tk.END, f"  {self.data.format_size(total)}\n",
                               "total")

        self.stats_text.config(state="disabled")

    def on_search(self, *args):
        """搜索事件"""
        filter_text = self.search_var.get()
        self.update_session_list(filter_text)

    def on_click(self, event):
        """点击事件 - 处理勾选框"""
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self.tree.identify_column(event.x)
        if column != "#1":
            return

        item = self.tree.identify_row(event.y)
        if not item:
            return

        self.toggle_check_for_item(item)

    def toggle_check_for_item(self, item):
        """切换指定项的选中状态"""
        current = self.tree.set(item, "check")
        session_id = self.tree.set(item, "session_id")
        status = self.tree.set(item, "status")

        # 活跃会话不允许选中
        if "运行中" in status:
            messagebox.showwarning("操作限制",
                "⚠️ 该会话正在运行中，无法选中或删除。\n\n"
                "请等待会话结束后再进行此操作。")
            return

        if current == "☐":
            self.tree.set(item, "check", "☑")
            self.checked_sessions[item] = session_id
        else:
            self.tree.set(item, "check", "☐")
            if item in self.checked_sessions:
                del self.checked_sessions[item]

        self.update_selected_count()

    def on_select(self, event):
        """选择事件"""
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            session_id = self.tree.set(item, "session_id")

            session = next((s for s in self.current_sessions
                            if s.get('sessionId') == session_id), None)

            if session:
                self.show_session_info(session)

    def on_double_click(self, event):
        """双击事件 - 查看对话"""
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        session_id = self.tree.set(item, "session_id")
        display = self.tree.set(item, "display")

        # 从 current_sessions 中获取完整的 project 路径
        session = next((s for s in self.current_sessions
                        if s.get('sessionId') == session_id), None)

        if not session:
            messagebox.showwarning("错误", "未找到会话信息")
            return

        project = session.get('project', 'N/A')

        # 检查是否是本地命令
        if self.is_local_command(display):
            DebugLogViewer(self.root, session_id, display, self.data)
            return

        conv_file = self.data.get_conversation_file(session_id, project)
        if not conv_file.exists():
            messagebox.showwarning(
                "无法查看",
                f"该会话没有对话数据文件\n\nSession ID: {session_id}\n项目路径: {project}")
            return

        ConversationViewer(self.root, session_id, project, display, self.data)

    def show_context_menu(self, event):
        """显示右键菜单"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def view_conversation(self):
        """查看对话"""
        self.on_double_click(None)

    def toggle_check(self):
        """切换选中项的勾选状态"""
        selection = self.tree.selection()
        if selection:
            self.toggle_check_for_item(selection[0])

    def select_all(self):
        """全选（跳过活跃会话）"""
        for item in self.tree.get_children():
            status = self.tree.set(item, "status")
            # 跳过活跃会话
            if "运行中" not in status:
                self.tree.set(item, "check", "☑")
                session_id = self.tree.set(item, "session_id")
                self.checked_sessions[item] = session_id
        self.update_selected_count()

    def deselect_all(self):
        """取消全选"""
        for item in self.tree.get_children():
            self.tree.set(item, "check", "☐")
        self.checked_sessions.clear()
        self.update_selected_count()

    def collect_deletion_preview(self, session_id: str,
                                 project_path: str) -> dict:
        """收集会话删除预览信息"""
        preview = {
            'session_id': session_id,
            'project_path': project_path,
            'files': [],
            'dirs': [],
            'total_size': 0
        }

        # 1. 对话文件
        conv_file = self.data.get_conversation_file(session_id, project_path)
        if conv_file.exists():
            size = conv_file.stat().st_size
            preview['files'].append({
                'path': str(conv_file),
                'size': size,
                'type': '对话文件'
            })
            preview['total_size'] += size

        # 2. Debug 文件
        debug_file = self.data.debug_dir / f"{session_id}.txt"
        if debug_file.exists():
            size = debug_file.stat().st_size
            preview['files'].append({
                'path': str(debug_file),
                'size': size,
                'type': 'Debug 日志'
            })
            preview['total_size'] += size

        # 3. Session-env 目录
        session_env = self.data.session_env_dir / session_id
        if session_env.exists() and session_env.is_dir():
            size = sum(f.stat().st_size for f in session_env.rglob('*')
                       if f.is_file())
            preview['dirs'].append({
                'path': str(session_env),
                'size': size,
                'type': 'Session 环境'
            })
            preview['total_size'] += size

        # 4. File-history 目录
        file_hist = self.data.file_history_dir / session_id
        if file_hist.exists() and file_hist.is_dir():
            size = sum(f.stat().st_size for f in file_hist.rglob('*')
                       if f.is_file())
            preview['dirs'].append({
                'path': str(file_hist),
                'size': size,
                'type': '文件历史'
            })
            preview['total_size'] += size

        # 5. Todo 文件
        if self.data.todos_dir.exists():
            for todo_file in self.data.todos_dir.glob(f"{session_id}-*.json"):
                size = todo_file.stat().st_size
                preview['files'].append({
                    'path': str(todo_file),
                    'size': size,
                    'type': 'Todo 记录'
                })
                preview['total_size'] += size

        return preview

    def show_deletion_preview_dialog(self, previews: list) -> bool:
        """显示删除预览对话框"""
        # 创建预览窗口
        preview_window = tk.Toplevel(self.root)
        preview_window.title("删除预览")
        preview_window.geometry("900x600")
        preview_window.transient(self.root)
        preview_window.grab_set()

        # 顶部警告信息
        header_frame = ttk.Frame(preview_window, padding=10)
        header_frame.pack(fill=tk.X)

        ttk.Label(header_frame,
                  text="⚠️ 即将删除以下文件",
                  font=("", 14, "bold"),
                  foreground="#cc0000").pack()

        # 统计信息
        total_files = sum(len(p['files']) for p in previews)
        total_dirs = sum(len(p['dirs']) for p in previews)
        total_size = sum(p['total_size'] for p in previews)

        stats_frame = ttk.Frame(preview_window, padding=10)
        stats_frame.pack(fill=tk.X)

        ttk.Label(
            stats_frame,
            text=
            f"会话数: {len(previews)} | 文件数: {total_files} | 目录数: {total_dirs} | 总大小: {self.data.format_size(total_size)}",
            font=("", 11)).pack()

        # 文件列表（使用 ScrolledText）
        text_frame = ttk.Frame(preview_window, padding=10)
        text_frame.pack(fill=tk.BOTH, expand=True)

        text = scrolledtext.ScrolledText(text_frame,
                                         font=("Courier", 10),
                                         wrap=tk.NONE,
                                         padx=10,
                                         pady=10)
        text.pack(fill=tk.BOTH, expand=True)

        # 配置标签样式
        text.tag_config("session_header",
                        foreground="#0066cc",
                        font=("", 11, "bold"))
        text.tag_config("file_path", foreground="#333333")
        text.tag_config("dir_path", foreground="#008800")
        text.tag_config("file_size", foreground="#666666")
        text.tag_config("warning", foreground="#cc0000", font=("", 10, "bold"))

        # 插入内容
        for idx, preview in enumerate(previews, 1):
            session_id = preview['session_id']
            project_path = preview['project_path']

            text.insert(tk.END, f"\n{'='*80}\n\n", "session_header")
            text.insert(tk.END, f"会话 {idx}/{len(previews)}\n",
                        "session_header")
            text.insert(tk.END, f"Session ID: {session_id}\n", "file_path")
            text.insert(tk.END, f"项目路径: {project_path}\n", "file_path")
            text.insert(
                tk.END,
                f"总大小: {self.data.format_size(preview['total_size'])}\n\n",
                "file_size")

            # 文件
            if preview['files']:
                text.insert(tk.END, "  📄 文件:\n", "file_path")
                for f in preview['files']:
                    text.insert(tk.END, f"    [{f['type']}] {f['path']}",
                                "file_path")
                    text.insert(tk.END,
                                f" ({self.data.format_size(f['size'])})\n",
                                "file_size")

            # 目录
            if preview['dirs']:
                text.insert(tk.END, "  📁 目录:\n", "dir_path")
                for d in preview['dirs']:
                    text.insert(tk.END, f"    [{d['type']}] {d['path']}",
                                "dir_path")
                    text.insert(tk.END,
                                f" ({self.data.format_size(d['size'])})\n",
                                "file_size")

            text.insert(tk.END, "\n")

        text.config(state="disabled")
        text.see(1.0)

        # 底部按钮
        button_frame = ttk.Frame(preview_window, padding=10)
        button_frame.pack(fill=tk.X)

        # 存储用户选择结果
        result = {'confirmed': False}

        def on_confirm():
            result['confirmed'] = True
            preview_window.destroy()

        def on_cancel():
            result['confirmed'] = False
            preview_window.destroy()

        ttk.Button(button_frame, text="❌ 取消",
                   command=on_cancel).pack(side=tk.RIGHT, padx=5)

        ttk.Button(button_frame, text="🗑️ 确认删除",
                   command=on_confirm).pack(side=tk.RIGHT, padx=5)

        # 等待窗口关闭
        preview_window.wait_window()
        return result['confirmed']

    def delete_selected(self):
        """删除选中的会话"""
        if not self.checked_sessions:
            return

        # 收集所有要删除的会话信息，并检查是否有活跃会话
        to_delete = []
        active_sessions = []
        for item, session_id in list(self.checked_sessions.items()):
            # 检查是否是活跃会话
            if session_id in self.active_sessions:
                session = next((s for s in self.current_sessions
                                if s.get('sessionId') == session_id), None)
                if session:
                    active_sessions.append(session_id)
            else:
                session = next((s for s in self.current_sessions
                                if s.get('sessionId') == session_id), None)
                if session:
                    to_delete.append((session_id, session.get('project', 'N/A')))

        # 如果有活跃会话被选中，显示警告
        if active_sessions:
            messagebox.showwarning("操作限制",
                f"⚠️ 检测到 {len(active_sessions)} 个活跃会话无法删除：\n\n" +
                "\n".join([f"  • {sid[:20]}..." for sid in active_sessions[:3]]) +
                (f"\n  ... 还有 {len(active_sessions) - 3} 个" if len(active_sessions) > 3 else "") +
                "\n\n请等待会话结束后再进行删除操作。")

        # 如果没有可删除的会话，直接返回
        if not to_delete:
            return

        # 收集删除预览信息
        previews = []
        for session_id, project_path in to_delete:
            preview = self.collect_deletion_preview(session_id, project_path)
            previews.append(preview)

        # 显示预览对话框
        if not self.show_deletion_preview_dialog(previews):
            return

        # 执行删除
        deleted = 0
        failed = 0
        for session_id, project_path in to_delete:
            result = self.data.delete_session(session_id, project_path)
            if result.get('success'):
                deleted += 1
            else:
                failed += 1

        self.checked_sessions.clear()
        self.load_data()

        messagebox.showinfo(
            "删除完成",
            f"成功删除: {deleted} 个\n" + (f"失败: {failed} 个" if failed > 0 else ""))

    def collect_orphaned_files_preview(self) -> dict:
        """收集无索引文件的预览信息"""
        valid_session_ids = self.data.get_all_session_ids()

        preview = {
            'debug_files': [],
            'conversation_files': [],
            'session_envs': [],
            'file_histories': [],
            'todos': [],
            'total_size': 0
        }

        # 1. Debug 文件
        for f in self.data.debug_dir.glob("*.txt"):
            sid = f.stem
            if sid not in valid_session_ids:
                size = f.stat().st_size
                preview['debug_files'].append({
                    'path': str(f),
                    'size': size,
                    'session_id': sid
                })
                preview['total_size'] += size

        # 2. 对话文件
        for project_dir in self.data.projects_dir.iterdir():
            if project_dir.is_dir():
                for f in project_dir.glob("*.jsonl"):
                    sid = f.stem
                    if sid not in valid_session_ids:
                        size = f.stat().st_size
                        preview['conversation_files'].append({
                            'path': str(f),
                            'size': size,
                            'session_id': sid
                        })
                        preview['total_size'] += size

        # 3. Session-env 目录
        for d in self.data.session_env_dir.iterdir():
            if d.is_dir():
                sid = d.name
                if sid not in valid_session_ids:
                    size = sum(f.stat().st_size for f in d.rglob('*')
                               if f.is_file())
                    preview['session_envs'].append({
                        'path': str(d),
                        'size': size,
                        'session_id': sid
                    })
                    preview['total_size'] += size

        # 4. File-history 目录
        if self.data.file_history_dir.exists():
            for d in self.data.file_history_dir.iterdir():
                if d.is_dir():
                    sid = d.name
                    if sid not in valid_session_ids:
                        size = sum(f.stat().st_size for f in d.rglob('*')
                                   if f.is_file())
                        preview['file_histories'].append({
                            'path': str(d),
                            'size': size,
                            'session_id': sid
                        })
                        preview['total_size'] += size

        # 5. Todo 文件
        if self.data.todos_dir.exists():
            for f in self.data.todos_dir.glob("*-*.json"):
                parts = f.stem.split('-')
                if parts:
                    sid = parts[0]
                    if sid not in valid_session_ids:
                        size = f.stat().st_size
                        preview['todos'].append({
                            'path': str(f),
                            'size': size,
                            'session_id': sid
                        })
                        preview['total_size'] += size

        return preview

    def show_cleanup_preview_dialog(self, preview: dict,
                                    valid_count: int) -> bool:
        """显示清理预览对话框"""
        # 创建预览窗口
        preview_window = tk.Toplevel(self.root)
        preview_window.title("清理无索引数据 - 预览")
        preview_window.geometry("1000x700")
        preview_window.transient(self.root)
        preview_window.grab_set()

        # 顶部警告信息
        header_frame = ttk.Frame(preview_window, padding=10)
        header_frame.pack(fill=tk.X)

        ttk.Label(header_frame,
                  text="⚠️ 危险操作 - 即将删除无索引文件",
                  font=("", 14, "bold"),
                  foreground="#cc0000").pack()

        # 统计信息
        total_items = (len(preview['debug_files']) +
                       len(preview['conversation_files']) +
                       len(preview['session_envs']) +
                       len(preview['file_histories']) + len(preview['todos']))

        stats_frame = ttk.Frame(preview_window, padding=10)
        stats_frame.pack(fill=tk.X)

        stats_text = (f"有效索引会话: {valid_count} 个 | "
                      f"将删除: {total_items} 项 | "
                      f"总大小: {self.data.format_size(preview['total_size'])}")
        ttk.Label(stats_frame, text=stats_text, font=("", 11)).pack()

        # 安全警告
        warning_frame = ttk.Frame(preview_window, padding=10)
        warning_frame.pack(fill=tk.X)

        warning_text = ("❗ 重要安全警告：\n"
                        "  • 此操作将删除所有不在 history.jsonl 索引中的文件\n"
                        "  • 如果您之前手动编辑过 history.jsonl，可能误删正在使用的会话\n"
                        "  • 建议先备份 ~/.claude 目录\n"
                        "  • 删除后将无法恢复文件")
        ttk.Label(warning_frame,
                  text=warning_text,
                  foreground="#cc6600",
                  justify=tk.LEFT).pack()

        # 文件列表
        text_frame = ttk.Frame(preview_window, padding=10)
        text_frame.pack(fill=tk.BOTH, expand=True)

        text = scrolledtext.ScrolledText(text_frame,
                                         font=("Courier", 10),
                                         wrap=tk.NONE,
                                         padx=10,
                                         pady=10)
        text.pack(fill=tk.BOTH, expand=True)

        # 配置标签样式
        text.tag_config("category",
                        foreground="#0066cc",
                        font=("", 11, "bold"))
        text.tag_config("file_path", foreground="#333333")
        text.tag_config("session_id", foreground="#666666")
        text.tag_config("file_size", foreground="#999999")
        text.tag_config("warning", foreground="#cc0000")

        # 插入内容
        text.insert(tk.END, "\n" + "=" * 90 + "\n\n", "category")

        # Debug 文件
        if preview['debug_files']:
            text.insert(tk.END,
                        f"🐛 Debug 文件 ({len(preview['debug_files'])} 项)\n\n",
                        "category")
            for item in preview['debug_files'][:50]:  # 限制显示数量
                text.insert(tk.END, f"  [{item['session_id'][:20]}...]",
                            "session_id")
                text.insert(tk.END, f" {item['path']}\n", "file_path")
                text.insert(
                    tk.END, f"    大小: {self.data.format_size(item['size'])}\n",
                    "file_size")
            if len(preview['debug_files']) > 50:
                text.insert(
                    tk.END, f"  ... 还有 {len(preview['debug_files']) - 50} 项\n",
                    "warning")
            text.insert(tk.END, "\n")

        # 对话文件
        if preview['conversation_files']:
            text.insert(
                tk.END, f"💬 对话文件 ({len(preview['conversation_files'])} 项)\n\n",
                "category")
            for item in preview['conversation_files'][:50]:
                text.insert(tk.END, f"  [{item['session_id'][:20]}...]",
                            "session_id")
                text.insert(tk.END, f" {item['path']}\n", "file_path")
                text.insert(
                    tk.END, f"    大小: {self.data.format_size(item['size'])}\n",
                    "file_size")
            if len(preview['conversation_files']) > 50:
                text.insert(
                    tk.END,
                    f"  ... 还有 {len(preview['conversation_files']) - 50} 项\n",
                    "warning")
            text.insert(tk.END, "\n")

        # Session-env 目录
        if preview['session_envs']:
            text.insert(
                tk.END, f"📦 Session 环境 ({len(preview['session_envs'])} 项)\n\n",
                "category")
            for item in preview['session_envs'][:30]:
                text.insert(tk.END, f"  [{item['session_id'][:20]}...]",
                            "session_id")
                text.insert(tk.END, f" {item['path']}\n", "file_path")
                text.insert(
                    tk.END, f"    大小: {self.data.format_size(item['size'])}\n",
                    "file_size")
            if len(preview['session_envs']) > 30:
                text.insert(
                    tk.END,
                    f"  ... 还有 {len(preview['session_envs']) - 30} 项\n",
                    "warning")
            text.insert(tk.END, "\n")

        # File-history 目录
        if preview['file_histories']:
            text.insert(tk.END,
                        f"📜 文件历史 ({len(preview['file_histories'])} 项)\n\n",
                        "category")
            for item in preview['file_histories'][:30]:
                text.insert(tk.END, f"  [{item['session_id'][:20]}...]",
                            "session_id")
                text.insert(tk.END, f" {item['path']}\n", "file_path")
                text.insert(
                    tk.END, f"    大小: {self.data.format_size(item['size'])}\n",
                    "file_size")
            if len(preview['file_histories']) > 30:
                text.insert(
                    tk.END,
                    f"  ... 还有 {len(preview['file_histories']) - 30} 项\n",
                    "warning")
            text.insert(tk.END, "\n")

        # Todo 文件
        if preview['todos']:
            text.insert(tk.END, f"📝 Todo 文件 ({len(preview['todos'])} 项)\n\n",
                        "category")
            for item in preview['todos'][:30]:
                text.insert(tk.END, f"  [{item['session_id'][:20]}...]",
                            "session_id")
                text.insert(tk.END, f" {item['path']}\n", "file_path")
                text.insert(
                    tk.END, f"    大小: {self.data.format_size(item['size'])}\n",
                    "file_size")
            if len(preview['todos']) > 30:
                text.insert(tk.END,
                            f"  ... 还有 {len(preview['todos']) - 30} 项\n",
                            "warning")
            text.insert(tk.END, "\n")

        text.config(state="disabled")
        text.see(1.0)

        # 底部按钮
        button_frame = ttk.Frame(preview_window, padding=10)
        button_frame.pack(fill=tk.X)

        # 存储用户选择结果
        result = {'confirmed': False}

        def on_confirm():
            # 二次确认
            confirm = messagebox.askyesno("最后确认", "⚠️ 您确定要删除这些文件吗？\n\n"
                                          "此操作不可撤销！",
                                          icon="warning")
            if confirm:
                result['confirmed'] = True
                preview_window.destroy()

        def on_cancel():
            result['confirmed'] = False
            preview_window.destroy()

        ttk.Button(button_frame, text="❌ 取消",
                   command=on_cancel).pack(side=tk.RIGHT, padx=5)

        ttk.Button(button_frame, text="🗑️ 确认删除",
                   command=on_confirm).pack(side=tk.RIGHT, padx=5)

        # 等待窗口关闭
        preview_window.wait_window()
        return result['confirmed']

    def cleanup_orphaned(self):
        """清理无索引数据"""
        valid_session_ids = self.data.get_all_session_ids()
        valid_count = len(valid_session_ids)

        # 收集无索引文件预览
        preview = self.collect_orphaned_files_preview()

        total_items = (len(preview['debug_files']) +
                       len(preview['conversation_files']) +
                       len(preview['session_envs']) +
                       len(preview['file_histories']) + len(preview['todos']))

        # 如果没有文件需要清理
        if total_items == 0:
            messagebox.showinfo("清理无索引数据",
                                "✅ 没有发现需要清理的无索引文件。\n\n所有文件都有有效的索引记录。")
            return

        # 显示预览对话框
        if not self.show_cleanup_preview_dialog(preview, valid_count):
            return

        # 执行清理
        cleanup_result = self.data.cleanup_orphaned_files()

        details = cleanup_result.get('details', [])
        max_details = 30
        details_text = "\n".join(details[:max_details])
        if len(details) > max_details:
            details_text += f"\n... 还有 {len(details) - max_details} 项"

        summary = f"""清理完成！

已删除:
  - Debug 文件: {cleanup_result['debug_files']} 个
  - 对话文件: {cleanup_result['conversation_files']} 个
  - Session 环境: {cleanup_result['session_envs']} 个
  - 文件历史: {cleanup_result['file_histories']} 个
  - Todo 文件: {cleanup_result['todos']} 个

释放空间: {self.data.format_size(cleanup_result['total_size_freed'])}

详情:
{details_text if details_text else '无文件需要清理'}
"""

        self.load_data()
        messagebox.showinfo("清理完成", summary)

    def is_local_command(self, display: str) -> bool:
        """判断是否是本地命令"""
        if not display:
            return False
        # 检查是否以 / 开头的命令
        if display.startswith('/'):
            return True
        return False

    def show_session_info(self, session):
        """显示对话预览"""
        session_id = session.get('sessionId', '')
        project = session.get('project', 'N/A')
        display = session.get('display', 'N/A')

        # 清空文本框
        self.info_text.config(state="normal")
        self.info_text.delete(1.0, tk.END)

        # 检查是否是本地命令
        if self.is_local_command(display):
            self.show_debug_log_preview(session_id)
            self.info_text.config(state="disabled")
            # 更新文件大小分布
            self.update_file_size_distribution(session)
            return

        # 显示对话标识
        messages = self.data.load_conversation(session_id, project)
        self.info_text.insert(tk.END, f"💬 对话预览 ({len(messages)} 条消息)\n\n",
                              "system_msg")

        if not messages:
            self.info_text.insert(tk.END, "❌ 该会话没有对话数据\n\n", "error")
            self.info_text.insert(tk.END, f"Session ID: {session_id}\n",
                                  "placeholder")
            self.info_text.insert(tk.END, f"项目: {project}\n", "placeholder")
            self.info_text.config(state="disabled")
            # 更新文件大小分布
            self.update_file_size_distribution(session)
            return

        # 显示对话预览（最多显示前20条消息）
        max_messages = 20
        count = 0
        for msg in messages:
            if count >= max_messages:
                break

            msg_type = msg.get('type', 'unknown')
            user_type = msg.get('userType', '')

            # 跳过 snapshot 类型
            if msg_type == 'file-history-snapshot':
                continue

            # 获取 message 字段
            message_obj = msg.get('message', {})
            if not message_obj:
                continue

            if user_type == 'external' and msg_type == 'user':
                # 用户消息
                content = message_obj.get('content', '')
                if isinstance(content, str):
                    content = self.clean_command_content_preview(content)
                    if content.strip():
                        self.info_text.insert(tk.END, f"\n你:\n", "user_msg")
                        self.info_text.insert(tk.END, f"{content}\n")
                        count += 1

            elif user_type == 'assistant' or msg_type == 'assistant':
                # Assistant 消息
                content = message_obj.get('content', [])
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        part_type = part.get('type', '')
                        if part_type == 'text':
                            text = part.get('text', '')
                            if text:
                                text_parts.append(text)
                        elif part_type == 'tool_use':
                            tool_name = part.get('name', 'unknown')
                            text_parts.append(f"[工具: {tool_name}]")

                    if text_parts:
                        full_text = '\n'.join(text_parts)
                        # 限制长度
                        if len(full_text) > 300:
                            full_text = full_text[:300] + "..."
                        self.info_text.insert(tk.END, f"\nClaude:\n",
                                              "assistant_msg")
                        self.info_text.insert(tk.END, f"{full_text}\n")
                        count += 1

        if count == 0:
            self.info_text.insert(tk.END, "⚠️ 没有找到可显示的对话内容\n", "error")
            self.info_text.insert(tk.END, f"(共 {len(messages)} 条记录)\n",
                                  "placeholder")
        elif len(messages) > max_messages:
            self.info_text.insert(
                tk.END, f"\n... 还有 {len(messages) - max_messages} 条消息\n",
                "placeholder")

        self.info_text.see(1.0)
        self.info_text.config(state="disabled")

        # 更新文件大小分布
        self.update_file_size_distribution(session)

    def show_debug_log_preview(self, session_id: str):
        """显示调试日志预览"""
        debug_file = self.data.debug_dir / f"{session_id}.txt"

        self.info_text.insert(tk.END, "📋 本地命令 - 调试日志预览\n\n", "system_msg")

        if not debug_file.exists():
            self.info_text.insert(tk.END, "❌ 未找到调试日志文件\n", "error")
            return

        try:
            with open(debug_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # 显示前 50 行
            max_lines = 50
            for i, line in enumerate(lines[:max_lines]):
                # 简化显示，移除时间戳等
                line = line.rstrip()
                if '[DEBUG]' in line:
                    # 只显示 DEBUG 行的主要内容
                    parts = line.split('[DEBUG] ', 1)
                    if len(parts) > 1:
                        content = parts[1]
                        # 截断过长的行
                        if len(content) > 150:
                            content = content[:150] + "..."
                        self.info_text.insert(tk.END, f"{content}\n")
                elif '[WARN]' in line or '[ERROR]' in line:
                    if len(line) > 150:
                        line = line[:150] + "..."
                    self.info_text.insert(tk.END, f"{line}\n", "error")

            if len(lines) > max_lines:
                self.info_text.insert(
                    tk.END, f"\n... 还有 {len(lines) - max_lines} 行日志\n",
                    "placeholder")

            self.info_text.see(1.0)

        except Exception as e:
            self.info_text.insert(tk.END, f"❌ 读取日志失败: {e}\n", "error")

    def clean_command_content_preview(self, content: str) -> str:
        """清理命令内容"""
        import re
        content = re.sub(r'<local-command-caveat>.*?</local-command-caveat>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<command-name>.*?</command-name>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<command-message>.*?</command-message>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<command-args>.*?</command-args>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<local-command-stdout>.*?</local-command-stdout>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<[^>]+>', '', content)
        # 限制预览长度
        if len(content) > 200:
            content = content[:200] + "..."
        return content.strip()


# ============ 调试日志查看器窗口 ============


class DebugLogViewer:
    """调试日志查看器"""

    def __init__(self, parent, session_id: str, session_name: str,
                 data: SessionData):
        self.session_id = session_id
        self.session_name = session_name
        self.data = data

        self.window = tk.Toplevel(parent)
        self.window.title(f"调试日志 - {session_name[:50]}")
        self.window.geometry("1000x700")

        self.setup_ui()
        self.load_debug_log()

    def setup_ui(self):
        """设置界面"""
        # 顶部信息栏
        top_frame = ttk.Frame(self.window, padding=10)
        top_frame.pack(fill=tk.X)

        ttk.Label(top_frame,
                  text=f"Session: {self.session_id}",
                  font=("Courier", 12)).pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame,
                   text="📄 复制 Session ID",
                   command=lambda: self.window.clipboard_clear() or self.window
                   .clipboard_append(self.session_id)).pack(side=tk.RIGHT,
                                                            padx=5)

        # 主文本区域
        self.text = scrolledtext.ScrolledText(self.window,
                                              font=("Courier", 12),
                                              wrap=tk.NONE,
                                              padx=10,
                                              pady=10)
        self.text.pack(fill=tk.BOTH, expand=True)

        # 配置标签样式
        self.text.tag_config("debug", foreground="#333333")
        self.text.tag_config("warn", foreground="#cc6600")
        self.text.tag_config("error", foreground="#cc0000")
        self.text.tag_config("timestamp", foreground="#999999")

        # 底部工具栏
        bottom_frame = ttk.Frame(self.window, padding=10)
        bottom_frame.pack(fill=tk.X)

        ttk.Label(bottom_frame, text="🔍 搜索:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(bottom_frame,
                                 textvariable=self.search_var,
                                 width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<Return>", self.search_text)

        ttk.Button(bottom_frame, text="查找下一个",
                   command=self.search_next).pack(side=tk.LEFT, padx=5)

        ttk.Button(bottom_frame, text="关闭",
                   command=self.window.destroy).pack(side=tk.RIGHT, padx=5)

        self.search_pos = None

    def load_debug_log(self):
        """加载调试日志"""
        debug_file = self.data.debug_dir / f"{self.session_id}.txt"

        if not debug_file.exists():
            self.text.insert(1.0, "❌ 调试日志文件不存在\n\n")
            self.text.insert(tk.END, f"文件路径: {debug_file}")
            return

        try:
            with open(debug_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            self.text.insert(tk.END, f"共 {len(lines)} 行日志\n\n", "timestamp")

            for line in lines:
                line = line.rstrip()
                if not line:
                    self.text.insert(tk.END, "\n")
                    continue

                # 根据日志级别设置颜色
                if '[ERROR]' in line:
                    self.text.insert(tk.END, line + "\n", "error")
                elif '[WARN]' in line:
                    self.text.insert(tk.END, line + "\n", "warn")
                else:
                    self.text.insert(tk.END, line + "\n", "debug")

            self.text.see(1.0)

        except Exception as e:
            self.text.insert(1.0, f"❌ 读取日志失败: {e}")

    def search_text(self, event=None):
        """搜索文本"""
        keyword = self.search_var.get()
        if not keyword:
            return

        start = "1.0" if self.search_pos is None else self.search_pos

        pos = self.text.search(keyword, start, stopindex=tk.END, nocase=True)
        if pos:
            self.search_pos = f"{pos}+{len(keyword)}c"
            self.text.see(pos)
            self.text.focus_set()
        else:
            pos = self.text.search(keyword,
                                   "1.0",
                                   stopindex=tk.END,
                                   nocase=True)
            if pos:
                self.search_pos = f"{pos}+{len(keyword)}c"
                self.text.see(pos)
                self.text.focus_set()
            else:
                messagebox.showinfo("搜索", f"未找到: {keyword}")

    def search_next(self):
        """查找下一个"""
        self.search_text()


# ============ 对话查看器窗口 ============


class ConversationViewer:
    """对话内容查看器"""

    def __init__(self, parent, session_id: str, project_path: str,
                 session_name: str, data: SessionData):
        self.session_id = session_id
        self.project_path = project_path
        self.session_name = session_name
        self.data = data

        self.window = tk.Toplevel(parent)
        self.window.title(f"对话内容 - {session_name[:50]}")
        self.window.geometry("1100x750")

        self.setup_ui()
        self.load_conversation()

    def setup_ui(self):
        """设置界面"""
        # 顶部信息栏
        top_frame = ttk.Frame(self.window, padding=10)
        top_frame.pack(fill=tk.X)

        info_text = f"Session: {self.session_id}"
        ttk.Label(top_frame, text=info_text,
                  font=("Courier", 12)).pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame,
                   text="📄 复制 Session ID",
                   command=lambda: self.window.clipboard_clear() or self.window
                   .clipboard_append(self.session_id)).pack(side=tk.RIGHT,
                                                            padx=5)

        # 主文本区域
        self.text = scrolledtext.ScrolledText(self.window,
                                              font=("", 12),
                                              wrap=tk.WORD,
                                              padx=10,
                                              pady=10)
        self.text.pack(fill=tk.BOTH, expand=True)

        self.setup_tags()

        # 底部工具栏
        bottom_frame = ttk.Frame(self.window, padding=10)
        bottom_frame.pack(fill=tk.X)

        ttk.Label(bottom_frame, text="🔍 搜索:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(bottom_frame,
                                 textvariable=self.search_var,
                                 width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<Return>", self.search_text)

        ttk.Button(bottom_frame, text="查找下一个",
                   command=self.search_next).pack(side=tk.LEFT, padx=5)

        ttk.Button(bottom_frame, text="关闭",
                   command=self.window.destroy).pack(side=tk.RIGHT, padx=5)

        self.search_pos = None

    def setup_tags(self):
        """设置文本标签样式"""
        self.text.tag_config("user_msg",
                             foreground="#0066cc",
                             font=("", 12, "bold"),
                             spacing1=10)
        self.text.tag_config("assistant_msg",
                             foreground="#008800",
                             font=("", 12),
                             spacing1=5)
        self.text.tag_config("system_msg",
                             foreground="#666666",
                             font=("", 11),
                             spacing1=3)
        self.text.tag_config("tool_msg", foreground="#aa6600", font=("", 11))
        self.text.tag_config("content",
                             foreground="#333333",
                             font=("", 12),
                             lmargin1=20,
                             lmargin2=20)
        self.text.tag_config("meta", foreground="#999999", font=("", 10))

    def load_conversation(self):
        """加载对话内容"""
        messages = self.data.load_conversation(self.session_id,
                                               self.project_path)

        if not messages:
            self.text.insert(1.0, "❌ 对话数据文件不存在或为空")
            return

        self.display_conversation(messages)

    def display_conversation(self, messages: list):
        """显示对话内容"""
        for msg in messages:
            msg_type = msg.get('type', 'unknown')
            user_type = msg.get('userType', '')

            # 跳过 snapshot 类型
            if msg_type == 'file-history-snapshot':
                continue

            # 获取 message 字段
            message_obj = msg.get('message', {})
            if not message_obj:
                continue

            if user_type == 'external' and msg_type == 'user':
                # 用户消息
                content = message_obj.get('content', '')
                if isinstance(content, str):
                    # 清理命令标签
                    content = self.clean_command_content(content)
                    if content.strip():
                        self.insert_message("你", content, "user_msg")

            elif user_type == 'assistant' or msg_type == 'assistant':
                # Assistant 消息
                content = message_obj.get('content', [])
                if isinstance(content, list):
                    # 遍历 content 数组
                    text_parts = []
                    for part in content:
                        part_type = part.get('type', '')
                        if part_type == 'text':
                            text = part.get('text', '')
                            if text:
                                text_parts.append(text)
                        elif part_type == 'thinking':
                            # 跳过 thinking
                            pass
                        elif part_type == 'tool_use':
                            # 工具调用
                            tool_name = part.get('name', 'unknown')
                            tool_input = part.get('input', {})
                            text_parts.append(f"[调用工具: {tool_name}]")

                    if text_parts:
                        full_text = '\n'.join(text_parts)
                        self.insert_message("Claude", full_text,
                                            "assistant_msg")

            elif msg_type == 'tool' or msg.get('type') == 'tool_result':
                # 工具结果
                content = msg.get('content', '')
                if content:
                    self.insert_message("工具结果", str(content)[:200], "tool_msg")

        self.text.see(1.0)

    def clean_command_content(self, content: str) -> str:
        """清理命令内容中的 XML 标签"""
        import re
        # 移除各种 XML 标签
        content = re.sub(r'<local-command-caveat>.*?</local-command-caveat>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<command-name>.*?</command-name>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<command-message>.*?</command-message>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<command-args>.*?</command-args>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<local-command-stdout>.*?</local-command-stdout>',
                         '',
                         content,
                         flags=re.DOTALL)
        content = re.sub(r'<[^>]+>', '', content)
        return content.strip()

    def insert_message(self, role: str, content: str, tag: str):
        """插入一条消息"""
        if not content or content.isspace():
            return

        self.text.insert(tk.END, f"\n{role}:\n", tag)
        self.text.insert(tk.END, f"{content}\n", "content")

    def search_text(self, event=None):
        """搜索文本"""
        keyword = self.search_var.get()
        if not keyword:
            return

        start = "1.0" if self.search_pos is None else self.search_pos

        pos = self.text.search(keyword, start, stopindex=tk.END, nocase=True)
        if pos:
            self.search_pos = f"{pos}+{len(keyword)}c"
            self.text.see(pos)
            self.text.focus_set()
        else:
            pos = self.text.search(keyword,
                                   "1.0",
                                   stopindex=tk.END,
                                   nocase=True)
            if pos:
                self.search_pos = f"{pos}+{len(keyword)}c"
                self.text.see(pos)
                self.text.focus_set()
            else:
                messagebox.showinfo("搜索", f"未找到: {keyword}")

    def search_next(self):
        """查找下一个"""
        self.search_text()


# ============ 主程序 ============


def main():
    # 超参数配置
    APP_TITLE = "Claude 会话管理器"
    WINDOW_GEOMETRY = "1200x700"
    DEVELOPER = "Qzjzl20000"
    VERSION = "v2.3"
    FOOTER_HINT = "💡 双击对话可查看详情"

    root = tk.Tk()
    app = SessionManagerApp(root,
                            app_title=APP_TITLE,
                            window_geometry=WINDOW_GEOMETRY,
                            developer=DEVELOPER,
                            version=VERSION,
                            footer_hint=FOOTER_HINT)
    root.mainloop()


if __name__ == "__main__":
    main()
