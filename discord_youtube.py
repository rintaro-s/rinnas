import discord
from discord.ext import commands
import asyncio
import yt_dlp
import threading
from flask import Flask, render_template, request, jsonify
import os
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import time
import re
import glob
import random
import subprocess
import uuid

# --- .envファイルから環境変数を読み込む ---
load_dotenv()

# --- 設定項目 ---
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
BOT_PREFIX = "m!"
UPLOAD_FOLDER = 'sounds'
AUDIO_CACHE_DIR = 'audio_cache' # ダウンロードした曲の保存場所
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg'}
FLASK_PORT = 8001
CACHE_MAX_AGE_DAYS = 7 # キャッシュファイルの最大保存日数
# ----------------

# --- イコライザー/エフェクトプリセット ---
EQ_PRESETS = {
    "none": "エフェクトなし", "bass_boost": "バスブースト", "vocal_boost": "ボーカル強調",
    "treble_boost": "高音強調", "nightcore": "ナイトコア", "vaporwave": "ヴェイパーウェイヴ"
}
FFMPEG_EQ_FILTERS = {
    "bass_boost": "equalizer=f=60:width_type=h:width=20:g=10",
    "vocal_boost": "superequalizer=1b=10:2b=10:3b=5:4b=5:5b=5:6b=5:7b=5:8b=5:9b=5:10b=5:11b=5:12b=5:13b=5:14b=5:15b=5",
    "treble_boost": "equalizer=f=8000:width_type=h:width=2000:g=10",
    "nightcore": "atempo=1.25,asetrate=48000*1.25",
    "vaporwave": "atempo=0.8,asetrate=48000*0.8"
}

# --- Botの状態を管理するグローバル変数 ---
bot_state = {
    "song_queue": [], "now_playing": None, "current_vc": None, "volume": 0.5,
    "loop_mode": "none", "last_played_song": None, "current_eq": "none",
    "sfx_volume": 0.9, "is_playing_sfx": False,
    "play_start_time": 0.0, "paused_time": 0.0, "is_paused": False,
    "pre_downloading_ids": set() # 先行ダウンロード中のIDを管理
}

# Lock to protect bot_state mutations across threads
bot_state_lock = threading.Lock()

# Helper to schedule play_next safely on the bot event loop in a background thread
def schedule_play_next():
    try:
        # Run play_next in a background thread and schedule it from the event loop
        run_in_bot_loop(asyncio.to_thread(play_next))
    except Exception:
        try:
            # fallback: call_soon_threadsafe to create a task that runs play_next in thread
            bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(asyncio.to_thread(play_next)))
        except Exception as e:
            print(f"Failed to schedule play_next: {e}")

# Discord Botの準備
intents = discord.Intents.default(); intents.guilds = True; intents.voice_states = True; intents.message_content = True
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents)
app = Flask(__name__); app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Helper Functions ---
class YTDLLogger:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(f"[yt-dlp error] {msg}")

def run_in_bot_loop(coro): return asyncio.run_coroutine_threadsafe(coro, bot.loop)
def allowed_file(filename): return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def get_ffmpeg_options(eq_key="none", start_offset=0.0):
    before_opts = f'-ss {start_offset}' if start_offset > 0 else ''
    audio_filters = FFMPEG_EQ_FILTERS.get(eq_key, None)
    return {'before_options': before_opts, 'options': f'-vn -af "{audio_filters}"' if audio_filters else '-vn'}

def get_audio_duration(file_path):
    """ffprobeを使って音声ファイルの長さを秒で取得"""
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return float(result.stdout)
    except Exception: return 5.0 # 失敗時はデフォルト5秒

def clean_audio_cache():
    now = time.time(); max_age = CACHE_MAX_AGE_DAYS * 86400
    for f in glob.glob(os.path.join(AUDIO_CACHE_DIR, '*')):
        if os.path.isfile(f) and (now - os.path.getmtime(f) > max_age):
            try: os.remove(f); print(f"Removed old cache: {f}")
            except OSError as e: print(f"Error removing {f}: {e}")

