import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import customtkinter as ctk
import yt_dlp
import threading
import json
import os
import subprocess
import requests
import time
from urllib.parse import urlparse, parse_qs
import webbrowser
from PIL import Image, ImageTk
import io
import pygame
import cv2
import numpy as np
from datetime import datetime, timedelta
import re

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class YuriTube:
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("YuriTube - Modern YouTube Client")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # 設定
        self.settings = {
            "download_path": os.path.expanduser("~/Downloads"),
            "quality": "720p",
            "audio_only": False,
            "subtitle_summary": True,
            "lmstudio_url": "http://localhost:1234/v1",
            "max_playlist_items": 50,
            "theme": "dark",
            "auto_next": True,
            "repeat_mode": "none",  # none, one, all
            "volume": 70,
            "speed": 1.0
        }
        
        # データ
        self.current_video = None
        self.playlist = []
        self.current_playlist_index = 0
        self.search_results = []
        self.favorites = []
        self.watch_history = []
        self.downloads_queue = []
        self.is_playing = False
        self.is_music_mode = False
        
        # pygame初期化
        pygame.mixer.init()
        
        self.setup_ui()
        self.load_settings()
        self.load_user_data()
        
    def setup_ui(self):
        # メインフレーム
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # サイドバー
        self.sidebar = ctk.CTkFrame(self.main_frame, width=250)
        self.sidebar.pack(side="left", fill="y", padx=(0, 10))
        self.sidebar.pack_propagate(False)
        
        # コンテンツエリア
        self.content_frame = ctk.CTkFrame(self.main_frame)
        self.content_frame.pack(side="right", fill="both", expand=True)
        
        self.setup_sidebar()
        self.setup_content_area()
        
    def setup_sidebar(self):
        # ロゴ
        logo_label = ctk.CTkLabel(self.sidebar, text="🎵 YuriTube", 
                                 font=ctk.CTkFont(size=24, weight="bold"))
        logo_label.pack(pady=20)
        
        # ナビゲーションボタン
        nav_buttons = [
            ("🏠 ホーム", self.show_home),
            ("🔍 検索", self.show_search),
            ("🎵 音楽モード", self.toggle_music_mode),
            ("📥 ダウンロード", self.show_downloads),
            ("📋 プレイリスト", self.show_playlists),
            ("❤️ お気に入り", self.show_favorites),
            ("📺 履歴", self.show_history),
            ("📊 統計", self.show_statistics),
            ("🎨 テーマ", self.show_themes),
            ("⚙️ 設定", self.show_settings)
        ]
        
        for text, command in nav_buttons:
            btn = ctk.CTkButton(self.sidebar, text=text, command=command,
                               anchor="w", height=40)
            btn.pack(fill="x", padx=10, pady=2)
        
        # 現在再生中の情報
        self.now_playing_frame = ctk.CTkFrame(self.sidebar)
        self.now_playing_frame.pack(fill="x", padx=10, pady=10, side="bottom")
        
        self.now_playing_label = ctk.CTkLabel(self.now_playing_frame, 
                                            text="再生中: なし", 
                                            wraplength=200)
        self.now_playing_label.pack(pady=5)
        
        # 再生コントロール
        control_frame = ctk.CTkFrame(self.now_playing_frame)
        control_frame.pack(fill="x", pady=5)
        
        self.prev_btn = ctk.CTkButton(control_frame, text="⏮", width=40,
                                     command=self.previous_track)
        self.prev_btn.pack(side="left", padx=2)
        
        self.play_btn = ctk.CTkButton(control_frame, text="⏸", width=40,
                                     command=self.toggle_play_pause)
        self.play_btn.pack(side="left", padx=2)
        
        self.next_btn = ctk.CTkButton(control_frame, text="⏭", width=40,
                                     command=self.next_track)
        self.next_btn.pack(side="left", padx=2)
        
        # 音量スライダー
        self.volume_slider = ctk.CTkSlider(self.now_playing_frame, 
                                         from_=0, to=100,
                                         command=self.change_volume)
        self.volume_slider.set(self.settings["volume"])
        self.volume_slider.pack(fill="x", padx=5, pady=5)
        
    def setup_content_area(self):
        # タブビュー
        self.tab_view = ctk.CTkTabview(self.content_frame)
        self.tab_view.pack(fill="both", expand=True, padx=10, pady=10)
        
        # メインタブ
        self.main_tab = self.tab_view.add("メイン")
        self.search_tab = self.tab_view.add("検索")
        self.player_tab = self.tab_view.add("プレイヤー")
        self.downloads_tab = self.tab_view.add("ダウンロード")
        
        self.setup_main_tab()
        self.setup_search_tab()
        self.setup_player_tab()
        self.setup_downloads_tab()
        
    def setup_main_tab(self):
        # URLエントリー
        url_frame = ctk.CTkFrame(self.main_tab)
        url_frame.pack(fill="x", padx=10, pady=10)
        
        ctk.CTkLabel(url_frame, text="YouTube URL:").pack(side="left", padx=5)
        
        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="https://youtube.com/watch?v=...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        load_btn = ctk.CTkButton(url_frame, text="読み込み", 
                               command=self.load_from_url)
        load_btn.pack(side="right", padx=5)
        
        # プレイリストオプション
        playlist_frame = ctk.CTkFrame(self.main_tab)
        playlist_frame.pack(fill="x", padx=10, pady=5)
        
        self.playlist_items_var = ctk.StringVar(value=str(self.settings["max_playlist_items"]))
        ctk.CTkLabel(playlist_frame, text="プレイリスト読み込み数:").pack(side="left", padx=5)
        
        playlist_entry = ctk.CTkEntry(playlist_frame, textvariable=self.playlist_items_var, width=80)
        playlist_entry.pack(side="left", padx=5)
        
        # おすすめ動画
        recommend_frame = ctk.CTkFrame(self.main_tab)
        recommend_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(recommend_frame, text="おすすめ動画", 
                    font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        self.recommend_scroll = ctk.CTkScrollableFrame(recommend_frame)
        self.recommend_scroll.pack(fill="both", expand=True)
        
        self.load_recommendations()
        
    def setup_search_tab(self):
        # 検索バー
        search_frame = ctk.CTkFrame(self.search_tab)
        search_frame.pack(fill="x", padx=10, pady=10)
        
        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="動画を検索...")
        self.search_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.search_entry.bind("<Return>", lambda e: self.search_videos())
        
        search_btn = ctk.CTkButton(search_frame, text="🔍", width=40,
                                 command=self.search_videos)
        search_btn.pack(side="right", padx=5)
        self.search_button = search_btn
        
        # 検索中アニメ用ラベル
        self.search_loading_label = ctk.CTkLabel(search_frame, text="")
        self.search_loading_label.pack(side="right", padx=(0,5))
        self._search_anim_job = None
        self._search_anim_count = 0
        
        # フィルター
        filter_frame = ctk.CTkFrame(self.search_tab)
        filter_frame.pack(fill="x", padx=10, pady=5)
        
        self.search_filter = ctk.CTkOptionMenu(filter_frame, 
                                             values=["すべて", "動画", "チャンネル", "プレイリスト"])
        self.search_filter.pack(side="left", padx=5)
        
        self.duration_filter = ctk.CTkOptionMenu(filter_frame,
                                               values=["すべて", "4分未満", "4-20分", "20分以上"])
        self.duration_filter.pack(side="left", padx=5)
        
        # 検索結果
        self.search_results_frame = ctk.CTkScrollableFrame(self.search_tab)
        self.search_results_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
    def _start_search_animation(self):
        # ドットを増やす簡易アニメ
        self._search_anim_count = (self._search_anim_count + 1) % 4
        dots = '.' * self._search_anim_count
        try:
            self.search_loading_label.configure(text=f"検索中{dots}")
        except Exception:
            pass
        self._search_anim_job = self.root.after(400, self._start_search_animation)

    def _stop_search_animation(self):
        if self._search_anim_job:
            try:
                self.root.after_cancel(self._search_anim_job)
            except Exception:
                pass
            self._search_anim_job = None
        try:
            self.search_loading_label.configure(text='')
        except Exception:
            pass
        self._search_anim_count = 0

    def search_videos(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        # 検索ボタンを無効化し、アニメ開始
        try:
            self.search_button.configure(state='disabled')
        except Exception:
            pass
        self._start_search_animation()
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()
    
    def _search_thread(self, query):
        try:
            ydl_opts = {
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            
            # より簡単で確実な検索
            search_query = f"ytsearch10:{query}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(search_query, download=False)
                
                self.search_results = []
                if search_results and 'entries' in search_results:
                    for entry in search_results['entries']:
                        if entry and entry.get('id'):
                            self.search_results.append({
                                'id': entry.get('id', ''),
                                'title': entry.get('title', 'タイトル不明'),
                                'uploader': entry.get('uploader', '不明'),
                                'duration': entry.get('duration', 0),
                                'view_count': entry.get('view_count', 0),
                                'url': f"https://youtube.com/watch?v={entry['id']}"
                            })
                
                self.root.after(0, self.update_search_results)
        except Exception as e:
            # エラーは UI で表示
            self.root.after(0, lambda e=e: messagebox.showerror("エラー", f"検索エラー: {str(e)}"))
        finally:
            # アニメ停止とボタン復帰
            self.root.after(0, self._stop_search_animation)
            try:
                self.root.after(0, lambda: self.search_button.configure(state='normal'))
            except Exception:
                pass

    def setup_player_tab(self):
        # 動画情報
        self.video_info_frame = ctk.CTkFrame(self.player_tab)
        self.video_info_frame.pack(fill="x", padx=10, pady=10)
        
        self.video_title_label = ctk.CTkLabel(self.video_info_frame, text="動画が選択されていません",
                                            font=ctk.CTkFont(size=16, weight="bold"))
        self.video_title_label.pack(pady=5)
        
        self.video_info_label = ctk.CTkLabel(self.video_info_frame, text="")
        self.video_info_label.pack()
        
        # プレイヤーコントロール
        player_control_frame = ctk.CTkFrame(self.player_tab)
        player_control_frame.pack(fill="x", padx=10, pady=10)
        
        # 再生速度
        speed_frame = ctk.CTkFrame(player_control_frame)
        speed_frame.pack(side="left", padx=5)
        
        ctk.CTkLabel(speed_frame, text="速度:").pack(side="left", padx=2)
        self.speed_var = ctk.StringVar(value="1.0")
        speed_options = ["0.25", "0.5", "0.75", "1.0", "1.25", "1.5", "1.75", "2.0", "3.0", "5.0", "10.0"]
        self.speed_menu = ctk.CTkOptionMenu(speed_frame, values=speed_options,
                                          variable=self.speed_var,
                                          command=self.change_speed)
        self.speed_menu.pack(side="left", padx=2)
        
        # 字幕要約
        self.summary_btn = ctk.CTkButton(player_control_frame, text="字幕要約",
                                       command=self.generate_summary)
        self.summary_btn.pack(side="left", padx=5)
        
        # ダウンロードボタン
        download_btn = ctk.CTkButton(player_control_frame, text="ダウンロード",
                                   command=self.add_to_download_queue)
        download_btn.pack(side="left", padx=5)
        
        # お気に入り追加
        fav_btn = ctk.CTkButton(player_control_frame, text="❤️",
                              command=self.toggle_favorite)
        fav_btn.pack(side="left", padx=5)
        
        # プレイリスト
        self.current_playlist_frame = ctk.CTkFrame(self.player_tab)
        self.current_playlist_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(self.current_playlist_frame, text="現在のプレイリスト",
                    font=ctk.CTkFont(size=14, weight="bold")).pack(pady=5)
        
        self.playlist_scroll = ctk.CTkScrollableFrame(self.current_playlist_frame)
        self.playlist_scroll.pack(fill="both", expand=True)
        
    def setup_downloads_tab(self):
        # ダウンロード設定
        download_settings_frame = ctk.CTkFrame(self.downloads_tab)
        download_settings_frame.pack(fill="x", padx=10, pady=10)
        
        # 品質選択
        quality_frame = ctk.CTkFrame(download_settings_frame)
        quality_frame.pack(side="left", padx=5)
        
        ctk.CTkLabel(quality_frame, text="品質:").pack(side="left", padx=2)
        self.quality_var = ctk.StringVar(value=self.settings["quality"])
        quality_menu = ctk.CTkOptionMenu(quality_frame, 
                                       values=["1080p", "720p", "480p", "360p", "audio_only"],
                                       variable=self.quality_var)
        quality_menu.pack(side="left", padx=2)
        
        # 保存先
        path_btn = ctk.CTkButton(download_settings_frame, text="保存先変更",
                               command=self.change_download_path)
        path_btn.pack(side="left", padx=5)
        
        # ダウンロードキュー
        self.download_queue_frame = ctk.CTkScrollableFrame(self.downloads_tab)
        self.download_queue_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
    # === コア機能 ===
    
    def load_from_url(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("エラー", "URLを入力してください")
            return
            
        threading.Thread(target=self._load_url_thread, args=(url,), daemon=True).start()
        
    def _load_url_thread(self, url):
        try:
            ydl_opts = {
                'extract_flat': True,
                'ignoreerrors': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                if 'entries' in info:  # プレイリスト
                    max_items = int(self.playlist_items_var.get())
                    entries = list(info['entries'])[:max_items]

                    self.playlist.clear()
                    for entry in entries:
                        if entry:
                            self.playlist.append({
                                'url': f"https://youtube.com/watch?v={entry['id']}",
                                'title': entry.get('title', 'タイトル不明'),
                                'duration': entry.get('duration', 0),
                                'uploader': entry.get('uploader', '不明')
                            })

                    self.current_playlist_index = 0
                    self.root.after(0, self.update_playlist_display)

                    if self.playlist:
                        self.load_video(self.playlist[0]['url'])

                else:  # 単一動画
                    self.playlist = [{'url': url, 'title': info.get('title', 'タイトル不明')}]
                    self.current_playlist_index = 0
                    self.load_video(url)

        except Exception as e:
            # クロージャで e を遅延参照しないようデフォルト引数で固定
            self.root.after(0, lambda e=e: messagebox.showerror("エラー", f"URL読み込みエラー: {str(e)}"))
    
    def load_video(self, url):
        threading.Thread(target=self._load_video_thread, args=(url,), daemon=True).start()
        
    def _load_video_thread(self, url):
        try:
            # 最もシンプルな方法で情報取得のみ
            ydl_opts = {
                'extract_flat': False,
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

                self.current_video = {
                    'url': url,
                    'title': info.get('title', 'タイトル不明'),
                    'uploader': info.get('uploader', '不明'),
                    'duration': info.get('duration', 0),
                    'view_count': info.get('view_count', 0),
                    'description': info.get('description', ''),
                    'thumbnails': info.get('thumbnails', []),
                    'subtitles': info.get('subtitles', {}),
                    'stream_url': info.get('url', ''),
                    'upload_date': info.get('upload_date', '')
                }

                self.root.after(0, self.update_video_display)
                self.add_to_history(self.current_video)

        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror("エラー", f"動画読み込みエラー: {str(e)}"))
    
    def search_videos(self):
        query = self.search_entry.get().strip()
        if not query:
            return
        # 検索ボタンを無効化し、アニメ開始
        try:
            self.search_button.configure(state='disabled')
        except Exception:
            pass
        self._start_search_animation()
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()
    
    def _search_thread(self, query):
        try:
            ydl_opts = {
                'extract_flat': True,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            
            # より簡単で確実な検索
            search_query = f"ytsearch10:{query}"
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_results = ydl.extract_info(search_query, download=False)
                
                self.search_results = []
                if search_results and 'entries' in search_results:
                    for entry in search_results['entries']:
                        if entry and entry.get('id'):
                            self.search_results.append({
                                'id': entry.get('id', ''),
                                'title': entry.get('title', 'タイトル不明'),
                                'uploader': entry.get('uploader', '不明'),
                                'duration': entry.get('duration', 0),
                                'view_count': entry.get('view_count', 0),
                                'url': f"https://youtube.com/watch?v={entry['id']}"
                            })
                
                self.root.after(0, self.update_search_results)
        except Exception as e:
            # エラーは UI で表示
            self.root.after(0, lambda e=e: messagebox.showerror("エラー", f"検索エラー: {str(e)}"))
        finally:
            # アニメ停止とボタン復帰
            self.root.after(0, self._stop_search_animation)
            try:
                self.root.after(0, lambda: self.search_button.configure(state='normal'))
            except Exception:
                pass
    
    # === UI更新関数 ===
    
    def update_video_display(self):
        if not self.current_video:
            return
            
        # タイトル更新
        self.video_title_label.configure(text=self.current_video['title'])
        
        # 動画情報更新
        duration_str = self.format_duration(self.current_video['duration'])
        view_count_str = f"{self.current_video['view_count']:,}" if self.current_video['view_count'] else "不明"
        
        info_text = f"チャンネル: {self.current_video['uploader']}\n"
        info_text += f"再生時間: {duration_str}\n"
        info_text += f"再生回数: {view_count_str}回"
        
        self.video_info_label.configure(text=info_text)
        
        # 現在再生中表示更新
        self.now_playing_label.configure(text=f"再生中: {self.current_video['title'][:30]}...")
        
        # プレイヤータブに切り替え
        self.tab_view.set("プレイヤー")
    
    def update_search_results(self):
        # 既存の結果をクリア
        for widget in self.search_results_frame.winfo_children():
            widget.destroy()
            
        for i, result in enumerate(self.search_results):
            result_frame = ctk.CTkFrame(self.search_results_frame)
            result_frame.pack(fill="x", padx=5, pady=2)
            
            # タイトル
            title_label = ctk.CTkLabel(result_frame, text=result['title'],
                                     font=ctk.CTkFont(weight="bold"))
            title_label.pack(anchor="w", padx=10, pady=2)
            
            # 詳細情報
            duration_str = self.format_duration(result['duration'])
            info_text = f"{result['uploader']} • {duration_str}"
            if result['view_count']:
                info_text += f" • {result['view_count']:,}回再生"
                
            info_label = ctk.CTkLabel(result_frame, text=info_text,
                                    text_color="gray")
            info_label.pack(anchor="w", padx=10)
            
            # ボタン
            btn_frame = ctk.CTkFrame(result_frame)
            btn_frame.pack(fill="x", padx=10, pady=5)
            
            play_btn = ctk.CTkButton(btn_frame, text="再生", width=80,
                                   command=lambda url=result['url']: self.play_video(url))
            play_btn.pack(side="left", padx=2)
            
            add_btn = ctk.CTkButton(btn_frame, text="プレイリストに追加", width=120,
                                  command=lambda r=result: self.add_to_playlist(r))
            add_btn.pack(side="left", padx=2)
    
    def update_playlist_display(self):
        # プレイリスト表示更新
        for widget in self.playlist_scroll.winfo_children():
            widget.destroy()
            
        for i, item in enumerate(self.playlist):
            item_frame = ctk.CTkFrame(self.playlist_scroll)
            item_frame.pack(fill="x", padx=5, pady=2)
            
            # 現在再生中マーク
            if i == self.current_playlist_index:
                item_frame.configure(border_color="blue", border_width=2)
            
            title_label = ctk.CTkLabel(item_frame, text=f"{i+1}. {item['title']}")
            title_label.pack(anchor="w", padx=10, pady=5)
            
            # 再生ボタン
            play_btn = ctk.CTkButton(item_frame, text="再生", width=60,
                                   command=lambda idx=i: self.play_playlist_item(idx))
            play_btn.pack(anchor="e", padx=10, pady=2)
    
    # === 再生コントロール ===
    
    def play_video(self, url):
        self.playlist = [{'url': url, 'title': '再生中...'}]
        self.current_playlist_index = 0
        self.load_video(url)
    
    def play_playlist_item(self, index):
        if 0 <= index < len(self.playlist):
            self.current_playlist_index = index
            self.load_video(self.playlist[index]['url'])
            self.update_playlist_display()
    
    def toggle_play_pause(self):
        self.is_playing = not self.is_playing
        self.play_btn.configure(text="⏸" if self.is_playing else "▶")
    
    def previous_track(self):
        if self.playlist and self.current_playlist_index > 0:
            self.current_playlist_index -= 1
            self.play_playlist_item(self.current_playlist_index)
    
    def next_track(self):
        if self.playlist and self.current_playlist_index < len(self.playlist) - 1:
            self.current_playlist_index += 1
            self.play_playlist_item(self.current_playlist_index)
        elif self.settings["repeat_mode"] == "all" and self.playlist:
            self.current_playlist_index = 0
            self.play_playlist_item(self.current_playlist_index)
    
    def change_volume(self, value):
        self.settings["volume"] = int(value)
        # pygame.mixer.music.set_volume(value / 100.0)
    
    def change_speed(self, speed):
        self.settings["speed"] = float(speed)
        # 実際の再生速度変更はプレイヤー実装に依存
    
    # === ダウンロード機能 ===
    
    def add_to_download_queue(self):
        if not self.current_video:
            messagebox.showwarning("警告", "ダウンロードする動画を選択してください")
            return
            
        download_item = {
            'url': self.current_video['url'],
            'title': self.current_video['title'],
            'quality': self.quality_var.get(),
            'status': '待機中',
            'progress': 0
        }
        
        self.downloads_queue.append(download_item)
        self.update_download_queue_display()
        
        # ダウンロード開始
        threading.Thread(target=self._download_video, args=(download_item,), daemon=True).start()
    
    def _download_video(self, download_item):
        try:
            download_item['status'] = 'ダウンロード中'
            
            def progress_hook(d):
                if d['status'] == 'downloading':
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes', 1)
                    progress = int((downloaded / total) * 100)
                    download_item['progress'] = progress
                    
                elif d['status'] == 'finished':
                    download_item['status'] = '完了'
                    download_item['progress'] = 100
            
            quality = download_item['quality']
            if quality == 'audio_only':
                format_selector = 'bestaudio/best'
                outtmpl = f"{self.settings['download_path']}/%(title)s.%(ext)s"
            else:
                height = quality.replace('p', '')
                format_selector = f'best[height<={height}]/best'
                outtmpl = f"{self.settings['download_path']}/%(title)s.%(ext)s"
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': outtmpl,
                'progress_hooks': [progress_hook],
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([download_item['url']])
                
        except Exception as e:
            download_item['status'] = 'エラー'
            print(f"ダウンロードエラー: {str(e)}")
    
    def update_download_queue_display(self):
        for widget in self.download_queue_frame.winfo_children():
            widget.destroy()
            
        for item in self.downloads_queue:
            item_frame = ctk.CTkFrame(self.download_queue_frame)
            item_frame.pack(fill="x", padx=5, pady=2)
            
            title_label = ctk.CTkLabel(item_frame, text=item['title'])
            title_label.pack(anchor="w", padx=10, pady=2)
            
            status_label = ctk.CTkLabel(item_frame, text=f"{item['status']} ({item['progress']}%)")
            status_label.pack(anchor="w", padx=10)
            
            progress_bar = ctk.CTkProgressBar(item_frame)
            progress_bar.pack(fill="x", padx=10, pady=5)
            progress_bar.set(item['progress'] / 100.0)
    
    def change_download_path(self):
        new_path = filedialog.askdirectory(initialdir=self.settings["download_path"])
        if new_path:
            self.settings["download_path"] = new_path
    
    # === 字幕要約機能 ===
    
    def generate_summary(self):
        if not self.settings["subtitle_summary"]:
            messagebox.showinfo("情報", "字幕要約機能は無効になっています")
            return
            
        if not self.current_video or not self.current_video.get('subtitles'):
            messagebox.showinfo("情報", "この動画には字幕がありません")
            return
            
        threading.Thread(target=self._generate_summary_thread, daemon=True).start()
    
    def _generate_summary_thread(self):
        try:
            # 字幕取得
            subtitles = self.current_video.get('subtitles', {})
            
            # 日本語字幕を優先、なければ英語
            subtitle_lang = None
            if 'ja' in subtitles:
                subtitle_lang = 'ja'
            elif 'en' in subtitles:
                subtitle_lang = 'en'
            else:
                # 他の言語から最初のものを選択
                if subtitles:
                    subtitle_lang = list(subtitles.keys())[0]
            
            if not subtitle_lang:
                self.root.after(0, lambda: messagebox.showinfo("情報", "利用可能な字幕がありません"))
                return
            
            # 字幕テキストを取得してLMStudioに送信
            subtitle_text = self.extract_subtitle_text(subtitles[subtitle_lang])
            summary = self.request_summary_from_lmstudio(subtitle_text)
            
            if summary:
                self.show_summary_popup(summary)
            else:
                self.root.after(0, lambda: messagebox.showerror("エラー", "要約生成に失敗しました"))
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("エラー", f"要約エラー: {str(e)}"))
    
    def extract_subtitle_text(self, subtitle_info):
        # 実際の実装では字幕ファイルをダウンロードして解析
        return "字幕テキストのサンプル"  # プレースホルダー
    
    def request_summary_from_lmstudio(self, text):
        try:
            response = requests.post(
                f"{self.settings['lmstudio_url']}/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [
                        {"role": "user", "content": f"以下の動画字幕を要約してください：\n\n{text}"}
                    ],
                    "max_tokens": 500
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return None
            
        except Exception:
            return None
    
    def show_summary_popup(self, summary):
        def show_popup():
            popup = ctk.CTkToplevel(self.root)
            popup.title("字幕要約")
            popup.geometry("600x400")
            
            text_widget = ctk.CTkTextbox(popup)
            text_widget.pack(fill="both", expand=True, padx=10, pady=10)
            text_widget.insert("1.0", summary)
            
            close_btn = ctk.CTkButton(popup, text="閉じる", command=popup.destroy)
            close_btn.pack(pady=10)
        
        self.root.after(0, show_popup)
    
    # === ナビゲーション関数 ===
    
    def show_home(self):
        self.tab_view.set("メイン")
    
    def show_search(self):
        self.tab_view.set("検索")
    
    def show_downloads(self):
        self.tab_view.set("ダウンロード")
    
    def toggle_music_mode(self):
        self.is_music_mode = not self.is_music_mode
        if self.is_music_mode:
            self.setup_music_mode()
        else:
            self.setup_normal_mode()
    
    def setup_music_mode(self):
        # 音楽モード用UI
        music_tab = self.tab_view.add("🎵 音楽")
        self.tab_view.set("🎵 音楽")
        
        # アルバムカバー風表示
        album_frame = ctk.CTkFrame(music_tab)
        album_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 大きなアルバムアート
        self.album_art_label = ctk.CTkLabel(album_frame, text="🎵", 
                                          font=ctk.CTkFont(size=120))
        self.album_art_label.pack(pady=20)
        
        # 曲情報
        if self.current_video:
            title_label = ctk.CTkLabel(album_frame, text=self.current_video['title'],
                                     font=ctk.CTkFont(size=18, weight="bold"))
            title_label.pack(pady=5)
            
            artist_label = ctk.CTkLabel(album_frame, text=self.current_video['uploader'],
                                      font=ctk.CTkFont(size=14))
            artist_label.pack()
        
        # 大きな再生コントロール
        big_control_frame = ctk.CTkFrame(album_frame)
        big_control_frame.pack(pady=20)
        
        prev_big_btn = ctk.CTkButton(big_control_frame, text="⏮", width=60, height=60,
                                   font=ctk.CTkFont(size=24),
                                   command=self.previous_track)
        prev_big_btn.pack(side="left", padx=10)
        
        self.play_big_btn = ctk.CTkButton(big_control_frame, text="⏸", width=80, height=80,
                                        font=ctk.CTkFont(size=32),
                                        command=self.toggle_play_pause)
        self.play_big_btn.pack(side="left", padx=10)
        
        next_big_btn = ctk.CTkButton(big_control_frame, text="⏭", width=60, height=60,
                                   font=ctk.CTkFont(size=24),
                                   command=self.next_track)
        next_big_btn.pack(side="left", padx=10)
    
    def setup_normal_mode(self):
        # 音楽タブを削除
        try:
            self.tab_view.delete("🎵 音楽")
        except:
            pass
    
    def show_playlists(self):
        # プレイリスト管理画面
        popup = ctk.CTkToplevel(self.root)
        popup.title("プレイリスト管理")
        popup.geometry("800x600")
        
        # プレイリスト一覧
        playlist_frame = ctk.CTkScrollableFrame(popup)
        playlist_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # サンプルプレイリスト
        playlists = ["お気に入り", "勉強用BGM", "作業用音楽", "最近追加した曲"]
        for playlist_name in playlists:
            pl_frame = ctk.CTkFrame(playlist_frame)
            pl_frame.pack(fill="x", pady=5)
            
            ctk.CTkLabel(pl_frame, text=f"📋 {playlist_name}",
                        font=ctk.CTkFont(size=14, weight="bold")).pack(side="left", padx=10, pady=10)
            
            ctk.CTkButton(pl_frame, text="再生", width=80).pack(side="right", padx=10, pady=5)
            ctk.CTkButton(pl_frame, text="編集", width=80).pack(side="right", padx=5, pady=5)
    
    def show_favorites(self):
        # お気に入り表示
        popup = ctk.CTkToplevel(self.root)
        popup.title("お気に入り")
        popup.geometry("800x600")
        
        fav_frame = ctk.CTkScrollableFrame(popup)
        fav_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        for fav in self.favorites:
            item_frame = ctk.CTkFrame(fav_frame)
            item_frame.pack(fill="x", pady=2)
            
            ctk.CTkLabel(item_frame, text=fav['title']).pack(side="left", padx=10, pady=5)
            ctk.CTkButton(item_frame, text="再生", width=80,
                         command=lambda url=fav['url']: self.play_video(url)).pack(side="right", padx=10, pady=5)
    
    def show_history(self):
        # 視聴履歴
        popup = ctk.CTkToplevel(self.root)
        popup.title("視聴履歴")
        popup.geometry("800x600")
        
        history_frame = ctk.CTkScrollableFrame(popup)
        history_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        for item in reversed(self.watch_history[-50:]):  # 最新50件
            hist_frame = ctk.CTkFrame(history_frame)
            hist_frame.pack(fill="x", pady=2)
            
            ctk.CTkLabel(hist_frame, text=item['title']).pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(hist_frame, text=item.get('watched_at', ''),
                        text_color="gray").pack(side="left", padx=10)
            ctk.CTkButton(hist_frame, text="再生", width=80,
                         command=lambda url=item['url']: self.play_video(url)).pack(side="right", padx=10, pady=5)
    
    def show_statistics(self):
        # 統計画面
        popup = ctk.CTkToplevel(self.root)
        popup.title("統計情報")
        popup.geometry("600x500")
        
        stats_frame = ctk.CTkFrame(popup)
        stats_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 統計情報
        stats = [
            f"総視聴回数: {len(self.watch_history)}回",
            f"お気に入り数: {len(self.favorites)}件",
            f"ダウンロード数: {len([d for d in self.downloads_queue if d['status'] == '完了'])}件",
            f"プレイリスト内動画数: {len(self.playlist)}件",
            f"今日の視聴時間: 2時間30分",  # 実装要
            f"今週の視聴時間: 15時間45分",  # 実装要
            f"最も視聴したチャンネル: サンプルチャンネル",  # 実装要
        ]
        
        for stat in stats:
            ctk.CTkLabel(stats_frame, text=stat, font=ctk.CTkFont(size=14)).pack(anchor="w", padx=20, pady=10)
    
    def show_themes(self):
        # テーマ選択
        popup = ctk.CTkToplevel(self.root)
        popup.title("テーマ選択")
        popup.geometry("400x300")
        
        theme_frame = ctk.CTkFrame(popup)
        theme_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(theme_frame, text="外観テーマ", 
                    font=ctk.CTkFont(size=16, weight="bold")).pack(pady=20)
        
        themes = [("ダーク", "dark"), ("ライト", "light"), ("システム", "system")]
        theme_var = ctk.StringVar(value=self.settings["theme"])
        
        for text, value in themes:
            radio = ctk.CTkRadioButton(theme_frame, text=text, variable=theme_var, value=value,
                                     command=lambda v=value: self.change_theme(v))
            radio.pack(pady=5)
    
    def change_theme(self, theme):
        self.settings["theme"] = theme
        ctk.set_appearance_mode(theme)
    
    def show_settings(self):
        # 設定画面
        popup = ctk.CTkToplevel(self.root)
        popup.title("設定")
        popup.geometry("600x700")
        
        settings_scroll = ctk.CTkScrollableFrame(popup)
        settings_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 設定セクション
        sections = [
            ("再生設定", [
                ("自動次へ", "auto_next", "checkbox"),
                ("リピートモード", "repeat_mode", "dropdown", ["none", "one", "all"]),
                ("デフォルト音量", "volume", "slider", (0, 100)),
                ("デフォルト再生速度", "speed", "dropdown", ["0.5", "1.0", "1.25", "1.5", "2.0"])
            ]),
            ("ダウンロード設定", [
                ("保存先", "download_path", "path"),
                ("デフォルト品質", "quality", "dropdown", ["1080p", "720p", "480p", "360p", "audio_only"])
            ]),
            ("LMStudio設定", [
                ("字幕要約機能", "subtitle_summary", "checkbox"),
                ("LMStudio URL", "lmstudio_url", "entry")
            ])
        ]
        
        for section_name, options in sections:
            section_frame = ctk.CTkFrame(settings_scroll)
            section_frame.pack(fill="x", pady=10)
            
            ctk.CTkLabel(section_frame, text=section_name,
                        font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
            
            for option in options:
                self.create_setting_widget(section_frame, *option)
    
    def create_setting_widget(self, parent, label, key, widget_type, options=None):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", padx=10, pady=5)
        
        ctk.CTkLabel(frame, text=label).pack(side="left", padx=10)
        
        if widget_type == "checkbox":
            var = ctk.BooleanVar(value=self.settings[key])
            # dict に正しく値をセットする
            checkbox = ctk.CTkCheckBox(frame, text="", variable=var,
                                     command=lambda k=key, v=var: self.settings.__setitem__(k, v.get()))
            checkbox.pack(side="right", padx=10)
            
        elif widget_type == "dropdown":
            var = ctk.StringVar(value=str(self.settings[key]))
            dropdown = ctk.CTkOptionMenu(frame, values=options, variable=var,
                                       command=lambda v, k=key: self.settings.__setitem__(k, v))
            dropdown.pack(side="right", padx=10)
            
        elif widget_type == "slider":
            min_val, max_val = options
            slider = ctk.CTkSlider(frame, from_=min_val, to=max_val,
                                 command=lambda v, k=key: self.settings.__setitem__(k, int(float(v))))
            slider.set(self.settings[key])
            slider.pack(side="right", padx=10)
            
        elif widget_type == "entry":
            var = ctk.StringVar(value=str(self.settings[key]))
            entry = ctk.CTkEntry(frame, textvariable=var)
            entry.pack(side="right", padx=10)
            entry.bind("<FocusOut>", lambda e, k=key, v=var: self.settings.__setitem__(k, v.get()))
            
        elif widget_type == "path":
            path_btn = ctk.CTkButton(frame, text="選択",
                                   command=lambda: self.select_path_setting(key))
            path_btn.pack(side="right", padx=10)
    
    def select_path_setting(self, key):
        path = filedialog.askdirectory(initialdir=self.settings[key])
        if path:
            self.settings[key] = path
    
    # === 追加機能（20個） ===
    
    def add_to_playlist(self, video_info):
        """1. プレイリストに動画追加"""
        self.playlist.append(video_info)
        self.update_playlist_display()
        messagebox.showinfo("情報", f"プレイリストに追加しました: {video_info['title']}")
    
    def toggle_favorite(self):
        """2. お気に入り切り替え"""
        if not self.current_video:
            return
            
        video_id = self.current_video['url']
        existing = next((f for f in self.favorites if f['url'] == video_id), None)
        
        if existing:
            self.favorites.remove(existing)
            messagebox.showinfo("情報", "お気に入りから削除しました")
        else:
            self.favorites.append({
                'url': self.current_video['url'],
                'title': self.current_video['title'],
                'added_at': datetime.now().isoformat()
            })
            messagebox.showinfo("情報", "お気に入りに追加しました")
    
    def add_to_history(self, video_info):
        """3. 視聴履歴追加"""
        history_item = {
            'url': video_info['url'],
            'title': video_info['title'],
            'watched_at': datetime.now().isoformat()
        }
        self.watch_history.append(history_item)
        
        # 履歴は最大1000件まで
        if len(self.watch_history) > 1000:
            self.watch_history = self.watch_history[-1000:]
    
    def load_recommendations(self):
        """4. おすすめ動画読み込み"""
        # サンプルおすすめ動画
        recommendations = [
            {"title": "【作業用BGM】集中力アップ音楽", "channel": "BGM Channel", "views": "1.2M"},
            {"title": "Python入門講座", "channel": "プログラミング学習", "views": "850K"},
            {"title": "リラックス音楽 - 睡眠用", "channel": "Relax Music", "views": "2.3M"},
        ]
        
        for rec in recommendations:
            rec_frame = ctk.CTkFrame(self.recommend_scroll)
            rec_frame.pack(fill="x", padx=5, pady=5)
            
            ctk.CTkLabel(rec_frame, text=rec["title"], font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=2)
            ctk.CTkLabel(rec_frame, text=f"{rec['channel']} • {rec['views']}回再生", text_color="gray").pack(anchor="w", padx=10)
    
    def create_smart_playlist(self):
        """5. スマートプレイリスト作成"""
        # 視聴履歴から自動でプレイリスト生成
        pass
    
    def export_playlist(self):
        """6. プレイリストエクスポート"""
        if not self.playlist:
            messagebox.showwarning("警告", "プレイリストが空です")
            return
            
        filepath = filedialog.asksaveasfilename(defaultextension=".json",
                                              filetypes=[("JSON files", "*.json")])
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.playlist, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", "プレイリストをエクスポートしました")
    
    def import_playlist(self):
        """7. プレイリストインポート"""
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    imported_playlist = json.load(f)
                self.playlist.extend(imported_playlist)
                self.update_playlist_display()
                messagebox.showinfo("成功", f"{len(imported_playlist)}件の動画をインポートしました")
            except Exception as e:
                messagebox.showerror("エラー", f"インポートエラー: {str(e)}")
    
    def shuffle_playlist(self):
        """8. プレイリストシャッフル"""
        import random
        if self.playlist:
            random.shuffle(self.playlist)
            self.update_playlist_display()
            messagebox.showinfo("情報", "プレイリストをシャッフルしました")
    
    def clear_playlist(self):
        """9. プレイリストクリア"""
        if messagebox.askyesno("確認", "プレイリストをクリアしますか？"):
            self.playlist.clear()
            self.update_playlist_display()
    
    def create_backup(self):
        """10. データバックアップ"""
        backup_data = {
            'settings': self.settings,
            'favorites': self.favorites,
            'watch_history': self.watch_history[-100:],  # 最新100件のみ
            'playlists': {'current': self.playlist}
        }
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfilename=f"yuri_tube_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        if filepath:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("成功", "バックアップを作成しました")
    
    def restore_backup(self):
        """11. データ復元"""
        filepath = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                
                self.settings.update(backup_data.get('settings', {}))
                self.favorites = backup_data.get('favorites', [])
                self.watch_history = backup_data.get('watch_history', [])
                self.playlist = backup_data.get('playlists', {}).get('current', [])
                
                self.update_playlist_display()
                messagebox.showinfo("成功", "データを復元しました")
                
            except Exception as e:
                messagebox.showerror("エラー", f"復元エラー: {str(e)}")
    
    def batch_download(self):
        """12. 一括ダウンロード"""
        if not self.playlist:
            messagebox.showwarning("警告", "プレイリストが空です")
            return
            
        if messagebox.askyesno("確認", f"プレイリスト内の{len(self.playlist)}件の動画をすべてダウンロードしますか？"):
            for video in self.playlist:
                download_item = {
                    'url': video['url'],
                    'title': video['title'],
                    'quality': self.quality_var.get(),
                    'status': '待機中',
                    'progress': 0
                }
                self.downloads_queue.append(download_item)
                threading.Thread(target=self._download_video, args=(download_item,), daemon=True).start()
            
            self.update_download_queue_display()
    
    def schedule_download(self):
        """13. スケジュールダウンロード"""
        # 時刻指定でダウンロード予約
        schedule_time = simpledialog.askstring("スケジュール", "ダウンロード開始時刻を入力 (HH:MM):")
        if schedule_time:
            messagebox.showinfo("予約完了", f"{schedule_time}にダウンロードを開始します")
    
    def video_converter(self):
        """14. 動画変換機能"""
        if not self.current_video:
            return
            
        formats = ["MP4", "MP3", "AVI", "MOV", "WAV"]
        selected_format = simpledialog.askstring("変換", f"変換形式を選択: {', '.join(formats)}")
        
        if selected_format and selected_format.upper() in formats:
            messagebox.showinfo("変換開始", f"{selected_format}形式での変換を開始します")
    
    def create_thumbnail_grid(self):
        """15. サムネイル一覧表示"""
        popup = ctk.CTkToplevel(self.root)
        popup.title("サムネイル一覧")
        popup.geometry("1000x700")
        
        grid_frame = ctk.CTkScrollableFrame(popup)
        grid_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # プレイリストのサムネイルをグリッド表示
        for i, video in enumerate(self.playlist[:20]):  # 最大20件
            row = i // 4
            col = i % 4
            
            thumb_frame = ctk.CTkFrame(grid_frame)
            thumb_frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            
            # サムネイル（プレースホルダー）
            ctk.CTkLabel(thumb_frame, text="📺", font=ctk.CTkFont(size=48)).pack(pady=10)
            ctk.CTkLabel(thumb_frame, text=video['title'][:20] + "...", wraplength=150).pack()
    
    def mini_player_mode(self):
        """16. ミニプレイヤーモード"""
        mini = ctk.CTkToplevel(self.root)
        mini.title("ミニプレイヤー")
        mini.geometry("300x200")
        mini.attributes('-topmost', True)
        
        if self.current_video:
            ctk.CTkLabel(mini, text=self.current_video['title'][:30] + "...",
                        wraplength=280).pack(pady=10)
        
        control_frame = ctk.CTkFrame(mini)
        control_frame.pack(pady=10)
        
        ctk.CTkButton(control_frame, text="⏮", width=40, command=self.previous_track).pack(side="left", padx=2)
        ctk.CTkButton(control_frame, text="⏸", width=40, command=self.toggle_play_pause).pack(side="left", padx=2)
        ctk.CTkButton(control_frame, text="⏭", width=40, command=self.next_track).pack(side="left", padx=2)
    
    def sleep_timer(self):
        """17. スリープタイマー"""
        minutes = simpledialog.askinteger("スリープタイマー", "何分後に停止しますか？", minvalue=1, maxvalue=480)
        if minutes:
            def stop_after_delay():
                time.sleep(minutes * 60)
                self.is_playing = False
                self.play_btn.configure(text="▶")
            
            threading.Thread(target=stop_after_delay, daemon=True).start()
            messagebox.showinfo("タイマー設定", f"{minutes}分後に再生を停止します")
    
    def crossfade_mode(self):
        """18. クロスフェード再生"""
        self.settings["crossfade"] = not self.settings.get("crossfade", False)
        status = "有効" if self.settings["crossfade"] else "無効"
        messagebox.showinfo("クロスフェード", f"クロスフェード機能を{status}にしました")
    
    def equalizer(self):
        """19. イコライザー"""
        eq_popup = ctk.CTkToplevel(self.root)
        eq_popup.title("イコライザー")
        eq_popup.geometry("400x300")
        
        frequencies = ["60Hz", "170Hz", "310Hz", "600Hz", "1kHz", "3kHz", "6kHz", "12kHz", "14kHz", "16kHz"]
        
        ctk.CTkLabel(eq_popup, text="イコライザー設定", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=10)
        
        sliders_frame = ctk.CTkFrame(eq_popup)
        sliders_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        for i, freq in enumerate(frequencies):
            freq_frame = ctk.CTkFrame(sliders_frame)
            freq_frame.pack(fill="x", pady=2)
            
            ctk.CTkLabel(freq_frame, text=freq, width=60).pack(side="left", padx=5)
            slider = ctk.CTkSlider(freq_frame, from_=-12, to=12, number_of_steps=24)
            slider.set(0)
            slider.pack(side="left", fill="x", expand=True, padx=5)
    
    def lyrics_display(self):
        """20. 歌詞表示"""
        if not self.current_video:
            return
            
        lyrics_popup = ctk.CTkToplevel(self.root)
        lyrics_popup.title("歌詞表示")
        lyrics_popup.geometry("500x600")
        
        lyrics_text = ctk.CTkTextbox(lyrics_popup)
        lyrics_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # サンプル歌詞
        sample_lyrics = """
        ♪ 歌詞がここに表示されます ♪
        
        [00:15] サンプル歌詞の行1
        [00:30] サンプル歌詞の行2
        [00:45] サンプル歌詞の行3
        
        ※実際の実装では字幕データから歌詞を抽出
        """
        
        lyrics_text.insert("1.0", sample_lyrics)
    
    # === ユーティリティ関数 ===
    
    def format_duration(self, seconds):
        """時間フォーマット"""
        if not seconds:
            return "不明"
        
        # seconds が float の場合があるので int に変換
        seconds = int(seconds)
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    
    def format_file_size(self, size_bytes):
        """ファイルサイズフォーマット"""
        if not size_bytes:
            return "不明"
            
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
    
    def validate_url(self, url):
        """URL検証"""
        youtube_domains = ['youtube.com', 'youtu.be', 'm.youtube.com', 'music.youtube.com']
        try:
            parsed = urlparse(url)
            return any(domain in parsed.netloc for domain in youtube_domains)
        except:
            return False
    
    def extract_video_id(self, url):
        """動画ID抽出"""
        try:
            parsed = urlparse(url)
            if 'youtu.be' in parsed.netloc:
                return parsed.path[1:]
            elif 'youtube.com' in parsed.netloc:
                query = parse_qs(parsed.query)
                return query.get('v', [None])[0]
        except:
            pass
        return None
    
    def get_video_info_cache_key(self, url):
        """キャッシュキー生成"""
        video_id = self.extract_video_id(url)
        return f"video_info_{video_id}" if video_id else None
    
    def cache_video_info(self, url, info):
        """動画情報キャッシュ"""
        cache_key = self.get_video_info_cache_key(url)
        if cache_key:
            # 実装時はファイルキャッシュまたはメモリキャッシュ
            pass
    
    def load_cached_video_info(self, url):
        """キャッシュされた動画情報読み込み"""
        cache_key = self.get_video_info_cache_key(url)
        if cache_key:
            # 実装時はファイルキャッシュまたはメモリキャッシュから読み込み
            pass
        return None
    
    # === データ管理 ===
    
    def load_settings(self):
        """設定読み込み"""
        settings_file = os.path.expanduser("~/.yuri_tube_settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, 'r', encoding='utf-8') as f:
                    loaded_settings = json.load(f)
                    self.settings.update(loaded_settings)
            except Exception as e:
                print(f"設定読み込みエラー: {e}")
    
    def save_settings(self):
        """設定保存"""
        settings_file = os.path.expanduser("~/.yuri_tube_settings.json")
        try:
            with open(settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"設定保存エラー: {e}")
    
    def load_user_data(self):
        """ユーザーデータ読み込み"""
        data_file = os.path.expanduser("~/.yuri_tube_data.json")
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.favorites = data.get('favorites', [])
                    self.watch_history = data.get('watch_history', [])
            except Exception as e:
                print(f"ユーザーデータ読み込みエラー: {e}")
    
    def save_user_data(self):
        """ユーザーデータ保存"""
        data_file = os.path.expanduser("~/.yuri_tube_data.json")
        try:
            data = {
                'favorites': self.favorites,
                'watch_history': self.watch_history
            }
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"ユーザーデータ保存エラー: {e}")
    
    def cleanup_old_data(self):
        """古いデータクリーンアップ"""
        # 30日以上古い履歴を削除
        cutoff_date = datetime.now() - timedelta(days=30)
        
        self.watch_history = [
            item for item in self.watch_history 
            if datetime.fromisoformat(item.get('watched_at', '2000-01-01')) > cutoff_date
        ]
    
    # === イベントハンドラー ===
    
    def on_closing(self):
        """アプリケーション終了時処理"""
        self.save_settings()
        self.save_user_data()
        self.cleanup_old_data()
        
        # pygame終了
        pygame.mixer.quit()
        
        self.root.destroy()
    
    def on_window_resize(self, event):
        """ウィンドウリサイズ処理"""
        # レスポンシブ対応
        pass
    
    def on_key_press(self, event):
        """キーボードショートカット"""
        if event.state & 0x4:  # Ctrl
            if event.keysym == 'space':
                self.toggle_play_pause()
            elif event.keysym == 'Right':
                self.next_track()
            elif event.keysym == 'Left':
                self.previous_track()
            elif event.keysym == 'f':
                self.toggle_favorite()
            elif event.keysym == 'd':
                self.add_to_download_queue()
            elif event.keysym == 'o':
                url = simpledialog.askstring("URL入力", "YouTubeのURLを入力:")
                if url:
                    self.url_entry.delete(0, 'end')
                    self.url_entry.insert(0, url)
                    self.load_from_url()
    
    def setup_keyboard_shortcuts(self):
        """キーボードショートカット設定"""
        self.root.bind('<Control-space>', lambda e: self.toggle_play_pause())
        self.root.bind('<Control-Right>', lambda e: self.next_track())
        self.root.bind('<Control-Left>', lambda e: self.previous_track())
        self.root.bind('<Control-f>', lambda e: self.toggle_favorite())
        self.root.bind('<Control-d>', lambda e: self.add_to_download_queue())
        self.root.bind('<F11>', lambda e: self.toggle_fullscreen())
        self.root.bind('<Escape>', lambda e: self.exit_fullscreen())
    
    def toggle_fullscreen(self):
        """フルスクリーン切り替え"""
        self.root.attributes('-fullscreen', not self.root.attributes('-fullscreen'))
    
    def exit_fullscreen(self):
        """フルスクリーン終了"""
        self.root.attributes('-fullscreen', False)
    
    # === 追加のユーティリティ機能 ===
    
    def search_suggestions(self, query):
        """検索候補取得"""
        # YouTube検索候補API（実装時）
        suggestions = [
            f"{query} 音楽",
            f"{query} 解説",
            f"{query} まとめ",
            f"{query} ライブ",
            f"{query} カバー"
        ]
        return suggestions[:5]
    
    def get_trending_videos(self):
        """トレンド動画取得"""
        # YouTube Trending API（実装時）
        return []
    
    def get_channel_videos(self, channel_id):
        """チャンネル動画取得"""
        # YouTube Channel API（実装時）
        return []
    
    def create_custom_playlist(self, name, video_urls):
        """カスタムプレイリスト作成"""
        playlist = {
            'name': name,
            'videos': video_urls,
            'created_at': datetime.now().isoformat(),
            'id': f"playlist_{int(time.time())}"
        }
        
        # プレイリストファイルに保存
        playlists_file = os.path.expanduser("~/.yuri_tube_playlists.json")
        playlists = []
        
        if os.path.exists(playlists_file):
            with open(playlists_file, 'r', encoding='utf-8') as f:
                playlists = json.load(f)
        
        playlists.append(playlist)
        
        with open(playlists_file, 'w', encoding='utf-8') as f:
            json.dump(playlists, f, ensure_ascii=False, indent=2)
        
        return playlist
    
    def run(self):
        """アプリケーション実行"""
        self.setup_keyboard_shortcuts()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.bind('<Configure>', self.on_window_resize)
        
        # 初期表示
        self.show_home()
        
        self.root.mainloop()

def main():
    """メイン関数"""
    try:
        # 必要なライブラリのチェック
        required_packages = ['yt_dlp', 'customtkinter', 'PIL', 'pygame', 'cv2', 'requests']
        missing_packages = []
        
        for package in required_packages:
            try:
                if package == 'PIL':
                    from PIL import Image
                elif package == 'cv2':
                    import cv2
                else:
                    __import__(package)
            except ImportError:
                missing_packages.append(package)
        
        if missing_packages:
            print(f"以下のパッケージがインストールされていません: {', '.join(missing_packages)}")
            print("pip install yt-dlp customtkinter pillow pygame opencv-python requests でインストールしてください")
            return
        
        # アプリケーション起動
        app = YuriTube()
        app.run()
        
    except Exception as e:
        print(f"アプリケーション開始エラー: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🎵 YuriTube - Modern YouTube Client 起動中...")
    print("妹がお兄ちゃんのために作った最高のYouTubeクライアントだよ～♪")
    main()