"""
Discord YouTube Bot v2 - discord_youtube.py を継承した拡張版
新機能: キャッシュDB、検索選択、プレイリストインポート、履歴API、スラッシュコマンド
"""
# discord_youtube.py からすべてをインポート
import discord_youtube
from discord_youtube import (
    bot, app, bot_state, bot_state_lock,
    AUDIO_CACHE_DIR, EQ_PRESETS, DISCORD_TOKEN, FLASK_PORT,
    run_in_bot_loop, download_song, pre_download_next_song, play_next,
    YTDLLogger
)
from discord import app_commands
import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
import json
import time
import re
import threading
from flask import request, jsonify

# === キャッシュDB設定 ===
CACHE_DB_FILE = os.path.join(AUDIO_CACHE_DIR, 'cache_db.json')


# === キャッシュDB管理 ===
class CacheDB:
    def __init__(self):
        self.data = {}
        self._load()
    
    def _load(self):
        if os.path.exists(CACHE_DB_FILE):
            try:
                with open(CACHE_DB_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
            except:
                self.data = {}
    
    def _save(self):
        with open(CACHE_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def add(self, video_id, title, uploader, duration, thumbnail, webpage_url):
        """キャッシュに追加"""
        self.data[video_id] = {
            'title': title,
            'uploader': uploader,
            'duration': duration,
            'thumbnail': thumbnail,
            'webpage_url': webpage_url,
            'cached_at': time.time(),
            'last_played': time.time(),
            'play_count': 1,
        }
        self._save()
    
    def update_played(self, video_id):
        """再生記録を更新"""
        if video_id in self.data:
            self.data[video_id]['play_count'] = self.data[video_id].get('play_count', 0) + 1
            self.data[video_id]['last_played'] = time.time()
            self._save()
    
    def get_all(self):
        return [{'video_id': k, **v} for k, v in self.data.items()]
    
    def get_recent(self, limit=10):
        items = sorted(self.data.items(), key=lambda x: x[1].get('last_played', 0), reverse=True)
        return [{'video_id': k, **v} for k, v in items[:limit]]
    
    def get_popular(self, limit=10):
        items = sorted(self.data.items(), key=lambda x: x[1].get('play_count', 0), reverse=True)
        return [{'video_id': k, **v} for k, v in items[:limit]]


cache_db = CacheDB()


# === YouTube検索機能 ===
def search_youtube(query, max_results=5):
    """YouTube検索"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'logger': YTDLLogger()
    }
    
    results = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            for entry in info.get('entries', []):
                if entry:
                    results.append({
                        'video_id': entry.get('id'),
                        'title': entry.get('title', '不明'),
                        'uploader': entry.get('uploader') or entry.get('channel', '不明'),
                        'duration': entry.get('duration', 0),
                        'thumbnail': entry.get('thumbnail'),
                        'webpage_url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                    })
    except Exception as e:
        print(f"検索エラー: {e}")
    
    return results


def fetch_playlist(url, max_items=20, start=0):
    """プレイリスト情報を取得"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'ignoreerrors': True,
        'logger': YTDLLogger()
    }
    
    result = {'title': '', 'songs': [], 'total': 0, 'errors': []}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                result['errors'].append('情報取得失敗')
                return result
            
            entries = info.get('entries')
            if entries:
                all_entries = list(entries)
                result['title'] = info.get('title', 'プレイリスト')
                result['total'] = len(all_entries)
                
                for entry in all_entries[start:start+max_items]:
                    if entry and entry.get('id'):
                        result['songs'].append({
                            'video_id': entry.get('id'),
                            'title': entry.get('title', '不明'),
                            'uploader': entry.get('uploader') or entry.get('channel', '不明'),
                            'duration': entry.get('duration', 0),
                            'thumbnail': entry.get('thumbnail'),
                            'webpage_url': f"https://www.youtube.com/watch?v={entry.get('id')}",
                        })
    except Exception as e:
        result['errors'].append(str(e))
    
    return result


# === 追加のDiscordコマンド ===

@bot.command(name='search', aliases=['sr'])
async def cmd_search(ctx, *, query: str):
    """検索して選択"""
    msg = await ctx.send(f"🔍 検索中: `{query}`")
    
    results = search_youtube(query, 5)
    
    if not results:
        await msg.edit(content="❌ 見つかりませんでした")
        return
    
    # 選択肢を表示
    embed = discord.Embed(title=f"🔍 検索結果: {query}", color=discord.Color.blue())
    
    for i, r in enumerate(results):
        dur = r.get('duration', 0) or 0
        dur_str = f"{dur//60}:{dur%60:02d}" if dur else "不明"
        embed.add_field(
            name=f"{i+1}. {r['title'][:50]}",
            value=f"👤 {r['uploader'][:30]} | ⏱ {dur_str}",
            inline=False
        )
    
    embed.set_footer(text="番号を入力して選択 (30秒以内)")
    await msg.edit(content=None, embed=embed)
    
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()
    
    try:
        reply = await bot.wait_for('message', check=check, timeout=30.0)
        idx = int(reply.content) - 1
        
        if 0 <= idx < len(results):
            selected = results[idx]
            
            # VCチェック
            vc = bot_state.get("current_vc")
            if not vc or not vc.is_connected():
                if ctx.author.voice:
                    bot_state["current_vc"] = await ctx.author.voice.channel.connect()
                else:
                    await ctx.send("❌ VCに入ってください")
                    return
            
            # キューに追加
            song_info = {
                'title': selected['title'],
                'thumbnail': selected.get('thumbnail'),
                'webpage_url': selected['webpage_url'],
                'uploader': selected['uploader'],
                'duration': selected.get('duration', 0),
                'video_id': selected['video_id']
            }
            bot_state["song_queue"].append(song_info)
            await ctx.send(f"✅ 追加: **{selected['title']}**")
            
            # 再生開始
            vc = bot_state.get("current_vc")
            if vc and not vc.is_playing() and not bot_state.get("is_paused", False):
                run_in_bot_loop(asyncio.to_thread(play_next))
        else:
            await ctx.send("❌ 無効な番号です")
    except asyncio.TimeoutError:
        await ctx.send("⏰ タイムアウトしました")


@bot.command(name='queue', aliases=['q'])
async def cmd_queue(ctx):
    """キュー表示"""
    embed = discord.Embed(title="🎵 再生キュー", color=discord.Color.blue())
    
    now_playing = bot_state.get("now_playing")
    if now_playing:
        embed.add_field(
            name="▶ 再生中",
            value=f"**{now_playing['title']}** - {now_playing.get('uploader', '不明')}",
            inline=False
        )
    
    queue = bot_state.get("song_queue", [])
    if queue:
        queue_text = "\n".join([f"`{i+1}.` {s['title'][:50]}" for i, s in enumerate(queue[:15])])
        if len(queue) > 15:
            queue_text += f"\n... 他 {len(queue)-15} 曲"
        embed.add_field(name=f"📋 キュー ({len(queue)}曲)", value=queue_text, inline=False)
    else:
        embed.add_field(name="📋 キュー", value="空です", inline=False)
    
    embed.set_footer(text=f"ループ: {bot_state.get('loop_mode', 'none')}")
    await ctx.send(embed=embed)


@bot.command(name='nowplaying', aliases=['np'])
async def cmd_np(ctx):
    """現在の曲"""
    now_playing = bot_state.get("now_playing")
    if not now_playing:
        await ctx.send("❌ 再生中の曲がありません")
        return
    
    embed = discord.Embed(title="🎵 Now Playing", color=discord.Color.green())
    embed.add_field(name="曲名", value=now_playing['title'], inline=False)
    embed.add_field(name="Uploader", value=now_playing.get('uploader', '不明'), inline=True)
    
    dur = now_playing.get('duration', 0) or 0
    start_time = bot_state.get("play_start_time", 0)
    pos = int(time.time() - start_time) if start_time else 0
    embed.add_field(name="再生位置", value=f"{pos//60}:{pos%60:02d} / {dur//60}:{dur%60:02d}", inline=True)
    
    if now_playing.get('thumbnail'):
        embed.set_thumbnail(url=now_playing['thumbnail'])
    
    await ctx.send(embed=embed)


@bot.command(name='playlist', aliases=['pl'])
async def cmd_playlist(ctx, url: str, max_items: int = 20, start: int = 0):
    """プレイリストインポート"""
    vc = bot_state.get("current_vc")
    if not vc or not vc.is_connected():
        if ctx.author.voice:
            bot_state["current_vc"] = await ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ VCに入ってください")
            return
    
    msg = await ctx.send(f"📥 読み込み中... (最大{max_items}曲)")
    
    result = fetch_playlist(url, max_items, start)
    
    if not result['songs']:
        await msg.edit(content=f"❌ 曲を取得できませんでした: {result['errors']}")
        return
    
    for s in result['songs']:
        song_info = {
            'title': s['title'],
            'thumbnail': s.get('thumbnail'),
            'webpage_url': s['webpage_url'],
            'uploader': s['uploader'],
            'duration': s.get('duration', 0),
            'video_id': s['video_id']
        }
        bot_state["song_queue"].append(song_info)
    
    await msg.edit(content=f"✅ **{result['title']}** から {len(result['songs'])}曲を追加 (全{result['total']}曲中)")
    
    vc = bot_state.get("current_vc")
    if vc and not vc.is_playing() and not bot_state.get("is_paused", False):
        run_in_bot_loop(asyncio.to_thread(play_next))


@bot.command(name='loop')
async def cmd_loop(ctx, mode: str = None):
    """ループ設定"""
    if mode and mode in ['none', 'song', 'queue']:
        bot_state["loop_mode"] = mode
    else:
        modes = ['none', 'queue', 'song']
        current = bot_state.get("loop_mode", "none")
        idx = modes.index(current) if current in modes else 0
        bot_state["loop_mode"] = modes[(idx + 1) % 3]
    
    labels = {'none': 'オフ', 'song': '曲ループ', 'queue': 'キューループ'}
    await ctx.send(f"🔁 ループ: {labels.get(bot_state['loop_mode'], 'オフ')}")


# === スラッシュコマンド ===

@bot.tree.command(name="search", description="検索して選択")
@app_commands.describe(query="検索キーワード")
async def slash_search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    
    results = search_youtube(query, 5)
    
    if not results:
        await interaction.followup.send("❌ 見つかりませんでした")
        return
    
    # SelectMenuを作成
    options = []
    for i, r in enumerate(results):
        dur = r.get('duration', 0) or 0
        dur_str = f"{dur//60}:{dur%60:02d}" if dur else ""
        label = f"{i+1}. {r['title'][:90]}"
        desc = f"{r['uploader'][:40]} {dur_str}"[:100]
        options.append(discord.SelectOption(
            label=label,
            value=r['video_id'],
            description=desc
        ))
    
    select = discord.ui.Select(placeholder="曲を選択", options=options)
    
    async def select_callback(inter: discord.Interaction):
        video_id = select.values[0]
        selected = next((r for r in results if r['video_id'] == video_id), None)
        
        if not selected:
            await inter.response.send_message("❌ 選択失敗", ephemeral=True)
            return
        
        # VCチェック
        vc = bot_state.get("current_vc")
        if not vc or not vc.is_connected():
            if inter.user.voice:
                bot_state["current_vc"] = await inter.user.voice.channel.connect()
            else:
                await inter.response.send_message("❌ VCに入ってください", ephemeral=True)
                return
        
        # キューに追加
        song_info = {
            'title': selected['title'],
            'thumbnail': selected.get('thumbnail'),
            'webpage_url': selected['webpage_url'],
            'uploader': selected['uploader'],
            'duration': selected.get('duration', 0),
            'video_id': selected['video_id']
        }
        bot_state["song_queue"].append(song_info)
        await inter.response.send_message(f"✅ 追加: **{selected['title']}**")
        
        # 再生開始
        vc = bot_state.get("current_vc")
        if vc and not vc.is_playing() and not bot_state.get("is_paused", False):
            run_in_bot_loop(asyncio.to_thread(play_next))
    
    select.callback = select_callback
    view = discord.ui.View(timeout=60)
    view.add_item(select)
    
    embed = discord.Embed(title=f"🔍 検索結果: {query}", color=discord.Color.blue())
    for i, r in enumerate(results):
        dur = r.get('duration', 0) or 0
        dur_str = f"{dur//60}:{dur%60:02d}" if dur else "不明"
        embed.add_field(
            name=f"{i+1}. {r['title'][:50]}",
            value=f"👤 {r['uploader'][:30]} | ⏱ {dur_str}",
            inline=False
        )
    
    await interaction.followup.send(embed=embed, view=view)


@bot.tree.command(name="queue", description="キュー表示")
async def slash_queue(interaction: discord.Interaction):
    embed = discord.Embed(title="🎵 再生キュー", color=discord.Color.blue())
    
    now_playing = bot_state.get("now_playing")
    if now_playing:
        embed.add_field(
            name="▶ 再生中",
            value=f"**{now_playing['title']}**",
            inline=False
        )
    
    queue = bot_state.get("song_queue", [])
    if queue:
        queue_text = "\n".join([f"`{i+1}.` {s['title'][:50]}" for i, s in enumerate(queue[:10])])
        if len(queue) > 10:
            queue_text += f"\n... 他 {len(queue)-10} 曲"
        embed.add_field(name=f"📋 キュー ({len(queue)}曲)", value=queue_text, inline=False)
    else:
        embed.add_field(name="📋 キュー", value="空です", inline=False)
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="nowplaying", description="現在の曲")
async def slash_np(interaction: discord.Interaction):
    now_playing = bot_state.get("now_playing")
    if not now_playing:
        await interaction.response.send_message("❌ 再生中の曲がありません")
        return
    
    embed = discord.Embed(title="🎵 Now Playing", color=discord.Color.green())
    embed.add_field(name="曲名", value=now_playing['title'], inline=False)
    embed.add_field(name="Uploader", value=now_playing.get('uploader', '不明'), inline=True)
    
    dur = now_playing.get('duration', 0) or 0
    start_time = bot_state.get("play_start_time", 0)
    pos = int(time.time() - start_time) if start_time else 0
    embed.add_field(name="再生位置", value=f"{pos//60}:{pos%60:02d} / {dur//60}:{dur%60:02d}", inline=True)
    
    if now_playing.get('thumbnail'):
        embed.set_thumbnail(url=now_playing['thumbnail'])
    
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="loop", description="ループ切り替え")
@app_commands.choices(mode=[
    app_commands.Choice(name="オフ", value="none"),
    app_commands.Choice(name="曲ループ", value="song"),
    app_commands.Choice(name="キューループ", value="queue"),
])
async def slash_loop(interaction: discord.Interaction, mode: app_commands.Choice[str] = None):
    if mode:
        bot_state["loop_mode"] = mode.value
    else:
        modes = ['none', 'queue', 'song']
        current = bot_state.get("loop_mode", "none")
        idx = modes.index(current) if current in modes else 0
        bot_state["loop_mode"] = modes[(idx + 1) % 3]
    
    labels = {'none': 'オフ', 'song': '曲ループ', 'queue': 'キューループ'}
    await interaction.response.send_message(f"🔁 ループ: {labels.get(bot_state['loop_mode'], 'オフ')}")


