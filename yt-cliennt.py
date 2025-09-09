#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Advanced YouTube/Video Client - フル機能動画・音楽クライアント
discord_youtube.pyを参考にした完全独立型のメディアプレイヤー

新機能15個:
1. 再生デバイス選択
2. カスタムイコライザー (10バンド)
3. 再生速度調整 (0.25x-4.0x)
4. A-Bリピート
5. 歌詞表示 (自動取得)
6. スペクトラムアナライザー
7. クロスフェード
8. 自動音量正規化
9. プレイリスト保存/読込
10. ダークモード/ライトモード切替
11. ホットキー操作
12. 睡眠タイマー
13. 再生統計
14. 音声のみモード (動画無効化)
15. 高度な検索フィルター
"""

import os
import sys
import time
import json
import uuid
import threading
import subprocess
import re
import glob
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import sqlite3
from collections import defaultdict

# --- 設定 ---
FLASK_PORT = 8050
CACHE_DIR = 'tmp/cache'
PLAYLIST_DIR = 'tmp/playlists' 
DOWNLOAD_DIR = 'tmp/downloads'
DB_FILE = 'tmp/client.db'
ALLOWED_EXTENSIONS = {'mp4', 'webm', 'mp3', 'wav', 'ogg', 'm4a'}

# --- グローバル状態管理 ---
client_state = {
    "queue": [],
    "current_index": -1,
    "now_playing": None,
    "is_playing": False,
    "is_paused": False,
    "volume": 0.8,
    "play_start_time": None,
    "paused_duration": 0.0,
    "playback_speed": 1.0,
    "crossfade_duration": 2.0,
    "auto_normalize": True,
    "audio_only_mode": False,
    "loop_mode": "none",  # none, single, all
    "shuffle": False,
    "eq_bands": [0] * 10,  # 10バンドEQ (-12dB to +12dB)
    "a_point": None,
    "b_point": None,
    "ab_repeat": False,
    "sleep_timer": None,
    "current_device": "default",
    "available_devices": [],
    "lyrics": None,
    "spectrum_data": [],
    "playback_stats": defaultdict(int),
    "search_filters": {
        "duration": "any",  # short, medium, long, any
        "upload_date": "any",  # hour, today, week, month, year, any
        "sort_by": "relevance"  # relevance, date, view_count, rating
    },
    "theme": "dark"
}

app = Flask(__name__)

# --- データベース初期化 ---
def init_database():
    """統計情報とプレイリストを保存するSQLiteDB初期化"""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS playback_stats (
            id INTEGER PRIMARY KEY,
            video_id TEXT UNIQUE,
            title TEXT,
            play_count INTEGER DEFAULT 0,
            total_duration REAL DEFAULT 0,
            last_played TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS saved_playlists (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            items TEXT,  -- JSON
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# --- ユーティリティ関数 ---
class YTDLLogger:
    def debug(self, msg): pass
    def info(self, msg): pass  
    def warning(self, msg): pass
    def error(self, msg): print(f"[yt-dlp] {msg}")

def get_audio_devices():
    """利用可能な音声デバイス一覧を取得"""
    try:
        # Windows: wmic で音声デバイス一覧取得
        if os.name == 'nt':
            result = subprocess.run(['wmic', 'sounddev', 'get', 'name'], 
                                  capture_output=True, text=True)
            devices = [line.strip() for line in result.stdout.split('\n') 
                      if line.strip() and 'Name' not in line]
            return ["default"] + devices
        else:
            # Linux/Mac: pactl やその他のコマンドで取得可能
            return ["default", "pulse", "alsa"]
    except Exception:
        return ["default"]

def get_video_info(query, use_filters=True):
    """動画情報取得 (検索フィルター適用) - フォーマット取得失敗時にフォールバックを試みる"""
    filters = client_state["search_filters"]

    base_opts = {
        'noplaylist': True,
        'quiet': True,
        'default_search': 'auto',
        'logger': YTDLLogger(),
        'no_warnings': True
    }

    # 検索フィルター適用
    if use_filters and not query.startswith('http'):
        search_query = query
        if filters["duration"] == "short":
            search_query += " duration:short"
        elif filters["duration"] == "long":
            search_query += " duration:long"
        if filters["upload_date"] != "any":
            search_query += f" uploaddate:{filters['upload_date']}"
        base_opts['default_search'] = f'ytsearch:{search_query}'

    # 試行リスト: よく使えるフォーマット指定を順に試す
    format_candidates = ['best', 'bestaudio/best', 'bestvideo+bestaudio/best']
    last_exc = None
    for fmt in format_candidates:
        opts = base_opts.copy()
        opts['format'] = fmt
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if isinstance(info, dict) and 'entries' in info:
                    info = info['entries'][0]
                return info
        except Exception as e:
            last_exc = e
            # ログに出しつつ次の候補へ
            print(f"get_video_info try fmt={fmt} failed: {e}")
            continue
    print(f"Video info error: {last_exc}")
    return None

def get_playlist_info(url, start_index=0, max_items=50):
    """プレイリスト情報取得"""
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'logger': YTDLLogger()
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                entries = info['entries'][start_index:start_index + max_items]
                return [entry for entry in entries if entry]
            return []
    except Exception as e:
        print(f"Playlist error: {e}")
        return []

def download_audio(video_info, audio_only=False):
    """音声/動画ダウンロード。outtmplは拡張子を自動決定し、ダウンロード後に実際のファイルを返す。"""
    if not video_info:
        return None

    video_id = video_info.get('id', str(uuid.uuid4()))

    os.makedirs(CACHE_DIR, exist_ok=True)
    out_template = os.path.join(CACHE_DIR, f"{video_id}.%(ext)s")

    # フォーマット選択
    if audio_only:
        format_selector = 'bestaudio/best'
        postprocessors = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
        }]
    else:
        # 優先: bestvideo+bestaudio -> best
        format_selector = 'bestvideo+bestaudio/best'
        postprocessors = None

    ydl_opts = {
        'format': format_selector,
        'outtmpl': out_template,
        'quiet': True,
        'logger': YTDLLogger(),
        'no_warnings': True,
        'noplaylist': True
    }
    if postprocessors:
        ydl_opts['postprocessors'] = postprocessors

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_info['webpage_url']])
        # ダウンロード後、実際に生成されたファイルを探す
        pattern = os.path.join(CACHE_DIR, f"{video_id}.*")
        matches = glob.glob(pattern)
        if matches:
            # 最新のファイルを返す
            matches.sort(key=os.path.getmtime, reverse=True)
            return matches[0]
        return None
    except Exception as e:
        print(f"Download error: {e}")
        return None

def get_lyrics(title, artist=""):
    """歌詞自動取得 (簡易実装)"""
    # 実際にはLyrics API (Genius, AZLyrics等) を使用
    # ここでは簡易的なプレースホルダー
    try:
        # 歌詞検索のシミュレーション
        return f"♪ {title} の歌詞\n\n[歌詞は外部APIから取得されます]\n\n♪"
    except Exception:
        return None

def update_playback_stats(video_info, duration_played):
    """再生統計更新"""
    if not video_info:
        return
        
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    video_id = video_info.get('id')
    title = video_info.get('title', 'Unknown')
    
    cursor.execute('''
        INSERT OR REPLACE INTO playback_stats 
        (video_id, title, play_count, total_duration, last_played)
        VALUES (?, ?, 
                COALESCE((SELECT play_count FROM playback_stats WHERE video_id = ?), 0) + 1,
                COALESCE((SELECT total_duration FROM playback_stats WHERE video_id = ?), 0) + ?,
                ?)
    ''', (video_id, title, video_id, video_id, duration_played, datetime.now()))
    
    conn.commit()
    conn.close()

# --- フラスクルート ---
@app.route('/')
def index():
    """メインページ"""
    return render_template('video_client.html')

@app.route('/api/status')
def get_status():
    """現在の状態を返す"""
    current_time = time.time()
    position = 0
    
    if client_state["now_playing"] and client_state["play_start_time"]:
        if client_state["is_paused"]:
            position = client_state["paused_duration"]
        else:
            position = (current_time - client_state["play_start_time"] - client_state["paused_duration"]) * client_state["playback_speed"]
    
    return jsonify({
        "queue": client_state["queue"],
        "current_index": client_state["current_index"],
        "now_playing": client_state["now_playing"],
        "is_playing": client_state["is_playing"],
        "is_paused": client_state["is_paused"],
        "position": position,
        "volume": client_state["volume"],
        "playback_speed": client_state["playback_speed"],
        "loop_mode": client_state["loop_mode"],
        "shuffle": client_state["shuffle"],
        "eq_bands": client_state["eq_bands"],
        "ab_repeat": client_state["ab_repeat"],
        "a_point": client_state["a_point"],
        "b_point": client_state["b_point"],
        "audio_only_mode": client_state["audio_only_mode"],
        "current_device": client_state["current_device"],
        "available_devices": get_audio_devices(),
        "lyrics": client_state["lyrics"],
        "search_filters": client_state["search_filters"],
        "theme": client_state["theme"],
        "crossfade_duration": client_state["crossfade_duration"],
        "auto_normalize": client_state["auto_normalize"]
    })

@app.route('/api/search', methods=['POST'])
def search_videos():
    """動画検索"""
    data = request.json or {}
    query = data.get('query', '')
    try:
        max_results = int(data.get('max_results', 20))
    except Exception:
        max_results = 20
    
    if not query:
        return jsonify({"error": "検索クエリが必要です"}), 400
    
    ydl_opts = {
        'quiet': True,
        'default_search': f'ytsearch{max_results}:{query}',
        'extract_flat': True,
        'logger': YTDLLogger()
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_results = ydl.extract_info(query, download=False)
        
        results = []
        if isinstance(search_results, dict) and 'entries' in search_results:
            for entry in search_results['entries']:
                if entry:
                    results.append({
                        'id': entry.get('id'),
                        'title': entry.get('title'),
                        'uploader': entry.get('uploader',
                        'duration': entry.get('duration'),
                        'thumbnail': entry.get('thumbnail'),
                        'webpage_url': entry.get('webpage_url')
                    })
        
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": f"検索エラー: {str(e)}"}), 500

@app.route('/api/add_to_queue', methods=['POST'])
def add_to_queue():
    """キューに追加"""
    data = request.json
    url_or_query = data.get('url', '')
    is_playlist = data.get('is_playlist', False)
    start_index = data.get('start_index', 0)
    max_items = data.get('max_items', 50)
    
    if not url_or_query:
        return jsonify({"error": "URL またはクエリが必要です"}), 400
    
    try:
        if is_playlist:
            entries = get_playlist_info(url_or_query, start_index, max_items)
            added_count = 0
            for entry in entries:
                video_info = get_video_info(entry.get('webpage_url') or entry.get('url'))
                if video_info:
                    client_state["queue"].append(video_info)
                    added_count += 1
            return jsonify({"message": f"{added_count}件をキューに追加しました"})
        else:
            video_info = get_video_info(url_or_query)
            if video_info:
                client_state["queue"].append(video_info)
                return jsonify({"message": "キューに追加しました"})
            else:
                return jsonify({"error": "動画情報を取得できませんでした"}), 400
    except Exception as e:
        return jsonify({"error": f"追加エラー: {str(e)}"}), 500

@app.route('/api/play', methods=['POST'])
def play_video():
    """再生開始"""
    data = request.json
    index = data.get('index', 0)
    
    if not client_state["queue"]:
        return jsonify({"error": "キューが空です"}), 400
        
    if index >= len(client_state["queue"]):
        return jsonify({"error": "無効なインデックスです"}), 400
    
    client_state["current_index"] = index
    client_state["now_playing"] = client_state["queue"][index]
    client_state["is_playing"] = True
    client_state["is_paused"] = False
    client_state["play_start_time"] = time.time()
    client_state["paused_duration"] = 0.0
    
    # 歌詞取得
    title = client_state["now_playing"].get('title', '')
    client_state["lyrics"] = get_lyrics(title)
    
    return jsonify({"message": "再生開始", "now_playing": client_state["now_playing"]})

@app.route('/api/control', methods=['POST'])
def control_playback():
    """再生コントロール"""
    data = request.json
    action = data.get('action')
    
    if action == 'pause':
        if client_state["is_playing"] and not client_state["is_paused"]:
            client_state["is_paused"] = True
            client_state["paused_duration"] += time.time() - client_state["play_start_time"]
            
    elif action == 'resume':
        if client_state["is_paused"]:
            client_state["is_paused"] = False
            client_state["play_start_time"] = time.time()
            
    elif action == 'stop':
        client_state["is_playing"] = False
        client_state["is_paused"] = False
        client_state["now_playing"] = None
        client_state["current_index"] = -1
        
    elif action == 'next':
        if client_state["current_index"] < len(client_state["queue"]) - 1:
            return play_video.__wrapped__(request={'json': {'index': client_state["current_index"] + 1}})
            
    elif action == 'previous':
        if client_state["current_index"] > 0:
            return play_video.__wrapped__(request={'json': {'index': client_state["current_index"] - 1}})
    
    return jsonify({"status": "ok"})

@app.route('/api/settings', methods=['POST'])
def update_settings():
    """設定更新"""
    data = request.json
    
    # 音量
    if 'volume' in data:
        volume = max(0.0, min(1.0, float(data['volume'])))
        client_state["volume"] = volume
    
    # 再生速度
    if 'playback_speed' in data:
        speed = max(0.25, min(4.0, float(data['playback_speed'])))
        client_state["playback_speed"] = speed
    
    # EQバンド
    if 'eq_bands' in data:
        eq_bands = data['eq_bands']
        if len(eq_bands) == 10:
            client_state["eq_bands"] = [max(-12, min(12, float(band))) for band in eq_bands]
    
    # ループモード
    if 'loop_mode' in data:
        if data['loop_mode'] in ['none', 'single', 'all']:
            client_state["loop_mode"] = data['loop_mode']
    
    # シャッフル
    if 'shuffle' in data:
        client_state["shuffle"] = bool(data['shuffle'])
    
    # オーディオデバイス
    if 'current_device' in data:
        client_state["current_device"] = data['current_device']
    
    # A-Bリピート
    if 'a_point' in data:
        client_state["a_point"] = float(data['a_point']) if data['a_point'] is not None else None
    if 'b_point' in data:
        client_state["b_point"] = float(data['b_point']) if data['b_point'] is not None else None
    if 'ab_repeat' in data:
        client_state["ab_repeat"] = bool(data['ab_repeat'])
    
    # その他設定
    for key in ['audio_only_mode', 'auto_normalize', 'theme', 'crossfade_duration']:
        if key in data:
            client_state[key] = data[key]
    
    # 検索フィルター
    if 'search_filters' in data:
        client_state["search_filters"].update(data['search_filters'])
    
    return jsonify({"message": "設定を更新しました"})

@app.route('/api/playlists', methods=['GET', 'POST', 'DELETE'])
def manage_playlists():
    """プレイリスト管理"""
    if request.method == 'GET':
        # プレイリスト一覧取得
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('SELECT name, created_at FROM saved_playlists ORDER BY updated_at DESC')
        playlists = [{"name": row[0], "created_at": row[1]} for row in cursor.fetchall()]
        conn.close()
        return jsonify({"playlists": playlists})
        
    elif request.method == 'POST':
        # プレイリスト保存
        data = request.json
        name = data.get('name', '')
        items = data.get('items', client_state["queue"])
        
        if not name:
            return jsonify({"error": "プレイリスト名が必要です"}), 400
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO saved_playlists (name, items, updated_at)
                VALUES (?, ?, ?)
            ''', (name, json.dumps(items), datetime.now()))
            conn.commit()
            return jsonify({"message": "プレイリストを保存しました"})
        except Exception as e:
            return jsonify({"error": f"保存エラー: {str(e)}"}), 500
        finally:
            conn.close()
            
    elif request.method == 'DELETE':
        # プレイリスト削除
        name = request.args.get('name', '')
        if not name:
            return jsonify({"error": "プレイリスト名が必要です"}), 400
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM saved_playlists WHERE name = ?', (name,))
        conn.commit()
        conn.close()
        return jsonify({"message": "プレイリストを削除しました"})

@app.route('/api/stats')
def get_stats():
    """再生統計取得"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 最も再生された動画
    cursor.execute('''
        SELECT title, play_count, total_duration 
        FROM playback_stats 
        ORDER BY play_count DESC 
        LIMIT 10
    ''')
    most_played = [{"title": row[0], "count": row[1], "duration": row[2]} for row in cursor.fetchall()]
    
    # 総再生時間
    cursor.execute('SELECT SUM(total_duration) FROM playback_stats')
    total_duration = cursor.fetchone()[0] or 0
    
    # 総再生回数
    cursor.execute('SELECT SUM(play_count) FROM playback_stats')
    total_plays = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return jsonify({
        "most_played": most_played,
        "total_duration": total_duration,
        "total_plays": total_plays,
        "queue_length": len(client_state["queue"])
    })

