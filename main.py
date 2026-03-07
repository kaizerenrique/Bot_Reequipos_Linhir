import discord
from discord.ext import commands
import logging
from config import DISCORD_TOKEN
from tasks.monitor import Monitor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LinhirBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.load_extension("discord_bot.commands")
        await self.load_extension("discord_bot.master")
        logger.info("Cogs cargados.")

        await self.tree.sync()
        logger.info("Comandos sincronizados.")

    async def on_ready(self):
        logger.info(f"Bot conectado como {self.user} (ID: {self.user.id})")
        logger.info(f"En {len(self.guilds)} servidores.")
        monitor = Monitor(self)
        monitor.check_new_battles.start()
        logger.info("Monitor de batallas iniciado.")


bot = LinhirBot()
bot.run(DISCORD_TOKEN)