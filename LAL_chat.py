import discord
from discord.ext import commands
import requests
import json
import base64
import io
from PIL import Image
import os
from dotenv import load_dotenv

load_dotenv()

# Discord bot設定
TOKEN = os.getenv('DISCORD_TOKEN')
LM_STUDIO_URL = os.getenv('LM_STUDIO_URL', 'http://localhost:1234/v1/chat/completions')

# インテントの設定
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def call_lm_studio(messages, image_data=None):
    """LM Studioにリクエストを送信"""
    try:
        # システムプロンプトを調整
        system_prompt = {
            "role": "system",
            "content": "私はあなたの兄です。明るく元気な妹口調で話して。あたなはLALv5-b3というLLMです。簡潔に話して"
        }
        messages.insert(0, system_prompt)
        
        # 画像がある場合はVLM用にフォーマット
        if image_data:
            messages[1]['content'] = [
                {"type": "text", "text": messages[1]['content']},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}
            ]
        
        payload = {
            "messages": messages,  # そのメッセージのみ送信
            "max_tokens": 4000,
            "temperature": 0.7
        }
        
        response = requests.post(LM_STUDIO_URL, json=payload, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        response_content = result['choices'][0]['message']['content']
        
        # <think>...</think>の部分を除去
        import re
        response_content = re.sub(r'<think>.*?</think>', '', response_content, flags=re.DOTALL)
        response_content = response_content.strip()
        
        # Discordの制限に合わせて2000文字以内に切り詰める
        return response_content[:2000]
    except Exception as e:
        return f"エラーが発生しました: {str(e)}"

async def process_image(attachment):
    """画像をbase64にエンコード"""
    try:
        # 画像をダウンロード
        image_data = await attachment.read()
        
        # PILで画像を処理（必要に応じてリサイズ）
        img = Image.open(io.BytesIO(image_data))
        if img.width > 1024 or img.height > 1024:
            img.thumbnail((1024, 1024))
        
        # base64エンコード
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        encoded_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
        
        return encoded_image
    except Exception as e:
        print(f"画像処理エラー: {e}")
        return None

async def collect_chat_history(channel, limit=10):
    """Discordチャンネルの直近のチャット履歴を収集"""
    history = []
    async for message in channel.history(limit=limit):
        if message.author != bot.user:  # ボット自身のメッセージは除外
            history.append({"role": "user", "content": message.content})
    return history[::-1]  # 時系列順に並べ替え

@bot.event
async def on_ready():
    print(f'{bot.user} がログインしました！')

@bot.event
async def on_message(message):
    # ボット自身のメッセージは無視
    if message.author == bot.user:
        return
    
    # ボットがメンションされているかチェック
    if bot.user.mentioned_in(message):
        # メンション部分を除去してテキストを取得
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        
        if not content:
            content = "こんにちは！"
        
        # 画像が添付されているかチェック
        image_data = None
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    image_data = await process_image(attachment)
                    break

        # メンション時はそのメッセージのみ送信
        messages = [{"role": "user", "content": content}]

        # 応答中メッセージを送信
        async with message.channel.typing():
            response = await call_lm_studio(messages, image_data)
        
        # 返信を送信（メンション付きで返信）
        await message.reply(response[:2000])  # 応答を2000文字以内に制限
    
    # コマンドを処理
    await bot.process_commands(message)

@bot.command(name='ping')
async def ping(ctx):
    """ボットの応答テスト"""
    await ctx.send('Pong!')

@bot.command(name='help_ai')
async def help_ai(ctx):
    """ヘルプメッセージ"""
    help_text = """
    **AIチャットボット使用方法:**
    • ボットをメンションして質問してください
    • 画像を添付してメンションすると、画像について説明します
    • `!ping` - ボットの応答テスト
    """
    await ctx.send(help_text)

# ボットを起動
if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("DISCORD_TOKEN is not set. Please set it in your .env file.")