@app.route('/api/download', methods=['POST'])
def download_media():
    """メディアダウンロード"""
    data = request.json
    url = data.get('url', '')
    audio_only = data.get('audio_only', False)
    
    if not url:
        return jsonify({"error": "URL が必要です"}), 400
    
    try:
        video_info = get_video_info(url)
        if not video_info:
            return jsonify({"error": "動画情報を取得できませんでした"}), 400
        
        file_path = download_audio(video_info, audio_only)
        if file_path and os.path.exists(file_path):
            return jsonify({"message": "ダウンロード完了", "file_path": file_path})
        else:
            return jsonify({"error": "ダウンロードに失敗しました"}), 500
    except Exception as e:
        return jsonify({"error": f"ダウンロードエラー: {str(e)}"}), 500

# 非同期プレイリスト追加タスク管理
playlist_tasks = {}
playlist_lock = threading.Lock()

def start_playlist_task(url, start_index=0, max_items=50, auto_play=False):
    task_id = uuid.uuid4().hex
    with playlist_lock:
        playlist_tasks[task_id] = {
            "status": "queued",
            "total": 0,
            "processed": 0,
            "added": 0,
            "errors": [],
            "titles": [],
            "start_time": time.time(),
            "finished": False,
            "first_added_index": None,
            "auto_play": bool(auto_play)
        }
    thread = threading.Thread(target=process_playlist_task, args=(task_id, url, start_index, max_items), daemon=True)
    thread.start()
    return task_id