def download_song(song_info):
    """指定された曲情報をダウンロードする"""
    video_id = song_info.get('video_id')
    if not video_id: return None
    
    cached_filepath = os.path.join(AUDIO_CACHE_DIR, f"{video_id}.opus")
    if os.path.exists(cached_filepath): return cached_filepath
    
    # 二重ダウンロード防止
    with bot_state_lock:
        if video_id in bot_state["pre_downloading_ids"]:
            return None
        bot_state["pre_downloading_ids"].add(video_id)
    
    try:
        print(f"Downloading: {song_info['title']}")
        ydl_opts = {
            'format': 'bestaudio/best', 'outtmpl': os.path.join(AUDIO_CACHE_DIR, f'{video_id}.%(ext)s'),
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'opus'}],
            'noplaylist': True, 'quiet': True, 'logger': YTDLLogger()
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([song_info['webpage_url']])
        return cached_filepath
    except Exception as e:
        print(f"Download failed for {song_info['title']}: {e}")
        return None
    finally:
        with bot_state_lock:
            bot_state["pre_downloading_ids"].discard(video_id)

def pre_download_next_song():
    """キューの次の曲を先行ダウンロードする"""
    with bot_state_lock:
        if not bot_state["song_queue"]:
            return
        next_song = bot_state["song_queue"][0]
    # run in background thread so it doesn't block
    threading.Thread(target=download_song, args=(next_song,), daemon=True).start()

# --- Player Logic ---
def play_next():
    # This function is intended to run in a background thread (use schedule_play_next to invoke)
    try:
        with bot_state_lock:
            vc = bot_state.get("current_vc")
            is_playing_sfx = bot_state.get("is_playing_sfx", False)
        if not vc or not vc.is_connected() or is_playing_sfx:
            with bot_state_lock:
                bot_state["now_playing"] = None
            return

        # choose next source_info under lock to avoid races
        with bot_state_lock:
            source_info = None
            if bot_state["loop_mode"] == "song" and bot_state.get("last_played_song"):
                source_info = bot_state["last_played_song"].copy()
            elif bot_state["song_queue"]:
                source_info = bot_state["song_queue"].pop(0)
                if bot_state["loop_mode"] == "queue" and bot_state.get("last_played_song"):
                    bot_state["song_queue"].append(bot_state["last_played_song"].copy())

            if not source_info:
                bot_state["now_playing"] = None; bot_state["last_played_song"] = None
                return
            # mark status (not holding lock during blocking ops)
            bot_state["now_playing"] = source_info
            bot_state["last_played_song"] = source_info

        # Download the file (blocking) in this background thread
        source_info['status'] = 'downloading'
        play_path = download_song(source_info)
        source_info.pop('status', None)

        if not play_path:
            # If download failed, try to schedule next
            schedule_play_next()
            return

        resume_offset = source_info.get('resume_offset', 0.0)
        ffmpeg_options = get_ffmpeg_options(bot_state.get("current_eq", "none"), start_offset=resume_offset)

        # Now schedule actual playback on the bot event loop
        async def _do_play():
            try:
                vc_local = bot_state.get("current_vc")
                if not vc_local or not vc_local.is_connected():
                    schedule_play_next(); return

                source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(play_path, **ffmpeg_options), volume=bot_state.get("volume", 0.5))

                def after_playing(error):
                    if error: print(f'Player error: {error}')
                    # schedule next in background thread
                    if not bot_state.get("stop_requested", False):
                        schedule_play_next()
                    bot_state["stop_requested"] = False

                vc_local.play(source, after=after_playing)
                with bot_state_lock:
                    bot_state["play_start_time"] = time.time() - resume_offset
                    bot_state["is_paused"] = False
                print(f"Now playing: {source_info['title']}")

                # 次の曲を先行ダウンロード
                pre_download_next_song()
            except Exception as e:
                print(f"_do_play error: {e}")
                schedule_play_next()

        # schedule the coroutine on the bot loop
        try:
            run_in_bot_loop(_do_play())
        except Exception:
            try:
                bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(_do_play()))
            except Exception as e:
                print(f"Failed to schedule _do_play: {e}")
    except Exception as e:
        print(f"play_next top-level error: {e}")
        try:
            schedule_play_next()
        except Exception:
            pass

