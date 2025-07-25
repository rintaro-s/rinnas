import discord
import os
import asyncio
import uuid
from flask import Flask, request
from werkzeug.utils import secure_filename
import threading
from dotenv import load_dotenv

# Discord Botの設定
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
INTENTS = discord.Intents.default()
INTENTS.message_content = True
client = discord.Client(intents=INTENTS)
UPLOAD_CHANNEL_ID = 1311135404929581107  # 整数で指定

# Flaskアプリの設定
app = Flask(__name__)
UPLOAD_FOLDER = "./uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
FLASK_PORT = 8050

# 動画圧縮用のCRF値
CRF_VALUES = [28, 30, 40, 48, 51]

# ユーザーごとのアップロード状態を管理
user_upload_links = {}

def generate_unique_filename(filename):
    return f"{uuid.uuid4()}_{secure_filename(filename)}"

@app.route("/", methods=["GET", "POST"])
def upload_page():
    if request.method == "POST":
        file = request.files.get("file")
        user_id = request.form.get("user_id")
        if file and file.filename.endswith(".mp4"):
            unique_name = generate_unique_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, unique_name)
            file.save(file_path)
            # Discordのイベントループに非同期処理を安全にスケジュール
            future = asyncio.run_coroutine_threadsafe(upload_to_discord(file_path, user_id), client.loop)
            try:
                future.result(timeout=60)  # 必要ならタイムアウトを設定
            except Exception as exc:
                print(f"Discordへのアップロード中にエラー: {exc}")
                # 放置やエラー時はファイルを消す
                if os.path.exists(file_path):
                    os.remove(file_path)
                return "エラーまたはアップロード放置により処理を中断しました。"
            return "動画がアップロードされ、処理が開始されました。"
    user_id = request.args.get("user_id", "")
    return f"""
    <!DOCTYPE html>
    <html lang="ja">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>動画アップロード</title>
    </head>
    <body>
        <h1>動画アップロード</h1>
        <form action="/" method="post" enctype="multipart/form-data">
            <input type="file" name="file" accept="video/mp4" required>
            <input type="hidden" name="user_id" value="{user_id}">
            <button type="submit">アップロード</button>
        </form>
    </body>
    </html>
    """

async def compress_video(file_path, user):
    """動画を圧縮して10MB以下にする。すべてのCRF値を試し、条件を満たす中で最も品質の高いもの（最も低いCRF値）を返す"""
    candidates = {}
    base = file_path.rsplit('.', 1)[0]
    for i, crf in enumerate(CRF_VALUES, start=1):
        compressed_path = f"{base}_compressed_crf{crf}.mp4"
        os.system(f"ffmpeg -y -i {file_path} -vcodec libx264 -crf {crf} {compressed_path}")
        size = os.path.getsize(compressed_path)
        if size <= 10 * 1024 * 1024:  # 10MB以下なら候補として保存
            candidates[crf] = compressed_path
        else:
            await user.send(f"容量がまだ大きいです。フェーズ{i}（crf={crf}）の結果: {size} bytes")
            os.remove(compressed_path)
    if candidates:
        best_crf = min(candidates.keys())  # 数値が低いほうが高品質
        best_path = candidates[best_crf]
        # 他の候補ファイルを削除
        for crf, path in candidates.items():
            if path != best_path:
                os.remove(path)
        return best_path
    return None



async def upload_to_discord(file_path, user_id):
    """動画をDiscordにアップロード"""
    channel = client.get_channel(UPLOAD_CHANNEL_ID)
    user = await client.fetch_user(user_id)  # ユーザー情報を取得

    if os.path.getsize(file_path) <= 10 * 1024 * 1024:  # 10MB以下ならそのままアップロード
        await user.send("フェーズ1処理中。")
        await channel.send(file=discord.File(file_path))
    else:
        await user.send("容量が大きいため、圧縮を開始します。")
        compressed_path = await compress_video(file_path, user)
        if compressed_path:
            await user.send("圧縮が完了しました。Discordにアップロードします。")
            await channel.send(file=discord.File(compressed_path))
            os.remove(compressed_path)
        else:
            await user.send("動画を圧縮しましたが、10MB以下にできませんでした。")
    os.remove(file_path)

@client.event
async def on_ready():
    print(f"Discord Botログイン: {client.user}")
    print(f"Bot ID: {client.user.id}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.lower().startswith("mp4!"):
        upload_url = f"http://127.0.0.1:{FLASK_PORT}/?user_id={message.author.id}"
        user_upload_links[message.author.id] = upload_url
        try:
            await message.author.send(f"動画をアップロードしてください: {upload_url}")
        except Exception as e:
            print(f"ダイレクトメッセージ送信失敗: {e}")

def run_flask():
    """Flaskアプリを別スレッドで実行"""
    app.run(port=FLASK_PORT, use_reloader=False)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    asyncio.run(client.start(TOKEN))
