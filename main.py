import discord
from discord.ext import tasks, commands
from discord import app_commands
import os
import asyncio
from dotenv import load_dotenv
from characterai import aiocai
from googletrans import Translator
import yt_dlp as youtube_dl
from datetime import timedelta, datetime

translator = Translator()

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CAI_KEY = os.getenv("CAI_API_KEY")

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.reactions = True
intents.members = True
bot = commands.Bot(command_prefix='.', intents=intents)

char_id = "9wmZ47U4nV6ddIKwUyI-UXWz4qSMhzlRDsXbEAU8le4"
client = aiocai.Client(CAI_KEY)

api_lock = asyncio.Lock()
queue_lock = asyncio.Lock()
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'verbose' : True
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

queues = {}

def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

async def play_next(ctx):
    queue = get_queue(ctx.guild.id)
    if len(queue) > 0:
        song = queue.pop(0)
        player = await YTDLSource.from_url(song['url'], loop=bot.loop, stream=True)

        def after_playing(error):
            if error:
                print(f'Error playing audio: {error}')
            bot.loop.create_task(play_next(ctx))

        ctx.guild.voice_client.play(player, after=after_playing)
        await ctx.channel.send(f'**Tocando agora:** {player.title}')

def is_owner(interaction : discord.Interaction):
    if interaction.user.id == interaction.guild.owner_id:
        return True
    return False
    
@bot.tree.command(name="play")
async def play(interaction: discord.Interaction, url: str):
    if not interaction.user.voice:
        await interaction.response.send_message("Você precisa estar em um canal de voz para usar este comando.", ephemeral=True)
        return

    channel = interaction.user.voice.channel

    if interaction.guild.voice_client is None:
        await channel.connect()

    await interaction.response.defer(ephemeral=True)

    data = await YTDLSource.from_url(url, loop=bot.loop, stream=True)

    async with queue_lock:
        queue = get_queue(interaction.guild.id)
        queue.append({'title': data.title, 'url': url})
    
    await interaction.followup.send(f"**Adicionado à fila:** {data.title}  / {url}")

    if not interaction.guild.voice_client.is_playing():
        await play_next(interaction)

@bot.tree.command(name='queue')
async def show_queue(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)
    if len(queue) == 0:
        await interaction.response.send_message("**A fila está vazia.**")
    else:
        queue_list = "\n".join([f"{idx + 1}. {song['title']}" for idx, song in enumerate(queue)])
        await interaction.response.send_message(f"**Fila de músicas:**\n{queue_list}")

@bot.tree.command(name='stop')
async def stop(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("Desconectando.")

@bot.tree.command(name='skip')
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("**Música pulada.**")
    else:
        await interaction.response.send_message("**Não há música tocando no momento.**")



async def cai(mensagem):
    try:
        async with api_lock:
            me = await client.get_me()
            async with await client.connect() as chat:
                new_chat, _ = await chat.new_chat(char_id, me.id)
                response_message = await chat.send_message(char_id, new_chat.chat_id, mensagem)
                return response_message.text
    except Exception as e:
        print(f"Erro ao conectar com a API do Character.ai: {e}")
        return "Desculpe, algo deu errado ao tentar falar com o personagem."


@bot.event
async def on_ready():
    print(f"O bot {bot.user.name} está online!")
    await bot.tree.sync()

@bot.event
async def on_message(message: discord.Message):
    if message.author.id == 981295581269983232:
        return
    if message.content == "<@981295581269983232>":
        async with message.channel.typing():
            resposta = await cai("Olá")
            traduzir = translator.translate(resposta, src="en", dest="pt")
            await message.reply(traduzir.text)
            return
    if bot.user.mentioned_in(message):
        mensagem_conteudo = message.clean_content.replace(f'@{bot.user.name}', '').strip()
        traducao = translator.translate(mensagem_conteudo, src="pt", dest="en")
        async with message.channel.typing():
            resposta = await cai(traducao.text)
            traduzir = translator.translate(resposta, src="en", dest="pt")
            await message.reply(traduzir.text)
            return
    if message.author.id == 1195487609334538350:
        mensagem_conteudo = message.clean_content.replace(f'@{bot.user.name}', '').strip()
        traducao = translator.translate(mensagem_conteudo, src="pt", dest="en")
        async with message.channel.typing():
            resposta = await cai(traducao.text)
            traduzir = translator.translate(resposta, src="en", dest="pt")
            await message.reply(traduzir.text)
            return

    await bot.process_commands(message)



bot.run(DISCORD_TOKEN)