# --- Bot Events & Commands ---
@bot.event
async def on_ready(): print(f'Logged in as {bot.user.name}')
# (join, leave コマンドは変更なし)
@bot.command()
async def join(ctx):
    if ctx.author.voice and ctx.author.voice.channel:
        channel = ctx.author.voice.channel;
        try:
            if ctx.voice_client: await ctx.voice_client.move_to(channel)
            else: bot_state["current_vc"] = await channel.connect()
            await ctx.send(f"`{channel.name}` に参加しました。")
        except Exception as e: await ctx.send(f"接続エラー: {e}")
    else: await ctx.send("ボイスチャンネルに参加してからコマンドを実行してください。")

@bot.command()
async def leave(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        bot_state.clear()
        bot_state.update({"volume": 0.5, "sfx_volume": 0.9, "song_queue": [], "pre_downloading_ids": set()})
        await ctx.send("切断しました。")

# --- Flask API Endpoints ---
@app.route('/')
def index(): return render_template('index.html')
@app.route('/api/status')
def get_status():
    vc = bot_state.get("current_vc")
    now_playing = bot_state.get("now_playing")
    is_paused = bot_state.get("is_paused", False)
    status = {
        "is_connected": vc and vc.is_connected(), "song_queue": bot_state.get("song_queue", []),
        "now_playing": now_playing, "is_paused": is_paused, "volume": bot_state.get("volume", 0.5),
        "loop_mode": bot_state.get("loop_mode", "none"), "current_eq": bot_state.get("current_eq", "none"),
        "eq_presets": EQ_PRESETS, "playback_position": 0
    }
    if now_playing:
        start_time = bot_state.get("play_start_time", 0)
        status["playback_position"] = (bot_state.get("paused_time", 0) if is_paused else time.time()) - start_time
    return jsonify(status)

# (add_song, control, queue management, etc. - ほぼ変更なし、微修正のみ)
@app.route('/api/add', methods=['POST'])
def add_song():
    # Bot が VC に入っていない場合は拒否
    if not bot_state.get("current_vc"):
        return jsonify({"error": "Bot is not in a voice channel"}), 400

    data = request.json or {}
    query = data.get('query')
    if not query:
        return jsonify({"error": "Query is missing"}), 400

    # オプション: プレイリストの自動追加を許可するか
    allow_playlist = bool(data.get('allow_playlist', False))

    # オプション: プレイリストから何件追加するか、どの位置から追加するか
    try:
        max_items = int(data.get('max_items', 10))
    except Exception:
        max_items = 10
    try:
        start_index = int(data.get('start_index', 0))
    except Exception:
        start_index = 0

    # 安全側の制限
    if max_items < 1:
        max_items = 1
    if max_items > 100:
        max_items = 100
    if start_index < 0:
        start_index = 0

    # yt-dlp オプション: プレイリスト処理は allow_playlist に依存
    ydl_opts = {
        'format': 'bestaudio/best',
        'noplaylist': not allow_playlist,
        'quiet': True,
        'default_search': 'auto',
        'logger': YTDLLogger()
    }

    added_items = []
    errors = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)

            # entries があればプレイリストまたは検索結果のリスト
            raw_entries = info.get('entries') if isinstance(info, dict) else None
            if raw_entries:
                # プレイリストが返ってきた
                if allow_playlist:
                    entries = list(raw_entries)
                else:
                    # プレイリスト自動追加がOFFの場合、最初の有効な動画のみ選ぶ
                    entries = []
                    for e in raw_entries:
                        if not e:
                            continue
                        vid = e.get('id') or e.get('url') or e.get('webpage_url')
                        if vid:
                            # 簡易的に webpage_url がなければ構築
                            if not e.get('webpage_url') and e.get('id'):
                                e['webpage_url'] = f'https://www.youtube.com/watch?v={e.get("id")}'

                            entries.append(e)
                            break
                    if not entries:
                        return jsonify({"error": "プレイリスト内に有効な動画が見つかりませんでした。プレイリスト自動追加を ON にして再試行してください。"}), 400
            else:
                # 単体情報または検索結果1件
                entries = [info] if info else []

            # スライスの開始・終了を計算
            if isinstance(entries, list):
                sliced = entries[start_index:start_index + max_items]
            else:
                sliced = [entries]

            for entry in sliced:
                if not entry:
                    continue
                # ensure we have webpage_url or construct it from id
                webpage = entry.get('webpage_url') or entry.get('url')
                if not webpage and entry.get('id'):
                    webpage = f'https://www.youtube.com/watch?v={entry.get("id")}'
                    entry['webpage_url'] = webpage

                # 可能なら video_id を抽出
                video_id_match = None
                url_field = webpage or ''
                m = re.search(r'(?:v=|\/embed\/|\/watch\?v=|youtu\.be\/)([\w-]{11})', url_field)
                if m:
                    video_id_match = m.group(1)
                elif entry.get('id') and isinstance(entry.get('id'), str) and len(entry.get('id')) == 11:
                    video_id_match = entry.get('id')

                if not video_id_match:
                    # スキップして理由を記録
                    errors.append(f"スキップ: タイトル='{entry.get('title','不明')}' の動画IDが取得できませんでした。")
                    continue

                song_info = {
                    'title': entry.get('title', '不明なタイトル'),
                    'thumbnail': entry.get('thumbnail'),
                    'webpage_url': webpage,
                    'uploader': entry.get('uploader', '不明'),
                    'duration': entry.get('duration', 0),
                    'video_id': video_id_match
                }
                bot_state["song_queue"].append(song_info)
                added_items.append(song_info)

        # 再生トリガ
        vc = bot_state.get("current_vc")
        if vc and not vc.is_playing() and not bot_state.get("is_paused", False):
            run_in_bot_loop(asyncio.to_thread(play_next))
        else:
            # 再生中でも次曲プリダウンロード
            pre_download_next_song()

        if not added_items:
            # 追加できなかった場合は詳細を返す
            detail = "; ".join(errors) if errors else "動画を追加できませんでした。"
            return jsonify({"error": "曲の追加に失敗しました。", "detail": detail}), 400

        return jsonify({"message": f"{len(added_items)} 曲を追加しました。", "added_songs": [s['title'] for s in added_items]})
    except yt_dlp.utils.DownloadError as e:
        print(f"Add song yt-dlp error: {e}")
        return jsonify({"error": "曲の追加中にyt-dlpエラーが発生しました。", "detail": str(e)}), 500
    except Exception as e:
        print(f"Add song error: {e}")
        return jsonify({"error": "曲の追加に失敗しました。", "detail": str(e)}), 500