@bot.tree.command(name="skip", description="スキップ")
async def slash_skip(interaction: discord.Interaction):
    vc = bot_state.get("current_vc")
    if vc and (vc.is_playing() or bot_state.get("is_paused")):
        vc.stop()
        await interaction.response.send_message("⏭ スキップしました")
    else:
        await interaction.response.send_message("❌ 再生中の曲がありません")


# === 追加のFlask API エンドポイント ===

@app.route('/api/search', methods=['POST'])
def api_search():
    data = request.json or {}
    query = data.get('query', '')
    if not query:
        return jsonify({'error': 'クエリが必要'}), 400
    
    results = search_youtube(query, int(data.get('max_results', 5)))
    return jsonify({'results': results})


@app.route('/api/history')
def api_history():
    """再生履歴（キャッシュDBから）"""
    return jsonify({'history': cache_db.get_recent(15)})


@app.route('/api/cache/stats')
def api_cache_stats():
    """キャッシュ統計"""
    all_cache = cache_db.get_all()
    total_size = 0
    for c in all_cache:
        path = os.path.join(AUDIO_CACHE_DIR, f"{c['video_id']}.opus")
        if os.path.exists(path):
            total_size += os.path.getsize(path)
    return jsonify({
        'total_songs': len(all_cache),
        'total_size_mb': round(total_size / (1024*1024), 2),
    })


