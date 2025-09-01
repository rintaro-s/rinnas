# --- 使い方 ---
# 1. .envファイルにDISCORD_TOKENとLM_STUDIO_URLを設定してください。
# 2. VoiceVox（またはVOICEVOX ENGINE）をローカルで起動してください（デフォルト: http://localhost:50021）。
# 3. このスクリプトを実行すると、指定のDiscordチャンネルでチャットを受け取り、
#    LM Studioに投げて返答を同じチャンネルに投稿し、VCでビィちゃんの声で読み上げます。
# 4. VC未接続時はサーバー内の最初のVCに自動参加します。

import discord
import requests
import asyncio
import os
import base64
import io
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1/chat/completions")
CHANNEL_ID = 1263086389935865857  # 送信先チャンネルID
GUILD_ID = 1257319197231288370    # サーバーID

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

class VCBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.voice_client = None

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        self.channel = self.get_channel(CHANNEL_ID)
        if not self.channel:
            self.channel = await self.fetch_channel(CHANNEL_ID)
        print(f"Target channel: {self.channel}")

    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.channel.id != CHANNEL_ID:
            return
        if not self.voice_client or not self.voice_client.is_connected():
            guild = self.get_guild(GUILD_ID)
            if guild and guild.voice_channels:
                vc = guild.voice_channels[0]
                self.voice_client = await vc.connect()
        # 画像添付があればbase64化
        image_data = None
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    image_data = await self.process_image(attachment)
                    break
        user_content = message.content
        response_text = await self.ask_lmstudio(user_content, image_data)
        await self.channel.send(response_text)
        await self.tts_and_play(response_text)

    async def ask_lmstudio(self, content, image_data=None):
        # LAL_chat.pyと同じ画像対応
        messages = [
            {"role": "user", "content": content}
        ]
        system_prompt = {
            "role": "system",
            "content": "あなたは可愛い妹です。明るく元気な妹口調で短く話してください。"
        }
        messages.insert(0, system_prompt)
        if image_data:
            messages[1]['content'] = [
                {"type": "text", "text": content},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}}
            ]
        payload = {
            "messages": messages,
            "max_tokens": 1000,
            "temperature": 0.7
        }
        try:
            resp = requests.post(LM_STUDIO_URL, json=payload, timeout=30)
            resp.raise_for_status()
            result = resp.json()
            return result['choices'][0]['message']['content'][:2000]
        except Exception as e:
            return f"エラー: {e}"

    async def process_image(self, attachment):
        try:
            image_data = await attachment.read()
            img = Image.open(io.BytesIO(image_data))
            if img.width > 1024 or img.height > 1024:
                img.thumbnail((1024, 1024))
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            encoded_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return encoded_image
        except Exception as e:
            print(f"画像処理エラー: {e}")
            return None

    async def tts_and_play(self, text):
        # VoiceVox APIで音声生成（ビィちゃん専用）
        wav_path = await asyncio.to_thread(self.generate_voice, text)
        if wav_path and self.voice_client and self.voice_client.is_connected():
            audio_source = discord.FFmpegPCMAudio(wav_path)
            while self.voice_client.is_playing():
                await asyncio.sleep(0.5)
            self.voice_client.play(audio_source)
            # 再生終了まで待機
            while self.voice_client.is_playing():
                await asyncio.sleep(0.5)
            os.remove(wav_path)

    def generate_voice(self, text):  # ← このメソッドがクラス内に正しく定義されているか確認
        try:
            url = "http://localhost:50021/audio_query"
            params = {"text": text, "speaker": 58}  # ビィちゃん
            r = requests.post(url, params=params)
            if r.status_code != 200:
                print(f"audio_query error: {r.status_code}")
                return None
            query_data = r.json()
            
            synthesis_url = "http://localhost:50021/synthesis"
            synthesis_params = {"speaker": 58}  # ビィちゃん（修正済み）
            audio_response = requests.post(
                synthesis_url,
                headers={"Content-Type": "application/json"},
                params=synthesis_params,
                json=query_data
            )
            if audio_response.status_code != 200:
                print(f"synthesis error: {audio_response.status_code}")
                return None
            
            temp_file = f"temp_voice_bii.wav"
            with open(temp_file, "wb") as f:
                f.write(audio_response.content)
            return temp_file
        except Exception as e:
            print(f"TTS生成エラー: {e}")
            return None

if __name__ == "__main__":
    bot = VCBot()
    bot.run(DISCORD_TOKEN)