@app.route('/api/soundboard/play', methods=['POST'])
def play_sound():
    vc = bot_state.get("current_vc"); sound_file = request.json.get('sound')
    if not vc or not sound_file: return jsonify({"error": "Invalid request"}), 400
    if bot_state["is_playing_sfx"]: return jsonify({"error": "Another SFX is already playing"}), 409

    sound_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(sound_file))
    if not os.path.exists(sound_path): return jsonify({"error": "Sound not found"}), 404

    now_playing_info = bot_state.get("now_playing")
    is_music_playing = vc.is_playing() and not bot_state["is_paused"] and now_playing_info

    # 音楽再生中でない場合は、効果音だけを再生
    if not is_music_playing:
        vc.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(sound_path), volume=bot_state.get("sfx_volume", 0.9)))
        return jsonify({"message": f"Playing {sound_file}"})

    # --- 音楽と効果音のミキシング処理 ---
    try:
        bot_state["is_playing_sfx"] = True
        
        music_path = os.path.join(AUDIO_CACHE_DIR, f"{now_playing_info['video_id']}.opus")
        if not os.path.exists(music_path): raise FileNotFoundError("Music cache not found")
        
        sfx_dur = get_audio_duration(sound_path)
        music_offset = time.time() - bot_state["play_start_time"]
        
        tmp_id = uuid.uuid4().hex
        mixed_path = os.path.join(AUDIO_CACHE_DIR, f"mix_{tmp_id}.opus")

        # --- ▼▼▼ 修正箇所 ▼▼▼ ---
        # ffmpegコマンドの -ss (シーク) オプションを、対象の入力ファイル(-i)の前に配置
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-ss', str(music_offset),  # 入力ファイルに対するオプションは、そのファイルの直前に置く
            '-i', music_path,
            '-i', sound_path,
            '-filter_complex', f"[0:a]volume=0.7[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=shortest",
            '-t', str(sfx_dur), 
            mixed_path
        ]
        # エラー内容をコンソールに出力するため、 capture_output=True に変更
        result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
        # --- ▲▲▲ 修正箇所 ▲▲▲ ---

        resumed_song = now_playing_info.copy()
        resumed_song['resume_offset'] = music_offset + sfx_dur

        bot_state["stop_requested"] = True; vc.stop()
        
        def after_sfx_mix(error):
            if error: print(f"SFX Mix playback error: {error}")
            try: os.remove(mixed_path)
            except OSError: pass
            
            bot_state["song_queue"].insert(0, resumed_song)
            bot_state["is_playing_sfx"] = False
            bot_state["stop_requested"] = False
            play_next()
        
        mixed_source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(mixed_path), volume=bot_state["volume"])
        vc.play(mixed_source, after=after_sfx_mix)

        return jsonify({"message": f"Playing {sound_file} over music"})
    except subprocess.CalledProcessError as e:
        # ffmpegがエラーを返した場合に、その内容をコンソールに出力
        print("--- FFMPEG MIXING ERROR ---")
        print(f"Stderr: {e.stderr}")
        print("---------------------------")
        bot_state["is_playing_sfx"] = False
        return jsonify({"error": "Failed to mix audio due to FFMPEG error"}), 500
    except Exception as e:
        print(f"Sound mixing error: {e}")
        bot_state["is_playing_sfx"] = False
        return jsonify({"error": "Failed to mix audio"}), 500