def start_playback_index(index):
    """内部で再生を開始するヘルパー（play_video の機能を直接呼ぶ）"""
    if index < 0 or index >= len(client_state["queue"]):
        return False
    client_state["current_index"] = index
    client_state["now_playing"] = client_state["queue"][index]
    client_state["is_playing"] = True
    client_state["is_paused"] = False
    client_state["play_start_time"] = time.time()
    client_state["paused_duration"] = 0.0
    # lyrics async fetch could be done later
    client_state["lyrics"] = get_lyrics(client_state["now_playing"].get('title', ''))
    return True


def process_playlist_task(task_id, url, start_index, max_items):
    try:
        playlist_tasks[task_id]["status"] = "fetching_entries"
        # get flat entries quickly
        entries = get_playlist_info(url, start_index, max_items)
        total = len(entries)
        playlist_tasks[task_id]["total"] = total
        # record current queue start index
        queue_start_index = len(client_state["queue"])
        first_added = None
        for idx, entry in enumerate(entries):
            playlist_tasks[task_id]["status"] = f"processing {idx+1}/{total}"
            try:
                # Use flat entry info to avoid heavy per-item requests
                video_url = entry.get('webpage_url') or entry.get('url') or entry.get('id')
                title = entry.get('title') or entry.get('id') or 'Unknown'
                uploader = entry.get('uploader') or ''
                vid = entry.get('id') or None
                info = {
                    'id': vid,
                    'title': title,
                    'uploader': uploader,
                    'webpage_url': video_url,
                    'duration': entry.get('duration', 0)
                }
                if first_added is None:
                    first_added = len(client_state['queue'])
                    playlist_tasks[task_id]['first_added_index'] = first_added
                client_state["queue"].append(info)
                playlist_tasks[task_id]["added"] += 1
                playlist_tasks[task_id]["titles"].append(title)
            except Exception as e:
                playlist_tasks[task_id]["errors"].append(str(e))
            playlist_tasks[task_id]["processed"] = idx + 1
            # small sleep to allow UI polling updates smoothly
            time.sleep(0.02)
        playlist_tasks[task_id]["status"] = "finished"
        # autoplay if requested
        if playlist_tasks[task_id].get('auto_play') and playlist_tasks[task_id]['first_added_index'] is not None:
            try:
                start_playback_index(playlist_tasks[task_id]['first_added_index'])
            except Exception as e:
                playlist_tasks[task_id]["errors"].append(f"autoplay failed: {e}")
    except Exception as e:
        playlist_tasks[task_id]["status"] = "error"
        playlist_tasks[task_id]["errors"].append(str(e))
    finally:
        playlist_tasks[task_id]["finished"] = True


