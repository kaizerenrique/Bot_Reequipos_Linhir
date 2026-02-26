# main.py
import discord
from discord.ext import commands
import logging
from config import DISCORD_TOKEN
from tasks.monitor import Monitor

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LinhirBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # Opcional, para comandos con prefijo
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        """Carga los cogs y sincroniza los comandos."""
        await self.load_extension("discord_bot.commands")
        logger.info("Cog de comandos cargado.")

        # Sincronizar comandos de barra globalmente
        await self.tree.sync()
        logger.info("Comandos de barra sincronizados.")

    async def on_ready(self):
        logger.info(f"Bot conectado como {self.user} (ID: {self.user.id})")
        logger.info(f"En {len(self.guilds)} servidores.")

        # Iniciar el monitor de batallas
        monitor = Monitor(self)
        monitor.check_new_battles.start()
        logger.info("Monitor de batallas iniciado.")


bot = LinhirBot()

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)