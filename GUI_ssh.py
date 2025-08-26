#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SSH GUI Client Ultimate - 全面改修版

未来的なクリスタル・ダークモダンUI、アニメーション、大幅な機能拡充、
そして自律的なアクションを実行可能なAIを搭載した究極のSSHクライアント。
"""

import tkinter as tk
from tkinter import messagebox, simpledialog, scrolledtext, filedialog
# Use standard tkinter.ttk for predictable, readable dark theme (do not use ttkbootstrap)
from tkinter import ttk
USING_TTKB = False

import paramiko
import threading
import os
import time
import json
import stat
from datetime import datetime
import re
from typing import Optional, Dict, Any, List

# LM Studio (OpenAI互換) 連携のためのrequestsライブラリ
try:
    import requests
except ImportError:
    requests = None

class SafetyGuardian:
    """サーバーの安全を守るための独立した監視クラス"""
    def __init__(self, settings_callback):
        self.get_settings = settings_callback
        self.command_timestamps: List[float] = []

    def get_config(self, key: str, default: Any) -> Any:
        return self.get_settings().get(key, default)

    def check_command(self, command: str) -> bool:
        """コマンド実行前の安全チェック"""
        # 1. 危険なコマンドパターンのチェック
        dangerous_patterns = self.get_config('dangerous_commands', [])
        for pat in dangerous_patterns:
            if re.search(pat, command):
                if not messagebox.askyesno("危険な操作の確認", f"危険なコマンドパターンが含まれています:\n`{pat}`\n\nコマンド:\n{command}\n\n本当に実行しますか？"):
                    return False

        # 2. 保護パスへの破壊的操作をチェック
        protected_paths = self.get_config('protected_paths', [])
        destructive_ops = ['rm', 'mv', 'chmod', 'chown', 'dd', 'mkfs']
        if any(op in command.split() for op in destructive_ops):
            for token in command.split():
                if token.startswith('/'):
                    for protected in protected_paths:
                        if os.path.normpath(token) == protected or os.path.normpath(token).startswith(protected + '/'):
                            messagebox.showerror("保護されたパス", f"保護されたシステムパスへの破壊的操作はブロックされました:\n{token}")
                            return False

        # 3. コマンド実行レート制限
        rate_limit_count = self.get_config('rate_limit_count', 10)
        rate_limit_seconds = self.get_config('rate_limit_seconds', 5)
        now = time.time()
        self.command_timestamps.append(now)
        # 古いタイムスタンプを削除
        self.command_timestamps = [ts for ts in self.command_timestamps if now - ts < rate_limit_seconds]
        if len(self.command_timestamps) > rate_limit_count:
            messagebox.showwarning("レート制限", f"{rate_limit_seconds}秒以内に{rate_limit_count}回以上のコマンドが実行されました。サーバー負荷を考慮し、操作を中断します。")
            self.command_timestamps = [] # リセット
            return False
            
        return True

    def check_file_write(self, path: str) -> bool:
        """ファイル書き込み前の安全チェック"""
        protected_paths = self.get_config('protected_paths', [])
        for protected in protected_paths:
            if os.path.normpath(path) == protected or os.path.normpath(path).startswith(protected + '/'):
                messagebox.showerror("保護されたパス", f"保護されたシステムパスへの書き込みはブロックされました:\n{path}")
                return False
        return True

    def check_file_read(self, size: int) -> bool:
        """ファイル読み込み前の安全チェック"""
        max_size = self.get_config('max_file_size', 20 * 1024 * 1024)
        if size > max_size:
            return messagebox.askyesno("ファイルサイズ警告", f"ファイルサイズが{size // 1024 // 1024}MBと大きいです。続行しますか？")
        return True


class SSHGUIClient:
    def __init__(self, root):
        self.root = root
        self.root.title("SSH GUI Client Ultimate")
        self.root.geometry("1600x1000")
        self.root.configure(bg='#1a1a1a')

        self.setup_modern_style()
        self.animation_tasks = {}
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.sftp_client: Optional[paramiko.SFTPClient] = None
        self.connected = False
        self.current_path = "/"
        self.connection_info: Dict[str, Any] = {}

        self.safety_settings = {
            'max_file_size': 20 * 1024 * 1024,
            'dangerous_commands': ['rm -rf /', 'dd if=', 'mkfs', 'fdisk', 'parted'],
            'protected_paths': ['/etc', '/boot', '/var', '/usr', '/bin', '/sbin', '/lib', '/lib64'],
            'rate_limit_count': 10,
            'rate_limit_seconds': 5,
            'timeout_seconds': 30,
            'backup_before_edit': True,
        }
        self.guardian = SafetyGuardian(lambda: self.safety_settings)

        self.active_operations = 0
        self.command_history = []
        self.history_index = -1
        self.tabs: Dict[str, Dict[str, Any]] = {}
        self.selected_files = []
        self.clipboard_content: Optional[Dict[str, Any]] = None
        self.sudo_var = tk.BooleanVar(value=False)

        self.ai_settings = {
            'endpoint': 'http://localhost:1234/v1/chat/completions',
            'model': 'local-model',
            'system_prompt': (
                'あなたはプロの自律型SSHオペレーターアシスタントです。ユーザーの指示を達成するため、'
                'コマンド実行、ファイル操作、情報収集などの`actions`を段階的に実行します。\n'
                '利用可能なアクション:\n'
                '- `chat`: ユーザーにメッセージを表示\n'
                '- `command`: シェルコマンドを実行\n'
                '- `read_file`: リモートファイルを読み取り、内容を返す\n'
                '- `list_dir`: ディレクトリの内容を一覧表示\n'
                '- `write_file`: リモートファイルに内容を書き込む\n'
                '- `set_cwd`: カレントディレクトリを変更\n'
                '- `open_in_editor`: GUIエディタでファイルを開く\n'
                '- `get_terminal_output`: 直近のターミナル出力を取得して解析\n'
                '- `resubmit`: 新しいプロンプトで自己対話を継続\n'
                '常に安全を最優先し、破壊的操作の前には必ず`chat`でユーザーの許可を得てください。'
            )
        }
        self.ai_include_file_var = tk.BooleanVar(value=False)
        self.ai_structured_var = tk.BooleanVar(value=True)
        self.ai_auto_execute_var = tk.BooleanVar(value=False)
        self.ai_message_history = []
        self.ai_last_suggested_command: Optional[str] = None
        self.ai_staged_actions = []

        self.history_file = os.path.expanduser('~/.ssh_gui_client_history.json')
        self.connection_history = []
        self.load_connection_history()

        self.build_modern_ui()
        self.animate_glow(self.root, start_color='#2a2a2a', end_color='#1a1a1a', duration=5000, interval=50, loop=True)

    def setup_modern_style(self):
        # Modern Dark Theme - より使いやすく現代的なカラーパレット
        self.colors = {
            'bg': '#1e1e1e',            # VS Code風ダーク背景
            'bg_secondary': '#2d2d30',  # パネル背景
            'bg_light': '#3e3e42',      # ハイライト/ホバー
            'bg_card': '#252526',       # カード背景
            'fg': '#cccccc',            # メイン文字色
            'fg_secondary': '#9d9d9d',  # 補助文字色
            'fg_muted': '#6f6f6f',      # 薄い文字色
            'accent': '#007acc',        # VS Code風アクセント
            'accent_light': '#1e8ce6',  # ライトアクセント
            'accent_dark': '#005a9e',   # ダークアクセント
            'success': '#28a745',       # 成功色
            'warning': '#fd7e14',       # 警告色
            'error': '#dc3545',         # エラー色
            'info': '#17a2b8',          # 情報色
            'code_bg': '#1e1e1e',       # エディタ背景
            'code_fg': '#d4d4d4',       # エディタ文字色
            'border': '#464647',        # 境界線
            'shadow': '#00000020',      # 影
        }

        self.style = ttk.Style()
        try:
            # Vista/Windows 10風のテーマを使用
            available_themes = self.style.theme_names()
            if 'vista' in available_themes:
                self.style.theme_use('vista')
            elif 'clam' in available_themes:
                self.style.theme_use('clam')
            else:
                self.style.theme_use('default')

            # モダンなベーススタイル
            self.style.configure('.', 
                background=self.colors['bg'], 
                foreground=self.colors['fg'],
                borderwidth=0,
                relief='flat'
            )

            # フレーム系
            self.style.configure('TFrame', 
                background=self.colors['bg'],
                relief='flat'
            )
            self.style.configure('Card.TFrame', 
                background=self.colors['bg_card'],
                relief='flat'
            )

            # ラベル
            self.style.configure('TLabel', 
                background=self.colors['bg'], 
                foreground=self.colors['fg'],
                font=('Segoe UI', 9)
            )
            self.style.configure('Heading.TLabel', 
                background=self.colors['bg'], 
                foreground=self.colors['fg'],
                font=('Segoe UI', 12, 'bold')
            )
            self.style.configure('Secondary.TLabel', 
                background=self.colors['bg'], 
                foreground=self.colors['fg_secondary'],
                font=('Segoe UI', 8)
            )

            # ラベルフレーム
            self.style.configure('TLabelframe', 
                background=self.colors['bg'],
                bordercolor=self.colors['border'],
                darkcolor=self.colors['bg'],
                lightcolor=self.colors['bg'],
                borderwidth=1,
                relief='solid'
            )
            self.style.configure('TLabelframe.Label', 
                background=self.colors['bg'], 
                foreground=self.colors['accent'],
                font=('Segoe UI', 9, 'bold')
            )

            # エントリー - モダンな入力フィールド
            self.style.configure('TEntry', 
                fieldbackground=self.colors['bg_secondary'],
                foreground=self.colors['fg'],
                bordercolor=self.colors['border'],
                insertcolor=self.colors['accent'],
                borderwidth=1,
                relief='solid'
            )
            self.style.map('TEntry', 
                fieldbackground=[('focus', self.colors['bg_light']),
                               ('active', self.colors['bg_light'])],
                bordercolor=[('focus', self.colors['accent']),
                           ('active', self.colors['accent'])]
            )

            # ボタン - フラットでモダンなデザイン
            self.style.configure('TButton', 
                background=self.colors['bg_secondary'],
                foreground=self.colors['fg'],
                bordercolor=self.colors['border'],
                focuscolor='none',
                borderwidth=1,
                relief='solid',
                padding=(12, 8),
                font=('Segoe UI', 9)
            )
            self.style.map('TButton', 
                background=[('active', self.colors['bg_light']),
                          ('pressed', self.colors['accent_dark'])],
                foreground=[('active', self.colors['fg']),
                          ('pressed', '#ffffff')],
                bordercolor=[('active', self.colors['accent']),
                           ('pressed', self.colors['accent_dark'])]
            )

            # プライマリボタン
            self.style.configure('Primary.TButton', 
                background=self.colors['accent'],
                foreground='#ffffff',
                bordercolor=self.colors['accent'],
                focuscolor='none',
                borderwidth=1,
                relief='solid',
                padding=(12, 8),
                font=('Segoe UI', 9, 'bold')
            )
            self.style.map('Primary.TButton', 
                background=[('active', self.colors['accent_light']),
                          ('pressed', self.colors['accent_dark'])],
                bordercolor=[('active', self.colors['accent_light']),
                           ('pressed', self.colors['accent_dark'])]
            )

            # 成功ボタン
            self.style.configure('Success.TButton', 
                background=self.colors['success'],
                foreground='#ffffff',
                bordercolor=self.colors['success']
            )

            # 警告ボタン
            self.style.configure('Warning.TButton', 
                background=self.colors['warning'],
                foreground='#ffffff',
                bordercolor=self.colors['warning']
            )

            # エラーボタン
            self.style.configure('Danger.TButton', 
                background=self.colors['error'],
                foreground='#ffffff',
                bordercolor=self.colors['error']
            )

            # Treeview - 見やすく整理
            self.style.configure('Treeview', 
                background=self.colors['bg_secondary'],
                foreground=self.colors['fg'],
                fieldbackground=self.colors['bg_secondary'],
                bordercolor=self.colors['border'],
                borderwidth=1,
                relief='solid',
                rowheight=24
            )
            self.style.map('Treeview', 
                background=[('selected', self.colors['accent'])],
                foreground=[('selected', '#ffffff')]
            )
            self.style.configure('Treeview.Heading', 
                background=self.colors['bg_light'],
                foreground=self.colors['fg'],
                bordercolor=self.colors['border'],
                relief='solid',
                font=('Segoe UI', 9, 'bold')
            )

            # Notebook - タブ形式
            self.style.configure('TNotebook', 
                background=self.colors['bg'],
                bordercolor=self.colors['border'],
                tabposition='n'
            )
            self.style.configure('TNotebook.Tab', 
                background=self.colors['bg_secondary'],
                foreground=self.colors['fg_secondary'],
                bordercolor=self.colors['border'],
                padding=(16, 8),
                font=('Segoe UI', 9)
            )
            self.style.map('TNotebook.Tab', 
                background=[('selected', self.colors['bg_light']),
                          ('active', self.colors['bg_light'])],
                foreground=[('selected', self.colors['fg']),
                          ('active', self.colors['fg'])]
            )

            # チェックボックス
            self.style.configure('TCheckbutton', 
                background=self.colors['bg'],
                foreground=self.colors['fg'],
                focuscolor='none',
                font=('Segoe UI', 9)
            )

            # プログレスバー
            self.style.configure('TProgressbar', 
                background=self.colors['accent'],
                troughcolor=self.colors['bg_secondary'],
                bordercolor=self.colors['border'],
                lightcolor=self.colors['accent'],
                darkcolor=self.colors['accent']
            )

            # スクロールバー
            self.style.configure('Vertical.TScrollbar', 
                background=self.colors['bg_secondary'],
                troughcolor=self.colors['bg'],
                bordercolor=self.colors['border'],
                arrowcolor=self.colors['fg_secondary'],
                darkcolor=self.colors['bg_secondary'],
                lightcolor=self.colors['bg_light']
            )

        except Exception as e:
            print(f"Style configuration error: {e}")
    
    def animate_glow(self, widget, start_color, end_color, duration, interval, loop=False):
        steps = duration // interval
        def _animate(step):
            try:
                r1, g1, b1 = self.root.winfo_rgb(start_color)
                r2, g2, b2 = self.root.winfo_rgb(end_color)
                r = int((r1 + (r2 - r1) * step / steps) // 256)
                g = int((g1 + (g2 - g1) * step / steps) // 256)
                b = int((b1 + (b2 - b1) * step / steps) // 256)
                new_color = f'#{r:02x}{g:02x}{b:02x}'
                widget.config(background=new_color)
                if step < steps:
                    task_id = self.root.after(interval, _animate, step + 1)
                    self.animation_tasks[widget] = task_id
                elif loop:
                    task_id = self.root.after(interval, self.animate_glow, widget, end_color, start_color, duration, interval, True)
                    self.animation_tasks[widget] = task_id
            except (tk.TclError, ValueError): return
        if widget in self.animation_tasks: self.root.after_cancel(self.animation_tasks[widget])
        _animate(0)

    def build_modern_ui(self):
        """モダンなカードベースのUIレイアウトを構築"""
        self.root.configure(bg=self.colors['bg'])
        
        # メインコンテナ
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        
        # ヘッダー部分
        header_frame = ttk.Frame(main_container, style='Card.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 16))
        self.create_modern_header(header_frame)
        
        # メインコンテンツエリア
        content_pane = ttk.PanedWindow(main_container, orient=tk.HORIZONTAL)
        content_pane.pack(fill=tk.BOTH, expand=True)
        
        # 左パネル (サイドバー)
        left_panel = ttk.Frame(content_pane, style='Card.TFrame')
        content_pane.add(left_panel, weight=1)
        
        # 右パネル (メインワークスペース)
        right_panel = ttk.Frame(content_pane)
        content_pane.add(right_panel, weight=3)
        
        # 左パネルにコンテンツを配置
        self.create_sidebar(left_panel)
        
        # 右パネルをさらに分割（上下）
        workspace_pane = ttk.PanedWindow(right_panel, orient=tk.VERTICAL)
        workspace_pane.pack(fill=tk.BOTH, expand=True, padx=(16, 0))
        
        # 上部ワークスペース
        upper_workspace = ttk.Frame(workspace_pane)
        workspace_pane.add(upper_workspace, weight=2)
        
        # 下部パネル
        lower_workspace = ttk.Frame(workspace_pane)
        workspace_pane.add(lower_workspace, weight=1)
        
        # ワークスペースコンテンツ
        self.create_workspace_tabs(upper_workspace)
        self.create_terminal_ai_panel(lower_workspace)
        
        # ステータスバー
        self.create_modern_status_bar(self.root)

    def create_modern_header(self, parent):
        """モダンなヘッダーバー"""
        # タイトルとクイックアクション
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill=tk.X, padx=16, pady=12)
        
        # アプリタイトル
        title_label = ttk.Label(title_frame, text="SSH Client Pro", 
                               style='Heading.TLabel')
        title_label.pack(side=tk.LEFT)
        
        # 接続ステータス
        self.connection_indicator = ttk.Label(title_frame, text="●", 
                                            foreground=self.colors['error'])
        self.connection_indicator.pack(side=tk.RIGHT, padx=(0, 8))
        
        self.connection_status_label = ttk.Label(title_frame, text="未接続", 
                                               style='Secondary.TLabel')
        self.connection_status_label.pack(side=tk.RIGHT)
        
        # 接続フォーム
        conn_frame = ttk.Frame(parent)
        conn_frame.pack(fill=tk.X, padx=16, pady=(0, 12))
        
        # 左側：接続フォーム
        form_frame = ttk.Frame(conn_frame)
        form_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # ホスト情報を横一列に
        host_frame = ttk.Frame(form_frame)
        host_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Label(host_frame, text="ホスト").pack(side=tk.LEFT, padx=(0, 8))
        self.host_entry = ttk.Entry(host_frame, width=20)
        self.host_entry.pack(side=tk.LEFT, padx=(0, 16))
        self.host_entry.insert(0, "localhost")
        
        ttk.Label(host_frame, text="ポート").pack(side=tk.LEFT, padx=(0, 8))
        self.port_entry = ttk.Entry(host_frame, width=8)
        self.port_entry.pack(side=tk.LEFT, padx=(0, 16))
        self.port_entry.insert(0, "22")
        
        ttk.Label(host_frame, text="ユーザー").pack(side=tk.LEFT, padx=(0, 8))
        self.user_entry = ttk.Entry(host_frame, width=15)
        self.user_entry.pack(side=tk.LEFT, padx=(0, 16))
        
        ttk.Label(host_frame, text="パスワード").pack(side=tk.LEFT, padx=(0, 8))
        self.password_entry = ttk.Entry(host_frame, show="*", width=15)
        self.password_entry.pack(side=tk.LEFT)
        
        # 右側：接続ボタン
        button_frame = ttk.Frame(conn_frame)
        button_frame.pack(side=tk.RIGHT, padx=(16, 0))
        
        self.connect_btn = ttk.Button(button_frame, text="接続", 
                                     command=self.connect_ssh, 
                                     style='Primary.TButton')
        self.connect_btn.pack(side=tk.TOP, pady=(0, 4))
        
        self.disconnect_btn = ttk.Button(button_frame, text="切断", 
                                        command=self.disconnect_ssh, 
                                        state=tk.DISABLED)
        self.disconnect_btn.pack(side=tk.TOP)

    def create_sidebar(self, parent):
        """サイドバー（ファイルブラウザ等）"""
        # サイドバータイトル
        sidebar_title = ttk.Label(parent, text="ファイルブラウザ", 
                                 style='Heading.TLabel')
        sidebar_title.pack(anchor=tk.W, padx=16, pady=(16, 8))
        
        # ナビゲーション
        nav_frame = ttk.Frame(parent)
        nav_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        
        ttk.Button(nav_frame, text="↑", command=self.go_parent_directory, 
                  width=3).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(nav_frame, text="🏠", command=self.go_home_directory, 
                  width=3).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(nav_frame, text="⟳", command=lambda: self.refresh_file_list(), 
                  width=3).pack(side=tk.LEFT)
        
        # パス表示
        path_frame = ttk.Frame(parent)
        path_frame.pack(fill=tk.X, padx=16, pady=(0, 8))
        
        ttk.Label(path_frame, text="パス:", style='Secondary.TLabel').pack(anchor=tk.W)
        self.path_var = tk.StringVar(value=self.current_path)
        self.path_entry = ttk.Entry(path_frame, textvariable=self.path_var)
        self.path_entry.pack(fill=tk.X, pady=(2, 0))
        self.path_entry.bind("<Return>", self.navigate_to_path)
        
        # ファイルリスト
        files_frame = ttk.Frame(parent)
        files_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 16))
        
        # Treeviewのセットアップ
        columns = ("name", "size", "type", "modified")
        self.file_tree = ttk.Treeview(files_frame, columns=columns, 
                                     show="tree headings", height=15)
        
        # 列の設定
        self.file_tree.heading("#0", text="📁", anchor=tk.W)
        self.file_tree.heading("name", text="名前", anchor=tk.W)
        self.file_tree.heading("size", text="サイズ", anchor=tk.E)
        self.file_tree.heading("type", text="種類", anchor=tk.W)
        self.file_tree.heading("modified", text="更新日", anchor=tk.W)
        
        self.file_tree.column("#0", width=30, minwidth=30, stretch=False)
        self.file_tree.column("name", width=150, minwidth=100)
        self.file_tree.column("size", width=80, minwidth=60, anchor=tk.E)
        self.file_tree.column("type", width=60, minwidth=60)
        self.file_tree.column("modified", width=120, minwidth=100)
        
        # スクロールバー
        scrollbar = ttk.Scrollbar(files_frame, orient=tk.VERTICAL, 
                                 command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=scrollbar.set)
        
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # イベントバインド
        self.file_tree.bind("<Double-1>", self.on_file_double_click)
        self.file_tree.bind("<Button-3>", self.show_context_menu)
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_select)

    def create_workspace_tabs(self, parent):
        """ワークスペースタブ（エディタ等）"""
        # タブヘッダー
        tab_header = ttk.Frame(parent)
        tab_header.pack(fill=tk.X, padx=16, pady=(16, 0))
        
        ttk.Label(tab_header, text="ワークスペース", 
                 style='Heading.TLabel').pack(side=tk.LEFT)
        
        # 新規ファイルボタン
        ttk.Button(tab_header, text="+ 新規", 
                  command=lambda: self.create_editor_tab("新規ファイル", "")).pack(side=tk.RIGHT)
        
        # エディタエリア
        editor_frame = ttk.Frame(parent, style='Card.TFrame')
        editor_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 16))
        
        self.editor_notebook = ttk.Notebook(editor_frame)
        self.editor_notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.editor_notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        # 初期タブを作成
        self.create_editor_tab("Welcome", self.get_welcome_content())

    def create_terminal_ai_panel(self, parent):
        """ターミナルとAIパネルを含む下部エリア"""
        # パネルヘッダー
        panel_header = ttk.Frame(parent)
        panel_header.pack(fill=tk.X, padx=16, pady=(16, 0))
        
        ttk.Label(panel_header, text="ターミナル & AI アシスタント", 
                 style='Heading.TLabel').pack(side=tk.LEFT)
        
        # パネルコンテンツ
        panel_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        panel_pane.pack(fill=tk.BOTH, expand=True, padx=16, pady=(8, 16))
        
        # ターミナルパネル
        terminal_frame = ttk.Frame(panel_pane, style='Card.TFrame')
        panel_pane.add(terminal_frame, weight=2)
        self.create_modern_terminal(terminal_frame)
        
        # AIパネル
        ai_frame = ttk.Frame(panel_pane, style='Card.TFrame')
        panel_pane.add(ai_frame, weight=1)
        self.create_modern_ai_panel(ai_frame)

    def create_modern_terminal(self, parent):
        """モダンなターミナルパネル"""
        # ターミナルヘッダー
        term_header = ttk.Frame(parent)
        term_header.pack(fill=tk.X, padx=12, pady=(12, 8))
        
        ttk.Label(term_header, text="ターミナル", 
                 style='Heading.TLabel').pack(side=tk.LEFT)
        
        ttk.Button(term_header, text="クリア", 
                  command=self.clear_terminal).pack(side=tk.RIGHT)
        
        # コマンド入力
        cmd_frame = ttk.Frame(parent)
        cmd_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
        
        ttk.Label(cmd_frame, text="$", style='Secondary.TLabel').pack(side=tk.LEFT, padx=(0, 8))
        
        self.command_entry = ttk.Entry(cmd_frame)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.command_entry.bind("<Return>", self.execute_command)
        self.command_entry.bind("<Up>", self.command_history_up)
        self.command_entry.bind("<Down>", self.command_history_down)
        
        self.sudo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cmd_frame, text="sudo", variable=self.sudo_var).pack(side=tk.LEFT, padx=(0, 8))
        
        ttk.Button(cmd_frame, text="実行", command=self.execute_command, 
                  style='Primary.TButton').pack(side=tk.RIGHT)
        
        # 出力エリア
        output_frame = ttk.Frame(parent)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        
        self.terminal_output = scrolledtext.ScrolledText(
            output_frame, 
            height=10, 
            background=self.colors['code_bg'], 
            foreground=self.colors['code_fg'],
            insertbackground=self.colors['accent'],
            font=('Consolas', 10)
        )
        self.terminal_output.pack(fill=tk.BOTH, expand=True)

    def create_modern_ai_panel(self, parent):
        """モダンなAIアシスタントパネル"""
        # AIヘッダー
        ai_header = ttk.Frame(parent)
        ai_header.pack(fill=tk.X, padx=12, pady=(12, 8))
        
        ttk.Label(ai_header, text="AI アシスタント", 
                 style='Heading.TLabel').pack(side=tk.LEFT)
        
        # 設定ボタン
        settings_frame = ttk.Frame(ai_header)
        settings_frame.pack(side=tk.RIGHT)
        
        self.ai_include_file_var = tk.BooleanVar(value=False)
        self.ai_auto_execute_var = tk.BooleanVar(value=False)
        self.ai_agent_var = tk.BooleanVar(value=False)
        
        ttk.Checkbutton(settings_frame, text="ファイル添付", 
                       variable=self.ai_include_file_var).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(settings_frame, text="自動実行", 
                       variable=self.ai_auto_execute_var).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(settings_frame, text="Agent", 
                       variable=self.ai_agent_var).pack(side=tk.LEFT, padx=2)
        
        # チャット表示
        chat_frame = ttk.Frame(parent)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 8))
        
        self.ai_chat_display = scrolledtext.ScrolledText(
            chat_frame, 
            wrap=tk.WORD, 
            height=8,
            background=self.colors['bg_secondary'], 
            foreground=self.colors['fg'],
            font=('Segoe UI', 9)
        )
        self.ai_chat_display.pack(fill=tk.BOTH, expand=True)
        
        # タグ設定
        self.ai_chat_display.tag_config('USER', foreground=self.colors['accent'])
        self.ai_chat_display.tag_config('ASSIST', foreground=self.colors['success'])
        self.ai_chat_display.tag_config('CODE', background=self.colors['code_bg'], 
                                       foreground=self.colors['code_fg'], 
                                       font=('Consolas', 9))
        self.ai_chat_display.tag_config('META', foreground=self.colors['fg_secondary'])
        
        self.ai_chat_display.insert(tk.END, "AI アシスタントにタスクを依頼できます。\n", 'META')
        self.ai_chat_display.config(state=tk.DISABLED)
        
        # AI入力
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, padx=12, pady=(0, 8))
        
        self.ai_input = ttk.Entry(input_frame)
        self.ai_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.ai_input.bind('<Return>', self.ai_enter_to_send)
        
        ttk.Button(input_frame, text="送信", command=self.send_ai_prompt, 
                  style='Primary.TButton').pack(side=tk.RIGHT)
        
        # アクション管理エリア
        action_frame = ttk.LabelFrame(parent, text="AI アクション")
        action_frame.pack(fill=tk.X, padx=12, pady=(0, 12))
        
        # アクションリスト
        action_list_frame = ttk.Frame(action_frame)
        action_list_frame.pack(fill=tk.X, padx=8, pady=8)
        
        self.ai_action_tree = ttk.Treeview(action_list_frame, 
                                          columns=("action", "details", "status"), 
                                          show="headings", height=4)
        self.ai_action_tree.heading("action", text="アクション")
        self.ai_action_tree.heading("details", text="詳細")
        self.ai_action_tree.heading("status", text="ステータス")
        
        self.ai_action_tree.column("action", width=80)
        self.ai_action_tree.column("details", width=200)
        self.ai_action_tree.column("status", width=80)
        
        self.ai_action_tree.pack(fill=tk.X)
        self.ai_action_tree.bind('<Double-1>', lambda e: self.show_ai_action_preview(e))
        
        # アクションボタン
        action_btn_frame = ttk.Frame(action_frame)
        action_btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        
        ttk.Button(action_btn_frame, text="承認", 
                  command=self.approve_selected_actions,
                  style='Success.TButton').pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(action_btn_frame, text="拒否", 
                  command=self.reject_selected_actions,
                  style='Danger.TButton').pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(action_btn_frame, text="プレビュー", 
                  command=lambda: self.show_ai_action_preview()).pack(side=tk.LEFT, padx=(0, 4))
        
        self.ai_exec_btn = ttk.Button(action_btn_frame, text="実行", 
                                     command=self.execute_approved_actions, 
                                     state=tk.DISABLED,
                                     style='Primary.TButton')
        self.ai_exec_btn.pack(side=tk.RIGHT)
        
        # 初期化
        self.ai_action_status = {}
        self.ai_staged_actions = []

    def create_modern_status_bar(self, parent):
        """モダンなステータスバー"""
        status_frame = ttk.Frame(parent, style='Card.TFrame')
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=16, pady=(0, 16))
        
        # 左側：接続情報
        left_status = ttk.Frame(status_frame)
        left_status.pack(side=tk.LEFT, padx=12, pady=8)
        
        self.connection_status = ttk.Label(left_status, text="未接続", 
                                         style='Secondary.TLabel')
        self.connection_status.pack(side=tk.LEFT, padx=(0, 16))
        
        self.path_status = ttk.Label(left_status, text="パス: /", 
                                   style='Secondary.TLabel')
        self.path_status.pack(side=tk.LEFT, padx=(0, 16))
        
        self.selection_status = ttk.Label(left_status, text="選択: 0個", 
                                        style='Secondary.TLabel')
        self.selection_status.pack(side=tk.LEFT)
        
        # 右側：操作ステータス
        right_status = ttk.Frame(status_frame)
        right_status.pack(side=tk.RIGHT, padx=12, pady=8)
        
        self.operation_status = ttk.Label(right_status, text="待機中", 
                                        style='Secondary.TLabel')
        self.operation_status.pack(side=tk.RIGHT)

    def get_welcome_content(self):
        """ウェルカムコンテンツ"""
        return """# SSH Client Pro へようこそ