# Flask endpoints for playlist progress
@app.route('/api/playlist_add_start', methods=['POST'])
def playlist_add_start():
    data = request.json or {}
    url = data.get('url')
    if not url:
        return jsonify({"error": "URL が必要です"}), 400
    try:
        start_index = int(data.get('start_index', 0))
    except Exception:
        start_index = 0
    try:
        max_items = int(data.get('max_items', 50))
    except Exception:
        max_items = 50
    auto_play = bool(data.get('auto_play', False))
    task_id = start_playlist_task(url, start_index, max_items, auto_play=auto_play)
    return jsonify({"task_id": task_id})

@app.route('/api/playlist_progress/<task_id>')
def playlist_progress(task_id):
    task = playlist_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)

# --- メイン実行 ---
if __name__ == '__main__':
    # 必要なディレクトリ作成
    for directory in [CACHE_DIR, PLAYLIST_DIR, DOWNLOAD_DIR, os.path.dirname(DB_FILE)]:
        os.makedirs(directory, exist_ok=True)
    
    # データベース初期化
    init_database()
    
    # 利用可能デバイス取得
    client_state["available_devices"] = get_audio_devices()
    
    print(f"🎵 Advanced Video Client starting on http://localhost:{FLASK_PORT}")
    print("Features: Device Selection, 10-Band EQ, Speed Control, A-B Repeat, Lyrics, etc.")
    
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=True)