import discord
from discord import app_commands
import asyncio
import requests
import os
import io
from dotenv import load_dotenv

load_dotenv()

class YomiageBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.voice_client = None
        self.voice_style = "四国めたん" # Default voice
        
        # Voice options
        self.voice_options = ["四国めたん", "ずんだもん", "春日部つむぎ", "波音リツ", "雨晴はう"]
    
    async def setup_hook(self):
        await self.tree.sync()

    async def on_ready(self):
        print(f"{self.user} is now running!")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="テキストチャンネル"))

bot = YomiageBot()

@bot.tree.command(name="vcconnect", description="Connect to a voice channel")
async def vcconnect(interaction: discord.Interaction):
    # Get all voice channels in the server
    voice_channels = interaction.guild.voice_channels
    
    if not voice_channels:
        await interaction.response.send_message("No voice channels found in this server.")
        return
    
    # Create choices from available voice channels
    choices = [app_commands.Choice(name=vc.name, value=vc.id) for vc in voice_channels]
    
    # Create a select menu with voice channel options
    select = discord.ui.Select(
        placeholder="Select a voice channel",
        options=[discord.SelectOption(label=choice.name, value=str(choice.value)) for choice in choices]
    )
    
    # Create view and add select menu
    view = discord.ui.View(timeout=180.0)
    view.add_item(select)
    
    async def select_callback(interaction: discord.Interaction):
        # Get the selected voice channel ID
        selected_id = int(select.values[0])
        voice_channel = discord.utils.get(voice_channels, id=selected_id)
        
        try:
            # Connect to the voice channel
            if bot.voice_client is not None:
                await bot.voice_client.disconnect()
            
            bot.voice_client = await voice_channel.connect()
            await interaction.response.send_message(f"Connected to {voice_channel.name}!")
        except RuntimeError as e:
            if "PyNaCl library needed" in str(e):
                await interaction.response.send_message(
                    "Error: PyNaCl library is not installed. Please run 'pip install PyNaCl' to use voice features."
                )
            else:
                await interaction.response.send_message(f"Error connecting to voice channel: {str(e)}")
        except Exception as e:
            await interaction.response.send_message(f"Error connecting to voice channel: {str(e)}")
    
    # Set the callback function
    select.callback = select_callback
    
    await interaction.response.send_message("Select a voice channel to connect:", view=view)

@bot.tree.command(name="vcdisconnect", description="Disconnect from voice channel")
async def vcdisconnect(interaction: discord.Interaction):
    if bot.voice_client is None:
        await interaction.response.send_message("Not connected to any voice channel.")
        return
    
    await bot.voice_client.disconnect()
    bot.voice_client = None
    await interaction.response.send_message("Disconnected from voice channel.")

@bot.tree.command(name="voice", description="Change voice style")
@app_commands.describe(style="Voice style to use")
@app_commands.choices(style=[
    app_commands.Choice(name=voice, value=voice) for voice in ["四国めたん", "ずんだもん", "春日部つむぎ", "波音リツ", "雨晴はう"]
])
async def change_voice(interaction: discord.Interaction, style: app_commands.Choice[str]):
    bot.voice_style = style.value
    await interaction.response.send_message(f"Voice changed to {style.value}")

@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return
    
    # Only read messages if connected to a voice channel
    if bot.voice_client is not None and bot.voice_client.is_connected():
        # Check for stop command
        if message.content == ";":
            if bot.voice_client.is_playing():
                bot.voice_client.stop()
                await message.channel.send("読み上げを停止しました", delete_after=3)
            return
            
        if message.content and not message.content.startswith('/'):
            # Clean up the message content
            content = message.content
            
            # Replace URLs with the word "リンク"
            import re
            url_pattern = r'https?://\S+'
            content = re.sub(url_pattern, 'リンク', content)
            
            # Add note about attachments if there are any
            if message.attachments:
                content += f" 添付ファイル {len(message.attachments)}件"
            
            try:
                # Call VoiceBox API
                voice_data = generate_voice(content, bot.voice_style)
                
                # Play the audio
                if voice_data:
                    audio_source = discord.FFmpegPCMAudio(voice_data)
                    if not bot.voice_client.is_playing():
                        bot.voice_client.play(audio_source)
                    else:
                        # Wait until current speech is done
                        while bot.voice_client.is_playing():
                            await asyncio.sleep(0.5)
                        bot.voice_client.play(audio_source)
            except Exception as e:
                print(f"Error generating voice: {e}")

def generate_voice(text, voice_style):
    """
    Call the local VoiceBox API to generate speech
    This assumes VoiceBox is running locally with default settings
    Adjust URL and parameters based on your VoiceBox setup
    """
    try:
        # This is an example - adjust to match your VoiceBox API
        url = "http://localhost:50021/audio_query"
        params = {"text": text, "speaker": get_speaker_id(voice_style)}
        
        # Generate audio query
        response = requests.post(url, params=params)
        if response.status_code != 200:
            print(f"Error querying VoiceBox API: {response.status_code}")
            return None
        
        query_data = response.json()
        
        # Generate audio
        synthesis_url = "http://localhost:50021/synthesis"
        synthesis_params = {"speaker": get_speaker_id(voice_style)}
        
        audio_response = requests.post(
            synthesis_url, 
            headers={"Content-Type": "application/json"},
            params=synthesis_params,
            json=query_data
        )
        
        if audio_response.status_code != 200:
            print(f"Error generating audio: {audio_response.status_code}")
            return None
        
        # Save audio to temporary file
        temp_file = f"temp_voice_{voice_style}.wav"
        with open(temp_file, "wb") as f:
            f.write(audio_response.content)
        
        return temp_file
        
    except Exception as e:
        print(f"Exception in generate_voice: {e}")
        return None

def get_speaker_id(voice_style):
    """Map voice style names to VoiceBox speaker IDs"""
    voice_map = {
        "四国めたん": 2,
        "ずんだもん": 3,
        "春日部つむぎ": 8,
        "波音リツ": 9,
        "雨晴はう": 10
    }
    return voice_map.get(voice_style, 2)  # Default to 四国めたん (ID 2) if not found

# Run the bot (replace TOKEN with your Discord bot token)
TOKEN = os.getenv("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("DISCORD_TOKEN is not set in .env file")
