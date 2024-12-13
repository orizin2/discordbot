import os  # 環境変数からトークンを取得するために使用
from threading import Thread
import nacl
import discord
import dotenv
import uvicorn
from discord.ext import commands
from fastapi import FastAPI
import yt_dlp as youtube_dl

dotenv.load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True  # ボイスステートを有効にする

bot = commands.Bot(command_prefix='!', intents=intents)

# デフォルトのFFmpegオプション。音量オプションは後で追加する。
ffmpeg_options = {
    'options': '-vn',
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin'
}

ydl_opts = {
    'format': 'best audio/best',
    'quiet': True,
    'playlist': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'cookiefile': None,
    'noprogress': True,
}

# yt-dlp を実行する際にカスタム引数を渡す
yt_dlp_command = f"--cookies-from-browser chrome"  # 使用しているブラウザに応じて変更
with youtube_dl.YoutubeDL(ydl_opts) as ydl:
    ydl.add_default_extra_info(yt_dlp_command)


ydl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
}

queue = []
looping = False
current_url = None
volume = 1.0  # デフォルトの音量


def search_youtube(query):
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
            return info['webpage_url']
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            return None


async def play_next(ctx):
    global current_url
    if looping and current_url:
        await ctx.invoke(bot.get_command('play'), url=current_url)
    elif queue:
        current_url = queue.pop(0)  # キューから次の楽曲を取得して再生
        await ctx.invoke(bot.get_command('play'), url=current_url)
    else:
        current_url = None  # キューが空になったら、現在のURLをリセット


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
        ffmpeg_options_with_volume = ffmpeg_options.copy()
        ffmpeg_options_with_volume['options'] += f' -af "volume={volume}"'

        voice_client.play(discord.FFmpegPCMAudio(url2, **ffmpeg_options_with_volume),
                          after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))

    await ctx.send(f"再生中: {url}")


@bot.command(name='pause', help='音楽を一時停止します')
async def pause(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("音楽を一時停止しました。")
    else:
        await ctx.send("現在再生中の音楽はありません。")


@bot.command(name='resume', help='音楽を再開します')
async def resume(ctx):
    if ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("音楽を再開しました。")
    else:
        await ctx.send("再開する音楽はありません。")


@bot.command(name='stop', help='音楽を停止します')
async def stop(ctx):
    if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
        ctx.voice_client.stop()
        await ctx.send("音楽を停止しました。")
    else:
        await ctx.send("停止する音楽はありません。")


@bot.command(name='loop', help='現在の曲をループします')
async def loop(ctx):
    global looping
    looping = not looping
    if looping:
        await ctx.send("ループを有効にしました。")
    else:
        await ctx.send("ループを無効にしました。")


@bot.command(name='skip', help='次の曲にスキップします')
async def skip(ctx):
    if ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("次の曲にスキップしました。")
    else:
        await ctx.send("スキップする曲はありません。")


@bot.command(name='volume', help='音量を設定します（例: !volume 0.5 で音量を半分に）')
async def set_volume(ctx, vol: float):
    global volume
    if 0 <= vol <= 2:
        volume = vol
        await ctx.send(f"音量を {volume * 100}% に設定しました。")
    else:
        await ctx.send("音量は0から2の範囲で設定してください。")


@bot.command(name='join', help='ボイスチャンネルに参加します')
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client is not None:
            if ctx.voice_client.channel == channel:
                await ctx.send("既にボイスチャンネルに接続されています。")
                return
            else:
                await ctx.voice_client.disconnect()
        try:
            await channel.connect()
            await ctx.send(f"ボイスチャンネル {channel} に参加しました。")
        except discord.ClientException:
            await ctx.send("ボイスチャンネルへの接続に失敗しました。")
        except Exception as e:
            await ctx.send(f"エラーが発生しました: {e}")
    else:
        await ctx.send("ボイスチャンネルに接続されていません。")


@bot.command(name='disconnect', help='ボイスチャンネルから退出します')
async def disconnect(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("ボイスチャンネルから退出しました。")
    else:
        await ctx.send("ボイスチャンネルに接続されていません。")

app = FastAPI()
@app.get("/")
async def root():
    return {"message": "aaa"}

def start():
    uvicorn.run(app,host="0.0.0.0", port=8080)
t = Thread(target=start)
t.start()

bot_token = os.environ.get("TOKEN")
bot.run(bot_token)

import discord
from discord.ext import tasks
import asyncio
import yt_dlp as youtube_dl
import requests

# Twitch API の設定
TWITCH_CLIENT_ID = "YOUR_TWITCH_CLIENT_ID"
TWITCH_ACCESS_TOKEN = "YOUR_TWITCH_ACCESS_TOKEN"
TWITCH_USERNAME = "kotoha_hkll"
DISCORD_CHANNEL_ID = 943452560847695884  # 通知を送る Discord チャンネルの ID
MENTION_ROLE_ID = 733529800219557928  # メンションする役職の ID (オプション)

# 配信状態の追跡
is_streaming = False

# 配信者の配信状況を取得する関数
def check_stream_status():
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_ACCESS_TOKEN}"
    }
    params = {
        "user_login": TWITCH_USERNAME
    }
    response = requests.get("https://api.twitch.tv/helix/streams", headers=headers, params=params)
    data = response.json()

    if "data" in data and len(data["data"]) > 0:
        return True  # 配信中
    return False  # 配信していない

# 定期的に配信状況を確認するタスク
@tasks.loop(minutes=1)
async def notify_stream_start():
    global is_streaming
    channel = bot.get_channel(DISCORD_CHANNEL_ID)

    if not channel:
        print("Discord チャンネルが見つかりませんでした。")
        return

    streaming_now = check_stream_status()

    if streaming_now and not is_streaming:
        is_streaming = True
        mention = f"<@&{MENTION_ROLE_ID}>" if MENTION_ROLE_ID else ""
        await channel.send(f"{mention} 🎥 {TWITCH_USERNAME} さんが Twitch で配信を開始しました！\nhttps://www.twitch.tv/{TWITCH_USERNAME}")

    elif not streaming_now and is_streaming:
        is_streaming = False
        print("配信が終了しました。")

# ボットが起動したときに通知タスクを開始
@bot.event
async def on_ready():
    print(f"Bot としてログイン: {bot.user}")
    notify_stream_start.start()