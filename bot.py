import os
from threading import Thread
import discord
import dotenv
import uvicorn
from discord.ext import commands, tasks
from fastapi import FastAPI
import yt_dlp as youtube_dl
import requests
import asyncio

dotenv.load_dotenv()

# Discord ボットの設定
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# yt-dlp のオプション設定
ydl_opts = {
    "format": "bestaudio/best",
    "quiet": False,
    "cookies": "./cookies.txt",  # YouTube クッキーのパス
}


# FastAPI アプリケーション
app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Bot is running!"}

# FastAPI サーバーをスレッドで起動する関数
def start():
    uvicorn.run(app, host="0.0.0.0", port=8080)

# グローバル変数の初期化
current_url = None
volume = 1.0  # デフォルト音量

# YouTube 動画検索用の関数
def search_youtube(query):
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            return info['webpage_url']
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            return None

# 音楽再生のためのコマンド
@bot.command(name='play', help='指定されたURLまたはキーワードで音楽を再生します')
async def play(ctx, *, url: str):
    global current_url
    voice_client = ctx.guild.voice_client

    if voice_client is None or not voice_client.is_connected():
        if ctx.author.voice:
            try:
                await ctx.author.voice.channel.connect()
                await ctx.send(f"ボイスチャンネル {ctx.author.voice.channel} に参加しました。")
            except discord.ClientException:
                await ctx.send("ボイスチャンネルへの接続に失敗しました。既に接続されています。")
            except Exception as e:
                await ctx.send(f"エラーが発生しました: {e}")
                return
        else:
            await ctx.send("ボイスチャンネルに接続されていません。")
            return

    if voice_client.is_playing():
        await ctx.send("既に再生中です。再生を停止してからもう一度試してください。")
        return

    if 'youtube.com' not in url and 'youtu.be' not in url:
        url = search_youtube(url)
        if url is None:
            await ctx.send("YouTubeで動画を見つけられませんでした。")
            return

    current_url = url

    async with ctx.typing():
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['url']

        # 音量設定を追加したFFmpegコマンドを使用
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
            'options': f'-vn -af "volume={volume}"'
        }

        voice_client.play(discord.FFmpegPCMAudio(url2, **ffmpeg_options),
                          after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))

    await ctx.send(f"再生中: {url}")

# 次の曲を再生する関数
async def play_next(ctx):
    if current_url:
        await ctx.invoke(bot.get_command('play'), url=current_url)

# ボットの起動時に通知タスクを開始
@bot.event
async def on_ready():
    print(f"Bot としてログイン: {bot.user}")
    notify_stream_start.start()

# FastAPI サーバーを別スレッドで起動
t = Thread(target=start)
t.start()

# Discord ボットを実行
bot_token = os.getenv("TOKEN")
bot.run(bot_token)