# (その他のエンドポイントは変更なし)
@app.route('/api/control', methods=['POST'])
def control_player():
    action = request.json['action']; vc = bot_state["current_vc"]
    if not vc: return jsonify({"error": "Not in a voice channel"}), 400
    if action == 'pause_resume':
        if bot_state["is_paused"]:
            vc.resume(); bot_state["is_paused"] = False
            bot_state["play_start_time"] += (time.time() - bot_state["paused_time"])
        elif vc.is_playing():
            vc.pause(); bot_state["is_paused"] = True; bot_state["paused_time"] = time.time()
    elif action == 'skip':
        if vc.is_playing() or vc.is_paused(): vc.stop()
    return jsonify({"status": "ok"})
@app.route('/api/queue/shuffle', methods=['POST'])
def shuffle_queue():
    if bot_state["song_queue"]: random.shuffle(bot_state["song_queue"])
    return jsonify({"message": "キューをシャッフルしました。"})
@app.route('/api/queue/clear', methods=['POST'])
def clear_queue():
    bot_state["song_queue"].clear(); return jsonify({"message": "キューをクリアしました。"})
@app.route('/api/soundboard/upload', methods=['POST'])
def upload_sound():
    if 'sound' not in request.files: return jsonify({"error": "ファイルが選択されていません。"}), 400
    file = request.files['sound']
    if file.filename == '': return jsonify({"error": "ファイル名がありません。"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({"message": f"'{filename}' をアップロードしました。"}), 201
    return jsonify({"error": "許可されていないファイル形式です。"}), 400
@app.route('/api/eq/set', methods=['POST'])
def set_eq():
    # ... (変更なし)
    eq_key = request.json.get('eq')
    if eq_key in EQ_PRESETS:
        bot_state["current_eq"] = eq_key
        # EQ変更時に再生を再開する処理
        vc = bot_state.get("current_vc"); now_playing_info = bot_state.get("now_playing")
        if vc and (vc.is_playing() or vc.is_paused()) and now_playing_info:
            elapsed = (bot_state["paused_time"] if bot_state["is_paused"] else time.time()) - bot_state["play_start_time"]
            song_to_replay = now_playing_info.copy(); song_to_replay['resume_offset'] = elapsed
            bot_state["song_queue"].insert(0, song_to_replay)
            bot_state["stop_requested"] = True; vc.stop()
            bot.loop.call_soon_threadsafe(play_next)
        return jsonify({"message": f"エフェクトを {EQ_PRESETS[eq_key]} に設定しました。"})
    return jsonify({"error": "無効なプリセットです。"}), 400
@app.route('/api/queue/remove', methods=['POST'])
def remove_from_queue():
    index = request.json['index']
    if 0 <= index < len(bot_state["song_queue"]):
        removed = bot_state["song_queue"].pop(index); return jsonify({"message": f"Removed {removed['title']}"})
    return jsonify({"error": "Invalid index"}), 400
@app.route('/api/volume', methods=['POST'])
def set_volume():
    volume = float(request.json['volume'])
    if 0.0 <= volume <= 2.0:
        bot_state["volume"] = volume
        if bot_state["current_vc"] and bot_state["current_vc"].source: bot_state["current_vc"].source.volume = volume
        return jsonify({"message": "Volume updated"})
    return jsonify({"error": "Volume must be between 0 and 2"}), 400
@app.route('/api/loop', methods=['POST'])
def toggle_loop():
    modes = ["none", "queue", "song"]; current_index = modes.index(bot_state["loop_mode"])
    bot_state["loop_mode"] = modes[(current_index + 1) % len(modes)]; return jsonify({"loop_mode": bot_state["loop_mode"]})
@app.route('/api/soundboard/list')
def list_sounds():
    try: sounds = [f for f in os.listdir(app.config['UPLOAD_FOLDER']) if allowed_file(f)]; return jsonify({"sounds": sounds})
    except FileNotFoundError: return jsonify({"sounds": []})
@app.route('/api/soundboard/volume', methods=['POST'])
def set_sfx_volume():
    volume = float(request.json.get('volume', 1.0))
    if 0.0 <= volume <= 2.0: bot_state["sfx_volume"] = volume; return jsonify({"message": f"SFX Volume set to {volume}"})
    return jsonify({"error": "Volume must be between 0.0 and 2.0"}), 400

# 設定: 自動変換を行うチャンネルID（複数可）。環境変数 ROMAJI_CHANNEL_IDS にカンマ区切りで設定するか、直接IDをここに追加。
ROMAJI_CHANNEL_IDS = [int(x) for x in os.getenv('ROMAJI_CHANNEL_IDS', '').split(',') if x.strip().isdigit()]
# 例: ROMAJI_CHANNEL_IDS = [1263086389935865857]

def is_mostly_romaji(text, threshold=0.9):
    """文字列がローマ字（ASCII英字と空白・記号）で構成されている割合を判定する簡易関数"""
    if not text: return False
    total = len(text)
    if total == 0: return False
    romaji_chars = 0
    for ch in text:
        if ch.isascii() and (ch.isalpha() or ch.isspace() or ch in "'-.,?/"):
            romaji_chars += 1
    return (romaji_chars / total) >= threshold

# とりあえず簡易マッピング: よくある固有名詞や外来語はカタカナにする
SIMPLE_NAME_MAP = {
    'doraemon': 'ドラえもん', 'pikachu': 'ピカチュウ', 'naruto': 'ナルト', 'onepiece': 'ワンピース'
}

# ローマ字をひらがなに変換する簡易ロジック
# 完全な変換は難しいため、ここでは基本的なヘボン式ローマ字→ひらがな（簡易）を実装
ROMAJI_TO_HIRA = {
    'kya':'きゃ','kyu':'きゅ','kyo':'きょ','sha':'しゃ','shu':'しゅ','sho':'しょ',
    'cha':'ちゃ','chu':'ちゅ','cho':'ちょ','nya':'にゃ','nyu':'にゅ','nyo':'にょ',
    'a':'あ','i':'い','u':'う','e':'え','o':'お',
    'ka':'か','ki':'き','ku':'く','ke':'け','ko':'こ',
    'sa':'さ','shi':'し','su':'す','se':'せ','so':'そ',
    'ta':'た','chi':'ち','tsu':'つ','te':'て','to':'と',
    'na':'な','ni':'に','nu':'ぬ','ne':'ね','no':'の',
    'ha':'は','hi':'ひ','fu':'ふ','he':'へ','ho':'ほ',
    'ma':'ま','mi':'み','mu':'む','me':'め','mo':'も',
    'ya':'や','yu':'ゆ','yo':'よ',
    'ra':'ら','ri':'り','ru':'る','re':'れ','ro':'ろ',
    'wa':'わ','wo':'を','n':'ん',
    'ga':'が','gi':'ぎ','gu':'ぐ','ge':'げ','go':'ご',
    'za':'ざ','ji':'じ','zu':'ず','ze':'ぜ','zo':'ぞ',
    'da':'だ','de':'で','do':'ど','ba':'ば','bi':'び','bu':'ぶ','be':'べ','bo':'ぼ',
    'pa':'ぱ','pi':'ぴ','pu':'ぷ','pe':'ぺ','po':'ぽ',
    'vu':'ヴ',
    # y-row combined sounds
    'kya':'きゃ','kyu':'きゅ','kyo':'きょ',
    'gya':'ぎゃ','gyu':'ぎゅ','gyo':'ぎょ',
    'sha':'しゃ','shu':'しゅ','sho':'しょ',
    'ja':'じゃ','ju':'じゅ','jo':'じょ','jya':'じゃ','jyu':'じゅ','jyo':'じょ',
    'bya':'びゃ','byu':'びゅ','byo':'びょ',
    'pya':'ぴゃ','pyu':'ぴゅ','pyo':'ぴょ',
    'mya':'みゃ','myu':'みゅ','myo':'みょ',
    'hya':'ひゃ','hyu':'ひゅ','hyo':'ひょ',
    'rya':'りゃ','ryu':'りゅ','ryo':'りょ',
    'sya':'しゃ','syu':'しゅ','syo':'しょ',
    'cha':'ちゃ','chu':'ちゅ','cho':'ちょ',
}
import re

ROMAJI_TOKEN_RE = re.compile(r"[a-zA-Z]+|[^a-zA-Z]+" )

def romaji_to_japanese(text):
    """簡易ローマ字→日本語変換: 単語単位でSIMPLE_NAME_MAPを優先し、残りをひらがなにする"""
    if not text: return ''
    tokens = ROMAJI_TOKEN_RE.findall(text)
    out_tokens = []
    for t in tokens:
        if re.fullmatch(r'[A-Za-z]+', t):
            key = t.lower()
            # 固有名詞やよくある外来語をマップ
            if key in SIMPLE_NAME_MAP:
                out_tokens.append(SIMPLE_NAME_MAP[key])
                continue
            # 単語を分割して変換（簡易）
            hira = _romaji_word_to_hiragana(key)
            out_tokens.append(hira)
        else:
            out_tokens.append(t)
    # 空白を全角スペースにして読みやすく
    return ''.join(out_tokens).replace(' ', '　')


def _romaji_word_to_hiragana(word):
    # greedy マッチングで3文字→2文字→1文字 の順で長いルールを優先
    i = 0; n = len(word); res = ''
    while i < n:
        # 促音（っ）の処理: 同音子音の連続
        if i+1 < n and word[i] == word[i+1] and word[i] not in 'aeiou':
            res += 'っ'; i += 1; continue
        # 3文字
        if i+3 <= n and word[i:i+3] in ROMAJI_TO_HIRA:
            res += ROMAJI_TO_HIRA[word[i:i+3]]; i += 3; continue
        # 2文字
        if i+2 <= n and word[i:i+2] in ROMAJI_TO_HIRA:
            res += ROMAJI_TO_HIRA[word[i:i+2]]; i += 2; continue
        # 1文字
        if word[i:i+1] in ROMAJI_TO_HIRA:
            res += ROMAJI_TO_HIRA[word[i:i+1]]; i += 1; continue
        # 数字や単語で処理できない場合はそのまま
        res += word[i]; i += 1
    return res

# 追加: メッセージ受信で自動変換を行うハンドラ
@bot.event
async def on_message(message):
    # ボットのメッセージやコマンドは無視
    if message.author == bot.user: return
    if message.content.startswith(BOT_PREFIX):
        await bot.process_commands(message)
        return

    # チャンネルチェック
    target_ids = ROMAJI_CHANNEL_IDS
    if not target_ids:
        # 環境変数未設定の場合、特定のIDをハードコード（ユーザーの要求チャンネル）
        try:
            target_ids = [1263086389935865857]
        except Exception:
            target_ids = []

    if message.channel.id not in target_ids:
        await bot.process_commands(message)
        return

    text = message.content.strip()
    if not text: return

    if is_mostly_romaji(text):
        converted = romaji_to_japanese(text)
        if converted and converted != text:
            try:
                await message.channel.send(f'{converted}')
            except Exception as e:
                print(f"Failed to send converted message: {e}")
    # process commands regardless
    await bot.process_commands(message)

# --- Application Runner ---
if __name__ == "__main__":
    for folder in [UPLOAD_FOLDER, AUDIO_CACHE_DIR]:
        if not os.path.exists(folder): os.makedirs(folder)
    clean_audio_cache()
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", FLASK_PORT))), daemon=True).start()
    if DISCORD_TOKEN: bot.run(DISCORD_TOKEN)
    else: print("エラー: DISCORD_TOKENが.envファイルに設定されていません。")