@app.route('/api/cache/recent')
def api_cache_recent():
    """最近再生した曲"""
    return jsonify({'songs': cache_db.get_recent(10)})


@app.route('/api/cache/popular')
def api_cache_popular():
    """よく再生する曲"""
    return jsonify({'songs': cache_db.get_popular(10)})


@app.route('/api/cache/add', methods=['POST'])
def api_cache_add():
    """キャッシュから曲を追加"""
    vc = bot_state.get("current_vc")
    if not vc or not vc.is_connected():
        return jsonify({'error': 'VCに接続していません'}), 400
    
    video_id = request.json.get('video_id')
    all_cache = cache_db.get_all()
    cached = next((c for c in all_cache if c['video_id'] == video_id), None)
    
    if not cached:
        return jsonify({'error': 'キャッシュにありません'}), 404
    
    song_info = {
        'title': cached['title'],
        'thumbnail': cached.get('thumbnail'),
        'webpage_url': cached['webpage_url'],
        'uploader': cached['uploader'],
        'duration': cached.get('duration', 0),
        'video_id': cached['video_id']
    }
    bot_state["song_queue"].append(song_info)
    
    if not vc.is_playing() and not bot_state.get("is_paused", False):
        run_in_bot_loop(asyncio.to_thread(play_next))
    
    return jsonify({'message': f'追加: {cached["title"]}'})