## 機能
- SSH接続とファイル管理
- リモートファイル編集
- ターミナル操作
- AI アシスタント（自動タスク実行）

## 使い方
1. 上部でサーバー情報を入力して接続
2. 左のファイルブラウザでファイルを選択
3. ターミナルでコマンド実行
4. AI アシスタントにタスクを依頼

## ショートカット
- Ctrl+S: ファイル保存
- Enter: コマンド実行
- ↑/↓: コマンド履歴

---
Modern UI Design - より使いやすく、より美しく
"""

    def create_connection_panel(self, parent):
        conn_frame = ttk.LabelFrame(parent, text="接続")
        conn_frame.pack(fill=tk.X, expand=True, pady=(0, 5))
        toolbar = ttk.Frame(conn_frame)
        toolbar.pack(fill=tk.X, padx=10, pady=5)
        self.ai_quick_entry = ttk.Entry(toolbar, width=40)
        self.ai_quick_entry.insert(0, "AIにクイック質問...")
        self.ai_quick_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.ai_quick_entry.bind('<Return>', lambda e: self.send_ai_quick())
        ttk.Button(toolbar, text="AIに送信", command=self.send_ai_quick).pack(side=tk.LEFT)
        form_frame = ttk.Frame(conn_frame)
        form_frame.pack(fill=tk.X, padx=10, pady=10)
        ttk.Label(form_frame, text="ホスト:").grid(row=0, column=0, sticky=tk.W)
        self.host_entry = ttk.Entry(form_frame, width=15)
        self.host_entry.grid(row=0, column=1, padx=(2, 8))
        self.host_entry.insert(0, "localhost")
        ttk.Label(form_frame, text="ポート:").grid(row=0, column=2, sticky=tk.W)
        self.port_entry = ttk.Entry(form_frame, width=6)
        self.port_entry.grid(row=0, column=3, padx=(2, 8))
        self.port_entry.insert(0, "22")
        ttk.Label(form_frame, text="ユーザー:").grid(row=0, column=4, sticky=tk.W)
        self.user_entry = ttk.Entry(form_frame, width=12)
        self.user_entry.grid(row=0, column=5, padx=(2, 8))
        ttk.Label(form_frame, text="パスワード:").grid(row=0, column=6, sticky=tk.W)
        self.password_entry = ttk.Entry(form_frame, show="*", width=12)
        self.password_entry.grid(row=0, column=7, padx=(2, 8))
        self.connect_btn = ttk.Button(form_frame, text="接続", command=self.connect_ssh)
        self.connect_btn.grid(row=0, column=8, padx=5)
        self.disconnect_btn = ttk.Button(form_frame, text="切断", command=self.disconnect_ssh, state=tk.DISABLED)
        self.disconnect_btn.grid(row=0, column=9)
        ttk.Label(form_frame, text="履歴:").grid(row=0, column=10, sticky=tk.W, padx=(15, 5))
        self.history_combo = ttk.Combobox(form_frame, width=28, state='readonly')
        self.history_combo.grid(row=0, column=11)
        self.history_combo.bind('<<ComboboxSelected>>', self.on_history_selected)
        ttk.Button(form_frame, text="削除", command=self.delete_selected_history).grid(row=0, column=12, padx=5)
        self.refresh_history_combo()

    def create_tools_panel(self, parent):
        tools_frame = ttk.LabelFrame(parent, text="クイックツール")
        tools_frame.pack(fill=tk.X, expand=True, pady=5)
        tools_notebook = ttk.Notebook(tools_frame)
        tools_notebook.pack(fill=tk.X, expand=True, padx=5, pady=5)
        proc_frame = ttk.Frame(tools_notebook)
        tools_notebook.add(proc_frame, text="プロセス")
        ttk.Button(proc_frame, text="全プロセス一覧", command=lambda: self.run_tool_command("ps aux")).pack(side=tk.LEFT, padx=5, pady=5)
        self.pid_entry = ttk.Entry(proc_frame, width=8)
        self.pid_entry.pack(side=tk.LEFT, pady=5)
        self.pid_entry.insert(0, "PID")
        ttk.Button(proc_frame, text="強制終了", command=self.kill_process).pack(side=tk.LEFT, padx=5, pady=5)
        svc_frame = ttk.Frame(tools_notebook)
        tools_notebook.add(svc_frame, text="サービス")
        self.svc_entry = ttk.Entry(svc_frame, width=15)
        self.svc_entry.pack(side=tk.LEFT, padx=5, pady=5)
        self.svc_entry.insert(0, "nginx")
        ttk.Button(svc_frame, text="開始", command=lambda: self.run_tool_command(f"sudo systemctl start {self.svc_entry.get()}")).pack(side=tk.LEFT, pady=5)
        ttk.Button(svc_frame, text="停止", command=lambda: self.run_tool_command(f"sudo systemctl stop {self.svc_entry.get()}")).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(svc_frame, text="再起動", command=lambda: self.run_tool_command(f"sudo systemctl restart {self.svc_entry.get()}")).pack(side=tk.LEFT, pady=5)
        ttk.Button(svc_frame, text="状態確認", command=lambda: self.run_tool_command(f"sudo systemctl status {self.svc_entry.get()}")).pack(side=tk.LEFT, padx=5, pady=5)
        log_frame = ttk.Frame(tools_notebook)
        tools_notebook.add(log_frame, text="ログ監視")
        self.log_path_entry = ttk.Entry(log_frame, width=30)
        self.log_path_entry.pack(side=tk.LEFT, padx=5, pady=5)
        self.log_path_entry.insert(0, "/var/log/syslog")
        ttk.Button(log_frame, text="監視開始 (tail -f)", command=self.tail_log).pack(side=tk.LEFT, padx=5, pady=5)
        safety_frame = ttk.Frame(tools_notebook)
        tools_notebook.add(safety_frame, text="安全設定")
        ttk.Label(safety_frame, text="保護パス (コンマ区切り):").pack(side=tk.LEFT, padx=5, pady=5)
        self.protected_paths_entry = ttk.Entry(safety_frame, width=40)
        self.protected_paths_entry.insert(0, ", ".join(self.safety_settings['protected_paths']))
        self.protected_paths_entry.pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(safety_frame, text="設定を適用", command=self.update_safety_settings).pack(side=tk.LEFT, padx=5, pady=5)

    def create_file_browser(self, parent):
        browser_frame = ttk.LabelFrame(parent, text="ファイルブラウザ")
        browser_frame.pack(fill=tk.BOTH, expand=True)
        nav_frame = ttk.Frame(browser_frame)
        nav_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(nav_frame, text="上へ", command=self.go_parent_directory).pack(side=tk.LEFT)
        ttk.Button(nav_frame, text="ホーム", command=self.go_home_directory).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="更新", command=lambda: self.refresh_file_list()).pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=self.current_path)
        self.path_entry = ttk.Entry(nav_frame, textvariable=self.path_var)
        self.path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.path_entry.bind("<Return>", self.navigate_to_path)
        list_frame = ttk.Frame(browser_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        columns = ("icon", "name", "size", "type", "permissions", "modified")
        self.file_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.file_tree.heading("icon", text="種別", anchor=tk.W)
        self.file_tree.heading("name", text="名前", anchor=tk.W)
        self.file_tree.heading("size", text="サイズ", anchor=tk.E)
        self.file_tree.heading("type", text="種類", anchor=tk.W)
        self.file_tree.heading("permissions", text="権限", anchor=tk.W)
        self.file_tree.heading("modified", text="更新日時", anchor=tk.W)
        self.file_tree.column("icon", width=50, minwidth=40, stretch=False)
        self.file_tree.column("name", width=220, minwidth=120)
        self.file_tree.column("size", width=100, minwidth=60, anchor=tk.E)
        self.file_tree.column("type", width=100, minwidth=60)
        self.file_tree.column("permissions", width=100, minwidth=90)
        self.file_tree.column("modified", width=160, minwidth=120)
        v_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=v_scrollbar.set)
        self.file_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.file_tree.bind("<Double-1>", self.on_file_double_click)
        self.file_tree.bind("<Button-3>", self.show_context_menu)
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_select)
    
    def create_editor_panel(self, parent):
        editor_frame = ttk.LabelFrame(parent, text="エディタ")
        editor_frame.pack(fill=tk.BOTH, expand=True)
        self.editor_notebook = ttk.Notebook(editor_frame)
        self.editor_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.editor_notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        self.create_editor_tab("新規ファイル", "# SSH GUI Client Ultimate へようこそ")

    def create_bottom_panel(self, parent):
        bottom_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        bottom_pane.pack(fill=tk.BOTH, expand=True)
        left_bottom_frame = ttk.Frame(bottom_pane)
        bottom_pane.add(left_bottom_frame, weight=3)
        right_bottom_frame = ttk.Frame(bottom_pane)
        bottom_pane.add(right_bottom_frame, weight=2)
        self.bottom_notebook = ttk.Notebook(left_bottom_frame)
        self.bottom_notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.create_terminal_tab()
        self.create_log_tab()
        self.create_ai_panel(right_bottom_frame)

    def create_terminal_tab(self):
        terminal_frame = ttk.Frame(self.bottom_notebook)
        toolbar = ttk.Frame(terminal_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        ttk.Label(toolbar, text="$").pack(side=tk.LEFT)
        self.command_entry = ttk.Entry(toolbar)
        self.command_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.command_entry.bind("<Return>", self.execute_command)
        self.command_entry.bind("<Up>", self.command_history_up)
        self.command_entry.bind("<Down>", self.command_history_down)
        ttk.Checkbutton(toolbar, text="sudo", variable=self.sudo_var, style='Switch.TCheckbutton').pack(side=tk.LEFT, padx=(0, 5))
        template_menu_btn = ttk.Menubutton(toolbar, text="テンプレート")
        template_menu = tk.Menu(template_menu_btn, tearoff=0)
        template_commands = ["ls -la", "df -h", "free -h", "top", "sudo apt update && sudo apt upgrade -y", "docker ps -a", "git status"]
        for cmd in template_commands:
            template_menu.add_command(label=cmd, command=lambda c=cmd: self.insert_template_command(c))
        template_menu_btn["menu"] = template_menu
        template_menu_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="生成...", command=self.open_command_generator).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar, text="実行", command=self.execute_command).pack(side=tk.RIGHT)
        ttk.Button(toolbar, text="クリア", command=self.clear_terminal).pack(side=tk.RIGHT, padx=5)
        self.terminal_output = scrolledtext.ScrolledText(terminal_frame, height=10, background=self.colors['code_bg'], foreground=self.colors['code_fg'], insertbackground=self.colors['accent'])
        self.terminal_output.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))
        self.bottom_notebook.add(terminal_frame, text="ターミナル")

    def create_log_tab(self):
        log_frame = ttk.Frame(self.bottom_notebook)
        self.log_output = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD, background=self.colors['bg_secondary'], foreground=self.colors['fg_secondary'])
        self.log_output.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_output.tag_config('INFO', foreground=self.colors['fg'])
        self.log_output.tag_config('SUCCESS', foreground=self.colors['success'])
        self.log_output.tag_config('WARNING', foreground=self.colors['warning'])
        self.log_output.tag_config('ERROR', foreground=self.colors['error'])
        self.bottom_notebook.add(log_frame, text="ログ")

    def create_ai_panel(self, parent):
        ai_frame = ttk.LabelFrame(parent, text="AIアシスタント")
        ai_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 設定行
        settings_row = ttk.Frame(ai_frame)
        settings_row.pack(fill=tk.X, padx=5, pady=5)
        ttk.Checkbutton(settings_row, text="ファイル添付", variable=self.ai_include_file_var, style='Switch.TCheckbutton').pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(settings_row, text="自動実行", variable=self.ai_auto_execute_var, style='Switch.TCheckbutton').pack(side=tk.LEFT, padx=5)
        ttk.Button(settings_row, text="履歴クリア", command=self.clear_ai_history).pack(side=tk.RIGHT)

        # チャット表示
        self.ai_chat_display = scrolledtext.ScrolledText(ai_frame, wrap=tk.WORD, background=self.colors['bg_secondary'], foreground=self.colors['fg'])
        self.ai_chat_display.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.ai_chat_display.tag_config('USER', foreground=self.colors['accent'])
        self.ai_chat_display.tag_config('ASSIST', foreground=self.colors['success'])
        self.ai_chat_display.tag_config('CODE', background=self.colors['code_bg'], foreground=self.colors['code_fg'], font=('Consolas', 9))
        self.ai_chat_display.tag_config('META', foreground=self.colors['fg_secondary'])
        self.ai_chat_display.insert(tk.END, "AIアシスタントにタスクを依頼できます。\n", 'META')
        self.ai_chat_display.config(state=tk.DISABLED)

        # 入力行
        input_frame = ttk.Frame(ai_frame)
        input_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        self.ai_input = scrolledtext.ScrolledText(input_frame, height=3)
        self.ai_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.ai_input.bind('<Return>', self.ai_enter_to_send)
        ttk.Button(input_frame, text="送信", command=self.send_ai_prompt).pack(side=tk.RIGHT)

        # アクション一覧
        action_frame = ttk.LabelFrame(ai_frame, text="AIアクション")
        action_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        self.ai_action_tree = ttk.Treeview(action_frame, columns=("action", "details", "status"), show="headings", height=6)
        self.ai_action_tree.heading("action", text="アクション")
        self.ai_action_tree.heading("details", text="詳細")
        self.ai_action_tree.heading("status", text="ステータス")
        self.ai_action_tree.column("action", width=100)
        self.ai_action_tree.column("details", width=320)
        self.ai_action_tree.column("status", width=100)
        self.ai_action_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 操作用ボタン
        btn_frame = ttk.Frame(action_frame)
        btn_frame.pack(fill=tk.X, padx=5, pady=(0, 5))
        ttk.Button(btn_frame, text="承認", command=self.approve_selected_actions).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="拒否", command=self.reject_selected_actions).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="プレビュー", command=lambda: self.show_ai_action_preview()).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="実行(単体)", command=self.execute_single_action).pack(side=tk.LEFT, padx=3)
        self.ai_exec_btn = ttk.Button(btn_frame, text="承認済みを実行", command=self.execute_approved_actions, state=tk.DISABLED)
        self.ai_exec_btn.pack(side=tk.RIGHT, padx=3)
        self.ai_agent_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btn_frame, text="Agentモード", variable=self.ai_agent_var).pack(side=tk.RIGHT, padx=8)

        # 状態とイベント
        self.ai_action_status = {}
        self.ai_action_tree.bind('<Double-1>', lambda e: self.show_ai_action_preview(e))

    def create_status_bar(self, parent):
        status_frame = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=1)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0))
        self.connection_status = ttk.Label(status_frame, text="未接続", foreground=self.colors['error'])
        self.connection_status.pack(side=tk.LEFT, padx=6)
        self.path_status = ttk.Label(status_frame, text="パス: /")
        self.path_status.pack(side=tk.LEFT, padx=6)
        self.selection_status = ttk.Label(status_frame, text="選択: 0個")
        self.selection_status.pack(side=tk.LEFT, padx=6)
        self.operation_status = ttk.Label(status_frame, text="待機中")
        self.operation_status.pack(side=tk.RIGHT, padx=6)

    def log_message(self, message, level="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        level_map = {"info": "[INFO]", "warning": "[WARN]", "error": "[ERROR]", "success": "[SUCCESS]"}
        tag = level.upper()
        log_line = f"[{timestamp}] {level_map.get(level, '[INFO]')} {message}\n"
        if hasattr(self, 'log_output'):
            self.log_output.config(state=tk.NORMAL)
            self.log_output.insert(tk.END, log_line, tag)
            self.log_output.see(tk.END)
            self.log_output.config(state=tk.DISABLED)
        if hasattr(self, 'operation_status'):
            self.operation_status.config(text=message)
            if level in self.colors:
                self.animate_glow(self.operation_status, self.colors['bg'], self.colors[level], 500, 20)
                self.root.after(1500, lambda: self.animate_glow(self.operation_status, self.colors[level], self.colors['bg'], 500, 20))

    def connect_ssh(self):
        host = self.host_entry.get().strip()
        port = int(self.port_entry.get().strip() or "22")
        username = self.user_entry.get().strip()
        password = self.password_entry.get()
        if not all([host, username]):
            messagebox.showerror("エラー", "ホストとユーザー名は必須です")
            return
        def _connect_thread():
            self.active_operations += 1
            self.log_message(f"接続試行中: {username}@{host}", "info")
            try:
                self.ssh_client = paramiko.SSHClient()
                self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.connection_status.config(text="接続中...", foreground=self.colors['warning'])
                self.ssh_client.connect(host, port=port, username=username, password=password, timeout=15)
                self.sftp_client = self.ssh_client.open_sftp()
                self.connected = True
                self.connection_info = {'host': host, 'port': port, 'username': username}
                self.connection_status.config(text=f"接続済み: {username}@{host}", foreground=self.colors['success'])
                self.connect_btn.config(state=tk.DISABLED)
                self.disconnect_btn.config(state=tk.NORMAL)
                self.go_home_directory()
                self.log_message(f"SSH接続成功: {username}@{host}", "success")
                self.add_connection_history(host, port, username)
            except Exception as e:
                self.connection_status.config(text="接続失敗", foreground=self.colors['error'])
                self.log_message(f"SSH接続失敗: {e}", "error")
                messagebox.showerror("接続エラー", f"SSH接続に失敗しました: {e}")
            finally:
                self.active_operations -= 1
        threading.Thread(target=_connect_thread, daemon=True).start()

    def disconnect_ssh(self):
        if self.sftp_client: self.sftp_client.close()
        if self.ssh_client: self.ssh_client.close()
        self.connected = False
        self.ssh_client = None
        self.sftp_client = None
        self.connection_status.config(text="未接続", foreground=self.colors['error'])
        self.connect_btn.config(state=tk.NORMAL)
        self.disconnect_btn.config(state=tk.DISABLED)
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        self.log_message("SSH接続を切断しました", "info")

    def execute_ssh_command(self, command, callback=None):
        if not self.connected or not self.ssh_client:
            if callback: callback(None, "SSHに接続されていません")
            return
        if not self.guardian.check_command(command):
            if callback: callback(None, "セーフティーガーディアンにより中止")
            return
        def _run():
            try:
                stdin, stdout, stderr = self.ssh_client.exec_command(command, timeout=self.safety_settings['timeout_seconds'])
                output = stdout.read().decode('utf-8', errors='ignore')
                error = stderr.read().decode('utf-8', errors='ignore')
                if callback:
                    self.root.after(0, callback, output, error)
            except Exception as e:
                self.log_message(f"コマンド実行エラー: {e}", "error")
                if callback:
                    self.root.after(0, callback, None, str(e))
        threading.Thread(target=_run, daemon=True).start()

    def refresh_file_list(self, path=None):
        if not self.connected or not self.sftp_client: return
        self.current_path = path if path is not None else self.current_path
        def _refresh():
            self.active_operations += 1
            self.operation_status.config(text=f"読込中: {self.current_path}")
            try:
                files = self.sftp_client.listdir_attr(self.current_path)
                files.sort(key=lambda x: (not self.is_directory(x), x.filename.lower()))
                def update_ui():
                    for item in self.file_tree.get_children(): 
                        self.file_tree.delete(item)
                    for attr in files:
                        is_dir = self.is_directory(attr)
                        icon = "📁" if is_dir else self.get_file_icon_emoji(attr.filename)
                        file_type = "ディレクトリ" if is_dir else self.get_file_type(attr.filename)
                        size = self.format_file_size(attr.st_size) if not is_dir else ""
                        modified = time.strftime("%m/%d %H:%M", time.localtime(attr.st_mtime))
                        
                        item_id = self.file_tree.insert("", tk.END, 
                                                       text=icon,
                                                       values=(attr.filename, size, file_type, modified))
                    self.path_var.set(self.current_path)
                    self.path_status.config(text=f"パス: {self.current_path}")
                self.root.after(0, update_ui)
            except Exception as e:
                self.log_message(f"ファイルリスト更新エラー: {e}", "error")
            finally:
                self.operation_status.config(text="待機中")
                self.active_operations -= 1
        threading.Thread(target=_refresh, daemon=True).start()

    def on_file_double_click(self, event=None):
        if not self.connected or not self.file_tree.selection(): 
            return
        item = self.file_tree.item(self.file_tree.selection()[0])
        filename = item['values'][0]  # 名前は最初の値
        file_type = item['values'][2]  # 種類は3番目の値
        path = os.path.join(self.current_path, filename).replace("\\", "/")
        if file_type == "ディレクトリ":
            self.refresh_file_list(path)
        else:
            self.open_file_for_editing(path, filename)

    def open_file_for_editing(self, file_path, filename):
        if not self.sftp_client: return
        def _open():
            self.active_operations += 1
            self.log_message(f"ファイルを開いています: {filename}", "info")
            try:
                attr = self.sftp_client.stat(file_path)
                if not self.guardian.check_file_read(attr.st_size): return
                with self.sftp_client.open(file_path, 'r') as rf:
                    content = rf.read().decode('utf-8', errors='ignore')
                self.root.after(0, lambda: self.create_editor_tab(filename, content, file_path))
                self.log_message(f"開きました: {file_path}", "success")
            except Exception as e:
                self.log_message(f"ファイルオープン失敗: {e}", "error")
            finally:
                self.active_operations -= 1
        threading.Thread(target=_open, daemon=True).start()

    def create_editor_tab(self, filename, content, file_path=None):
        tab_frame = ttk.Frame(self.editor_notebook)
        editor = scrolledtext.ScrolledText(tab_frame, wrap=tk.NONE, undo=True, background=self.colors['code_bg'], foreground=self.colors['code_fg'], insertbackground=self.colors['accent'])
        editor.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        editor.insert(1.0, content)
        editor.edit_modified(False)
        editor.bind('<<Modified>>', lambda e, t=tab_frame: self.on_editor_modified(t))
        self.editor_notebook.add(tab_frame, text=filename)
        self.editor_notebook.select(tab_frame)
        tab_id = self.editor_notebook.select()
        self.tabs[tab_id] = {'frame': tab_frame, 'editor': editor, 'file_path': file_path, 'filename': filename, 'modified': False}
        return self.tabs[tab_id]

    def on_editor_modified(self, tab_frame):
        tab_id = self.editor_notebook.nametowidget(self.editor_notebook.select())
        if tab_frame != tab_id: return
        meta = self.get_current_tab_meta()
        if not meta or meta['modified']: return
        if meta['editor'].edit_modified():
            meta['modified'] = True
            meta['editor'].edit_modified(False)
            self.editor_notebook.tab(self.editor_notebook.select(), text='*' + meta['filename'])

    def save_current_file(self):
        meta = self.get_current_tab_meta()
        if not meta or not self.connected or not self.sftp_client: return
        content = meta['editor'].get(1.0, tk.END)
        if content.endswith('\n'): content = content[:-1]
        path = meta.get('file_path')
        if not path:
            filename = simpledialog.askstring('リモート保存', 'ファイル名を入力:', initialvalue=meta['filename'])
            if not filename: return
            path = os.path.join(self.current_path, filename).replace('\\', '/')
            meta['file_path'] = path
            meta['filename'] = os.path.basename(filename)
        if not self.guardian.check_file_write(path): return
        def _save():
            self.active_operations += 1
            self.log_message(f"保存中: {path}", "info")
            try:
                parent_dir = os.path.dirname(path)
                if parent_dir: self.execute_ssh_command(f"mkdir -p '{parent_dir}'")
                with self.sftp_client.open(path, 'w') as wf:
                    wf.write(content.encode('utf-8'))
                meta['modified'] = False
                self.root.after(0, lambda: self.editor_notebook.tab(self.editor_notebook.select(), text=meta['filename']))
                self.log_message(f"保存しました: {path}", "success")
                self.refresh_file_list()
            except Exception as e:
                self.log_message(f"保存失敗: {e}", "error")
            finally:
                self.active_operations -= 1
        threading.Thread(target=_save, daemon=True).start()

    def execute_command(self, event=None):
        cmd = self.command_entry.get().strip()
        if not cmd or not self.connected: return
        if self.sudo_var.get() and not cmd.strip().startswith('sudo'):
            cmd = f"sudo {cmd}"
        self.terminal_output.insert(tk.END, f"$ {cmd}\n")
        if cmd not in self.command_history: self.command_history.append(cmd)
        self.history_index = len(self.command_history)
        def callback(out, err):
            if out: self.terminal_output.insert(tk.END, out)
            if err: self.terminal_output.insert(tk.END, 'エラー: ' + err, 'ERROR')
            self.terminal_output.insert(tk.END, '\n')
            self.terminal_output.see(tk.END)
            if any(cmd.strip().startswith(c) for c in ['ls', 'cd', 'mkdir', 'rm', 'mv', 'cp']):
                self.refresh_file_list()
        self.execute_ssh_command(f"cd '{self.current_path}' && {cmd}", callback)
        self.command_entry.delete(0, tk.END)

    def send_ai_quick(self):
        user_input = self.ai_quick_entry.get().strip()
        if not user_input or user_input == "AIにクイック質問...": return
        self.send_ai_text(user_input)
        self.ai_quick_entry.delete(0, tk.END)

    def send_ai_prompt(self):
        user_input = self.ai_input.get().strip()
        if not user_input: return
        if user_input.startswith('!'):
            self.handle_local_agent_command(user_input)
        else:
            self.send_ai_text(user_input)
        self.ai_input.delete(0, tk.END)

    def ai_enter_to_send(self, e): 
        self.send_ai_prompt()
        return 'break'

    def send_ai_text(self, user_input: str):
        self.append_ai_chat('user', user_input)
        threading.Thread(target=self.query_lmstudio, args=(user_input,), daemon=True).start()

    def append_ai_chat(self, role, text):
        self.ai_chat_display.config(state=tk.NORMAL)
        prefix = 'あなた: ' if role == 'user' else 'AI: '
        self.ai_chat_display.insert(tk.END, prefix, role.upper())
        parts = re.split(r"(```[\s\S]*?```)", text)
        for p in parts:
            tag = 'CODE' if p.startswith('```') else role.upper()
            clean_p = p.strip().strip('`').strip()
            if clean_p:
                self.ai_chat_display.insert(tk.END, clean_p + ('\n' if tag == 'CODE' else ''), tag)
        self.ai_chat_display.insert(tk.END, '\n\n')
        self.ai_chat_display.see(tk.END)
        self.ai_chat_display.config(state=tk.DISABLED)
        self.ai_message_history.append({'role': 'user' if role == 'user' else 'assistant', 'content': text})
        if len(self.ai_message_history) > 40: self.ai_message_history = self.ai_message_history[-40:]

    def query_lmstudio(self, user_input):
        if requests is None:
            self.root.after(0, self.append_ai_chat, 'assist', 'requestsライブラリが必要です: pip install requests')
            return
            
        content = user_input
        if self.ai_include_file_var.get():
            meta = self.get_current_tab_meta()
            if meta:
                file_text = meta['editor'].get(1.0, tk.END)
                content += f"\n\n添付ファイル ({meta['filename']}):\n```\n{file_text}\n```"
            else:
                self.root.after(0, self.log_message, "AI: ファイル添付がONですが、アクティブなエディタタブが見つかりません。", "warning")

        messages = [{'role': 'system', 'content': self.ai_settings['system_prompt']}]
        messages.extend(self.ai_message_history)
        messages.append({'role': 'user', 'content': content})
        
        payload = { 'model': 'local-model', 'messages': messages, 'temperature': 0.2 }
        if self.ai_structured_var.get():
            payload['response_format'] = {
                "type": "json_schema", "json_schema": {
                    "name": "ssh_gui_actions", "strict": True, "schema": {
                        "type": "object", "properties": { "actions": { "type": "array", "items": {"type": "object"} } }, "required": ["actions"]
                    }
                }
            }
        
        def _process_response(data):
            try:
                reply_content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                parsed = None
                if self.ai_structured_var.get():
                    try: parsed = json.loads(reply_content)
                    except json.JSONDecodeError: parsed = None
                
                if parsed and 'actions' in parsed and isinstance(parsed['actions'], list):
                    self.handle_structured_ai_result(parsed)
                else:
                    self.append_ai_chat('assist', reply_content)
                    if cmd := self.extract_command_from_text(reply_content):
                        self.ai_staged_actions = [{'type': 'command', 'command': cmd}]
                        self.update_ai_action_tree()
                    else:
                        self.ai_staged_actions = []
                        self.update_ai_action_tree()
            except Exception as e:
                self.append_ai_chat('assist', f'応答処理エラー: {e}')
            finally:
                self.log_message("待機中", "info")

        try:
            self.log_message("AI応答待機中...", "info")
            resp = requests.post(self.ai_settings['endpoint'], json=payload, timeout=60)
            if resp.status_code != 200:
                self.root.after(0, self.append_ai_chat, 'assist', f'AI呼び出し失敗: HTTP {resp.status_code} {resp.text[:200]}')
                return
            self.root.after(0, _process_response, resp.json())
        except Exception as e:
            self.root.after(0, self.append_ai_chat, 'assist', f'AI呼び出しエラー: {e}')
            self.root.after(0, self.log_message, "待機中", "info")

    def handle_structured_ai_result(self, obj):
        raw_actions = obj.get('actions', [])
        normalized_actions = []
        for action in raw_actions:
            if 'name' in action and 'arguments' in action and isinstance(action['arguments'], dict):
                normalized_action = {'type': action['name']}
                normalized_action.update(action['arguments'])
                normalized_actions.append(normalized_action)
            elif 'type' in action:
                normalized_actions.append(action)
        
        # 保存してツリーを更新
        self.ai_staged_actions = normalized_actions
        # 初期はすべて pending
        self.ai_action_status = {i: 'pending' for i in range(len(self.ai_staged_actions))}
        self.update_ai_action_tree()

        # ユーザに見えるように要約テキストをチャットに追加
        try:
            if normalized_actions:
                summary_lines = ["AI が提案したアクション:"]
                for a in normalized_actions:
                    atype = a.get('type', '<unknown>')
                    # 代表的なフィールドを人間可読にまとめる
                    details = []
                    if 'command' in a:
                        details.append(f"command={a.get('command')}")
                    if 'path' in a:
                        details.append(f"path={a.get('path')}")
                    if 'message' in a:
                        details.append(f"message={a.get('message')}")
                    if 'content' in a:
                        details.append(f"content={a.get('content')[:200]}")
                    detail_str = ", ".join(details) if details else ''
                    summary_lines.append(f"- {atype}: {detail_str}")
                summary_text = "\n".join(summary_lines)
                self.append_ai_chat('assist', summary_text)
        except Exception:
            # 要約生成は非致命的。失敗しても続行
            pass

        # 自動実行が有効なら実行
        if self.ai_auto_execute_var.get():
            self.execute_ai_staged_actions()

    def update_ai_action_tree(self):
        for item in self.ai_action_tree.get_children(): self.ai_action_tree.delete(item)
        for idx, action in enumerate(self.ai_staged_actions):
            atype = action.get('type', 'unknown')
            details = action.get('command') or action.get('path') or action.get('message') or action.get('content', '')
            status = self.ai_action_status.get(idx, 'pending')
            self.ai_action_tree.insert("", tk.END, iid=str(idx), values=(atype, details[:300], status))
        # 承認済みがある場合に実行ボタンを有効にする
        has_approved = any(s == 'approved' for s in self.ai_action_status.values())
        self.ai_exec_btn.config(state=tk.NORMAL if has_approved else tk.DISABLED)
        # 色分けを軽く追加
        try:
            self.ai_action_tree.tag_configure('approved', background='#203a20')
            self.ai_action_tree.tag_configure('rejected', background='#3a2020')
            self.ai_action_tree.tag_configure('pending', background='')
            for idx in range(len(self.ai_staged_actions)):
                st = self.ai_action_status.get(idx, 'pending')
                self.ai_action_tree.item(str(idx), tags=(st,))
        except Exception:
            pass

    def execute_ai_staged_actions(self):
        # 自動実行時は pending を自動承認
        if self.ai_auto_execute_var.get():
            for i in range(len(self.ai_staged_actions)):
                if self.ai_action_status.get(i) == 'pending':
                    self.ai_action_status[i] = 'approved'
        # 承認済みを実行
        self.execute_approved_actions()

    def approve_selected_actions(self):
        sel = self.ai_action_tree.selection()
        for iid in sel:
            try:
                idx = int(iid)
                self.ai_action_status[idx] = 'approved'
            except Exception:
                continue
        self.update_ai_action_tree()

    def reject_selected_actions(self):
        sel = self.ai_action_tree.selection()
        for iid in sel:
            try:
                idx = int(iid)
                self.ai_action_status[idx] = 'rejected'
            except Exception:
                continue
        self.update_ai_action_tree()

    def execute_approved_actions(self):
        # 承認されたアクションを順に実行する。
        approved_idxs = [i for i, s in sorted(self.ai_action_status.items()) if s == 'approved']
        if not approved_idxs:
            return
        # 実行中フラグ
        self.log_message(f"承認済みアクションを{len(approved_idxs)}件実行します", "info")
        for idx in approved_idxs:
            try:
                action = self.ai_staged_actions[idx]
                # コマンドは非同期実行してコールバックでAIに返せる
                if action.get('type') == 'command' and 'command' in action:
                    cmd = action['command']
                    def _cb(out, err, aidx=idx, ac=action, _cmd=cmd):
                        # 実行結果をログとAIへ返す（Agentモード）
                        try:
                            if out:
                                self.terminal_output.insert(tk.END, out)
                            if err:
                                self.terminal_output.insert(tk.END, f"エラー: {err}\n", 'ERROR')
                            self.terminal_output.see(tk.END)
                            if self.ai_agent_var.get():
                                summary = f"コマンド `{_cmd}` の実行結果:\n```\n{(out or '')[:2000]}\n```"
                                self.send_ai_text(summary)
                        finally:
                            # 実行済みにする
                            self.ai_action_status[aidx] = 'done'
                            self.update_ai_action_tree()
                    self.execute_ssh_command(f"cd '{self.current_path}' && {cmd}", _cb)
                else:
                    # 他のアクションは既存の実行関数を利用
                    self._execute_ai_action(action)
                    if self.ai_agent_var.get():
                        # 簡易的な実行報告を送る
                        self.send_ai_text(f"アクション `{action.get('type')}` を実行しました。")
                    self.ai_action_status[idx] = 'done'
                    self.update_ai_action_tree()
            except Exception as e:
                self.append_ai_chat('assist', f'アクション実行エラー: {type(e).__name__} - {e}')
                self.ai_action_status[idx] = 'rejected'
                self.update_ai_action_tree()
    
    def _execute_ai_action(self, action):
        action_type = action.get('type')
        if action_type == 'chat': self.append_ai_chat('assist', action.get('message', ''))
        elif action_type == 'command':
            cmd = action.get('command', '')
            if cmd:
                self.command_entry.delete(0, tk.END)
                self.command_entry.insert(0, cmd)
                self.execute_command()
        elif action_type == 'write_file':
            path = action.get('path') or action.get('file_path')
            content = action.get('content', '')
            if not path:
                self.append_ai_chat('assist', '`write_file`アクションには`path`が必要です。')
                return
            if not self.connected or not self.sftp_client:
                messagebox.showerror('エラー', 'SSHに接続していません')
                return
            if not self.guardian.check_file_write(path):
                return
            if messagebox.askyesno('AIファイル書き込み確認', f'AIがリモートファイル `{path}` を上書きします。許可しますか？'):
                # バックアップ（任意）
                try:
                    if self.safety_settings.get('backup_before_edit', False):
                        ts = datetime.now().strftime('%Y%m%d-%H%M%S')
                        bak = f"{path}.{ts}.bak"
                        try:
                            self.sftp_client.stat(path)
                            try:
                                self.sftp_client.rename(path, bak)
                                self.log_message(f"バックアップ作成: {bak}", 'info')
                            except Exception:
                                # renameできない場合はコピー
                                with self.sftp_client.open(path, 'r') as rf:
                                    data = rf.read()
                                with self.sftp_client.open(bak, 'w') as wf:
                                    wf.write(data)
                                self.log_message(f"バックアップ作成(コピー): {bak}", 'info')
                        except IOError:
                            pass
                except Exception as e:
                    self.log_message(f"バックアップ失敗: {e}", 'warning')
                # ディレクトリ作成と書き込み
                self.ensure_remote_dirs(os.path.dirname(path))
                with self.sftp_client.open(path, 'w') as f:
                    f.write(content.encode('utf-8'))
                self.log_message(f"AIによりファイル書き込み: {path}", "success")
                self.open_file_for_editing(path, os.path.basename(path))
        elif action_type == 'read_file':
            path = action.get('path')
            if not path or not self.connected: return
            with self.sftp_client.open(path, 'r') as f: content = f.read().decode('utf-8', 'ignore')
            self.send_ai_text(f"ファイル `{path}` の内容を読み込みました。これを踏まえて次のアクションを提案してください:\n```\n{content[:2000]}\n```")
        elif action_type == 'list_dir':
            path = action.get('path') or self.current_path
            items = self.sftp_client.listdir(path)
            self.send_ai_text(f"ディレクトリ `{path}` の内容は次の通りです: {', '.join(items)}. これを踏まえて次のアクションを提案してください。")
        elif action_type == 'set_cwd':
            path = action.get('path')
            if path: self.refresh_file_list(path)
        elif action_type == 'open_in_editor':
            path = action.get('path')
            if path: self.open_file_for_editing(path, os.path.basename(path))
        elif action_type == 'resubmit':
            prompt = action.get('prompt')
            if prompt: self.send_ai_text(prompt)
        else: self.append_ai_chat('assist', f'未知のアクションタイプ: {action_type}')

    def ensure_remote_dirs(self, remote_dir: Optional[str]):
        if not remote_dir:
            return
        try:
            self.execute_ssh_command(f"mkdir -p '{remote_dir}'")
        except Exception as e:
            self.log_message(f"ディレクトリ作成エラー: {e}", 'warning')

    def handle_local_agent_command(self, text: str):
        # 例: !approve all / !reject all / !run / !agent on|off
        cmd = text.strip()[1:].strip()
        if cmd == 'approve all':
            self.ai_action_status = {i: 'approved' for i in range(len(self.ai_staged_actions))}
            self.update_ai_action_tree()
            self.append_ai_chat('assist', 'すべてのアクションを承認しました。')
        elif cmd == 'reject all':
            self.ai_action_status = {i: 'rejected' for i in range(len(self.ai_staged_actions))}
            self.update_ai_action_tree()
            self.append_ai_chat('assist', 'すべてのアクションを拒否しました。')
        elif cmd == 'run':
            self.execute_approved_actions()
        elif cmd.startswith('agent '):
            on = cmd.split(' ', 1)[1].strip().lower() in ('on', 'true', '1')
            self.ai_agent_var.set(on)
            self.append_ai_chat('assist', f'Agentモード: {"ON" if on else "OFF"}')
        else:
            self.append_ai_chat('assist', f'未知のローカルコマンド: {cmd}')

    def show_ai_action_preview(self, event=None):
        sel = self.ai_action_tree.selection()
        if not sel:
            messagebox.showinfo('プレビュー', 'アクションが選択されていません')
            return
        # 先頭選択を表示
        try:
            idx = int(sel[0])
            action = self.ai_staged_actions[idx]
            win = tk.Toplevel(self.root)
            win.title(f"アクションプレビュー: {idx}")
            txt = scrolledtext.ScrolledText(win, wrap=tk.WORD, width=80, height=20)
            txt.pack(fill=tk.BOTH, expand=True)
            txt.insert(tk.END, json.dumps(action, ensure_ascii=False, indent=2))
            txt.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror('プレビューエラー', str(e))

    def execute_single_action(self):
        sel = self.ai_action_tree.selection()
        if not sel:
            messagebox.showinfo('実行', 'アクションが選択されていません')
            return
        try:
            idx = int(sel[0])
            action = self.ai_staged_actions[idx]
            # 簡易的に承認してから実行する動作
            self.ai_action_status[idx] = 'approved'
            self.update_ai_action_tree()
            # 実行は既存ロジックを流用
            if action.get('type') == 'command' and 'command' in action:
                cmd = action['command']
                def _cb(out, err, aidx=idx, _cmd=cmd):
                    if out: self.terminal_output.insert(tk.END, out)
                    if err: self.terminal_output.insert(tk.END, f"エラー: {err}\n", 'ERROR')
                    self.terminal_output.see(tk.END)
                    self.ai_action_status[aidx] = 'done'
                    self.update_ai_action_tree()
                    if self.ai_agent_var.get():
                        summary = f"コマンド `{_cmd}` の実行結果:\n```\n{(out or '')[:2000]}\n```"
                        self.send_ai_text(summary)
                self.execute_ssh_command(f"cd '{self.current_path}' && {cmd}", _cb)
            else:
                # その他は同期的に呼ぶ（安全なものに限定）
                self._execute_ai_action(action)
                self.ai_action_status[idx] = 'done'
                self.update_ai_action_tree()
        except Exception as e:
            messagebox.showerror('実行エラー', str(e))

    def extract_command_from_text(self, text: str) -> Optional[str]:
        # まずはコードブロックを探す
        m = re.search(r"```(?:bash|sh)?\n([\s\S]*?)\n```", text)
        if m:
            cand = m.group(1).strip().splitlines()[0].strip()
            return cand
        # 次にバックティック単一行
        m = re.search(r"`([^`]+)`", text)
        if m:
            return m.group(1).strip()
        # 最後に単純なコマンドらしき行を探す（ls, cat, sedなどで始まる行）
        for line in text.splitlines():
            s = line.strip()
            if not s: continue
            if re.match(r'^(ls|cat|grep|find|sed|awk|du|df|tail|head|sudo|systemctl|journalctl|cp|mv|rm|chmod|chown|docker)\b', s):
                return s
        return None

    def get_current_tab_meta(self): return self.tabs.get(self.editor_notebook.select())
    def navigate_to_path(self, event=None): self.refresh_file_list(self.path_var.get())
    def go_parent_directory(self): self.refresh_file_list(os.path.dirname(self.current_path) or '/')
    def go_home_directory(self): self.execute_ssh_command('echo $HOME', lambda out, err: self.refresh_file_list(out.strip() if out else '/'))
    def get_file_icon_emoji(self, filename):
        """ファイル種別に応じた絵文字アイコンを返す"""
        ext = os.path.splitext(filename)[1].lower()
        icon_map = {
            '.py': '🐍', '.js': '💛', '.html': '🌐', '.css': '🎨', 
            '.json': '📄', '.md': '📝', '.txt': '📄', '.sh': '⚡',
            '.zip': '🗜️', '.gz': '🗜️', '.tar': '🗜️', '.rar': '🗜️',
            '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️',
            '.pdf': '📕', '.doc': '📘', '.docx': '📘', '.xls': '📊',
            '.mp3': '🎵', '.wav': '🎵', '.mp4': '🎬', '.avi': '🎬',
            '.log': '📋', '.conf': '⚙️', '.cfg': '⚙️', '.ini': '⚙️'
        }
        return icon_map.get(ext, '📄')

    def on_file_select(self, event=None): 
        selected_items = self.file_tree.selection()
        self.selected_files = []
        for item in selected_items:
            filename = self.file_tree.item(item)['values'][0]  # 名前は最初の値
            self.selected_files.append(filename)
        self.selection_status.config(text=f"選択: {len(self.selected_files)}個")
    def clear_terminal(self): self.terminal_output.delete(1.0, tk.END)
    def command_history_up(self, e):
        if self.history_index > 0: self.history_index -= 1
        elif self.command_history: self.history_index = 0
        else: return
        self.command_entry.delete(0, tk.END); self.command_entry.insert(0, self.command_history[self.history_index])
    def command_history_down(self, e):
        if self.history_index < len(self.command_history) - 1: self.history_index += 1
        else: return
        self.command_entry.delete(0, tk.END); self.command_entry.insert(0, self.command_history[self.history_index])
    def command_history_up(self, e):
        if self.history_index > 0: 
            self.history_index -= 1
        elif self.command_history: 
            self.history_index = 0
        else: 
            return
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, self.command_history[self.history_index])
        
    def command_history_down(self, e):
        if self.history_index < len(self.command_history) - 1: 
            self.history_index += 1
        else: 
            return
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, self.command_history[self.history_index])
    def on_tab_changed(self, event=None): pass
    def clear_ai_history(self): self.ai_message_history.clear(); self.ai_chat_display.config(state=tk.NORMAL); self.ai_chat_display.delete(1.0, tk.END); self.ai_chat_display.config(state=tk.DISABLED); self.ai_staged_actions = []; self.update_ai_action_tree()

    def load_connection_history(self): self.connection_history = json.load(open(self.history_file, 'r', encoding='utf-8')) if os.path.exists(self.history_file) else []
    def save_connection_history(self): json.dump(self.connection_history[-10:], open(self.history_file, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    def add_connection_history(self, h, p, u): entry = {'host':h, 'port':p, 'username':u}; self.connection_history = [e for e in self.connection_history if e != entry]; self.connection_history.insert(0, entry); self.save_connection_history(); self.refresh_history_combo()
    def refresh_history_combo(self): self.history_combo['values'] = [f"{c['username']}@{c['host']}:{c['port']}" for c in self.connection_history]
    def on_history_selected(self, e):
        sel = self.history_combo.get()
        user_host, port = sel.rsplit(':', 1)
        user, host = user_host.split('@', 1)
        self.host_entry.delete(0,tk.END); self.host_entry.insert(0,host)
        self.port_entry.delete(0,tk.END); self.port_entry.insert(0,port)
        self.user_entry.delete(0,tk.END); self.user_entry.insert(0,user)
    def delete_selected_history(self):
        sel = self.history_combo.get()
        self.connection_history = [c for c in self.connection_history if f"{c['username']}@{c['host']}:{c['port']}" != sel]
        self.save_connection_history(); self.refresh_history_combo(); self.history_combo.set('')

    def is_directory(self, attr): return stat.S_ISDIR(attr.st_mode)
    def get_file_icon(self, filename):
        ext = os.path.splitext(filename)[1].lower()
        return {'py':'[Py]', 'js':'[JS]', 'html':'[HTML]', 'css':'[CSS]', 'json':'[JSON]', 'md':'[MD]', 'txt':'[TXT]', 'sh':'[SH]', 'zip':'[ZIP]', 'gz':'[GZ]', 'tar':'[TAR]', 'rar':'[RAR]', 'jpg':'[IMG]', 'jpeg':'[IMG]', 'png':'[IMG]', 'gif':'[IMG]', 'pdf':'[PDF]', 'doc':'[DOC]', 'docx':'[DOCX]', 'xls':'[XLS]'}.get(ext, '[File]')
    def get_file_type(self, filename): return (os.path.splitext(filename)[1][1:].upper() or "File")
    def format_file_size(self, size):
        units = ['B', 'KB', 'MB', 'GB', 'TB']
        i = 0
        size = float(size)
        while size >= 1024 and i < len(units) - 1:
            size /= 1024.0
            i += 1
        return f"{size:.1f} {units[i]}"
    def format_permissions(self, mode): return stat.filemode(mode)

    def show_context_menu(self, event):
        if not self.file_tree.identify_row(event.y): return
        self.file_tree.selection_set(self.file_tree.identify_row(event.y))
        menu = tk.Menu(self.root, tearoff=0, background=self.colors['bg_secondary'], foreground=self.colors['fg'], activebackground=self.colors['accent_dark'])
        menu.add_command(label="開く/移動", command=self.on_file_double_click)
        menu.add_command(label="ダウンロード", command=self.download_files)
        menu.add_separator(background=self.colors['bg_light'])
        menu.add_command(label="コピー", command=self.copy_files)
        menu.add_command(label="貼り付け", command=self.paste_files, state=tk.NORMAL if self.clipboard_content else tk.DISABLED)
        menu.add_separator(background=self.colors['bg_light'])
        menu.add_command(label="削除", command=self.delete_files)
        menu.tk_popup(event.x_root, event.y_root)

    def download_files(self):
        if not self.connected or not self.selected_files: return
        local_dir = filedialog.askdirectory(title="保存先を選択")
        if not local_dir: return
        for f in self.selected_files:
             threading.Thread(target=self.sftp_client.get, args=(os.path.join(self.current_path, f), os.path.join(local_dir, f))).start()
        self.log_message(f"{len(self.selected_files)}個のファイルをダウンロード開始", "success")

    def copy_files(self): self.clipboard_content = {'op': 'copy', 'src': self.current_path, 'files': self.selected_files}; self.log_message("コピーしました", "info")
    def paste_files(self):
        if not self.clipboard_content: return
        for f in self.clipboard_content['files']: self.execute_ssh_command(f"cp -r '{os.path.join(self.clipboard_content['src'], f)}' '{self.current_path}'")
        self.refresh_file_list()
    def delete_files(self):
        if not self.selected_files or not messagebox.askyesno("削除確認", f"'{', '.join(self.selected_files)}' を完全に削除しますか？"): return
        for f in self.selected_files: self.execute_ssh_command(f"rm -rf '{os.path.join(self.current_path, f)}'")
        self.refresh_file_list()

    def insert_template_command(self, command_text):
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, command_text)

    def open_command_generator(self):
        gen_win = tk.Toplevel(self.root)
        gen_win.title("コマンド生成")
        gen_win.geometry("550x400")
        gen_win.configure(bg=self.colors['bg'])
        notebook = ttk.Notebook(gen_win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.create_gen_tab(notebook, "find", [("検索パス:", ".", 40), ("ファイル名パターン:", "*", 40), ("タイプ:", "a", {"All": "a", "File": "f", "Dir": "d"})])
        self.create_gen_tab(notebook, "grep", [("検索パターン:", "", 40), ("検索パス/ファイル:", ".", 40), ("オプション:", [], {"再帰(-r)": "-r", "無視(-i)": "-i", "行番号(-n)": "-n"})])
        self.create_gen_tab(notebook, "tar", [("操作:", "c", {"作成(c)": "c", "展開(x)": "x"}), ("アーカイブ名:", "archive.tar.gz", 40), ("対象:", ".", 40), ("オプション:", ["z", "v"], {"gzip(z)": "z", "詳細(v)": "v"})])
        self.create_gen_tab(notebook, "chmod", [("対象パス:", "", 40), ("権限(数字):", "755", 10), ("再帰的(-R):", False, {})])
        def generate_command():
            tab_text = notebook.tab(notebook.select(), "text")
            widgets = notebook.nametowidget(notebook.select()).widgets
            cmd = ""
            if tab_text == "find":
                path, name, ftype = [w.get() for w in widgets.values() if isinstance(w, (ttk.Entry, tk.StringVar))]
                type_opt = {"f": "-type f", "d": "-type d"}.get(ftype, "")
                cmd = f"find {path} -name '{name}' {type_opt}".strip()
            elif tab_text == "grep":
                pattern, path = [w.get() for w in widgets.values() if isinstance(w, ttk.Entry)]
                opt_map = {"再帰(-r)": "-r", "無視(-i)": "-i", "行番号(-n)": "-n"}
                opt_str = " ".join([opt_map[key] for key, var in zip(opt_map, widgets.values()) if isinstance(var, tk.BooleanVar) and var.get()])
                cmd = f"grep {opt_str} '{pattern}' {path}".strip()
            self.insert_template_command(cmd)
            gen_win.destroy()
        ttk.Button(gen_win, text="生成して挿入", command=generate_command).pack(pady=10)

    def create_gen_tab(self, notebook, name, fields):
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=name)
        frame.widgets = {}
        for i, (label, default, options) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky=tk.W, padx=5, pady=5)
            if isinstance(options, dict):
                if isinstance(default, list):
                    for j, (text, val) in enumerate(options.items()):
                        var = tk.BooleanVar(value=(val in default))
                        ttk.Checkbutton(frame, text=text, variable=var).grid(row=i, column=j+1, sticky=tk.W)
                        frame.widgets[f"{name}_{text}"] = var
                else:
                    var = tk.StringVar(value=default)
                    for j, (text, val) in enumerate(options.items()):
                        ttk.Radiobutton(frame, text=text, variable=var, value=val).grid(row=i, column=j+1, sticky=tk.W)
                    frame.widgets[f"{name}_{label}"] = var
            else:
                entry = ttk.Entry(frame, width=options)
                entry.insert(0, default)
                entry.grid(row=i, column=1, sticky=tk.EW, padx=5, pady=5, columnspan=3)
                frame.widgets[f"{name}_{label}"] = entry

    def run_tool_command(self, cmd):
        self.insert_template_command(cmd)
        self.execute_command()
        self.bottom_notebook.select(0)

    def kill_process(self):
        pid = self.pid_entry.get().strip()
        if pid and pid.isdigit(): self.run_tool_command(f"kill -9 {pid}")
        else: messagebox.showerror("エラー", "有効なPIDを入力してください。")

    def ping_host(self):
        host = self.ping_entry.get().strip()
        if host: self.run_tool_command(f"ping -c 4 {host}")
        else: messagebox.showerror("エラー", "ホスト名またはIPアドレスを入力してください。")

    def tail_log(self):
        log_path = self.log_path_entry.get().strip()
        if log_path: self.run_tool_command(f"tail -f {log_path}")
        else: messagebox.showerror("エラー", "ログファイルのパスを入力してください。")

    def update_safety_settings(self):
        paths = [p.strip() for p in self.protected_paths_entry.get().split(',') if p.strip()]
        self.safety_settings['protected_paths'] = paths
        self.log_message("安全設定を更新しました。", "success")

def main():
    root = tk.Tk() if not USING_TTKB else ttk.Window(themename="cyborg")
    app = SSHGUIClient(root)
    def on_closing():
        if app.connected:
            app.disconnect_ssh()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', on_closing)
    app.log_message('SSH GUI Client Ultimate 起動完了', 'success')
    root.mainloop()

if __name__ == '__main__':
    main()
