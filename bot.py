import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import database as db

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await db.init_db()
    await bot.load_extension("cogs.loans")
    await bot.load_extension("cogs.reminders")
    await bot.tree.sync()
    print(f"✅ Bot ready: {bot.user} ({bot.user.id})")


if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN 環境變數未設定")
    bot.run(token)