@app.route('/api/playlist/import', methods=['POST'])
def api_playlist_import():
    """プレイリストインポート"""
    vc = bot_state.get("current_vc")
    if not vc or not vc.is_connected():
        return jsonify({'error': 'VCに接続していません'}), 400
    
    data = request.json or {}
    url = data.get('url', '')
    max_items = int(data.get('max_items', 20))
    start = int(data.get('start', 0))
    
    if not url:
        return jsonify({'error': 'URLが必要'}), 400
    
    result = fetch_playlist(url, max_items, start)
    
    if not result['songs']:
        return jsonify({'error': '取得失敗', 'detail': result['errors']}), 400
    
    for s in result['songs']:
        song_info = {
            'title': s['title'],
            'thumbnail': s.get('thumbnail'),
            'webpage_url': s['webpage_url'],
            'uploader': s['uploader'],
            'duration': s.get('duration', 0),
            'video_id': s['video_id']
        }
        bot_state["song_queue"].append(song_info)
    
    if not vc.is_playing() and not bot_state.get("is_paused", False):
        run_in_bot_loop(asyncio.to_thread(play_next))
    
    return jsonify({
        'message': f"{len(result['songs'])}曲を追加",
        'title': result['title'],
        'added': len(result['songs']),
        'total': result['total']
    })


