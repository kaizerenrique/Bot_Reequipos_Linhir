import asyncio
import discord
from discord_bot.bot import LinhirBot
from tasks.monitor import Monitor
from config import DISCORD_TOKEN

bot = LinhirBot()
monitor = Monitor(bot)

@bot.event
async def on_ready():
    # Iniciar tarea de monitoreo
    monitor.check_new_battles.start()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)