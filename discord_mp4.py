import discord
import os
import asyncio
from flask import Flask, request
from werkzeug.utils import secure_filename
import threading
import subprocess
import uuid
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
INTENTS = discord.Intents.default()
INTENTS.message_content = True
client = discord.Client(intents=INTENTS)
UPLOAD_CHANNEL_ID = 1288678451456380969  # 整数で指定

app = Flask(__name__)
UPLOAD_FOLDER = "./uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
FLASK_PORT = 8050

GPU_BITRATES = ["5M", "3M", "1M", "500K", "100k"]

user_upload_links = {}

def generate_unique_filename(filename):
    return f"{uuid.uuid4()}_{secure_filename(filename)}"

@app.route("/", methods=["GET", "POST"])
def upload_page():
    if request.method == "POST":
        file = request.files.get("file")
        user_id_str = request.form.get("user_id")
        try:
            user_id = int(user_id_str)
        except Exception as e:
            return "無効なuser_idです。"
        if file and file.filename.endswith(".mp4"):
            safe_name = generate_unique_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, safe_name)
            file.save(file_path)
            channel_id = user_upload_links.get(user_id, {}).get("channel_id")
            future = asyncio.run_coroutine_threadsafe(
                upload_to_discord(file_path, user_id, channel_id),
                client.loop
            )
            try:
                future.result(timeout=60)
            except:
                if os.path.exists(file_path):
                    os.remove(file_path)
                return "エラーまたは放置リクエストにより処理を中断しました。"
            return "動画がアップロードされ、処理が開始されました。"
    user_id = request.args.get("user_id", "")
    return f'''
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
    '''

async def compress_video(file_path, user):
    """
    CPU (libx264) を使って互換性重視で圧縮する。
    - まずビットレートを下げて試す
    - それでも10MB以下にならない場合は解像度を下げて再試行する
    互換性向上のために以下を指定:
    - libx264
    - -pix_fmt yuv420p
    - -movflags +faststart
    - audio: aac 128k
    """
    base = file_path.rsplit('.', 1)[0]
    # H.264向けのビットレート（上から順に試す）
    bitrates = ["5M", "3M", "1M", "700k", "500k", "300k", "150k"]
    # 解像度を下げるフォールバック（幅: 高さは -2 でアスペクト比維持）
    scales = [None, "1280:-2", "854:-2", "640:-2"]

    phase = 0
    for scale in scales:
        for br in bitrates:
            phase += 1
            # ファイル名に分かりやすくスケール・ビットレートを付加
            scale_suffix = f"_{scale.split(':')[0]}p" if scale else ""
            compressed_path = f"{base}_compressed_cpu_{br}{scale_suffix}.mp4"

            # ffmpeg コマンドを組み立てる（互換性重視）
            cmd = f'ffmpeg -y -i "{file_path}" '
            if scale:
                cmd += f'-vf "scale={scale}" '
            cmd += (
                f'-c:v libx264 -preset medium -profile:v high -pix_fmt yuv420p '
                f'-b:v {br} -c:a aac -b:a 128k -movflags +faststart "{compressed_path}"'
            )

            await user.send(f"圧縮フェーズ{phase}開始: ビットレート={br}{', 解像度=' + scale if scale else ''}")
            try:
                # shell=True を使ってコマンド文字列を流す（Windows 環境を想定）
                subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
            except Exception as e:
                await user.send(f"圧縮中に例外が発生しました: {e}")
                continue

            if os.path.exists(compressed_path):
                size = os.path.getsize(compressed_path)
                if size <= 10 * 1024 * 1024:
                    await user.send(f"圧縮成功: {size} bytes (フェーズ{phase})")
                    return compressed_path
                else:
                    await user.send(f"フェーズ{phase}の結果: {size} bytes でまだ大きいため次を試します。")
                    try:
                        os.remove(compressed_path)
                    except:
                        pass
            else:
                await user.send(f"フェーズ{phase}で圧縮ファイルが生成されませんでした。次を試します。")

    # どのフェーズでも10MB以下にできなかった
    await user.send("すべての圧縮フェーズを試しましたが、10MB以下に出来ませんでした。解像度の大幅ダウンや長さのカットを検討してください。")
    return None

async def upload_to_discord(file_path, user_id, channel_id):
    user = await client.fetch_user(user_id)
    if not user:
        print(f"Invalid user ID: {user_id}")
        return
    channel = client.get_channel(channel_id)
    if channel is None:
        try:
            channel = await client.fetch_channel(channel_id)
        except Exception as e:
            await user.send("アップロード先チャンネルを取得できませんでした。")
            os.remove(file_path)
            return

    if os.path.getsize(file_path) <= 10 * 1024 * 1024:
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
    client.loop.create_task(update_gpu_status())

async def update_gpu_status():
    while True:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True
            )
            usage_str = result.stdout.strip().split('\n')[0]
            await client.change_presence(activity=discord.Game(name=f"私のGPU: {usage_str}%"))
        except:
            await client.change_presence(activity=discord.Game(name="GPU usage check error"))
        await asyncio.sleep(10)

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    if message.content.lower().startswith("mp4!"):
        upload_url = f"http://rinnas.f5.si:{FLASK_PORT}/?user_id={message.author.id}"
        user_upload_links[message.author.id] = {"channel_id": message.channel.id}
        try:
            await message.author.send(f"動画をアップロードしてください: {upload_url}")
        except Exception as e:
            print(f"ダイレクトメッセージ送信失敗: {e}")

def run_flask():
    app.run(host="0.0.0.0", port=FLASK_PORT, use_reloader=False)

if __name__ == "__main__":
    if TOKEN:
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        asyncio.run(client.start(TOKEN))
    else:
        print("DISCORD_TOKEN is not set in .env file")