# === ダウンロード完了時にキャッシュDBを更新するフック ===
_original_download_song = discord_youtube.download_song

def patched_download_song(song_info):
    """ダウンロード後にキャッシュDBを更新"""
    result = _original_download_song(song_info)
    if result:
        # キャッシュDBに追加
        video_id = song_info.get('video_id')
        if video_id and video_id not in cache_db.data:
            cache_db.add(
                video_id,
                song_info.get('title', '不明'),
                song_info.get('uploader', '不明'),
                song_info.get('duration', 0),
                song_info.get('thumbnail'),
                song_info.get('webpage_url', '')
            )
        else:
            cache_db.update_played(video_id)
    return result

# モンキーパッチ
discord_youtube.download_song = patched_download_song


# === on_ready時にスラッシュコマンドを同期 ===
_original_on_ready = None

@bot.event
async def on_ready():
    print(f'✅ {bot.user.name} が起動しました (v2拡張版)')
    print(f'🌐 WebUI: http://localhost:{FLASK_PORT}')
    
    try:
        synced = await bot.tree.sync()
        print(f'🔧 {len(synced)} スラッシュコマンドを同期しました')
    except Exception as e:
        print(f'コマンド同期エラー: {e}')


# === メイン実行 ===
if __name__ == "__main__":
    print("=" * 50)
    print("🎵 Discord YouTube Bot v2 (拡張版)")
    print("=" * 50)
    print("discord_youtube.py をベースに追加機能を提供")
    print("")
    
    # discord_youtube.py のメインを実行
    # (すでにapp, botはインポート済み)
    from discord_youtube import UPLOAD_FOLDER
    
    for folder in [UPLOAD_FOLDER, AUDIO_CACHE_DIR]:
        if not os.path.exists(folder):
            os.makedirs(folder)
    
    # Flask起動（別スレッド）
    threading.Thread(
        target=lambda: app.run(host='0.0.0.0', port=int(os.environ.get("PORT", FLASK_PORT)), threaded=True),
        daemon=True
    ).start()
    
    # Bot起動
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        print("❌ DISCORD_TOKENが設定されていません")
